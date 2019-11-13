from flask import jsonify, request

from pronto import app, db, xref
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


@app.route("/api/signatures/")
def get_best_candidates():
    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

    base_cond = "WHERE "
    params = {}
    try:
        dbcode = request.args["database"].strip()
    except KeyError:
        pass
    else:
        base_cond += "MS.DBCODE1 = :dbcode AND "
        params["dbcode"] = dbcode

    search_query = request.args.get("search", "").strip()
    if search_query:
        base_cond += "UPPER(MS.METHOD_AC1) LIKE :q AND "
        params["q"] = search_query.upper() + '%'

    base_cond += "MS.PROT_PRED = 'S'"

    residue_evidence = request.args.get("resevi") is not None
    if residue_evidence:
        resi_cond = "AND MS.RESI_PRED = 'S'"
    else:
        resi_cond = ""

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT MS.METHOD_AC1, MAX(MS.PROT_SIM), MAX(MS.PROT_OVER_COUNT)
        FROM {}.METHOD_SIMILARITY MS
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM1 
          ON MS.METHOD_AC1 = EM1.METHOD_AC
        INNER JOIN INTERPRO.ENTRY2METHOD EM2 
          ON MS.METHOD_AC2 = EM2.METHOD_AC
        INNER JOIN INTERPRO.METHOD M1 
          ON MS.METHOD_AC1 = M1.METHOD_AC
        INNER JOIN INTERPRO.METHOD M2 
          ON MS.METHOD_AC2 = M2.METHOD_AC
        {} {}
        AND EM1.ENTRY_AC IS NULL
        AND (
          (M1.SIG_TYPE = 'H' AND M2.SIG_TYPE = 'H')
          OR (M1.SIG_TYPE != 'H' AND M2.SIG_TYPE != 'H')
        )
        GROUP BY MS.METHOD_AC1
        ORDER BY 2 DESC, 3 DESC
        """.format(app.config["DB_SCHEMA"], base_cond, resi_cond),
        params
    )

    accessions = [row[0] for row in cur]
    count = len(accessions)
    signatures = {}
    if count:
        accessions = accessions[(page-1)*page_size:page*page_size]
        cur.execute(
            """
            SELECT 
              MS.METHOD_AC1, MS.DBCODE1, MS.PROT_COUNT1,
              MS.METHOD_AC2, MS.PROT_COUNT2, E.ENTRY_AC, E.ENTRY_TYPE, E.NAME, 
              MS.COLL_COUNT, MS.PROT_OVER_COUNT, MS.RESI_PRED, 
              (
                SELECT COUNT(*) 
                FROM INTERPRO.METHOD_COMMENT 
                WHERE METHOD_AC=MS.METHOD_AC1
              ) NUM_COMMENTS
            FROM {}.METHOD_SIMILARITY MS
            INNER JOIN INTERPRO.ENTRY2METHOD EM2 
              ON MS.METHOD_AC2 = EM2.METHOD_AC
            INNER JOIN INTERPRO.ENTRY E
              ON EM2.ENTRY_AC = E.ENTRY_AC
            INNER JOIN INTERPRO.METHOD M1 
              ON MS.METHOD_AC1 = M1.METHOD_AC
            INNER JOIN INTERPRO.METHOD M2 
              ON MS.METHOD_AC2 = M2.METHOD_AC
            WHERE MS.METHOD_AC1 IN ({}) 
            AND MS.PROT_PRED = 'S'
            {}
            AND (
              (M1.SIG_TYPE = 'H' AND M2.SIG_TYPE = 'H')
              OR (M1.SIG_TYPE != 'H' AND M2.SIG_TYPE != 'H')
            )
            ORDER BY MS.PROT_SIM DESC, MS.PROT_OVER_COUNT DESC
            """.format(
                app.config["DB_SCHEMA"],
                ','.join([':'+str(i+1) for i in range(len(accessions))]),
                resi_cond),
            accessions
        )

        accessions = []
        for row in cur:
            acc1 = row[0]

            try:
                s = signatures[acc1]
            except KeyError:
                accessions.append(acc1)
                database = xref.find_ref(dbcode=row[1], ac=acc1)
                s = signatures[acc1] = {
                    "accession": acc1,
                    "link": database.gen_link(),
                    "color": database.color,
                    "database": database.name,
                    "proteins": row[2],
                    "predictions": [],
                    "comments": row[11]
                }

            s["predictions"].append({
                "accession": row[3],
                "proteins": row[4],
                "entry": {
                    "accession": row[5],
                    "type": row[6],
                    "name": row[7]
                },
                "collocations": row[8],
                "overlaps": row[9],
                "residues": row[10] == 'S'
            })

    cur.close()
    return jsonify({
        "count": count,
        "results": [signatures[acc] for acc in accessions],
        "page_info": {
            "page": page,
            "page_size": page_size
        }
    })


@app.route("/api/signatures/integrations/")
def get_recent_integrations():
    cur = db.get_oracle().cursor()
    cur.execute("SELECT FILE_DATE FROM INTERPRO.DB_VERSION WHERE DBCODE = 'I'")
    date, = cur.fetchone()
    cur.execute(
        """
        SELECT METHOD_AC
        FROM INTERPRO.ENTRY2METHOD_AUDIT
        WHERE TIMESTAMP >= (
          SELECT FILE_DATE FROM INTERPRO.DB_VERSION WHERE DBCODE = 'I'
        )
        GROUP BY METHOD_AC
        HAVING SUM(CASE WHEN ACTION='I' THEN 1 
                        WHEN ACTION='D' THEN -1 
                        ELSE 0 END) > 0
        """
    )
    signatures = [row[0] for row in cur]
    cur.close()
    return jsonify({
        "date": date.strftime("%d %B %Y"),
        "results": signatures,
    })


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
      SELECT METHOD_AC1, PROT_COUNT1, METHOD_AC2, PROT_COUNT2, 
             COLL_COUNT, PROT_OVER_COUNT
      FROM {0}.METHOD_OVERLAP
      WHERE METHOD_AC1 IN ({1})
      AND METHOD_AC2 IN ({1})
        """.format(
            app.config["DB_SCHEMA"],
            ','.join([":acc" + str(i) for i in range(len(accessions))])
        ),
        {"acc" + str(i): acc for i, acc in enumerate(accessions)}
    )

    signatures = {}
    for acc_1, n_prot_1, acc_2, n_prot_2, n_coloc, n_overlap in cur:
        if acc_1 in signatures:
            s = signatures[acc_1]
        else:
            s = signatures[acc_1] = {
                'num_proteins': n_prot_1,
                'signatures': {}
            }

        s['signatures'][acc_2] = {
            'num_coloc': n_coloc,
            'num_overlap': n_overlap
        }

        if acc_2 in signatures:
            s = signatures[acc_2]
        else:
            s = signatures[acc_2] = {
                'num_proteins': n_prot_2,
                'signatures': {}
            }

        s['signatures'][acc_1] = {
            'num_coloc': n_coloc,
            'num_overlap': n_overlap
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
