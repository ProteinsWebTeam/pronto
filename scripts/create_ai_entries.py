#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import argparse
import requests
import sys
import time

from typing import List, Optional

from utilities import (
    logger,
    build_parser,
    check_login_details,
    check_url,
)


def main(argv: Optional[List[str]] = None):
    if argv is None:
        parser = build_parser()
        args = parser.parse_args()
    else:
        parser = build_parser(argv)
        args = parser.parse_args()

    check_url(args)

    username, password = check_login_details()

    payload = {
        "username": username,
        "password": password,
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
            f"{args.pronto}/login/",
        )
        sys.exit(1)
    else:
        logger.warning("Logged in as %s", username)

    if args.auto_integrate == "ai" and not args.databases:
        logger.error(
            f"To create ai entries, please provide a suitable database: panther, ncbifam or cathgene3d"
        )

    create_entries(s, args)


def make_query(args) -> str:
    database = args.databases[0] if args.auto_integrate == "ai" else ""
    search = "&search=DUF" if args.auto_integrate == "duf" else ""
    pastintegrated = "&pastintegrated=0"
    check = (
        "&checked=0"
        if args.auto_integrate == "duf" or args.auto_integrate == "cdd"
        else ""
    )

    if args.auto_integrate == "duf":
        database = "pfam"
    if args.auto_integrate == "cdd":
        database = "cdd"

    search_url = (
        f"{args.pronto}/api/database/{database}/signatures/?integrated=0&commented=0{search}{check}{pastintegrated}"
        f"&sort-by=reviewed-proteins&sort-order=desc&page_size={args.batch_size}"
    )
    return search_url


def get_cdd_list(accession: str, host: str, s: requests.Session) -> tuple[None | str, None | str, None | str,]:
    signature = s.get(f"{host}/api/signature/{accession}/")
    candidate = None
    if signature.status_code != 200:
        logger.error(
            "Could not retrieve data for signature %s", accession
        )
        return candidate, None, None

    proteins = signature.json()["proteins"]
    description = signature.json()["description"]
    abstract = signature.json()["abstract"]
    short_name = signature.json()["name"]

    if proteins["complete"] > 0:
        prediction = s.get(f"{host}/api/signature/{accession}/predictions/")
        if not prediction.json():
            candidate = short_name

    return candidate, description, abstract


def is_human_complete(sig_response: dict) -> bool:
    """Check if human curated data is complete"""
    keys = ["name", "description", "abstract"]
    return all(sig_response.get(key) for key in keys)


def is_llm(sig_response: dict) -> bool:
    """Check if record is ai-generated:
    It should have at least one ai-generated element
    """
    keys = ["llm_name", "llm_description", "llm_abstract"]
    return all(sig_response.get(key) for key in keys)


def is_llm_incomplete(sig_response: dict) -> bool:
    """Check for potential data or REST API error.
    AI-generated data should be complete"""
    keys = ["llm_name", "llm_description", "llm_abstract"]
    return (
        False
        if all(sig_response.get(key) for key in keys)
        or all(not sig_response.get(key) for key in keys)
        else True
    )


def write_error(message, args):
    if args.file:
        with open("failed_signatures.tsv", "a") as fh:
            fh.write(message)
    else:
        sys.stderr.write(message)


def create_entries(
    s: requests.Session,
    args: argparse.Namespace,
) -> None:

    submission_url = f"{args.pronto}/api/entry/"

    sigs_query = s.get(make_query(args))

    if sigs_query.status_code != 200:
        if args.auto_integrate == "ai":
            database = args.databases[0]
        else:
            database = args.auto_integrate

        logger.error(
            "Failed to retrieve unintegrated signatures for %s:\n%s",
            database,
            sigs_query.text,
        )

    sig_total, sig_count = len(sigs_query.json()["results"]), 0
    sig_perc = {round(sig_total * i / 10): f"{i * 10}%" for i in range(1, 11)}

    payload = None
    for signature in sigs_query.json()["results"]:
        sig_count += 1
        perc = sig_count / sig_total * 100
        try:
            logger.info("Parsed %s of signatures", sig_perc[perc])
        except KeyError:
            pass

        sig_acc = signature["accession"]
        sig_type = signature["type"]["code"]
        sig_url = f"{args.pronto}/api/signature/{sig_acc}/"

        if args.auto_integrate == "cdd":
            candidate, description, abstract = get_cdd_list(sig_acc, args.pronto, s)
            if candidate:
                if (
                    description
                    and len(description) < 100
                    and len(candidate) < 30
                ):
                    long_name = description
                    short_name = candidate

                else:
                    continue
                if abstract:
                    payload = {
                        "type": sig_type,
                        "name": long_name,
                        "short_name": short_name,
                        "is_checked": False,
                        "is_llm": False,
                        "is_llm_reviewed": False,
                        "signatures": [sig_acc],
                        "import_description": True,
                    }
                    print(payload)
                else:
                    continue

        if args.auto_integrate == "duf":
            sig_response = s.get(sig_url)

            if sig_response.status_code != 200:
                logger.error("Could not retrieve data for signature %s", sig_acc)
                continue

            long_name = (
                f"Domain of unknown function ({sig_response.json()['name']})"
            )

            if sig_response.json()["abstract"]:
                payload = {
                    "type": sig_type,
                    "name": long_name,
                    "short_name": sig_response.json()["name"],
                    "is_checked": False,
                    "is_llm": False,
                    "is_llm_reviewed": False,
                    "signatures": [sig_acc],
                    "import_description": True,
                }

            else:
                continue

        if args.auto_integrate == "ai":
            sig_response = s.get(sig_url)

            if sig_response.status_code != 200:
                logger.error("Could not retrieve data for signature %s", sig_acc)
                continue

            if is_human_complete(sig_response.json()):
                # human curatored data is complete
                # leave to curator to choose between human- and ai-generated data
                continue

            if is_llm(sig_response.json()) is False:
                continue

            if is_llm_incomplete(sig_response.json()):
                logger.error(
                    (
                        "AI data (name/short-name/desc) for signature '%s' is incomplete\n"
                        "AI generated data is incomplete. This may reflect an error in the data generation process\n"
                        "the the pronto RESTAPI.\n"
                        "Not creating an entry for this signature"
                    ),
                    sig_acc,
                )
                message = (
                    f"SIGNATURE:{sig_acc}\t{sig_response.json()['llm_name']}\t{sig_response.json()['llm_description']}\t"
                    f"ERROR: AI-generated data is incomplete.\n"
                )
                write_error(message, args)
                continue

            if sig_response.json()["llm_name"] is not None:
                if len(sig_response.json()["llm_name"]) > 30:
                    logger.error(
                        "Short name '%s' too long. Entry short names cannot be longer than 30 characters.\n",
                        sig_response.json()["llm_description"],
                    )
                    message = (
                        f"SIGNATURE:{sig_acc}\t{sig_response.json()['llm_name']}\t{sig_response.json()['llm_description']}\t"
                        f"ERROR: Short name too long.\n"
                    )
                    write_error(message, args)

            payload = {
                "type": sig_type,
                "name": sig_response.json()["llm_description"],
                "short_name": sig_response.json()["llm_name"],
                "is_llm": True,
                "is_llm_reviewed": False,
                "is_checked": True,
                "signatures": [sig_acc],
            }

        if payload:
            submission_response = s.put(
                submission_url,
                json=payload,
                timeout=args.timeout,
            )

            if submission_response.status_code == 400:
                try:
                    entries = []
                    for entry in submission_response.json()["error"]["entries"]:
                        entries.append(
                            {
                                "accession": entry["accession"],
                                "name": entry["name"],
                                "short_name": entry["short_name"],
                            }
                        )

                    logger.error(
                        (
                            "Failed to create and insert a new entry for signature '%s'\n"
                            "because the name '%s' and/or short name '%s' is already associated with an entry -- %s\n"
                            "Entries: %s"
                        ),
                        sig_acc,
                        payload["short_name"],
                        payload["name"],
                        submission_response.status_code,
                        entries,
                    )
                    for entry in entries:
                        message = (
                            f"SIGNATURE:{sig_acc}\t{payload['short_name']}\t{payload['name']}\t"
                            f"ENTRY:{entry['accession']}\t{entry['name']}\t{entry['short_name']}\n"
                        )
                        write_error(message, args)

                except KeyError:
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
                    payload["short_name"],
                    payload["name"],
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
