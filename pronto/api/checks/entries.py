import re
from typing import Dict, List, Optional, Set, Tuple

from cx_Oracle import Cursor

from pronto.utils import connect_pg, SIGNATURES
from pronto.api.signatures.matrices import get_comparisons
from .utils import load_exceptions, load_global_exceptions, load_terms

DoS = Dict[str, Set[str]]
LoS = List[str]
Err = List[Tuple[str, Optional[str]]]
LoT = List[Tuple[str, str, str]]


def ck_abbreviations(entries: LoT, terms: LoS, exceptions: DoS) -> Err:
    prog1 = re.compile(r"\d+\s{2,}kDa")
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


def ck_domain_in_family(cur: Cursor) -> Err:
    cur.execute(
        """
        SELECT ENTRY_AC, NAME
        FROM INTERPRO.ENTRY
        WHERE ENTRY_TYPE='F'
        AND CHECKED = 'Y'
        AND (NAME LIKE '%-terminal' OR NAME LIKE '%-terminal domain')
        """
    )

    return cur.fetchall()


def ck_acc_in_name(entries: LoT, exceptions: DoS) -> Err:
    prog = re.compile(fr"\b(?:{'|'.join(SIGNATURES)})\b")

    errors = []
    for acc, name, short_name in entries:
        entry_exceptions = exceptions.get(acc, set())
        for match in prog.findall(name):
            if match not in entry_exceptions:
                errors.append((acc, match))

    return errors


def ck_double_quote(entries: LoT) -> Err:
    return [(acc, None) for acc, name, short_name in entries if '"' in name]


def ck_encoding(entries: LoT, exceptions: Set[str]) -> Err:
    errors = []
    for acc, name, short_name in entries:
        for char in name:
            if not char.isascii():
                errors.append((acc, char))
        for char in short_name:
            if not char.isascii():
                errors.append((acc, char))

    return errors


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


def ck_match_counts(ora_cur: Cursor, pg_url: str) -> Err:
    pg_con = connect_pg(pg_url)
    pg_cur = pg_con.cursor()
    pg_cur.execute(
        """
        SELECT accession
        FROM interpro.signature
        WHERE num_sequences = 0
        """
    )
    no_hits = {acc for acc, in pg_cur}
    pg_cur.close()
    pg_con.close()

    ora_cur.execute(
        """
        SELECT E.ENTRY_AC, EM.METHOD_AC
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2METHOD EM ON E.ENTRY_AC = EM.ENTRY_AC
        WHERE E.CHECKED = 'Y'
        """
    )
    return [(e_acc, s_acc) for e_acc, s_acc in ora_cur if s_acc in no_hits]


def ck_letter_case(entries: LoT, exceptions: Tuple[str]) -> Err:
    prog = re.compile("[a-z]")
    errors = []
    for acc, name, short_name in entries:
        if prog.match(name) and not name.startswith(exceptions):
            errors.append((acc, name.split(' ')[0]))

        if prog.match(short_name) and not short_name.startswith(exceptions):
            errors.append((acc, short_name.split('_')[0]))

    return errors


def ck_retracted(cur: Cursor, entries: LoT) -> Err:
    # Get retracted publications (EXTERNAL_ID is a VARCHAR)
    cur.execute(
        """
        SELECT DISTINCT C.EXTERNAL_ID
        FROM CDB.CITATIONS@LITPUB C
        INNER JOIN CDB.CITATION_PUBLICATIONTYPES@LITPUB C2T
            ON C.ID = C2T.CITATION_ID
        INNER JOIN CDB.CV_PUBLICATION_TYPES@LITPUB CV
            ON C2T.PUBLICATION_TYPE_ID = CV.ID
        WHERE CV.NAME = 'Retracted Publication'
        """
    )
    retracted = {row[0] for row in cur}

    # Get accession of entries
    accessions = {acc for acc, name, short_name in entries}

    # Get citations for each entry (PUBMED_ID is a NUMBER)
    cur.execute(
        """
        SELECT DISTINCT E2P.ENTRY_AC, C.PUBMED_ID
        FROM (
            SELECT ENTRY_AC, PUB_ID
            FROM INTERPRO.ENTRY2PUB
            UNION
            SELECT ENTRY_AC, PUB_ID
            FROM INTERPRO.SUPPLEMENTARY_REF
        ) E2P
        INNER JOIN INTERPRO.CITATION C 
            ON E2P.PUB_ID = C.PUB_ID        
        """
    )

    errors = []
    for row in cur:
        acc = row[0]
        pmid = str(row[1])
        if acc in accessions and pmid in retracted:
            errors.append((acc, pmid))

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


def ck_unchecked_parents(cur: Cursor) -> Err:
    """Find unchecked entries with one or more checked children

    :param cur: Cursor object
    :return: a list of accessions
    """
    cur.execute(
        """
        SELECT DISTINCT P.ENTRY_AC
        FROM INTERPRO.ENTRY P
        INNER JOIN INTERPRO.ENTRY2ENTRY EE ON P.ENTRY_AC = EE.PARENT_AC
        INNER JOIN INTERPRO.ENTRY C ON EE.ENTRY_AC = C.ENTRY_AC
        WHERE P.CHECKED = 'N' AND C.CHECKED = 'Y'
        """
    )
    return [(acc, None) for acc, in cur]


def ck_unchecked_children(cur: Cursor) -> Err:
    """Find unchecked entries whose parent is checked

    :param cur: Cursor object
    :return: a list of accessions
    """
    cur.execute(
        """
        SELECT DISTINCT C.ENTRY_AC
        FROM INTERPRO.ENTRY C
        INNER JOIN INTERPRO.ENTRY2ENTRY EE ON C.ENTRY_AC = EE.ENTRY_AC
        INNER JOIN INTERPRO.ENTRY P ON EE.PARENT_AC = P.ENTRY_AC
        WHERE C.CHECKED = 'N' AND P.CHECKED = 'Y'
        """
    )
    return [(acc, None) for acc, in cur]


def ck_children_type(cur: Cursor) -> Err:
    cur.execute(
    """
        SELECT A.PARENT_AC PARENT, A.ENTRY_AC CHILD
        FROM INTERPRO.ENTRY2ENTRY A
        JOIN INTERPRO.ENTRY B1 ON A.ENTRY_AC = B1.ENTRY_AC
        JOIN INTERPRO.ENTRY B2 ON A.PARENT_AC = B2.ENTRY_AC
        WHERE B2.ENTRY_TYPE != B1.ENTRY_TYPE
        ORDER BY A.PARENT_AC,A.ENTRY_AC
    """
    )
    errors = []

    for row in cur:
        errors.append((row[0], row[1]))

    return errors


def ck_no_children(cur: Cursor) -> Err:
    cur.execute(
    """
        SELECT A.PARENT_AC PARENT, A.ENTRY_AC CHILD 
        FROM INTERPRO.ENTRY2ENTRY A
        JOIN INTERPRO.ENTRY B1 ON A.ENTRY_AC = B1.ENTRY_AC
        JOIN INTERPRO.ENTRY B2 ON A.PARENT_AC = B2.ENTRY_AC
        WHERE B2.ENTRY_TYPE IN ('R','C','A','B','P','H')
        ORDER BY A.PARENT_AC, A.ENTRY_AC
        """
    )
    errors = []

    for row in cur:
        errors.append((row[0], row[1]))

    return errors


def ck_child_matches(cur: Cursor, pg_url: str, exceptions: DoS) -> Err:
    # Get PRINTS accessions
    cur.execute("SELECT METHOD_AC FROM INTERPRO.METHOD WHERE DBCODE = 'F'")
    prints_signatures = {acc for acc, in cur.fetchall()}

    cur.execute(
        """
        SELECT E2E.PARENT_AC, E2MP.METHOD_AC, E2E.ENTRY_AC, E2M.METHOD_AC
        FROM INTERPRO.ENTRY2ENTRY E2E
        JOIN INTERPRO.ENTRY2METHOD E2M ON E2E.ENTRY_AC = E2M.ENTRY_AC
        JOIN INTERPRO.ENTRY2METHOD E2MP ON E2E.PARENT_AC = E2MP.ENTRY_AC
        ORDER BY E2E.PARENT_AC
        """
    )

    entries = {}
    for row in cur:
        parent_ac, p_sign, child_ac, c_sign = row

        if p_sign in prints_signatures or c_sign in prints_signatures:
            continue

        try:
            entries[parent_ac]["p_sign"].add(p_sign)
            entries[parent_ac][child_ac].add(c_sign)
        except KeyError:
            if parent_ac in entries:
                entries[parent_ac][child_ac]=set()
            else:
                entries[parent_ac] = {"p_sign":set(), child_ac:set()}
            entries[parent_ac]["p_sign"].add(p_sign)
            entries[parent_ac][child_ac].add(c_sign)

    errors = []
    pg_con = connect_pg(pg_url)
    pg_cur = pg_con.cursor()
    for parent_ac, info in entries.items():
        all_sign = set()
        for item in info.values():
            all_sign = all_sign.union(item)
        
        signatures, comparisons = get_comparisons(pg_cur, tuple(all_sign))
        no_overlap = {}

        for sign1, coloc in comparisons.items():
            if sign1 in list(info["p_sign"]):
                for sign2 in coloc:
                    if coloc[sign2]["overlaps"] == 0:
                        try:
                            no_overlap[sign2].append(sign1)
                        except KeyError:
                            no_overlap[sign2] = [sign1]

        entry_exceptions = exceptions.get(parent_ac, set())

        if len(no_overlap) > 0:
            for child_ac, list_sign in info.items():
                count = 0
                for sign in list_sign:
                    """
                    If the child signature is found having no overlap, 
                    verify it doesn't match any of the parent signatures
                    """
                    if sign in no_overlap and len(no_overlap[sign]) == len(info["p_sign"]): 
                        count += 1

                """
                If none the child signatures are found matching 
                the parent signatures, report an error
                """
                if count == len(list_sign) and child_ac not in entry_exceptions:
                    errors.append((parent_ac, child_ac))

    pg_cur.close()
    pg_con.close()

    return errors


def ck_underscore(entries: LoT, exceptions: Set[str]) -> Err:
    prog1 = re.compile(r"\w*_\w*")
    prog2 = re.compile(r"_(?:binding|bd|related|rel|like)(?![a-zA-Z])")

    errors = []
    for acc, name, short_name in entries:
        for match in prog1.findall(name):
            if acc not in exceptions:
                errors.append((acc, match))

        for match in prog2.findall(short_name):
            if acc not in exceptions:
                errors.append((acc, match))

    return errors


def ck_no_cab(cur: Cursor) -> Err:
    cur.execute("""
            SELECT ENTRY_AC
            FROM INTERPRO.ENTRY
            WHERE CHECKED = 'Y'
            MINUS
            SELECT DISTINCT ENTRY_AC
            FROM INTERPRO.ENTRY2COMMON
        """
    )

    return cur.fetchall()


def ck_fragments(cur: Cursor, sign_frag_only: set) -> Err:
    # Integrated ENTRIES that have METHODs that MATCH ONLY FRAGMENTS
    errors = []

    if len(sign_frag_only) > 0:
        binds = [":" + str(i + 1) for i in range(len(sign_frag_only))]

        cur.execute(
            f"""
                SELECT E.ENTRY_AC, E2M.METHOD_AC
                FROM INTERPRO.ENTRY E
                JOIN INTERPRO.ENTRY2METHOD E2M ON E.ENTRY_AC=E2M.ENTRY_AC
                WHERE E.CHECKED='Y' AND E2M.METHOD_AC IN ({",".join(binds)})
                GROUP BY E.ENTRY_AC, E2M.METHOD_AC
            """, list(sign_frag_only))

        for row in cur:
            entry_ac, sign = row
            if sign in sign_frag_only:
                errors.append((entry_ac, sign))

    return errors


def get_frags_only_signatures(pg_url: str) -> Err:
    pg_con = connect_pg(pg_url)
    pg_cur = pg_con.cursor()

    pg_cur.execute(
        """
            SELECT accession
            FROM signature
            WHERE num_sequences > 0
            AND num_complete_sequences = 0
        """
    )
    errors = [row[0] for row in pg_cur]

    pg_cur.close()
    pg_con.close()

    return errors


def check(ora_cur: Cursor, pg_url: str):
    ora_cur.execute("SELECT ENTRY_AC, NAME, SHORT_NAME FROM INTERPRO.ENTRY")
    entries = ora_cur.fetchall()

    terms = load_terms(ora_cur, "abbreviation")
    exceptions = load_exceptions(ora_cur, "abbreviation", "ENTRY_AC", "TERM")
    for item in ck_abbreviations(entries, terms, exceptions):
        yield "abbreviation", item

    for item in ck_domain_in_family(ora_cur):
        yield "domain_in_family_name", item

    exceptions = load_exceptions(ora_cur, "acc_in_name", "ENTRY_AC", "TERM")
    for item in ck_acc_in_name(entries, exceptions):
        yield "acc_in_name", item

    for item in ck_double_quote(entries):
        yield "double_quote", item

    exceptions = load_global_exceptions(ora_cur, "encoding")
    for item in ck_encoding(entries, exceptions):
        yield "encoding", item

    exceptions = load_global_exceptions(ora_cur, "gene_symbol")
    for item in ck_gene_symbol(entries, exceptions):
        yield "gene_symbol", item

    terms = load_terms(ora_cur, "forbidden")
    exceptions = load_exceptions(ora_cur, "forbidden", "ENTRY_AC", "TERM")
    for item in ck_forbidden_terms(entries, terms, exceptions):
        yield "forbidden", item

    exceptions = load_global_exceptions(ora_cur, "lower_case_name")
    for item in ck_letter_case(entries, tuple(exceptions)):
        yield "lower_case_name", item

    for item in ck_integration(ora_cur):
        yield "integration", item

    for item in ck_match_counts(ora_cur, pg_url):
        yield "matches", item

    for item in ck_same_names(ora_cur):
        yield "same_name", item

    for item in ck_retracted(ora_cur, entries):
        yield "retracted", item

    exceptions = load_exceptions(ora_cur, "similar_name", "ENTRY_AC",
                                 "ENTRY_AC2")
    for item in ck_similar_names(ora_cur, exceptions):
        yield "similar_name", item

    terms = load_terms(ora_cur, "spelling")
    exceptions = load_exceptions(ora_cur, "spelling", "ENTRY_AC", "TERM")
    for item in ck_spelling(entries, terms, exceptions):
        yield "spelling", item

    for item in ck_type_conflicts(ora_cur):
        yield "type_conflict", item

    for item in ck_unchecked_parents(ora_cur):
        yield "unchecked_parent", item

    for item in ck_unchecked_children(ora_cur):
        yield "unchecked_child", item
    
    for item in ck_children_type(ora_cur):
        yield "child_type_conflict", item

    for item in ck_no_children(ora_cur):
        yield "unauthorised_child", item
    
    exceptions = load_exceptions(ora_cur, "child_matches", "ENTRY_AC", "TERM")
    for item in ck_child_matches(ora_cur, pg_url, exceptions):
        yield "child_matches", item

    exceptions = load_exceptions(ora_cur, "underscore", "ENTRY_AC", "TERM")
    for item in ck_underscore(entries, set(exceptions)):
        yield "underscore", item
    
    for item in ck_no_cab(ora_cur):
        yield "empty_annotation", item

    sign_frag_only = get_frags_only_signatures(pg_url)
    for item in ck_fragments(ora_cur, sign_frag_only):
        yield "fragment_matches", item
