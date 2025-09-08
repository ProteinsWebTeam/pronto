# -*- coding: utf-8 -*-

from flask import jsonify

from pronto import utils
from . import bp


@bp.route("/<path:accessions>/matrices/")
def get_matrices(accessions):
    accessions = tuple(set(utils.split_path(accessions)))

    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()

    signatures, comparisons, exclusive = get_comparisons(cur, accessions)

    cur.close()
    con.close()
    
    return jsonify({
        "signatures": signatures,
        "comparisons": comparisons,
        "exclusive": exclusive
    })


def get_comparisons(cur, accessions: tuple):

    exclusive = {}
    for anchor_signature in accessions:
        anchor_signature_proteins = cur.execute(
            f"""
            SELECT protein_acc 
            FROM signature2protein 
            WHERE signature_acc = '{anchor_signature}'
            """
            ).fetchall()
        
        not_anchor_signatures = [x for x in accessions if x != anchor_signature] 
        not_anchor_signature_proteins = cur.execute(
            f"""SELECT protein_acc 
            FROM signature2protein 
            WHERE signature_acc in ({','.join(['%s'] * len(not_anchor_signatures))})
            """, not_anchor_signatures).fetchall()

        exclusive_to_anchor_signature = set(anchor_signature_proteins) - set(not_anchor_signature_proteins)
        exclusive[anchor_signature] = len(exclusive_to_anchor_signature)
    
    in_params = ','.join('%s' for _ in accessions)

    cur.execute(
        f"""
        SELECT accession, num_complete_sequences
        FROM interpro.signature
        WHERE accession IN ({in_params})
        """, accessions
    )
    signatures = dict(cur.fetchall())

    cur.execute(
        f"""
        SELECT signature_acc_1, signature_acc_2, num_collocations, num_overlaps
        FROM interpro.comparison
        WHERE signature_acc_1 IN ({in_params})
        AND signature_acc_2 IN ({in_params})
        """, accessions + accessions
    )

    comparisons = {}
    for acc1, acc2, collocations, overlaps in cur:
        try:
            s = comparisons[acc1]
        except KeyError:
            s = comparisons[acc1] = {}
        finally:
            s[acc2] = {
                "collocations": collocations,
                "overlaps": overlaps
            }

    return signatures, comparisons, exclusive
