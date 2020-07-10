# -*- coding: utf-8 -*-

from flask import jsonify

from pronto import utils
from . import bp


@bp.route("/<path:accessions>/comments/")
def get_comments(accessions):
    accessions = utils.split_path(accessions)

    con = utils.connect_pg()
    with con.cursor() as cur:
        cur.execute(
            f"""
            SELECT ps.comment_id, min(ps.comment_text), 
                   sp.signature_acc, COUNT(*) cnt
            FROM signature2protein sp
            INNER JOIN protein_similarity ps ON sp.protein_acc = ps.protein_acc
            WHERE sp.signature_acc IN ({','.join("%s" for _ in accessions)})
            GROUP BY ps.comment_id, signature_acc
            """, accessions
        )

        comments = {}
        for comment_id, comment_text, accession, cnt in cur:
            try:
                d = comments[comment_id]
            except KeyError:
                d = comments[comment_id] = {
                    "id": comment_id,
                    "value": comment_text,
                    "signatures": {}
                }
            finally:
                d["signatures"][accession] = cnt

    con.close()

    return jsonify({
        "results": sorted(comments.values(),
                          key=lambda d: -max(d["signatures"].values()))
    })
