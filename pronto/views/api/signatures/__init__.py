from flask import jsonify, request

from pronto import app, db
from . import proteins, taxonomy


def build_method2protein_query(signatures: dict, **kwargs):
    # Taxon left/right number (for lineage)
    left_num = kwargs.get("left_num")
    right_num = kwargs.get("right_num")

    dbcode = kwargs.get("dbcode")
    descr_id = kwargs.get("descr_id")
    topic_id = kwargs.get("topic_id")
    comment_id = kwargs.get("comment_id")
    go_id = kwargs.get("go_id")
    ec_no = kwargs.get("ec_no")
    rank = kwargs.get("rank")
    search = kwargs.get("search")
    md5 = kwargs.get("md5")

    # Proteins may be matched by these signatures
    may = []
    # Proteins must be matched by these signatures
    must = []
    # Proteins must not be matched by these signatures
    mustnot = []

    for acc, status in signatures.items():
        if status is None:
            may.append(acc)
        elif status:
            must.append(acc)
        else:
            mustnot.append(acc)

    if dbcode == 'S':
        name = "METHOD2PROTEIN PARTITION (M2P_SWISSP)"
    elif dbcode == 'T':
        name = "METHOD2PROTEIN PARTITION (M2P_TREMBL)"
    else:
        name = "METHOD2PROTEIN"

    params = {}
    query = ""
    if may:
        query += """
            SELECT DISTINCT PROTEIN_AC
            FROM {}.{}
            WHERE METHOD_AC IN ({})        
        """.format(
            app.config["DB_SCHEMA"],
            name,
            ','.join([":may" + str(i) for i in range(len(may))])
        )
        params.update({"may" + str(i): acc for i, acc in enumerate(may)})

        # Filter by description
        if descr_id is not None:
            query += """
                AND DESC_ID = :descr_id
            """
            params["descr_id"] = descr_id

        # Search by protein accession
        if search:
            query += """
                AND PROTEIN_AC LIKE :search_like
            """
            params["search_like"] = search + "%"

        # Filter by taxonomic origin
        if left_num is not None and right_num is not None:
            query += """
                AND LEFT_NUMBER BETWEEN :left_num AND :right_num
            """
            params.update({
                "left_num": left_num,
                "right_num": right_num
            })

        # Filter by MD5 (protein match structure)
        if md5 is not None:
            query += """
                AND MD5 = :md5
            """
            params["md5"] = md5

    if must:
        if query:
            query += """
                INTERSECT
            """

        query += """
            SELECT PROTEIN_AC
            FROM (
              SELECT PROTEIN_AC, COUNT(METHOD_AC) CT
              FROM {}.{}
              WHERE METHOD_AC IN ({})
              GROUP BY PROTEIN_AC
            )   
            WHERE CT = :n_must    
        """.format(
            app.config["DB_SCHEMA"],
            name,
            ','.join([":must" + str(i) for i in range(len(must))])
        )
        params.update({"must" + str(i): acc for i, acc in enumerate(must)})
        params["n_must"] = len(must)

        # Filter by description
        if descr_id is not None:
            query += """
                    AND DESC_ID = :descr_id
                """
            params["descr_id"] = descr_id

        # Search by protein accession
        if search:
            query += """
                    AND PROTEIN_AC LIKE :search_like
                """
            params["search_like"] = search + "%"

        # Filter by taxonomic origin
        if left_num is not None and right_num is not None:
            query += """
                AND LEFT_NUMBER BETWEEN :left_num AND :right_num
            """
            params.update({
                "left_num": left_num,
                "right_num": right_num
            })

        # Filter by MD5 (protein match structure)
        if md5 is not None:
            query += """
                AND MD5 = :md5
            """
            params["md5"] = md5

    if mustnot:
        if query:
            query += """
                MINUS
            """

        query += """
                SELECT DISTINCT PROTEIN_AC
                FROM {}.METHOD2PROTEIN
                WHERE METHOD_AC IN ({})        
        """.format(
            app.config["DB_SCHEMA"],
            ','.join([":mustnot" + str(i) for i in range(len(mustnot))])
        )
        params.update({
            "mustnot" + str(i): acc for i, acc in enumerate(mustnot)
        })

    # Filter by SwissProt comment
    if topic_id is not None and comment_id is not None:
        query += """
            INTERSECT
            SELECT PROTEIN_AC
            FROM {}.PROTEIN_COMMENT
            WHERE TOPIC_ID = :topic_id AND COMMENT_ID = :comment_id
        """.format(app.config["DB_SCHEMA"])

        params.update({
            "topic_id": topic_id,
            "comment_id": comment_id
        })

    # Filter by GO term
    if go_id is not None:
        query += """
            INTERSECT
            SELECT DISTINCT PROTEIN_AC
            FROM {}.PROTEIN2GO
            WHERE GO_ID = :go_id
        """.format(app.config["DB_SCHEMA"])

        params["go_id"] = go_id

    # Filter by EC number
    if ec_no is not None:
        query += """
            INTERSECT
            SELECT DISTINCT PROTEIN_AC
            FROM {}.ENZYME
            WHERE ECNO = :ec_no
        """.format(app.config["DB_SCHEMA"])

        params["ec_no"] = ec_no

    # Filter by taxonomic rank
    if rank is not None:
        query += """
            INTERSECT
            SELECT DISTINCT PROTEIN_AC
            FROM {0}.METHOD2PROTEIN
            WHERE LEFT_NUMBER IN (
              SELECT LEFT_NUMBER
              FROM {0}.LINEAGE
              WHERE RANK = :rank
            )
        """.format(app.config["DB_SCHEMA"])

        params["rank"] = rank

    final_query = """
        SELECT DISTINCT PROTEIN_AC, MD5, LEN
        FROM {0}.METHOD2PROTEIN
        WHERE PROTEIN_AC IN (
          {1}
        )
    """.format(app.config["DB_SCHEMA"], query)

    return final_query, params


@app.route("/api/signatures/<path:accessions_str>/descriptions/")
def get_uniprot_descriptions(accessions_str):
    accessions = []
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc and acc not in accessions:
            accessions.append(acc)

    dbcode = request.args.get("db", "S").upper()
    if dbcode == "S":
        column = "M.REVIEWED_COUNT"
        condition = "AND M.REVIEWED_COUNT > 0"
    elif dbcode == "T":
        column = "M.UNREVIEWED_COUNT"
        condition = "AND M.UNREVIEWED_COUNT > 0"
    else:
        column = "M.REVIEWED_COUNT + M.UNREVIEWED_COUNT"
        condition = ""

    query = """
        SELECT M.DESC_ID, D.TEXT, M.METHOD_AC, {0}
        FROM {1}.METHOD_DESC M
        INNER JOIN {1}.DESC_VALUE D
        ON M.DESC_ID = D.DESC_ID
        WHERE M.METHOD_AC IN ({2})
        {3}
    """.format(
        column,
        app.config["DB_SCHEMA"],
        ','.join([":" + str(i) for i in range(len(accessions))]),
        condition
    )

    descriptions = {}
    cur = db.get_oracle().cursor()
    cur.execute(query, accessions)
    for _id, text, accession, n_proteins in cur:
        if _id in descriptions:
            descriptions[_id]["signatures"][accession] = n_proteins
        else:
            descriptions[_id] = {
                "id": _id,
                "value": text,
                "signatures": {accession: n_proteins}
            }

    cur.close()
    return jsonify({
        "descriptions": sorted(descriptions.values(),
                               key=lambda d: -sum(d["signatures"].values())),
        "source_database": dbcode
    })


@app.route("/api/signatures/<path:accessions_str>/similarity/")
def get_similarity_comments(accessions_str):
    accessions = []
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc and acc not in accessions:
            accessions.append(acc)

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT M.COMMENT_ID, C.TEXT, M.METHOD_AC, M.N_PROT
        FROM (
          SELECT 
            PC.COMMENT_ID, 
            M2P.METHOD_AC, 
            COUNT(DISTINCT M2P.PROTEIN_AC) N_PROT
          FROM {0}.METHOD2PROTEIN M2P
            INNER JOIN {0}.PROTEIN_COMMENT PC 
            ON M2P.PROTEIN_AC = PC.PROTEIN_AC
          WHERE M2P.METHOD_AC IN ({1})
          AND PC.TOPIC_ID = 34
          GROUP BY PC.COMMENT_ID, M2P.METHOD_AC
        ) M
        INNER JOIN {0}.COMMENT_VALUE C 
        ON M.COMMENT_ID = C.COMMENT_ID AND C.TOPIC_ID = 34
        """.format(
            app.config["DB_SCHEMA"],
            ','.join([':' + str(i) for i in range(len(accessions))])
        ),
        accessions
    )

    comments = {}
    for _id, text, accession, n_proteins in cur:
        if _id in comments:
            comments[_id]["signatures"][accession] = n_proteins
        else:
            comments[_id] = {
                "id": _id,
                "value": text,
                "signatures": {accession: n_proteins}
            }

    cur.close()
    return jsonify(sorted(comments.values(),
                          key=lambda c: -sum(c["signatures"].values())))


@app.route("/api/signatures/<path:accessions_str>/go/")
def get_go_terms(accessions_str):
    accessions = []
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc and acc not in accessions:
            accessions.append(acc)

    aspects = request.args.get("aspects", "C,P,F").upper().split(',')
    aspects = list(set(aspects) & {'C', 'P', 'F'})

    query = """
        SELECT 
          T.GO_ID, T.NAME, T.CATEGORY, 
          MP.METHOD_AC, MP.PROTEIN_AC, 
          PG.REF_DB_CODE, PG.REF_DB_ID
        FROM {0}.METHOD2PROTEIN MP
        INNER JOIN {0}.PROTEIN2GO PG 
          ON MP.PROTEIN_AC = PG.PROTEIN_AC
        INNER JOIN {0}.TERM T
          ON PG.GO_ID = T.GO_ID
        WHERE MP.METHOD_AC IN ({1})
    """.format(
        app.config["DB_SCHEMA"],
        ','.join([":acc" + str(i) for i in range(len(accessions))])
    )

    params = {"acc" + str(i): acc for i, acc in enumerate(accessions)}
    if 0 < len(aspects) < 3:
        query += """
            AND T.CATEGORY IN ({})
        """.format(','.join([":aspct" + str(i) for i in range(len(aspects))]))

        for i, aspect in enumerate(aspects):
            params["aspct" + str(i)] = aspect

    cur = db.get_oracle().cursor()
    cur.execute(query, params)

    terms = {}
    for go_id, name, cat, s_acc, p_acc, ref_db, ref_id in cur:
        if go_id in terms:
            t = terms[go_id]
        else:
            t = terms[go_id] = {
                "id": go_id,
                "name": name,
                "aspect": cat,
                "signatures": {}
            }

        if s_acc in t["signatures"]:
            s = t["signatures"][s_acc]
        else:
            s = t["signatures"][s_acc] = {
                "proteins": set(),
                "references": set()
            }
        s["proteins"].add(p_acc)
        if ref_db == "PMID":
            s["references"].add(ref_id)

    cur.close()

    for t in terms.values():
        for s in t["signatures"].values():
            s["num_proteins"] = len(s.pop("proteins"))
            s["num_references"] = len(s.pop("references"))

    return jsonify({
        "terms": sorted(terms.values(), key=_term_key),
        "aspects": aspects
    })


def _term_key(t):
    n = sum([s["num_proteins"] for s in t["signatures"].values()])
    return -n, t["id"]


@app.route("/api/signatures/<path:accessions_str>/matrices/")
def get_signature_matrices(accessions_str):
    accessions = []
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc and acc not in accessions:
            accessions.append(acc)

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT 
          MM.METHOD_AC, MM.N_PROT, 
          MO.METHOD_AC2, MO.N_PROT, MO.AVG_OVER, MO.N_PROT_OVER
        FROM {0}.METHOD_MATCH MM
        INNER JOIN (
          SELECT METHOD_AC1, METHOD_AC2, N_PROT, AVG_OVER, N_PROT_OVER
          FROM {0}.METHOD_OVERLAP MO
          WHERE METHOD_AC1 IN ({1})
          AND METHOD_AC2 IN ({1})
        ) MO ON MM.METHOD_AC = MO.METHOD_AC1
        WHERE METHOD_AC IN ({1})
        """.format(
            app.config["DB_SCHEMA"],
            ','.join([":acc" + str(i) for i in range(len(accessions))])
        ),
        {"acc" + str(i): acc for i, acc in enumerate(accessions)}
    )

    signatures = {}
    for acc_1, n_prot, acc_2, n_coloc, avg_over, n_overlap in cur:
        if acc_1 in signatures:
            s = signatures[acc_1]
        else:
            s = signatures[acc_1] = {
                'num_proteins': n_prot,
                'signatures': {}
            }

        s['signatures'][acc_2] = {
            'num_coloc': n_coloc,
            'num_overlap': n_overlap,
            'avg_overlap': avg_over
        }

    cur.close()

    return jsonify(signatures)


@app.route("/api/signatures/<path:accessions_str>/enzyme/")
def get_enzyme_entries(accessions_str):
    accessions = []
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc and acc not in accessions:
            accessions.append(acc)

    dbcode = request.args.get("db", "S").upper()
    if dbcode == 'S':
        name = "METHOD2PROTEIN PARTITION (M2P_SWISSP)"
    elif dbcode == 'T':
        name = "METHOD2PROTEIN PARTITION (M2P_TREMBL)"
    else:
        name = "METHOD2PROTEIN"
        dbcode = None

    query = """
        SELECT
          EZ.ECNO,
          MP.METHOD_AC,
          COUNT(DISTINCT MP.PROTEIN_AC)
        FROM {0}.{1} MP
          INNER JOIN {0}.ENZYME EZ 
          ON MP.PROTEIN_AC = EZ.PROTEIN_AC
        WHERE MP.METHOD_AC IN ({2})    
    """.format(
        app.config["DB_SCHEMA"],
        name,
        ','.join([":acc" + str(i) for i in range(len(accessions))])
    )
    params = {":acc" + str(i): acc for i, acc in enumerate(accessions)}
    query += " GROUP BY EZ.ECNO, MP.METHOD_AC"

    cur = db.get_oracle().cursor()
    cur.execute(query, params)

    enzymes = {}
    for ecno, acc, num_proteins in cur:
        if ecno in enzymes:
            enzymes[ecno]["signatures"][acc] = num_proteins
        else:
            enzymes[ecno] = {
                "id": ecno,
                "signatures": {acc: num_proteins}
            }

    cur.close()

    return jsonify({
        "entries": sorted(enzymes.values(),
                               key=lambda d: -sum(d["signatures"].values())),
        "source_database": dbcode
    })
