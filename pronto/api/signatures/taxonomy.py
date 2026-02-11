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
        taxon_cond = "AND sp.taxon_left_num BETWEEN %s AND %s"
        params += (left_num, right_num)


    cur.execute(
        f"""
        SELECT sp.signature_acc, t.id, t2.id, t2.rank, t2.name, count(*)
        FROM signature2protein sp
          INNER JOIN taxon t ON sp.taxon_left_num = t.left_number
          INNER JOIN lineage l ON t.id = l.child_id
          INNER JOIN taxon t2 ON l.parent_id = t2.id
        WHERE sp.signature_acc IN ({','.join('%s' for _ in accessions)})
        {taxon_cond}
        GROUP BY sp.signature_acc, t.id, t2.id, t2.rank, t2.name
        """, params
    )
    lineages = {}

    for acc, tid, anc_id, anc_rank, anc_name, cnt in cur.fetchall():
        if tid in lineages:
            lineage = lineages[tid]

        else:
            lineage = lineages[tid] = [{
                "id": None,
                "name": None,
                "rank": None,
                "matches": {}
            } for rank in RANKS]

        i = RANKS.index(anc_rank)
        node = lineage[i]

        if node["id"] is None:
            node.update( {
                "id": anc_id,
                "name": anc_name,
                "rank": anc_rank
                } )

        if acc in node["matches"]:
            node["matches"][acc] += cnt
        else:
            node["matches"][acc] = cnt


    tree = {
        "children": []
    }

    for tid, lineage in lineages.items():

        target = tree

        for item in lineage:
            node_id = item["id"]

            found = None
            for child in target["children"]:
                if child["id"] == node_id:
                    found = child
                    break

            if found is None:
                found = {
                    "id": node_id,
                    "name": item["name"],
                    "rank": item["rank"],
                    "matches": dict(item["matches"]),
                    "children": []
                }
                target["children"].append(found)
            else:
                for acc, cnt in item["matches"].items():
                    found["matches"][acc] = found["matches"].get(acc, 0) + cnt

            target = found

    tree = tree["children"]
    prune_at_leaf_rank(tree, leaf_rank)

    cur.close()
    con.close()

    return jsonify({
        "results": tree,
        "integrated": get_sig2interpro(accessions)
    })


def prune_at_leaf_rank(nodes, leaf_rank):
    """
    Remove placeholder nodes (id is None), promoting their children.
    Prune all nodes below the given leaf_rank.

    """
    pruned = []

    for node in nodes:
        # skip node if it is below the leaf_rank
        if node["rank"] in RANKS and RANKS.index(node["rank"]) > RANKS.index(leaf_rank):
            continue

        # recursively prune children
        children = node.get("children", [])
        if children:
            children = prune_at_leaf_rank(children, leaf_rank)

        # if node is a placeholder, promote its children
        if node.get("id") is None or node.get("rank") is None:
            pruned.extend(children)
        else:
            # remove empty children for leaf nodes
            if node["rank"] == leaf_rank:
                node.pop("children", None)
            else:
                node["children"] = children
            pruned.append(node)

    return pruned


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
