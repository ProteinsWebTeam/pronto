# -*- coding: utf-8 -*-

from typing import Dict, List, Set

DoS = Dict[str, Set[str]]

"""
Checks to perform
Key: check type
Value: (
    label,
    accepts specific terms, 
    accepts exceptions, 
    accepts global exceptions
)

Rule of thumb: if a check takes specific terms, it should not accept 
    global exceptions (otherwise there is not point in adding 
    a global exceptions, just delete the term to search)
"""
CHECKS = {
    "abbreviation": ("Invalid abbreviation", True, True, False),
    "acc_in_name": ("Accession in name", False, True, False),
    "cab_length": ("Too short", False, False, False),
    "citation": ("Invalid citation", True, True, False),
    "double_quote": ("Double quotes", False, False, False),
    "encoding": ("Invalid character", False, True, True),
    "gene_symbol": ("Gene symbol", False, True, True),
    "forbidden": ("Forbidden term", True, True, False),
    "integration": ("No signatures", False, False, False),
    "link": ("Broken link", False, False, False),
    "lower_case_name": ("Invalid name", False, True, True),
    "punctuation": ("Invalid punctuation", True, True, False),
    "same_name": ("Same names", False, False, False),
    "similar_name": ("Similar names", False, True, False),
    "spelling": ("Misspelling", True, True, False),
    "substitution": ("Bad substitution", True, True, False),
    "type_conflict": ("Type conflict", False, False, False),
    "unchecked_node": ("Unchecked entry", False, False, False),
    "underscore": ("Underscore in name", False, True, False),
}


def load_exceptions(cur, check_type: str, key_col: str, val_col: str) -> DoS:
    cur.execute(
        f"""
        SELECT {key_col}, {val_col}
        FROM INTERPRO.SANITY_EXCEPTION
        WHERE CHECK_TYPE = :1 AND {key_col} IS NOT NULL
        """, (check_type,)
    )
    exceptions = {}
    for key, val in cur:
        try:
            exceptions[key].add(val)
        except KeyError:
            exceptions[key] = {val}

    return exceptions


def load_global_exceptions(cur, check_type: str) -> Set[str]:
    cur.execute(
        """
        SELECT TERM
        FROM INTERPRO.SANITY_EXCEPTION
        WHERE CHECK_TYPE = :1
        """, (check_type,)
    )
    return {term for term, in cur}


def load_terms(cur, check_type: str) -> List[str]:
    cur.execute(
        """
        SELECT TERM
        FROM INTERPRO.SANITY_CHECK
        WHERE CHECK_TYPE = :1
        """, (check_type,)
    )
    return [term for term, in cur]
