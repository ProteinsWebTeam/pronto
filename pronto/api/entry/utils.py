import re
from pronto.api.signatures import get_sig2interpro

MEMBERS_PATTERNS = {
    "cath-gene3d": r"\bG3DSA:\d+(?:\.\d+)+\b",
    "cdd": r"\bcd\d+\b",
    "hamap": r"\bMF_\d+\b",
    "ncbifam": r"\bNF\d+\b",
    "panther": r"\bPTHR\d+\b",
    "pirsf": r"\bPIRSF\d+\b",
    "pfam": r"\bPF\d+\b",
    "prints": r"\bPR\d+\b",
    "prosite": r"\bPS\d+\b",
    "sfld": r"\bSFLD_\d+\b",
    "smart": r"\bSM\d+\b",
    "superfamily": r"\bSSF\d+\b"
}


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


def _replace_member_accessions(text: str) -> str:
    for member, pattern in MEMBERS_PATTERNS.items():
        regex = re.compile(pattern, re.IGNORECASE)

        def replacer(match):
            accession = match.group(0)
            ipr_acc = get_sig2interpro(accession)
            if ipr_acc:
                return f"[interpro:{ipr_acc}]"
            return f"[{member}:{accession}]"

        text = regex.sub(replacer, text)
    return text


def _standardise_citations(text: str) -> str:
    regex = re.compile(
        r"\((\s*(?:\[\s*cite:[^\]]+\s*\]\s*,?\s*)+)\)",
        flags=re.IGNORECASE
    )

    def standardize_multiple(match):
        inner = match.group(1)
        inner = re.sub(r"\s*,\s*", ", ", inner.strip())
        return f"[[{inner}]]"

    text = regex.sub(standardize_multiple, text)
    text = re.sub(
        r"\[\[(.*?)\]\]",
        lambda m: "[[" + re.sub(r"\s*,\s*", ", ", m.group(1).strip()) + "]]",
        text,
        flags=re.DOTALL
    )
    return text


def sanitize_description(text):
    if not text:
        return text
    text = _replace_greek_letters(text)
    text = _replace_terminus(text)
    text = _replace_terminal(text)
    text = _replace_member_accessions(text)
    text = _standardise_citations(text)
    return text
