#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import argparse
import logging
import sys

from typing import List, Optional


logger = logging.getLogger(__name__)


DATABASES = ["panther", "ncbifam", "cathgene3d"]


def clean_url(url):
    return url.rstrip("/")


def build_parser(argv: Optional[List] = None):
    parser = argparse.ArgumentParser(
        prog="Import AI generated data",
        description="Automatically integrated AI-generated signatures into the IPPRO database",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "username",
        type=str,
        help="Oracle db username - used to login into pronto"
    )

    parser.add_argument(
        "password",
        type=str,
        help="Oracle db password - used to login into pronto"
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
        action="store_false",
        default=False,
        help="Write out signatures with non-unique name/short name to a TSV file",
    )

    parser.add_argument(
        "--databases",
        action="store",
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
