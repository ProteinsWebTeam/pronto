import re
from pronto.api.signatures import get_sig2interpro
from pronto.utils import SIGNATURES


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

    for pattern in SIGNATURES:
        accessions.update(re.findall(pattern, text, flags=re.IGNORECASE))
    sig2ipr = get_sig2interpro(list(accessions))

    for pattern, member in SIGNATURES.items():
        regex = re.compile(pattern, re.IGNORECASE)

        def replacer(match):
            accession = match.group(0)
            if accession in sig2ipr:
                return f"[interpro:{sig2ipr[accession]}]"
            return f"[{member}:{accession}]"

        text = regex.sub(replacer, text)

    return text


def sanitize_description(text):
    if not text:
        return text
    text = _replace_greek_letters(text)
    text = _replace_terminus(text)
    text = _replace_terminal(text)
    text = _replace_accessions(text)
    return text
