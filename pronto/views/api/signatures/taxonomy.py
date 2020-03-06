from flask import jsonify, request

from pronto import app, db


def _get_proteins(cur, accession, rank, taxon_id):
    cur.execute(
        """
        SELECT MP.PROTEIN_AC
          FROM (
            SELECT PROTEIN_AC, TAX_ID
            FROM {0}.METHOD2PROTEIN
            WHERE METHOD_AC = :1
          ) MP
        INNER JOIN {0}.LINEAGE L 
          ON MP.TAX_ID = L.TAX_ID 
          AND L.RANK = :2
          AND L.RANK_TAX_ID = :3
        """.format(app.config["DB_SCHEMA"]),
        (accession, rank, taxon_id)
    )

    return {row[0] for row in cur}


@app.route("/api/signatures/<path:accessions_str>/taxonomy/<rank>/<int:taxon_id>/")
def get_taxa_common_proteins(accessions_str, rank, taxon_id):
    common = None
    cur = db.get_oracle().cursor()
    for acc in accessions_str.split("/"):
        if common is None:
            common = _get_proteins(cur, acc, rank, taxon_id)
        else:
            common &= _get_proteins(cur, acc, rank, taxon_id)

    proteins = []
    if common:
        cur.execute(
            """
            SELECT 
              P.PROTEIN_AC, P.DBCODE, P.LEN, P.NAME, 
              DV.TEXT, E.TAX_ID, E.FULL_NAME
            FROM {0}.PROTEIN P
            INNER JOIN {0}.PROTEIN_DESC PD 
              ON P.PROTEIN_AC = PD.PROTEIN_AC
            INNER JOIN {0}.DESC_VALUE DV
              ON PD.DESC_ID = DV.DESC_ID
            INNER JOIN {0}.ETAXI E
              ON P.TAX_ID = E.TAX_ID
            WHERE P.PROTEIN_AC IN ({1})
            ORDER BY P.PROTEIN_AC
            """.format(
                app.config["DB_SCHEMA"],
                ','.join([":" + str(i+1) for i in range(len(common))])
            ),
            tuple(common)
        )

        for row in cur:
            protein_acc = row[0]
            if row[1] == 'S':
                is_reviewed = True
                link = "//sp.isb-sib.ch/uniprot/{}".format(protein_acc)
            else:
                is_reviewed = False
                link = "//www.uniprot.org/uniprot/{}".format(protein_acc)

            proteins.append({
                "accession": protein_acc,
                "reviewed": is_reviewed,
                "link": link,
                "length": row[2],
                "identifier": row[3],
                "name": row[4],
                "taxon": {
                    "id": row[5],
                    "name": row[6]
                }
            })

    cur.close()
    return jsonify({
        "count": len(proteins),
        "proteins": proteins,
        "page_info": {
            "page": 1,
            "page_size": len(proteins)
        }
    })

    return

    params = {
        "rank": rank,
        "taxid": taxon_id
    }
    accessions = []
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc and acc not in accessions:
            params["acc" + str(len(accessions))] = acc
            accessions.append(acc)

    params["cnt"] = len(accessions)

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT 
          P.PROTEIN_AC, P.DBCODE, P.LEN, P.NAME, 
          DV.TEXT, E.TAX_ID, E.FULL_NAME
        FROM {0}.PROTEIN P
        INNER JOIN {0}.PROTEIN_DESC PD 
          ON P.PROTEIN_AC = PD.PROTEIN_AC
        INNER JOIN {0}.DESC_VALUE DV
          ON PD.DESC_ID = DV.DESC_ID
        INNER JOIN {0}.ETAXI E
          ON P.TAX_ID = E.TAX_ID
        WHERE P.PROTEIN_AC IN (
            SELECT PROTEIN_AC
            FROM (
              SELECT MP.PROTEIN_AC, COUNT(*) CNT
              FROM {0}.METHOD2PROTEIN MP
              LEFT OUTER JOIN {0}.LINEAGE L 
                ON MP.LEFT_NUMBER = L.LEFT_NUMBER
              WHERE MP.METHOD_AC IN ({1})
              AND L.RANK = :rank
              AND L.TAX_ID = :taxid
              GROUP BY MP.PROTEIN_AC
            ) WHERE CNT = :cnt        
        )
        ORDER BY P.PROTEIN_AC
        """.format(
            app.config["DB_SCHEMA"],
            ','.join([":acc" + str(i) for i in range(len(accessions))])
        ),
        params
    )

    proteins = []
    for row in cur:
        protein_acc = row[0]
        if row[1] == 'S':
            is_reviewed = True
            link = "//sp.isb-sib.ch/uniprot/{}".format(protein_acc)
        else:
            is_reviewed = False
            link = "//www.uniprot.org/uniprot/{}".format(protein_acc)

        proteins.append({
            "accession": protein_acc,
            "reviewed": is_reviewed,
            "link": link,
            "length": row[2],
            "identifier": row[3],
            "name": row[4],
            "taxon": {
                "id": row[5],
                "name": row[6]
            }
        })

    cur.close()
    return jsonify({
        "count": len(proteins),
        "proteins": proteins,
        "page_info": {
            "page": 1,
            "page_size": len(proteins)
        }
    })


@app.route("/api/signatures/<path:accessions_str>/taxonomy/")
def get_taxonomic_origins(accessions_str):
    accessions = []
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc and acc not in accessions:
            accessions.append(acc)

    taxon_name = None
    try:
        taxon_id = int(request.args["taxon"])
    except (KeyError, ValueError):
        taxon_id = None
    else:
        cur = db.get_oracle().cursor()
        cur.execute(
            """
            SELECT FULL_NAME
            FROM {}.ETAXI
            WHERE TAX_ID = :1
            """.format(app.config["DB_SCHEMA"]),
            (taxon_id,)
        )
        row = cur.fetchone()
        cur.close()
        if row:
            taxon_name = row[0]
        else:
            return jsonify({}), 400  # TODO: return error

    ranks = (
        "superkingdom",
        "kingdom",
        "phylum",
        "class",
        "order",
        "family",
        "genus",
        "species"
    )
    i = 0
    try:
        i = ranks.index(request.args.get("rank"))
    except ValueError:
        pass
    finally:
        rank = ranks[i]

    query = """
            SELECT E.TAX_ID, E.FULL_NAME, MT.METHOD_AC, MT.PROTEIN_COUNT
            FROM {0}.METHOD_TAXA MT
            LEFT OUTER JOIN {0}.ETAXI E 
              ON MT.TAX_ID = E.TAX_ID
        """.format(app.config["DB_SCHEMA"])

    params = {"rank": rank}
    for i, acc in enumerate(accessions):
        params["acc" + str(i)] = acc

    if taxon_id is not None:
        query += """
            INNER JOIN {}.LINEAGE L
            ON E.TAX_ID = L.TAX_ID 
            AND L.RANK_TAX_ID = :taxid
        """.format(app.config["DB_SCHEMA"])
        params["taxid"] = taxon_id

    query += """
        WHERE MT.METHOD_AC IN ({}) 
        AND MT.RANK = :rank
    """.format(
        ','.join([":acc" + str(i) for i in range(len(accessions))]),
    )

    cur = db.get_oracle().cursor()
    cur.execute(query, params)
    taxa = {}
    for tax_id, tax_name, acc, n_proteins in cur:
        if tax_id in taxa:
            taxa[tax_id]["signatures"][acc] = n_proteins
        else:
            taxa[tax_id] = {
                "id": tax_id,
                "name": tax_name if tax_id else "Others",
                "signatures": {acc: n_proteins}
            }

    cur.close()

    return jsonify({
        "taxa": sorted(taxa.values(), key=_taxa_key),
        "rank": rank,
        "taxon": {
            "id": taxon_id,
            "name": taxon_name
        }
    })


def _taxa_key(t):
    return 1 if t["id"] is None else 0, -sum(t["signatures"].values())
