#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import argparse
import re
import requests
import sys
import time

from typing import List, Optional

from utilities import (
    logger,
    build_parser,
    check_url,
)


TYPE_DICT = {
    "Binding site": "B",
    "Conserved site": "C",
    "Domain": "D",
    "Family": "F",
    "Homologous superfamily": "H",
    "PTM": "P",
    "Repeat": "R",
}


def main(argv: Optional[List[str]] = None):
    if argv is None:
        parser = build_parser()
        args = parser.parse_args()
    else:
        parser = build_parser(argv)
        args = parser.parse_args()

    check_url(args)

    payload = {
        "username": args.username,
        "password": args.password,
    }

    s = requests.Session()
    r = s.post(
        f"{args.pronto}/login/",
        data=payload,
        timeout=args.timeout,
    )

    if s.cookies.get("session") is None:
        logger.error(
            (
                "Failed to log into pronto.\n"
                "Check the url (%s), username and password are correct\n"
                "Terminating program"
            ),
            f"{args.pronto}/login/"
        )
        sys.exit(1)
    else:
        logger.warning("Logged in as %s", args.username)

    create_entries(s, args)


def is_llm(signature: dict) -> bool:
    keys = ["llm_name", "llm_description", "llm_abstract"]
    return any(signature.get(key) for key in keys)


def write_error(message, args):
    if args.cache:
        with open("failed_signatures.tsv", "a") as fh:
            fh.write(message)
    else:
        sys.stderr.write(message)


def create_entries(
    s: requests.Session,
    args: argparse.Namespace,
) -> None:
    """
    Attempt to create entries for ai generated signatures.

    :param s: requests session which is logged into pronto
    :param args: cli args parser
    """
    submission_url = f"{args.pronto}/api/entry/".replace("//api", "/api")

    for database in args.databases:
        query_url = (
            f"{args.pronto}/api/database/{database}/signatures/?integrated=0&commented=0"
            f"&sort-by=reviewed-proteins&sort-order=desc&page_size={args.batch_size}"
        )
        sigs_query = s.get(query_url)

        if sigs_query.status_code != 200:
            logger.error(
                "Failed to retrieve unintergated ai-generated signatures for %s:\n%s",
                database,
                sigs_query.text,
            )
            continue

        sig_total, sig_count = len(sigs_query.json()['results']), 0
        sig_perc = {
            "25%": round(sig_total * 0.25),
            "50%": round(sig_total * 0.5),
            "75%": round(sig_total * 0.75),
        }
        sig_perc = {f"{i*10}%": round(sig_total * i/20) for i in range(1, 21)}

        for signature in sigs_query.json()['results']:
            perc = (sig_count / sig_total * 100)
            if perc in sig_perc.values():
                logger.info("Parserd %s of signatures", sig_perc[perc])

            sig_acc = signature['accession']
            sig_type = signature['type']['code']
            sig_url = f"{args.pronto}//api/signature/{sig_acc}/"

            sig_response = s.get(sig_url)

            if sig_response.status_code != 200:
                logger.error("Could not retrieve data for signature %s", sig_acc)
                continue

            if is_llm(signature) is False:
                print("F")
                try:
                    signature['llm_name']
                except KeyError:
                    print("not LLM NAME")
                try:
                    signature['llm_description']
                except KeyError:
                    print("not LLM description")
                try:
                    print(signature['llm_abstract'])
                except KeyError:
                    print("Not LLM ABSTRACT")
                continue
            print("TRUE********")

            if sig_response.json()['llm_description'] is not None:
                if len(sig_response.json()['llm_description']) > 30:
                    logger.error(
                        (
                            "Short name '%s' too long. Entry short names cannot be longer than 30 characters.\n"
                        ),
                        sig_response.json()['llm_description']
                    )
                    message = (
                        f"SIGNATURE:{sig_acc}\t{sig_response.json()['llm_name']}\t{sig_response.json()['llm_description']}\t"
                        f"ERROR: Short name too long.\n"
                    )
                    write_error(message, args)

            payload = {
                "type": sig_type,
                "name": sig_response.json()['llm_name'],
                "short_name": sig_response.json()['llm_description'],
                'is_llm': True,
                'is_llm_reviewed': False,
                'is_checked': False,
                'signatures': sig_acc,
            }

            submission_response = s.put(
                submission_url,
                json=payload,
                timeout=args.timeout,
            )

            if submission_response.status_code == 400:
                if submission_response.text.find('"entries":') != -1:
                    entries = [{
                        "accession": re.findall(r'\"accession\":\"\D{3,4}\d+\",', entry)[0][13:-2],
                        "name": re.findall(r'\"name\":\".+?\"', entry)[0][8:-2],
                        "short_name": re.findall(r'\"short_name\":\".+?\"', entry)[0][14:-2],
                    } for entry in re.findall(r'entries\":\[.+\}\]', submission_response.text)[0][9:].split("}") if entry.find("accession") != -1]

                    logger.error(
                        (
                            "Failed to create and insert a new entry for signature '%s'\n"
                            "because the name '%s' and/or short name '%s' is already associated with an entry -- %s\n"
                            "Entries: %s"
                        ),
                        sig_acc,
                        sig_response.json()['llm_name'],
                        sig_response.json()['llm_description'],
                        submission_response.status_code,
                        entries,
                    )
                    for entry in entries:
                        message = (
                            f"SIGNATURE:{sig_acc}\t{sig_response.json()['llm_name']}\t{sig_response.json()['llm_description']}\t"
                            f"ENTRY:{entry['accession']}\t{entry['name']}\t{entry['short_name']}\n"
                        )
                        write_error(message, args)
                else:
                    logger.error(
                        "Error (HTTP code: %s) raised while tying to generate entry for signature %s:\n%s",
                        submission_response.status_code,
                        sig_acc,
                        submission_response.text,
                    )
            elif submission_response.status_code == 500:
                logger.error(
                    (
                        "Failed to create and insert a new entry for signature '%s'\n"
                        "with the name '%s' and/or short name '%s'\nError: %s -- %s"
                    ),
                    sig_acc,
                    sig_response.json()['llm_name'],
                    sig_response.json()['llm_description'],
                    submission_response.text,
                    submission_response.status_code,
                )
            elif submission_response.status_code != 200:
                logger.warning(
                    "Failed to generate entry for %s:\n%s\nResponse code: %s\nURL: %s",
                    sig_acc,
                    submission_response.text,
                    submission_response.status_code,
                    submission_url,
                )

            time.sleep(args.request_pause)


if __name__ == "__main__":
    main()