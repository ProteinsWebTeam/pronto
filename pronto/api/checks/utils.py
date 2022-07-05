# -*- coding: utf-8 -*-

from typing import Dict, List, Set

DoS = Dict[str, Set[str]]

"""
Checks to perform

Name: title of section on the settings page
Description: sub-title of section
Label: description of the error in the errors report 

Types of exceptions:
  - t (term):   the exception is for an entry/annotation 
                associated to a searched term (`terms` must be True)
  - p (pair):   the exception is for a pair entry->entry or entry->signature
  - s (single): the exception is for a single entry 
                (i.e. the entry is allowed to fail the check)
  - g (global): the exception is for a string that could be found in names, 
                annotations, etc.
  - None:       no exception allowed 
"""
CHECKS = {
    "abbreviation": {
        "name": "Abbreviations",
        "description": "Abbreviations forbidden in entry names, short names, "
                       "and annotations",
        "label": "Invalid abbreviation",
        "details": "This term is in the list of forbidden abbreviations",
        "terms": True,
        "exceptions": 't'
    },
    "domain_in_family_name": {
        "name": "Domain in family entry name",
        "description": "Entry names of family cannot contain a domain",
        "label": "Domain in family entry name",
        "terms": False,
        "exceptions": None
    },
    "acc_in_name": {
        "name": "Accessions in names",
        "description": "Entry names cannot contain accessions",
        "label": "Accession in entry name",
        "terms": False,
        "exceptions": 'p'
    },
    "cab_length": {
        "name": "Annotations too short",
        "description": "Entry annotations must have a minimal length",
        "label": "Annotation too short",
        "terms": False,
        "exceptions": None
    },
    "citation": {
        "name": "References",
        "description": "Annotations cannot contain ill-formed references "
                       "or unpublished/personal observations",
        "label": "Invalid reference",
        "terms": True,
        "exceptions": 't'
    },
    "double_quote": {
        "name": "Double quotes",
        "description": "Entry names cannot contain double quotes",
        "label": "Double quotes in name",
        "terms": False,
        "exceptions": None
    },
    "encoding": {
        "name": "Encoding",
        "description": "Special characters should be avoided",
        "label": "Invalid character",
        "terms": False,
        "exceptions": 'g'
    },
    "gene_symbol": {
        "name": "Gene symbols",
        "description": "Entry names may contain protein symbols (NnnY), "
                       "but not gene symbols (nnnY)",
        "label": "Gene symbol in name",
        "details": "Use the protein symbol (NnnY) instead",
        "terms": False,
        "exceptions": 'g'
    },
    "forbidden": {
        "name": "Banned words",
        "description": "Words that must not be part of entry names",
        "label": "Banned word",
        "terms": True,
        "exceptions": 't'
    },
    "integration": {
        "name": "Empty entries",
        "description": "Checked entries must integrate at least "
                       "one member database signature",
        "label": "Entry without signatures",
        "terms": False,
        "exceptions": None
    },
    "link": {
        "name": "Broken links",
        "description": "Dead external links",
        "label": "Broken link",
        "terms": False,
        "exceptions": None
    },
    "lower_case_name": {
        "name": "Uncapitalized names",
        "description": "Entry names must start with a capital",
        "label": "Uncapitalized name",
        "terms": False,
        "exceptions": 'g'
    },
    "matches": {
        "name": "No matches",
        "description": "Checked entries cannot integrate signatures "
                       "without protein matches",
        "label": "Signature without matches",
        "terms": False,
        "exceptions": None
    },
    "punctuation": {
        "name": "Punctuation errors",
        "description": "Common punctuation errors "
                       "(e.g. whitespace before punctuation characters)",
        "label": "Punctuation error",
        "details": "This annotation contains a common punctuation error "
                   "(e.g. a whitespace before a punctuation mark)",
        "terms": True,
        "exceptions": 't'
    },
    "retracted": {
        "name": "Retracted publication",
        "description": "Entries cannot reference retracted publication",
        "label": "Retracted publication",
        "terms": False,
        "exceptions": None
    },
    "same_name": {
        "name": "Same names",
        "description": "Clash between name and short name "
                       "in different entries",
        "label": "Same names",
        "terms": False,
        "exceptions": None
    },
    "similar_name": {
        "name": "Similar names",
        "description": "Name and short names differing only "
                       "by non-alphanumeric characters",
        "label": "Similar names",
        "terms": False,
        "exceptions": 'p'
    },
    "spelling": {
        "name": "Misspellings",
        "description": "Common spelling and grammatical errors",
        "label": "Misspelling",
        "details": "This word is in the list "
                   "of common spelling/grammatical errors",
        "terms": True,
        "exceptions": 't'
    },
    "substitution": {
        "name": "Bad substitutions",
        "description": "Substitutions caused by invalid characters",
        "label": "Bad substitution",
        "terms": True,
        "exceptions": 't'
    },
    "type_conflict": {
        "name": "Types conflicts",
        "description": "Homologous superfamilies containing non-CATH-Gene3D "
                       "or SUPERFAMILY signatures",
        "label": "Types conflict",
        "terms": False,
        "exceptions": None
    },
    "unchecked_parent": {
        "name": "Unchecked parent entries",
        "description": "Unchecked entries with at least one checked child",
        "label": "Unchecked parent",
        "terms": False,
        "exceptions": None
    },
    "unchecked_child": {
        "name": "Unchecked child entries",
        "description": "Unchecked entries whose parents are checked",
        "label": "Unchecked child",
        "terms": False,
        "exceptions": None
    },
    "child_type_conflict": {
        "name": "Child type conflict",
        "description": "Parent and child entry have a different type",
        "label": "Child type conflict",
        "terms": False,
        "exceptions": None
    },
    "unauthorised_child": {
        "name": "Unauthorised child",
        "description": "Entries of type R, C, A, B, P, H cannot have children",
        "label": "Unauthorised child",
        "terms": False,
        "exceptions": None
    },
    "underscore": {
        "name": "Underscores in names",
        "description": "Names cannot contain underscores and, in short names,"
                       " 'binding', 'bd', 'related', 'rel', and 'like' should "
                       "be hyphenated (preceded by an hyphen rather than "
                       "an underscore, e.g. DNA-bd)",
        "label": "Underscore in name",
        "terms": False,
        "exceptions": 's'
    },
    "generic_go": {
        "name": "Forbidden GO term",
        "description": "GO term used is too generic or is a root GO term",
        "label": "Forbidden GO term",
        "terms": False,
        "exceptions": None
    },
    "secondary_go": {
        "name": "Replaced GO term",
        "description": "GO term has been replaced",
        "label": "Replaced GO term",
        "terms": False,
        "exceptions": None
    },
    "obsolete_go": {
        "name": "Obsolete GO term",
        "description": "GO term used is obsolete",
        "label": "Obsolete GO term",
        "terms": False,
        "exceptions": None
    },
    "interpro2go": {
        "name": "GO term in empty entry",
        "description": "GO term used in an entry without signature",
        "label": "GO term in empty entry",
        "terms": False,
        "exceptions": None
    },
    "deleted_entry": {
        "name": "Deleted entry",
        "description": "The entry doesn't exist",
        "label": "Deleted entry",
        "terms": False,
        "exceptions": None
    },
    "sign_not_found": {
        "name": "Signature not found",
        "description": "The signature doesn't exist in the InterPro database",
        "label": "Signature not found",
        "terms": False,
        "exceptions": None
    },
    "empty_annotation": {
        "name": "No annotation block",
        "description": "The entry doesn't have an annotation block",
        "label": "No annotation block",
        "terms": False,
        "exceptions": None
    },
    "child_matches": {
        "name": "Parent/child overlap",
        "description": "Low number of overlap found with child entry",
        "label": "Poor parent/child overlap",
        "terms": False,
        "exceptions": 'p'
    },
    "skip_no_matches": {
        "name": "No matches found",
        "description": "No matches found where skip flag = N",
        "label": "No matches found",
        "terms": False,
        "exceptions": None
    },
    "fragment_matches": {
        "name": "Fragment matches",
        "description": "Only fragment matches found for signature",
        "label": "Fragment matches",
        "terms": False,
        "exceptions": None
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
