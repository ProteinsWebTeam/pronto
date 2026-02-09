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


@bp.route("/<path:accessions>/taxonomy/<string:rank>/")
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
        },
        "integrated": get_sig2interpro(accessions)
    })


@bp.route("/<path:accessions>/taxonomy/")
def get_taxonomy_tree(accessions):
    leaf_rank = request.args.get("leaf", "species")

    if leaf_rank not in RANKS:
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
        taxon_cond = "AND s2p.taxon_left_num BETWEEN %s AND %s"
        params += (left_num, right_num)

    rank_list = ",".join("%s" for _ in ranks)
    params = params + tuple(ranks)

    cur.execute(
        f"""
        WITH protein_taxon_counts AS (
            -- count proteins per leaf taxon per signature
            SELECT
                s2p.signature_acc,
                t.id AS taxon_id,
                COUNT(DISTINCT s2p.protein_acc) AS protein_count
            FROM interpro.signature2protein s2p
            JOIN interpro.taxon t
              ON s2p.taxon_left_num = t.left_number
            WHERE s2p.signature_acc IN ({','.join('%s' for _ in accessions)})
            {taxon_cond}
            GROUP BY s2p.signature_acc, t.id
        ),
        lineage_expansion AS (
            -- propagate counts to all ancestors
            SELECT
                ptc.signature_acc,
                ptc.taxon_id AS node_id,
                ptc.protein_count
            FROM protein_taxon_counts ptc

            UNION ALL

            SELECT
                ptc.signature_acc,
                l.parent_id AS node_id,
                ptc.protein_count
            FROM protein_taxon_counts ptc
            JOIN interpro.lineage l
              ON l.child_id = ptc.taxon_id
        ),
        aggregated AS (
            SELECT
                le.signature_acc,
                t.id,
                t.name,
                t.rank,
                t.left_number,
                t.right_number,
                SUM(le.protein_count) AS protein_count
            FROM lineage_expansion le
            JOIN interpro.taxon t
              ON t.id = le.node_id
            WHERE t.rank IN ({rank_list})
            GROUP BY
                le.signature_acc,
                t.id,
                t.name,
                t.rank,
                t.left_number,
                t.right_number
        )
        SELECT
            a.signature_acc,
            a.id AS taxon_id,
            a.name,
            a.rank,
            (
                SELECT p.id
                FROM interpro.taxon p
                WHERE
                    p.rank IN ({rank_list})
                    AND p.left_number < a.left_number
                    AND p.right_number > a.right_number
                ORDER BY p.left_number DESC
                LIMIT 1
            ) AS parent_id,
            a.protein_count
        FROM aggregated a
        ORDER BY a.left_number
        """,
        params + tuple(ranks)
    )

    nodes = {}
    parents = {}

    for acc, tid, name, rank, parent_id, cnt in cur.fetchall():
        node = nodes.setdefault(
            tid,
            {
                "id": tid,
                "name": name,
                "rank": rank,
                "matches": {},
                "children": []
            }
        )
        node["matches"][acc] = node["matches"].get(acc, 0) + cnt
        parents[tid] = parent_id

    # Attach children
    for tid, node in nodes.items():
        parent_id = parents.get(tid)
        if parent_id is not None and parent_id in nodes:
            nodes[parent_id]["children"].append(node)

    # Retrieve roots
    roots = [
        node
        for tid, node in nodes.items()
        if parents.get(tid) is None or parents.get(tid) not in nodes
    ]

    # Prune tree at leaf rank
    for root in roots:
        prune_at_leaf_rank(root, leaf_rank)

    cur.close()
    con.close()

    return jsonify({
        "results": roots,
        "integrated": get_sig2interpro(accessions)
    })


def prune_at_leaf_rank(node, leaf_rank):
    """
    Walk top-down.
    When a node reaches leaf_rank, cut all descendants.
    Also remove empty children.
    """
    if node["rank"] == leaf_rank:
        node.pop("children", None)
        return

    children = node.get("children")
    if not children:
        node.pop("children", None)
        return

    kept = []
    for child in children:
        prune_at_leaf_rank(child, leaf_rank)
        kept.append(child)

    if kept:
        node["children"] = kept
    else:
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
