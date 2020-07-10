# -*- coding: utf-8 -*-

from flask import jsonify, request

from pronto import utils
from . import bp


RANKS = {"superkingdom", "kingdom", "phylum", "class", "order", "family",
         "genus", "species"}


@bp.route("/<path:accessions>/taxonomy/<rank>/")
def get_taxonomy_origins(accessions, rank):
    if rank not in RANKS:
        return jsonify({
            "error": {
                "title": "Bad Request (invalid rank)",
                "message": f"Available ranks: {', '.join(RANKS)}."
            }
        }), 400

    accessions = utils.split_path(accessions)
    taxon_id = request.args.get("taxon")

    con = utils.connect_pg()
    cur = con.cursor()

    taxon_name = left_num = right_num = None
    if taxon_id:
        cur.execute(
            """
            SELECT name, left_number, right_number 
            FROM taxon 
            WHERE id = %s
            """, (taxon_id,)
        )
        row = cur.fetchone()
        if row:
            taxon_name, left_num, right_num = row
        else:
            cur.close()
            con.close()
            return jsonify({
                "error": {
                    "title": "Bad Request (invalid taxon)",
                    "message": f"No taxon with ID {taxon_id}."
                }
            }), 400

    if left_num is None:
        taxon_cond = ""
        params = (rank,) + tuple(accessions)
    else:
        taxon_cond = "AND sp.taxon_left_num BETWEEN %s AND %s"
        params = (rank,) + tuple(accessions) + (left_num, right_num)

    cur.execute(
        f"""
        SELECT t.id, t.name, p.signature_acc, p.cnt 
        FROM (
            SELECT sp.signature_acc, l.parent_id, COUNT(*) cnt
            FROM signature2protein sp
            INNER JOIN taxon t
              ON sp.taxon_left_num = t.left_number
            INNER JOIN lineage l
              ON t.id = l.child_id AND l.parent_rank = %s
            WHERE sp.signature_acc IN ({','.join('%s' for _ in accessions)})
            {taxon_cond}
            GROUP BY sp.signature_acc, l.parent_id
        ) p
        INNER JOIN taxon t
          ON p.parent_id = t.id
        """, params
    )

    results = {}
    for node_id, node_name, acc, cnt in cur:
        try:
            node = results[node_id]
        except KeyError:
            node = results[node_id] = {
                "id": node_id,
                "name": node_name,
                "signatures": {}
            }
        finally:
            node["signatures"][acc] = cnt

    cur.close()
    con.close()

    return jsonify({
        # Sort taxa by the total number of proteins
        "results": sorted(results.values(),
                          key=lambda x: -sum(x["signatures"].values())),
        "taxon": {
            "id": taxon_id,
            "name": taxon_name,
        }
    })
