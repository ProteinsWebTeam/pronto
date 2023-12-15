from typing import Dict, List, Set
from flask import jsonify, request

from pronto import utils
from . import bp, get_sig2interpro


_ASPECTS = {'cellular_component', 'molecular_function', 'biological_process'}


@bp.route("/<path:accessions>/go/")
def get_go_terms(accessions):
    accessions = utils.split_path(accessions)
    aspects = set(request.args.getlist("aspect"))
    if aspects - _ASPECTS:
        return jsonify({
            "error": {
                "title": "Bad Request (invalid aspect)",
                f"message": f"Accepted aspects are: {', '.join(_ASPECTS)}."
            }
        }), 400

    con = utils.connect_pg()    
    with con.cursor() as cur:
        in_stmt = ','.join("%s" for _ in accessions)
        params = accessions + accessions

        if aspects and aspects != _ASPECTS:
            aspects_stmt = (f"AND t.category "
                            f"IN ({','.join('%s' for _ in aspects)})")
            params += list(aspects)
        else:
            aspects_stmt = ""

        cur.execute(
            f"""
            SELECT t.id, t.name, t.category, sp.signature_acc, sp.protein_acc,
                   pg.ref_db_code, pg.ref_db_id, sp.model_acc
            FROM signature2protein sp
            INNER JOIN (
                SELECT *
                FROM protein2go
                WHERE protein_acc IN (
                    SELECT DISTINCT protein_acc
                    FROM signature2protein
                    WHERE signature_acc IN ({in_stmt})
                )
            ) pg ON sp.protein_acc = pg.protein_acc
            INNER JOIN term t ON pg.term_id = t.id
            WHERE signature_acc IN ({in_stmt})
            {aspects_stmt}
            """, params
        )

        terms = {}
        subfams = set()
        g3d_signs = dict()
        for row in cur:
            term_id = row[0]
            try:
                term = terms[term_id]
            except KeyError:
                term = terms[term_id] = {
                    "id": term_id,
                    "name": row[1],
                    "aspect": row[2],
                    "signatures": {}
                }

            signature_acc = row[3]
            try:
                s = term["signatures"][signature_acc]
            except KeyError:
                s = term["signatures"][signature_acc] = [set(), set(), set()]

            s[0].add(row[4])  # protein
            if row[5] == "PMID":
                s[1].add(row[6])  # Pubmed reference

            if row[7] is not None:
                subfams.add(row[7])
            elif signature_acc.startswith("G3DSA"):
                try:
                    g3d_signs[signature_acc].add(row[4])
                except KeyError:
                    g3d_signs[signature_acc] = {row[4]}

        terms = get_go2panther(subfams, terms, cur)

        terms = get_go2funfam(g3d_signs, terms, cur)

    con.close()

    for term in terms.values():
        for signature_acc, obj in term["signatures"].items():
            proteins, refs, signature2go = obj
            term["signatures"][signature_acc] = {
                "proteins": len(proteins),
                "references": len(refs),
                "signaturego": len(signature2go)
            }

    return jsonify({
        "aspects": list(aspects) or list(_ASPECTS),
        "results": sorted(terms.values(), key=_sort_term),
        "integrated": get_sig2interpro(accessions)
    })


def _sort_term(term):
    max_prots = max(s["proteins"] for s in term["signatures"].values())
    return -max_prots, term["id"]


def get_go2panther(subfams: Set[str], terms: Dict[str, dict], pg_cur):
    con = utils.connect_oracle()
    cur = con.cursor()
    
    go_terms = set()
    subfams = list(subfams)
    for i in range(0, len(subfams), 1000):
        subset = subfams[i:i+1000]
        binds = [":" + str(j+1) for j in range(len(subset))]
        cur.execute(
            f"""
            SELECT DISTINCT METHOD_AC, GO_ID
            FROM INTERPRO.PANTHER2GO
            WHERE METHOD_AC IN ({','.join(binds)})
            """,
            subset
        )

        for row in cur:
            term_id = row[1]
            pth_fam = row[0].split(':')[0]

            try:
                term = terms[term_id]
            except KeyError:
                term = terms[term_id] = {"id": term_id, "signatures": {}}
                go_terms.add(term_id)

            try:
                s = term["signatures"][pth_fam]
            except KeyError:
                s = term["signatures"][pth_fam] = [set(), set(), set()]

            s[2].add(row[0])

    cur.close()
    con.close()

    go_terms = list(go_terms)
    for i in range(0, len(go_terms), 100):
        subset = go_terms[i:i+100]

        for term in get_go_details(subset, pg_cur):
            terms[term["id"]].update(term)

    return terms


def get_go2funfam(gene3dset: dict, terms: dict, pg_cur):
    con = utils.connect_oracle()
    cur = con.cursor()

    go_terms = set()

    for signature, proteins in gene3dset.items():

        for i in range(0, len(proteins), 1000):
            subset = list(proteins)[i:i+1000]
            binds = [":" + str(j+1) for j in range(len(subset))]
            subset.append(f"{signature}%")

            request = f"""
            SELECT DISTINCT METHOD_AC, GO_ID
            FROM INTERPRO.FUNFAM2GO M
            WHERE PROTEIN_AC IN ({','.join(binds)})
            AND METHOD_AC LIKE :{len(binds)+1}
            """

            cur.execute(request, subset)

            for row in cur:
                term_id = row[1]

                try:
                    term = terms[term_id]
                except KeyError:
                    term = terms[term_id] = {"id": term_id, "signatures": {}}
                    go_terms.add(term_id)

                try:
                    s = term["signatures"][signature]
                except KeyError:
                    s = term["signatures"][signature] = [set(), set(), set()]

                s[2].add(row[0])

    cur.close()
    con.close()

    go_terms = list(go_terms)
    for i in range(0, len(go_terms), 100):
        subset = go_terms[i:i+100]

        for term in get_go_details(subset, pg_cur):
            terms[term["id"]].update(term)

    return terms


def get_go_details(term_ids: List[str], pg_cur) -> List[dict]:
    details = []

    binds = ["%s" for _ in term_ids]
    pg_cur.execute(
        f"""
        SELECT t.id, t.name, t.category
        FROM term t
        WHERE t.id IN ({','.join(binds)})
        """,
        term_ids
    )

    columns = ("id", "name", "aspect")
    for row in pg_cur.fetchall():
        details.append(dict(zip(columns, row)))

    return details
