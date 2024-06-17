#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import argparse
import logging
import os
import sys
import tomllib
from datetime import datetime
import openai
import json

from typing import List, Optional


logger = logging.getLogger(__name__)

DATABASES = ["panther", "ncbifam", "cathgene3d"]
AUTO_TYPE = ["cdd", "duf", "ai"]

def clean_url(url):
    return url.rstrip("/")


def build_parser(argv: Optional[List] = None):
    parser = argparse.ArgumentParser(
        prog="Import AI generated data",
        description="Automatically integrated AI-generated signatures into the IPPRO database",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-b",
        "--batch_size",
        type=int,
        default=50000000,
        help="Number of signatures to parse at a time.",
    )

    parser.add_argument(
        "--file",
        action="store_true",
        default=False,
        help="Write out signatures with non-unique name/short name to a TSV file",
    )

    parser.add_argument(
        "--pronto",
        type=clean_url,
        default="http://pronto.ebi.ac.uk:5000",
        help="URL of pronto - used to connect to the pronto API."
    )
    # test deployment - http://pronto-tst.ebi.ac.uk:5000

    parser.add_argument(
        "--request_pause",
        type=float,
        default=0.01,
        help="Seconds to wait between payloards to the Pronto REST API",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Seconds timeout limit for connection to pronto",
    )

    parser.add_argument(
        "--databases",
        type=str.lower,
        nargs="+",
        choices=DATABASES,
        default=None,
        help="Member databases to integrate ai generated signatures from. Default: None",
    )

    parser.add_argument(
        "auto_integrate",
        type=str.lower,
        choices=AUTO_TYPE,
        help="Type of auto-integration",
    )

    parser.add_argument(
        "--cdd_template",
        type=str,
        default=None,
        help="Template file to generate alternative CDD name if CDD description is too long for entry name",
    )

    if argv is None:
        return parser
    else:
        return parser.parse_args(argv)


def check_url(args: argparse.Namespace) -> None:
    """Check user does(n't) want to connect to the live Pronto server

    :param args: cli args parser
    """
    if args.pronto.startswith("http://pronto.ebi.ac.uk:5000"):
        response = input("About to connect to the live pronto server. Do you want to proceed? [y/N]")
        if response.lower() not in ['y', 'yes']:
            logger.warning("Opt to not continue. Terminating program.")
            sys.exit(1)


def check_login_details() -> tuple[str, str]:
    """Check if the environment variables for the users pronto credentials
    username and password are available"""
    username, password = None, None
    if os.getenv("PRONTO_USER"):
        username = os.getenv("PRONTO_USER")
    if os.getenv("PRONTO_PWD"):
        password = os.getenv("PRONTO_PWD")

    if not username or not password:
        logger.error(
            "Username and/or password not in environmental variables\n"
            "Please set 'PRONTO_USER' and 'PRONTO_PWD' to your pronto condentials.\n"
            "Terminating program"
        )
        sys.exit(1)

    return username, password


def generate_names(template, payload):
    prompt = make_prompt(payload)
    system, user = make_user(prompt, template)
    content, to_dump, request = make_summary(payload, system, user, prompt, 0.2)
    long_name = content["names"][0]
    return long_name


def make_prompt(info: dict, merge: bool = False) -> str:
    cdd_info = info
    ctx = f"```json\n{json.dumps(cdd_info)}\n```"
    # print(ctx)
    return ctx


def make_summary(
        info, system, user_message, prompt, temp: float
) -> tuple[dict, dict, bool]:
    to_dump = {}
    content = {}

    client = openai.OpenAI()
    model = "gpt-4o"

    accession = info["accession"]
    print(
        f"{datetime.now():%Y-%m-%d %H:%M:%S}: {accession}", file=sys.stderr, flush=True
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]

    while True:
        try:
            completion = client.chat.completions.create(
                messages=messages,
                model=model,
                response_format={"type": "json_object"},
                temperature=temp,
            )
        except openai.NotFoundError:
            raise
        except openai.BadRequestError:
            requested = True
            break
        except openai.OpenAIError:
            raise
        else:
            response = completion.model_dump(exclude_unset=True)
            requested = True

            content = load_content(response)
            if content:
                to_dump = {
                    "accession": info["accession"],
                    "model": model,
                    "temperature": temp,
                    "prompt": prompt,
                    "response": response,
                }

            break

    return content, to_dump, requested


def make_user(prompt, templatefile):
    with open(templatefile, "rb") as fh:
        template = tomllib.load(fh)
        before = template["before"].strip()
        after = template["after"].strip()
        system = template["system"].strip()
    #
    user = prompt

    if before:
        user = f"{before}\n{user}"

    if after:
        user = f"{user}\n{after}"

    return user, system


def load_content(response: dict) -> dict | None:
    choice = response["choices"][0]
    if choice["finish_reason"] == "stop":
        return json.loads(choice["message"]["content"])
    else:
        return None
