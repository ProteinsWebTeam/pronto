# -*- coding: utf-8 -*-

import re
from typing import Dict, List, Optional, Set, Tuple

from cx_Oracle import Cursor

from .utils import load_exceptions, load_global_exceptions, load_terms


DoS = Dict[str, Set[str]]
LoS = List[str]
Err = List[Tuple[str, Optional[str]]]
LoT = List[Tuple[str, str, str]]


def ck_abbreviations(entries: LoT, terms: LoS, exceptions: DoS) -> Err:
    prog1 = re.compile(r"\d+\s+kDa")
    prog2 = re.compile(r"\b[cn][\-\s]termin(?:al|us)", flags=re.I)
    prog2_except = {"N-terminal", "C-terminal",
                    "C terminus", "N terminus"}

    prog3 = re.compile('|'.join(terms)) if terms else None
    prog3_excep = exceptions

    errors = []
    for acc, name, short_name in entries:
        for match in prog1.findall(name) + prog1.findall(short_name):
            errors.append((acc, match))

        for match in prog2.findall(name) + prog2.findall(short_name):
            if match not in prog2_except:
                errors.append((acc, match))

        if prog3:
            for match in prog3.findall(name) + prog3.findall(short_name):
                if acc not in prog3_excep or match not in prog3_excep[acc]:
                    errors.append((acc, match))

    return errors


def ck_acc_in_name(entries: LoT, exceptions: DoS) -> Err:
    terms = [
        r"G3DSA:[\d.]{4,}",
        r"IPR\d{4,}",
        r"MF_\d{4,}",
        r"PF\d{4,}",
        r"PIRSF\d{4,}",
        r"PR\d{4,}",
        r"PS\d{4,}",
        r"PTHR\d{4,}",
        r"SFLD[FGS]\d{4,}",
        r"SM\d{4,}",
        r"SSF\d{4,}",
        r"TIGR\d{4,}",
        r"cd\d{4,}",
        r"sd\d{4,}"
    ]
    prog = re.compile(fr"\b(?:{'|'.join(terms)})\b")

    errors = []
    for acc, name, short_name in entries:
        entry_exceptions = exceptions.get(acc, set())
        for match in prog.findall(name):
            if match not in entry_exceptions:
                errors.append((acc, match))

    return errors


def ck_double_quote(entries: LoT) -> Err:
    return [(acc, None) for acc, name, short_name in entries if '"' in name]


def ck_gene_symbol(entries: LoT, exceptions: Set[str]) -> Err:
    prog1 = re.compile(r"\b[a-z]{3}[A-Z]\b")
    prog2 = re.compile(r"(?:^|_)([a-z]{3}[A-Z])\b")

    errors = []
    for acc, name, short_name in entries:
        match = prog1.search(name)
        if match and match.group() not in exceptions:
            errors.append((acc, match.group()))

        match = prog2.search(short_name)
        if match and match.group(1) not in exceptions:
            errors.append((acc, match.group(1)))

    return errors


def ck_forbidden_terms(entries: LoT, terms: LoS, exceptions: DoS) -> Err:
    errors = []
    for acc, name, short_name in entries:
        entry_exceptions = exceptions.get(acc, set())
        for term in terms:
            if term in name and term not in entry_exceptions:
                errors.append((acc, term))

    return errors


def ck_integration(cur: Cursor) -> Err:
    cur.execute(
        """
        SELECT E.ENTRY_AC
        FROM INTERPRO.ENTRY E
        INNER JOIN (
            SELECT ENTRY_AC, COUNT(*) AS CNT
            FROM INTERPRO.ENTRY2METHOD
            GROUP BY ENTRY_AC
        ) EM ON E.ENTRY_AC = EM.ENTRY_AC
        WHERE E.CHECKED = 'Y' AND EM.CNT = 0
        ORDER BY E.ENTRY_AC
        """
    )
    return [(acc, None) for acc, in cur]


def ck_letter_case(entries: LoT, exceptions: Tuple[str]) -> Err:
    prog = re.compile("[a-z]")
    errors = []
    for acc, name, short_name in entries:
        if prog.match(name) and not name.startswith(exceptions):
            errors.append((acc, name.split(' ')[0]))

        if prog.match(short_name) and not short_name.startswith(exceptions):
            errors.append((acc, short_name.split('_')[0]))

    return errors


def ck_same_names(cur: Cursor) -> Err:
    cur.execute(
        """
        SELECT A.ENTRY_AC, B.ENTRY_AC
        FROM INTERPRO.ENTRY A
        INNER JOIN INTERPRO.ENTRY B
          ON (
            A.ENTRY_AC != B.ENTRY_AC
            AND (LOWER(A.NAME) = LOWER(B.SHORT_NAME))
          )
        """
    )
    return cur.fetchall()


def ck_similar_names(cur: Cursor, exceptions: DoS) -> Err:
    cur.execute(
        """
        SELECT A.ENTRY_AC, B.ENTRY_AC
        FROM INTERPRO.ENTRY A
        INNER JOIN INTERPRO.ENTRY B
          ON (
            A.ENTRY_AC < B.ENTRY_AC
            AND (
              REGEXP_REPLACE(A.NAME, '[^a-zA-Z0-9]+', '') = 
                REGEXP_REPLACE(B.NAME, '[^a-zA-Z0-9]+', '')
              OR REGEXP_REPLACE(A.SHORT_NAME, '[^a-zA-Z0-9]+', '') = 
                REGEXP_REPLACE(B.SHORT_NAME, '[^a-zA-Z0-9]+', '')
            )
          )
        """
    )
    errors = []
    for acc1, acc2 in cur:
        if acc1 not in exceptions or acc2 not in exceptions[acc1]:
            errors.append((acc1, acc2))

    return errors


def ck_spelling(entries: LoT, terms: LoS, exceptions: DoS) -> Err:
    prog = re.compile(fr"\b(?:{'|'.join(terms)})\b", flags=re.I)

    errors = []
    for acc, name, short_name in entries:
        entry_exceptions = exceptions.get(acc, set())
        for match in prog.findall(name) + prog.findall(short_name):
            if match not in entry_exceptions:
                errors.append((acc, match))

    return errors


def ck_type_conflicts(cur: Cursor) -> Err:
    """Find homologous superfamily entries containing a signature that is not
    from CATH-Gene3D or SUPERFAMILY

    :param cur: Cursor object
    :return: a list of tuples (entry accession, signature accession)
    """
    cur.execute(
        """
        SELECT E.ENTRY_AC, M.METHOD_AC
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2METHOD EM 
          ON (E.ENTRY_AC = EM.ENTRY_AC AND E.ENTRY_TYPE = 'H')
        INNER JOIN INTERPRO.METHOD M 
          ON (EM.METHOD_AC = M.METHOD_AC AND M.DBCODE NOT IN ('X', 'Y'))
        """
    )
    return cur.fetchall()


def ck_unchecked_nodes(cur: Cursor) -> Err:
    """Find unchecked entries whose parent/children are checked

    :param cur: Cursor object
    :return: a list of accessions
    """
    cur.execute(
        """
        SELECT E.ENTRY_AC
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2ENTRY EE ON E.ENTRY_AC = EE.ENTRY_AC
        INNER JOIN INTERPRO.ENTRY P ON EE.PARENT_AC = P.ENTRY_AC
        WHERE E.CHECKED = 'N' AND P.CHECKED = 'Y'
        UNION 
        SELECT E.ENTRY_AC
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2ENTRY EE ON E.ENTRY_AC = EE.PARENT_AC
        INNER JOIN INTERPRO.ENTRY C ON EE.ENTRY_AC = C.ENTRY_AC
        WHERE E.CHECKED = 'N' AND C.CHECKED = 'Y'
        """
    )
    return [(acc, None) for acc, in cur]


def ck_underscore(entries: LoT, exceptions: Set[str]) -> Err:
    prog1 = re.compile(r"\w*_\w*")
    prog2 = re.compile(r"_(?:binding|bd|related|rel|like)")

    errors = []
    for acc, name, short_name in entries:
        for match in prog1.findall(name):
            if acc not in exceptions:
                errors.append((acc, match))

        for match in prog2.findall(short_name):
            if acc not in exceptions:
                errors.append((acc, match))

    return errors


def check(cur: Cursor):
    cur.execute("SELECT ENTRY_AC, NAME, SHORT_NAME FROM INTERPRO.ENTRY")
    entries = cur.fetchall()

    terms = load_terms(cur, "abbreviation")
    exceptions = load_exceptions(cur, "abbreviation", "ENTRY_AC", "TERM")
    for item in ck_abbreviations(entries, terms, exceptions):
        yield "abbreviation", item

    exceptions = load_exceptions(cur, "acc_in_name", "ENTRY_AC", "TERM")
    for item in ck_acc_in_name(entries, exceptions):
        yield "acc_in_name", item

    for item in ck_double_quote(entries):
        yield "double_quote", item

    exceptions = load_global_exceptions(cur, "gene_symbol")
    for item in ck_gene_symbol(entries, exceptions):
        yield "gene_symbol", item

    terms = load_terms(cur, "forbidden")
    exceptions = load_exceptions(cur, "forbidden", "ENTRY_AC", "TERM")
    for item in ck_forbidden_terms(entries, terms, exceptions):
        yield "forbidden", item

    exceptions = load_global_exceptions(cur, "lower_case_name")
    for item in ck_letter_case(entries, tuple(exceptions)):
        yield "lower_case_name", item

    for item in ck_integration(cur):
        yield "integration", item

    for item in ck_same_names(cur):
        yield "same_name", item

    exceptions = load_exceptions(cur, "similar_name", "ENTRY_AC", "ENTRY_AC2")
    for item in ck_similar_names(cur, exceptions):
        yield "similar_name", item

    terms = load_terms(cur, "spelling")
    exceptions = load_exceptions(cur, "spelling", "ENTRY_AC", "TERM")
    for item in ck_spelling(entries, terms, exceptions):
        yield "spelling", item

    for item in ck_type_conflicts(cur):
        yield "type_conflict", item

    for item in ck_unchecked_nodes(cur):
        yield "unchecked_node", item

    exceptions = load_exceptions(cur, "underscore", "ENTRY_AC", "TERM")
    for item in ck_underscore(entries, set(exceptions)):
        yield "underscore", item
