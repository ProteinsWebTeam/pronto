# -*- coding: utf-8 -*-

import json

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


@bp.route("/<path:accessions>/lca/")
def get_lowest_common_ancestor(accessions):
    accessions = utils.split_path(accessions)
    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT DISTINCT sp.signature_acc, t.id
        FROM signature2protein sp
        INNER JOIN taxon t
        ON sp.taxon_left_num = t.left_number
        WHERE sp.signature_acc IN ({','.join('%s' for _ in accessions)})
        """, accessions
    )
    signatures = {}
    taxa = []
    for acc, node_id in cur:
        taxa.append(node_id)
        try:
            signatures[acc].append(node_id)
        except KeyError:
            signatures[acc] = [node_id]

    taxa = list(set(taxa))
    lineages = {}
    for i in range(0, len(taxa), 1000):
        params = taxa[i:i+1000]
        cur.execute(
            f"""
            SELECT id, lineage
            FROM interpro.taxon
            WHERE id IN ({','.join('%s' for _ in params)})
            """, params
        )

        for node_id, lineage in cur:
            lineages[node_id] = json.loads(lineage)

    superkingdoms = {
        2: "Bacteria",
        2157: "Archaea",
        2759: "Eukaryota",
        10239: "Viruses"
    }
    lca = {}
    taxa = []
    for acc in signatures:
        ancestors = {}
        for node_id in set(signatures[acc]):
            path1 = lineages[node_id]
            root_id = path1[0]  # superkingdom

            if root_id not in superkingdoms:
                continue

            # Find the lower common ancestor belonging to this superkingdom
            try:
                path2 = ancestors[root_id]
            except KeyError:
                # First occurrence of this superkingdom
                ancestors[root_id] = path1
            else:
                i = 0
                while i < len(path1) and i < len(path2):
                    if path1[i] != path2[i]:
                        break
                    i += 1

                # Path to the lowest common ancestor
                ancestors[root_id] = path1[:i]

        lca[acc] = {}

        for root_id, path in ancestors.items():
            lca_id = path[-1]
            taxa.append(lca_id)
            lca[acc][root_id] = lca_id

    cur.execute(
        f"""
        SELECT id, name, rank
        FROM interpro.taxon
        WHERE id IN ({','.join('%s' for _ in taxa)})
        """, list(taxa)
    )
    taxa = {node_id: (name, rank) for node_id, name, rank in cur}
    cur.close()
    con.close()

    results = []
    for r_id, r_name in sorted(superkingdoms.items(), key=lambda x: x[1]):
        signatures = []

        for acc in accessions:
            try:
                lca_id = lca[acc][r_id]
            except KeyError:
                lca_id = lca_name = lca_rank = None
            else:
                lca_name, lca_rank = taxa[lca_id]

            signatures.append({
                "accession": acc,
                "id": lca_id,
                "name": lca_name,
                "rank": lca_rank
            })

        results.append({
            "name": r_name,
            "signatures": signatures
        })

    return jsonify(results)
