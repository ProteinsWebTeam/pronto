# -*- coding: utf-8 -*-

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
                   pg.ref_db_code, pg.ref_db_id
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
    
        params_pthr2go = list(aspects) if aspects and aspects != _ASPECTS else []
        terms = get_go2panther(accessions, terms, cur, aspects_stmt, params_pthr2go)

    con.close()

    for term in terms.values():
        for signature_acc, (proteins, refs, pthr2go) in term["signatures"].items():
            term["signatures"][signature_acc] = {
                "proteins": len(proteins),
                "references": len(refs),
                "panthergo": len(pthr2go)
            }

    return jsonify({
        "aspects": list(aspects) or list(_ASPECTS),
        "results": sorted(terms.values(), key=_sort_term),
        "integrated": get_sig2interpro(accessions)
    })


def _sort_term(term):
    max_prots = max(s["proteins"] for s in term["signatures"].values())
    return -max_prots, term["id"]


def get_go2panther(accessions, terms, pg_cur, aspects_stmt, params):

    acc = "','".join(accessions)
    acc = f"'{acc}'"

    pg_cur.execute(
        f"""
        SELECT DISTINCT s2p.model_acc
        FROM interpro.signature2protein s2p
        WHERE s2p.signature_acc in ({acc})
        AND s2p.model_acc IS NOT NULL
        """
    )
    subfams =  "','".join(row[0] for row in pg_cur.fetchall())

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
    f"""
        SELECT DISTINCT METHOD_AC, GO_ID
        FROM INTERPRO.PANTHER2GO
        WHERE METHOD_AC IN ('{subfams}')
        """
    )

    for row in cur:
        term_id = row[1]
        pth_fam = row[0].split(':')[0]

        try:
            term = terms[term_id]
        except KeyError:
            term = terms[term_id] = get_go_details(term_id, pg_cur, aspects_stmt, params)
        
        if term:
            try:
                s = term["signatures"][pth_fam]
            except KeyError:
                s = term["signatures"][pth_fam] = [set(), set(), set()]

            s[2].add(row[0])

    cur.close()
    con.close()

    return terms

def get_go_details(term_id, pg_cur, aspects_stmt, params):
    godetails = {}

    pg_cur.execute(
            f"""
            SELECT t.id, t.name, t.category
            FROM term t
            WHERE t.id = '{term_id}'
            {aspects_stmt}  
            """, (params)
        )
    for row in pg_cur:
        go_id = row[0]
        godetails = {
                "id":go_id, 
                "name": row[1], 
                "aspect": row[2], 
                "signatures": {}
            }

    return godetails