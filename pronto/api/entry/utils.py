import re
from oracledb import Cursor, DatabaseError
from pronto.api.signatures import get_sig2interpro
from pronto.utils import SIGNATURES, connect_oracle


def _replace_greek_letters(text):
    structural_terms = ["helix", "helices", "sheet", "strand", "propeller", "barrel",
                        "sandwich", "meander", "configuration", "structure", "fold"]
    replacement_map = {
        "alpha": "α",
        "beta": "β"
    }
    sep = r"[\s\-\+/]+"
    replacements = "|".join(replacement_map.keys())
    pattern = rf"\b({replacements})(?=(?:{sep}(?:{replacements}))?{sep}(?:{'|'.join(structural_terms)})s?\b)"
    return re.sub(pattern,
                  lambda m: replacement_map[m.group(1).lower()], text, flags=re.IGNORECASE)


def _replace_terminus(text):
    return re.sub(r"\b([CN])\-terminus\b",
                  lambda m: f"{m.group(1)} terminus", text, flags=re.IGNORECASE)


def _replace_terminal(text):
    return re.sub(r"\b([CN])\s+terminal\b",
                  lambda m: f"{m.group(1)}-terminal", text, flags=re.IGNORECASE)


def _replace_accessions(text: str) -> str:
    accessions = set()
    patterns = set()
    for pattern in SIGNATURES:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            accessions.update(matches)
            patterns.add(pattern)

    if accessions:
        sig2ipr = get_sig2interpro(list(accessions))
        for pattern in patterns:
            database = SIGNATURES[pattern]

            def replacer(match):
                accession = match.group(0)
                if accession in sig2ipr:
                    return f"[interpro:{sig2ipr[accession]}]"
                return f"[{database}:{accession}]"

            text = re.sub(pattern, replacer, text, flags=re.IGNORECASE)
    return text


def _replace_terms(text):
    replacements = [
        (r"\bHMM describes\b", "entry represents"),
        (r"\bdomain family\b", "entry"),
        (
            r"\b(this|the)\s+(HMM|model)\s+"
            r"(represents|corresponds|identifies|characterizes|summarizes|covers|"
            r"recognizes|distinguishes|contains|includes|excludes|finds|hits|spans)\b",
            r"\1 entry \3",
        ),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text.replace("“", '"').replace("”", '"')


def _standardise_citations(text: str) -> str:
    def normalize(match):
        inner = match.group(1)
        citations = re.findall(
            r"\[\s*(cite:[^\]]+)\s*\]",
            inner,
            flags=re.IGNORECASE,
        )
        if len(citations) == 1:
            return f"[[{citations[0]}]]"
        multiple_citations = ", ".join(citations)
        return f"[[{multiple_citations}]]"

    text = re.sub(
        r"\((\s*(?:\[\s*cite:[^\]]+\s*\]\s*,?\s*)+)\)",
        normalize,
        text,
        flags=re.IGNORECASE,
    )
    return text


def _captilize_exceptions(text) -> str:
    con = connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT TERM
        FROM INTERPRO.PRONTO_SANITY_EXCEPTION
        WHERE CHECK_TYPE = 'lower_case_name'
        """,
    )
    exceptions = [row[0] for row in cur.fetchall()]
    cur.close()
    con.close()

    if text.split()[0] not in exceptions:
        text = text[0].upper() + text[1:]
    return text


def _british_standard(text) -> str:
    replacements = {
        "homologs": "homologues",
        "speling": "spelling",
        "behavior": "behaviour",
    }
    for american, british in replacements.items():
        text = re.sub(rf"\b{american}\b", british, text, flags=re.IGNORECASE)
    return text


def sanitize_description(text):
    if not text:
        return text
    text = _replace_greek_letters(text)
    text = _replace_terminus(text)
    text = _replace_terminal(text)
    text = _replace_accessions(text)
    text = _replace_terms(text)
    text = _standardise_citations(text)
    text = _british_standard(text)
    return text


def sanitize_name(name):
    name = re.sub(r"\b(-family proteins|-family protein)\b", "-like", name, flags=re.IGNORECASE)
    name = _captilize_exceptions(name)
    return name


def sanitize_short_name(short_name):
    short_name = re.sub(r"\b(_like|_fam)\b", "-like", short_name, flags=re.IGNORECASE)
    short_name = re.sub(r"\b_like\b", "-like", short_name, flags=re.IGNORECASE)
    short_name = _captilize_exceptions(short_name)
    return short_name