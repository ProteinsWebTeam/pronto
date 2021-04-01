# -*- coding: utf-8 -*-

from flask import jsonify, request

from pronto import utils
from . import bp, get_sig2interpro


@bp.route("/<path:accessions>/descriptions/")
def get_descriptions(accessions):
    accessions = utils.split_path(accessions)
    reviewed_only = "reviewed" in request.args

    con = utils.connect_pg()
    with con.cursor() as cur:
        cur.execute(
            f"""
            SELECT p.name_id, pn.text, p.signature_acc, p.cnt
            FROM (
                SELECT name_id, signature_acc, COUNT(*) cnt
                FROM signature2protein
                WHERE signature_acc IN ({','.join("%s" for _ in accessions)})
                {'AND is_reviewed' if reviewed_only else ''}
                GROUP BY name_id, signature_acc
            ) p
            INNER JOIN protein_name pn ON p.name_id = pn.name_id
            """, accessions
        )

        descriptions = {}
        for name_id, text, accession, cnt in cur:
            try:
                d = descriptions[name_id]
            except KeyError:
                d = descriptions[name_id] = {
                    "id": name_id,
                    "value": text,
                    "signatures": {}
                }
            finally:
                d["signatures"][accession] = cnt

    con.close()

    return jsonify({
        "results": sorted(descriptions.values(),
                          key=lambda d: -max(d["signatures"].values())),
        "integrated": get_sig2interpro(accessions)
    })
