# -*- coding: utf-8 -*-

from typing import Dict, List, Set

DoS = Dict[str, Set[str]]

"""
Checks to perform

Types of exceptions:
  - t (term):   the exception is for an entry/annotation 
                associated to a searched term (`terms` must be True)
  - p (pair):   the exception is for a pair entry->entry or entry->signature
  - s (single): the exception is for a single entry 
                (i.e. the entry is allowed to fail the check)
  - g (global): the exception is for a string that could be found in names, 
                annotations, etc.
  - empty:      no exception allowed 
"""
CHECKS = {
    "abbreviation": {
        "name": "Abbreviations",
        "label": "Invalid abbreviation",
        "description": "Some abbreviations are forbidden in entry names, "
                       "short names, and annotations.",
        "terms": True,
        "exceptions": 't'
    },
    "acc_in_name": {
        "name": "Accessions in names",
        "label": "Entry names should not contain accessions.",
        "description": "InterPro accessions",
        "terms": False,
        "exceptions": 'p'
    },
    "cab_length": {
        "name": "Annotations too short",
        "label": "Annotation too short",
        "description": "Entry annotations must have a minimal length.",
        "terms": False,
        "exceptions": ''
    },
    "citation": {
        "name": "Citations",
        "label": "Invalid citation",
        "description": "",
        "terms": True,
        "exceptions": 't'
    },
    "double_quote": {
        "name": "Double quotes",
        "label": "Double quotes in name",
        "description": "",
        "terms": False,
        "exceptions": ''
    },
    "encoding": {
        "name": "Encoding",
        "label": "Invalid character",
        "description": "",
        "terms": False,
        "exceptions": 'g'
    },
    "gene_symbol": {
        "name": "Gene symbols",
        "label": "Gene symbol in name",
        "description": "",
        "terms": False,
        "exceptions": 'g'
    },
    "forbidden": {
        "name": "Banned words",
        "label": "Banned word",
        "description": "",
        "terms": True,
        "exceptions": 'p'
    },
    "integration": {
        "name": "Empty entries",
        "label": "Empty entry",
        "description": "",
        "terms": False,
        "exceptions": ''
    },
    "link": {
        "name": "Broken links",
        "label": "Broken link",
        "description": "",
        "terms": False,
        "exceptions": ''
    },
    "lower_case_name": {
        "name": "Invalid names",
        "label": "Invalid name",
        "description": "",
        "terms": False,
        "exceptions": 'g'
    },
    "punctuation": {
        "name": "Punctuation errors",
        "label": "Punctuation error",
        "description": "",
        "terms": True,
        "exceptions": 't'
    },
    "same_name": {
        "name": "Same names",
        "label": "Same names",
        "description": "",
        "terms": False,
        "exceptions": ''
    },
    "similar_name": {
        "name": "Similar names",
        "label": "Similar names",
        "description": "",
        "terms": False,
        "exceptions": 'p'
    },
    "spelling": {
        "name": "Misspellings",
        "label": "Misspelling",
        "description": "",
        "terms": True,
        "exceptions": 't'
    },
    "substitution": {
        "name": "Bad substitutions",
        "label": "Bad substitution",
        "description": "",
        "terms": True,
        "exceptions": 't'
    },
    "type_conflict": {
        "name": "Types conflicts",
        "label": "Types conflict",
        "description": "",
        "terms": False,
        "exceptions": ''
    },
    "unchecked_node": {
        "name": "Unchecked entries",
        "label": "Unchecked entry",
        "description": "",
        "terms": False,
        "exceptions": ''
    },
    "underscore": {
        "name": "Underscores in names",
        "label": "Underscore in name",
        "description": "",
        "terms": False,
        "exceptions": 's'
    },
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
