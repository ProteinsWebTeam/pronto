import re
import time
from urllib.error import URLError
from urllib.request import urlopen

from oracledb import Cursor

from pronto.utils import SIGNATURES
from .utils import load_exceptions, load_global_exceptions, load_terms


DoS = dict[str, set[str]]
LoS = list[str]
Err = list[tuple[str, str | None]]
LoT = list[tuple[str, str]]


def ck_begin_uppercase(cabs: LoT, exceptions: DoS) -> Err:
    prog = re.compile(r"^\s*(?:<p>)?\s*([a-z][A-Za-z]+)\s+")

    errors = []
    for ann_id, text in cabs:
        match = prog.match(text)
        if match:
            error = match.group(1)
            errors.append((ann_id, error))

    return [
        (ann_id, error)
        for (ann_id, error) in errors
        if ann_id not in exceptions or error not in exceptions[ann_id]
    ]


def ck_abbreviations(cabs: LoT, terms: LoS, exceptions: DoS) -> Err:
    prog1 = re.compile(r"\d+\s{2,}kDa")
    prog2 = re.compile(r"\b[cn][\-\s]termin(?:al|us)", flags=re.I)
    prog2_except = {"N-terminal", "C-terminal",
                    "C terminus", "N terminus"}

    prog3 = re.compile('|'.join(terms)) if terms else None

    errors = []
    for ann_id, text in cabs:
        for match in prog1.findall(text):
            errors.append((ann_id, match))

        for match in prog2.findall(text):
            if match not in prog2_except:
                errors.append((ann_id, match))

        if prog3:
            for match in prog3.findall(text):
                errors.append((ann_id, match))

    return [
        (ann_id, error)
        for (ann_id, error) in errors
        if ann_id not in exceptions or error not in exceptions[ann_id]
    ]


def ck_citations(cabs: LoT, terms: LoS, exceptions: DoS) -> Err:
    prog = re.compile('|'.join(map(re.escape, terms)), flags=re.I)

    errors = []
    for ann_id, text in cabs:
        ann_exceptions = exceptions.get(ann_id, set())
        for match in prog.findall(text):
            if match not in ann_exceptions:
                errors.append((ann_id, match))

    return errors


def ck_encoding(cabs: LoT, exceptions: set[str]) -> Err:
    errors = []
    for ann_id, text in cabs:
        for char in text:
            if not char.isascii() and str(ord(char)) not in exceptions:
                errors.append((ann_id, char))

    return errors


def ck_length(cabs: LoT, min_length: int = 25) -> Err:
    prog = re.compile(r"no\s+abs", flags=re.I)
    errors = []

    for ann_id, text in cabs:
        if len(text) < min_length or prog.search(text):
            errors.append((ann_id, None))

    return errors


def ck_links(cabs: LoT, max_attempts: int = 5) -> Err:
    prog = re.compile(r"https?://[\w\-@:%.+~#=/?&]+", flags=re.I)

    errors = []
    for ann_id, text in cabs:
        for url in set(prog.findall(text)):
            for _ in range(max_attempts):
                try:
                    res = urlopen(url)
                except URLError as exc:
                    """
                    Could be an HTTPError (subclass of URLError),
                    but it does not matter if it's a dead domain 
                    or an error on a valid domain (e.g. 404, 500, etc.) 
                    """
                    time.sleep(1)
                else:
                    if res.status < 400:
                        break
            else:
                errors.append((ann_id, url))

    return errors


def ck_punctuations(cabs: LoT, terms: LoS, exceptions: DoS) -> Err:
    prog_global = re.compile(r"\. \[")
    prog_detail = re.compile(r"[a-z]{3}|\d[\]\d]\]|\d\]\)", flags=re.I)

    errors = []
    for ann_id, text in cabs:
        ann_exceptions = exceptions.get(ann_id, set())

        for term in terms:
            if term in text and term not in ann_exceptions:
                errors.append((ann_id, term))

        for match in prog_global.finditer(text):
            term = match.group(0)
            if term in ann_exceptions:
                continue

            i, j = match.span()
            if text[i-3:i] == "e.g":
                continue  # e.g. [
            elif text[i-2:i] == "sp":
                continue  # sp. [
            elif text[i-5:i] == "et al":
                continue  # et al. [
            elif prog_detail.match(text[i-3:i]):
                """
                [a-z]{3}            ent. [
                \d[\]\d]\]          22]. [
                                    3]]. [
                \d\]\)              7]). [
                """
                continue
            else:
                errors.append((ann_id, term))

    return errors


def ck_spelling(cabs: LoT, terms: LoS, exceptions: DoS) -> Err:
    prog1 = re.compile(fr"\b(?:{'|'.join(terms)})\b", flags=re.I)
    gram_terms = ["gram\s*-(?!negative|positive)", "gram\s*\+", "gram pos",
                  "gram neg", "g-positive", "g-negative"]
    prog2 = re.compile('|'.join(gram_terms), flags=re.I)

    errors = []
    for ann_id, text in cabs:
        ann_exceptions = exceptions.get(ann_id, set())
        for match in prog1.findall(text):
            if match not in ann_exceptions:
                errors.append((ann_id, match))

        for match in prog2.findall(text):
            if match not in ann_exceptions:
                errors.append((ann_id, match))

    return errors


def ck_substitutions(cabs: LoT, terms: LoS, exceptions: DoS) -> Err:
    errors = []
    for ann_id, text in cabs:
        ann_exceptions = exceptions.get(ann_id, set())
        for term in terms:
            if term in text and ann_id not in ann_exceptions:
                errors.append((ann_id, term))

    return errors


def ck_interpro_accessions(cur: Cursor, cabs: LoT) -> Err:
    cur.execute(
        """
        SELECT ENTRY_AC 
        FROM INTERPRO.ENTRY
        WHERE CHECKED = 'Y'
        """
    )
    checked_entries = [row[0] for row in cur]

    errors = []
    accession = re.compile(r"IPR\d{6}")
    for ann_id, text in cabs:
        for match in accession.finditer(text):
            term = match.group(0)
            if term not in checked_entries:
                errors.append((ann_id, term))

    return errors


def ck_signature_accessions(cur: Cursor, cabs: LoT) -> Err:
    cur.execute(
        """
        SELECT METHOD_AC
        FROM INTERPRO.METHOD
        """
    )
    signatures = [row[0] for row in cur]

    errors = []
    prog = re.compile(fr"\b(?:{'|'.join(SIGNATURES)})\b")
    for ann_id, text in cabs:
        for match in prog.finditer(text):
            term = match.group(0)
            if term not in signatures:
                errors.append((ann_id, term))

    return errors


def check(cur: Cursor):
    cur.execute(
        """
        SELECT ANN_ID, TEXT
        FROM INTERPRO.COMMON_ANNOTATION
        WHERE ANN_ID IN (SELECT DISTINCT ANN_ID FROM INTERPRO.ENTRY2COMMON)
        """
    )
    cabs = cur.fetchall()

    terms = load_terms(cur, "abbreviation")
    exceptions = load_exceptions(cur, "abbreviation", "ANN_ID", "TERM")
    for item in ck_abbreviations(cabs, terms, exceptions):
        yield "abbreviation", item
    
    exceptions = load_exceptions(cur, "begin_uppercase", "ANN_ID", "TERM")
    for item in ck_begin_uppercase(cabs, exceptions):
        yield "begin_uppercase", item

    for item in ck_length(cabs):
        yield "cab_length", item

    terms = load_terms(cur, "citation")
    exceptions = load_exceptions(cur, "citation", "ANN_ID", "TERM")
    for item in ck_citations(cabs, terms, exceptions):
        yield "citation", item

    exceptions = load_global_exceptions(cur, "encoding")
    for item in ck_encoding(cabs, exceptions):
        yield "encoding", item

    for item in ck_length(cabs):
        yield "link", item

    terms = load_terms(cur, "punctuation")
    exceptions = load_exceptions(cur, "punctuation", "ANN_ID", "TERM")
    for item in ck_punctuations(cabs, terms, exceptions):
        yield "punctuation", item

    terms = load_terms(cur, "spelling")
    exceptions = load_exceptions(cur, "spelling", "ANN_ID", "TERM")
    for item in ck_spelling(cabs, terms, exceptions):
        yield "spelling", item

    terms = load_terms(cur, "substitution")
    exceptions = load_exceptions(cur, "substitution", "ANN_ID", "TERM")
    for item in ck_substitutions(cabs, terms, exceptions):
        yield "substitution", item

    for item in ck_interpro_accessions(cur, cabs):
        yield "deleted_entry", item

    for item in ck_signature_accessions(cur, cabs):
        yield "sign_not_found", item
