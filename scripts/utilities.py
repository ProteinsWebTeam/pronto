#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import argparse
import logging
import os
import sys

from typing import List, Optional


logger = logging.getLogger(__name__)


DATABASES = ["panther", "ncbifam", "cathgene3d"]


class ValidateDatabases(argparse.Action):
    """Check the user has provided valid databases."""
    def __call__(self, parser, args, values, option_string=None):
        invalid = False
        for value in values:
            if value.lower() not in DATABASES:
                invalid = True
                raise ValueError(f'Invalid database "{value}" provided. Accepted databases: {DATABASES}')
        if invalid:
            sys.exit(1)
        setattr(args, self.dest, [value.lower() for value in values])


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
        "-c",
        "--cache",
        action="store_true",
        default=False,
        help="Write out signatures with non-unique name/short name to a TSV file",
    )

    parser.add_argument(
        "--databases",
        action=ValidateDatabases,
        nargs="+",
        choices=DATABASES,
        default=DATABASES,
        help="Member databases to integrate ai generated signatures from. Default: ALL"
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
        type=int,
        default=1,
        help="Seconds to wait between payloards to the Pronto REST API",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Seconds timeout limit for connection to pronto",
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
    if os.getenv('PRONTO_USER'):
        username = os.getenv('PRONTO_USER')
    if os.getenv('PRONTO_PWD'):
        password = os.getenv('PRONTO_PWD')

    if not username or not password:
        logger.error(
            "Username and/or password not in environmental variables\n"
            "Please set 'PRONTO_USER' and 'PRONTO_PWD' to your pronto condentials.\n"
            "Terminating program"
        )
        sys.exit(1)

    return username, password
