# -*- coding: utf-8 -*-

from typing import Dict, List, Set

DoS = Dict[str, Set[str]]

"""
Checks to perform

Rule of thumb: if a check takes specific terms, it should not accept 
    global exceptions (otherwise there is not point in adding 
    a global exceptions, just delete the term to search)
"""
CHECKS = {
    "abbreviation": {
        "name": "Abbreviations",
        "label": "Invalid abbreviation",
        "description": "Some abbreviations are forbidden in entry names, "
                       "short names, and annotations.",
        "use_terms": True,
        "use_exceptions": True,
        "use_global_exceptions": False
    },
    "acc_in_name": {
        "name": "Accessions in names",
        "label": "Entry names should not contain accessions.",
        "description": "InterPro accessions",
        "use_terms": False,
        "use_exceptions": True,
        "use_global_exceptions": False
    },
    "cab_length": {
        "name": "Annotations too short",
        "label": "Annotation too short",
        "description": "Entry annotations must have a minimal length.",
        "use_terms": False,
        "use_exceptions": False,
        "use_global_exceptions": False
    },
    "citation": {
        "name": "Citations",
        "label": "Invalid citation",
        "description": "",
        "use_terms": True,
        "use_exceptions": True,
        "use_global_exceptions": False
    },
    "double_quote": {
        "name": "Double quotes",
        "label": "Double quotes in name",
        "description": "",
        "use_terms": False,
        "use_exceptions": False,
        "use_global_exceptions": False
    },
    "encoding": {
        "name": "Encoding",
        "label": "Invalid character",
        "description": "",
        "use_terms": False,
        "use_exceptions": True,
        "use_global_exceptions": True
    },
    "gene_symbol": {
        "name": "Gene symbols",
        "label": "Gene symbol in name",
        "description": "",
        "use_terms": False,
        "use_exceptions": True,
        "use_global_exceptions": True
    },
    "forbidden": {
        "name": "Banned words",
        "label": "Banned word",
        "description": "",
        "use_terms": True,
        "use_exceptions": True,
        "use_global_exceptions": False
    },
    "integration": {
        "name": "Empty entries",
        "label": "Empty entry",
        "description": "",
        "use_terms": False,
        "use_exceptions": False,
        "use_global_exceptions": False
    },
    "link": {
        "name": "Broken links",
        "label": "Broken link",
        "description": "",
        "use_terms": False,
        "use_exceptions": False,
        "use_global_exceptions": False
    },
    "lower_case_name": {
        "name": "Invalid names",
        "label": "Invalid name",
        "description": "",
        "use_terms": True,
        "use_exceptions": True,
        "use_global_exceptions": True
    },
    "punctuation": {
        "name": "Punctuation errors",
        "label": "Punctuation error",
        "description": "",
        "use_terms": True,
        "use_exceptions": True,
        "use_global_exceptions": False
    },
    "same_name": {
        "name": "Same names",
        "label": "Same names",
        "description": "",
        "use_terms": False,
        "use_exceptions": False,
        "use_global_exceptions": False
    },
    "similar_name": {
        "name": "Similar names",
        "label": "Similar names",
        "description": "",
        "use_terms": False,
        "use_exceptions": True,
        "use_global_exceptions": False
    },
    "spelling": {
        "name": "Misspellings",
        "label": "Misspelling",
        "description": "",
        "use_terms": True,
        "use_exceptions": True,
        "use_global_exceptions": False
    },
    "substitution": {
        "name": "Bad substitutions",
        "label": "Bad substitution",
        "description": "",
        "use_terms": True,
        "use_exceptions": True,
        "use_global_exceptions": False
    },
    "type_conflict": {
        "name": "Types conflicts",
        "label": "Types conflict",
        "description": "",
        "use_terms": False,
        "use_exceptions": False,
        "use_global_exceptions": False
    },
    "unchecked_node": {
        "name": "Unchecked entries",
        "label": "Unchecked entry",
        "description": "",
        "use_terms": False,
        "use_exceptions": False,
        "use_global_exceptions": False
    },
    "underscore": {
        "name": "Underscores in names",
        "label": "Underscore in name",
        "description": "",
        "use_terms": False,
        "use_exceptions": True,
        "use_global_exceptions": False
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
