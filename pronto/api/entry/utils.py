import re
from pronto.api.signatures import get_sig2interpro
from pronto.utils import SIGNATURES, connect_oracle
from pronto.api.checks.utils import load_global_exceptions


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
        full_pattern = rf"\b{pattern}\b"
        matches = re.findall(full_pattern, text, flags=re.IGNORECASE)
        if matches:
            accessions.update(matches)
            patterns.add(pattern)

    if accessions:
        sig2ipr = get_sig2interpro(list(accessions))
        for pattern in patterns:
            database = SIGNATURES[pattern]

            def repl(match: re.Match) -> str:
                sig_acc = match.group(2) or match.group(3)
                ipr_acc = sig2ipr.get(sig_acc)

                if ipr_acc:
                    return f"[interpro:{ipr_acc}]"
                else:
                    return f"[{database}:{sig_acc}]"

            """
            Look for accession in bracketed form or bare, e.g.
                [pfam:PFxxxxx]
                PFxxxxx
            """
            full_pattern = rf"\[([a-z]+):({pattern})\]|\b({pattern})\b"
            text = re.sub(full_pattern, repl, text, flags=re.IGNORECASE)
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
        inner = match.group(0)
        citations = re.findall(
            r"\[\s*cite:[^\]]+\s*\]",
            inner,
            flags=re.IGNORECASE,
        )
        return f"[{', '.join(citations)}]"

    citations_patterns = [
        r"\[\s*\[\s*cite:[^\]]+\s*\](?:\s*,?\s*\[\s*cite:[^\]]+\s*\])*\s*\]",
        r"\(\s*\[\s*cite:[^\]]+\s*\](?:\s*,?\s*\[\s*cite:[^\]]+\s*\])*\s*\)",
        r"(?:\[\[\s*cite:[^\]]+\s*\]\])+"
    ]
    for pattern in citations_patterns:
        text = re.sub(pattern, normalize, text, flags=re.IGNORECASE)

    return text


def _standardise_ec(text: str) -> str:
    number_pattern = r'\d+\.\d+\.\d+(?:\.\d+)?(?:\.(?:x|-))?'
    bracket_pattern = re.compile(
        rf'\[\s*EC\s*:?\s*({number_pattern})\s*\]', flags=re.IGNORECASE
    )
    pattern = re.compile(
        rf'(?<!\[)\bEC(?:\s+|:)\s*({number_pattern})\b', flags=re.IGNORECASE
    )
    def replacer(match: re.Match) -> str:
        ec = match.group(1)
        if ec.endswith((".x", ".-")):
            ec = ec[:-2]
        return f"[ec:{ec}]"

    text = bracket_pattern.sub(replacer, text)
    text = pattern.sub(replacer, text)

    return text


def _capitalize_first(text) -> str:
    con = connect_oracle()
    with con.cursor() as cur:
        keep_lower_terms = load_global_exceptions(cur, 'lower_case_name')
    con.close()

    for term in keep_lower_terms:
        if text.startswith(term):
            return text
    return text[0].upper() + text[1:]


def sanitize_domain(text):
    if not text:
        return text
    safe_patterns = [
        r",\s*[cC]\-?terminal\b",
        r",\s*[nN]\-?terminal\b",
        r",\s*beta\b",
        r",\s*alpha\b",
        r",\s*catalytic\b",
        r",\s*motor\b",
        r",\s*cupin\b",
        r",\s*helical\b",
        r",\s*metallophosphatase\b",
        r",\s*middle\b",
        r",\s*second\b",
        r",\s*central\b",
        r",\s*transmembrane\b",
    ]

    has_domain_already = re.search(
        r"\bdomain(s)?\b|domain[-\s]",
        text,
        flags=re.IGNORECASE
    )
    if has_domain_already:
        return text

    has_safe_pattern = any(
        re.search(p, text) for p in safe_patterns
    )
    if has_safe_pattern:
        text = re.sub(r"\s*$", " domain", text)
    return text


def sanitize_description(text: str) -> str:
    if not text:
        return text
    text = _replace_greek_letters(text)
    text = _replace_terminus(text)
    text = _replace_terminal(text)
    text = _replace_accessions(text)
    text = _replace_terms(text)
    text = _standardise_citations(text)
    text = _standardise_ec(text)
    return text


def sanitize_name(name: str) -> str:
    name = re.sub(r"-family proteins?\b", "-like", name, flags=re.I)
    name = _capitalize_first(name)
    return name


def sanitize_short_name(short_name: str) -> str:
    short_name = re.sub(r"_(fam|like)\b", "-like", short_name, flags=re.I)
    short_name = _capitalize_first(short_name)
    return short_name