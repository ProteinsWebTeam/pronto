# -*- coding: utf-8 -*-

from flask import jsonify, request

from pronto import utils
from . import bp, get_sig2interpro

RANKS = (
    "domain",
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)
RANK_SET = set(RANKS)

@bp.route("/<path:accessions>/taxonomy/<string:rank>/")
def get_taxonomy_origins(accessions, rank):
    if rank not in RANK_SET:
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
        },
        "integrated": get_sig2interpro(accessions)
    })


@bp.route("/<path:accessions>/taxonomy_tree/", defaults={"leaf_rank": "species"})
@bp.route("/<path:accessions>/taxonomy_tree/<string:leaf_rank>/")
def get_taxonomy_tree(accessions, leaf_rank):
    if leaf_rank not in RANK_SET:
        return jsonify({
            "error": {
                "title": "Bad Request (invalid rank)",
                "message": f"Available ranks: {', '.join(RANKS)}."
            }
        }), 400

    accessions = utils.split_path(accessions)
    taxon_id = request.args.get("taxon")

    max_rank_idx = RANKS.index(leaf_rank)
    ranks = RANKS[:max_rank_idx + 1]

    con = utils.connect_pg()
    cur = con.cursor()

    # Optional taxon restriction
    left_num = right_num = None
    if taxon_id:
        cur.execute(
            """
            SELECT left_number, right_number
            FROM taxon
            WHERE id = %s
            """, (taxon_id,)
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            con.close()
            return jsonify({
                "error": {
                    "title": "Bad Request (invalid taxon)",
                    "message": f"No taxon with ID {taxon_id}."
                }
            }), 400
        left_num, right_num = row

    taxon_cond = ""
    params = tuple(accessions)
    if left_num is not None:
        taxon_cond = "AND sp.taxon_left_num BETWEEN %s AND %s"
        params += (left_num, right_num)

    # Aggregate matches per rank using lineage.parent_rank
    nodes = {}

    for rank in ranks:
        cur.execute(
            f"""
            SELECT
                t.id,
                t.name,
                %s AS rank,
                sp.signature_acc,
                COUNT(*) AS cnt
            FROM signature2protein sp
            JOIN taxon child
              ON sp.taxon_left_num = child.left_number
            JOIN lineage l
              ON child.id = l.child_id
             AND l.parent_rank = %s
            JOIN taxon t
              ON l.parent_id = t.id
            WHERE sp.signature_acc IN ({','.join('%s' for _ in accessions)})
            {taxon_cond}
            GROUP BY t.id, t.name, sp.signature_acc
            """,
            (rank, rank) + params
        )

        for tid, name, r, acc, cnt in cur.fetchall():
            node = nodes.setdefault(tid, {
                "id": tid,
                "name": name,
                "rank": r,
                "matches": {},
                "children": []
            })
            node["matches"][acc] = node["matches"].get(acc, 0) + cnt

    if not nodes:
        cur.close()
        con.close()
        return jsonify({
            "results": [],
            "integrated": get_sig2interpro(accessions)
        })

    # Add children using rank-adjacent lineage
    for parent_rank, child_rank in zip(ranks, ranks[1:]):
        cur.execute(
            """
            SELECT l.parent_id, l.child_id
            FROM lineage l
            JOIN taxon p ON l.parent_id = p.id
            JOIN taxon c ON l.child_id = c.id
            WHERE p.rank = %s
              AND c.rank = %s
            """,
            (parent_rank, child_rank)
        )

        for pid, cid in cur.fetchall():
            if pid in nodes and cid in nodes:
                nodes[pid]["children"].append(nodes[cid])

    cur.close()
    con.close()

    # Roots are domains
    roots = [
        n for n in nodes.values()
        if n["rank"] == "domain"
    ]

    # Remove empty children from leaf nodes
    for root in roots:
        prune_empty_children(root)

    return jsonify({
        "results": roots,
        "integrated": get_sig2interpro(accessions)
    })

def prune_empty_children(node):
    children = node.get("children")
    if not children:
        node.pop("children", None)
        return

    for child in children:
        prune_empty_children(child)

    # In case children were removed recursively
    if not node["children"]:
        node.pop("children", None)


@bp.route("/<path:accessions>/taxon/<int:taxon_id>/")
def get_taxon_children(accessions, taxon_id):
    accessions = utils.split_path(accessions)
    con = utils.connect_pg()
    cur = con.cursor()
    taxon_name = None
    if taxon_id:
        cur.execute("SELECT name FROM taxon WHERE id = %s", (taxon_id,))
        row = cur.fetchone()
        if row:
            taxon_name, = row
        else:
            cur.close()
            con.close()
            return jsonify({
                "error": {
                    "title": "Bad Request (invalid taxon)",
                    "message": f"No taxon with ID {taxon_id}."
                }
            }), 400

    cur.execute(
        f"""
        SELECT t2.id, MIN(t2.name), MIN(t2.rank), sp.signature_acc, COUNT(*)
        FROM signature2protein sp
        INNER JOIN taxon t
          ON sp.taxon_left_num = t.left_number
        INNER JOIN lineage l
          ON t.id = l.child_id AND l.parent_id = %s
        INNER JOIN taxon t2 
          ON l.parent_id = t2.parent_id 
          AND t.left_number BETWEEN t2.left_number AND t2.right_number
        WHERE sp.signature_acc IN ({','.join('%s' for _ in accessions)})
        GROUP BY sp.signature_acc, t2.id;
        """, tuple([taxon_id] + accessions)
    )
    results = {}
    for node_id, node_name, node_rank, acc, cnt in cur:
        try:
            node = results[node_id]
        except KeyError:
            node = results[node_id] = {
                "id": node_id,
                "name": node_name,
                "rank": node_rank if node_rank in RANKS else None,
                "signatures": {}
            }
        finally:
            node["signatures"][acc] = cnt

    cur.close()
    con.close()

    return jsonify({
        # Sort taxa by name
        "results": sorted(results.values(), key=lambda x: x["name"]),
        "taxon": {
            "id": taxon_id,
            "name": taxon_name,
        }
    })
