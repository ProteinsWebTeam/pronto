from flask import jsonify, request

from pronto import app, db, xref


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

    params = {}
    query = ""
    if may:
        query += """
            SELECT DISTINCT PROTEIN_AC
            FROM INTERPRO_ANALYSIS_LOAD.METHOD2PROTEIN
            WHERE METHOD_AC IN ({})        
        """.format(','.join([":may" + str(i) for i in range(len(may))]))
        params.update({"may" + str(i): acc for i, acc in enumerate(may)})

        # Filter by description
        if descr_id is not None:
            query += """
                AND DESC_ID = :descr_id
            """
            params["descr_id"] = descr_id

        # Filter by review status
        if dbcode:
            query += """
                AND DBCODE = :dbcode
            """
            params["dbcode"] = dbcode

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
              FROM INTERPRO_ANALYSIS_LOAD.METHOD2PROTEIN
              WHERE METHOD_AC IN ({})
              GROUP BY PROTEIN_AC
            )   
            WHERE CT = :n_must    
        """.format(','.join([":must" + str(i) for i in range(len(must))]))
        params.update({"must" + str(i): acc for i, acc in enumerate(must)})
        params["n_must"] = len(must)

        # Filter by description
        if descr_id is not None:
            query += """
                    AND DESC_ID = :descr_id
                """
            params["descr_id"] = descr_id

        # Filter by review status
        if dbcode:
            query += """
                    AND DBCODE = :dbcode
                """
            params["dbcode"] = dbcode

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
                FROM INTERPRO_ANALYSIS_LOAD.METHOD2PROTEIN
                WHERE METHOD_AC IN ({})        
        """.format(','.join([":mustnot" + str(i)
                             for i in range(len(mustnot))]))
        params.update({
            "mustnot" + str(i): acc for i, acc in enumerate(mustnot)
        })

    # Filter by SwissProt comment
    if topic_id is not None and comment_id is not None:
        query += """
            INTERSECT
            SELECT PROTEIN_AC
            FROM INTERPRO_ANALYSIS_LOAD.PROTEIN_COMMENT
            WHERE TOPIC_ID = :topic_id AND COMMENT_ID = :comment_id
        """
        params.update({
            "topic_id": topic_id,
            "comment_id": comment_id
        })

    # Filter by GO term
    if go_id is not None:
        query += """
            INTERSECT
            SELECT DISTINCT PROTEIN_AC
            FROM INTERPRO_ANALYSIS_LOAD.PROTEIN2GO
            WHERE GO_ID = :go_id
        """
        params["go_id"] = go_id

    # Filter by EC number
    if ec_no is not None:
        query += """
            INTERSECT
            SELECT DISTINCT PROTEIN_AC
            FROM INTERPRO_ANALYSIS_LOAD.ENZYME
            WHERE ECNO = :ec_no
        """
        params["ec_no"] = ec_no

    # Filter by taxonomic rank
    if rank is not None:
        query += """
            INTERSECT
            SELECT DISTINCT PROTEIN_AC
            FROM INTERPRO_ANALYSIS_LOAD.METHOD2PROTEIN
            WHERE LEFT_NUMBER IN (
              SELECT LEFT_NUMBER
              FROM INTERPRO_ANALYSIS_LOAD.LINEAGE
              WHERE RANK = :rank
            )
        """
        params["rank"] = rank

    final_query = """
        SELECT DISTINCT PROTEIN_AC, MD5, LEN
        FROM INTERPRO_ANALYSIS_LOAD.METHOD2PROTEIN
        WHERE PROTEIN_AC IN (
          {}
        )
    """.format(query)

    return final_query, params


@app.route("/api/signatures/<path:accessions_str>/proteins/")
def get_overlapping_proteins(accessions_str):
    accessions = set()
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc and acc:
            accessions.add(acc)

    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 5

    try:
        taxon_id = int(request.args["taxon"])
    except (KeyError, ValueError):
        left_num = right_num = None
    else:
        cur = db.get_oracle().cursor()
        cur.execute(
            """
            SELECT LEFT_NUMBER, RIGHT_NUMBER
            FROM INTERPRO_ANALYSIS_LOAD.ETAXI
            WHERE TAX_ID = :1
            """,
            (taxon_id,)
        )
        row = cur.fetchone()
        cur.close()
        if row:
            left_num, right_num = row
        else:
            return jsonify({}), 400  # TODO: return error

    try:
        descr_id = int(request.args["description"])
    except (KeyError, ValueError):
        descr_id = None

    try:
        topic_id = int(request.args["topic"])
        comment_id = int(request.args["comment"])
    except (KeyError, ValueError):
        topic_id = None
        comment_id = None

    dbcode = request.args.get("db", "S").upper()
    if dbcode not in ("S", "T"):
        dbcode = None

    include = set()
    for acc in request.args.get("include", "").split(","):
        acc = acc.strip()
        if acc:
            include.add(acc)

    exclude = set()
    for acc in request.args.get("exclude", "").split(","):
        acc = acc.strip()
        if acc:
            exclude.add(acc)

    go_id = request.args.get("go")
    ec_no = request.args.get("ec")
    rank = request.args.get("rank")
    search = request.args.get("search", "").strip()
    md5 = request.args.get("md5")  # protein match structure

    signatures = {}
    for acc in (accessions | include):
        signatures[acc] = True if acc in include else None
    signatures.update({acc: False for acc in exclude})

    if all([s is False for s in signatures.values()]):
        return jsonify({}), 400  # TODO: return error

    # Query to select proteins
    query, params = build_method2protein_query(signatures,
                                               left_num=left_num,
                                               right_num=right_num,
                                               dbcode=dbcode,
                                               descr_id=descr_id,
                                               topic_id=topic_id,
                                               comment_id=comment_id,
                                               go_id=go_id,
                                               ec_no=ec_no,
                                               rank=rank,
                                               search=search,
                                               md5=md5)

    if md5:
        # Query to group proteins by match structure
        query = """
            SELECT PROTEIN_AC, MD5, NULL N_PROT
            FROM ({})
        """.format(query)
    else:
        # Query to group proteins by match structure
        query = """
            SELECT PROTEIN_AC, MD5, N_PROT
            FROM (
              SELECT
                PROTEIN_AC,
                MD5,
                COUNT(*) OVER (PARTITION BY MD5) AS N_PROT,
                ROW_NUMBER() OVER (PARTITION BY MD5 ORDER BY LEN) AS RN
              FROM ({})            
            )
            WHERE RN = 1
        """.format(query)

    cur = db.get_oracle().cursor()

    # Get the total number of proteins
    cur.execute(
        """
        SELECT COUNT(*)
        FROM ({})
        """.format(query),
        params
    )
    n_proteins = cur.fetchone()[0]

    # Adding order clause (for pagination)
    if md5:
        query += " ORDER BY PROTEIN_AC"
    else:
        query += " ORDER BY N_PROT DESC, PROTEIN_AC"

    params.update({
        "min_row": max(0, (page - 1) * page_size),
        "max_row": min(n_proteins, page * page_size)
    })

    cur.execute(
        """
        SELECT 
          A.PROTEIN_AC, A.MD5, A.N_PROT, P.DBCODE, P.LEN, E.FULL_NAME, 
          D.TEXT, MA.METHOD_AC, ME.NAME, ME.CANDIDATE, ME.DBCODE,
          EM.ENTRY_AC, MA.POS_FROM, MA.POS_TO, MA.FRAGMENTS
        FROM (
          SELECT PROTEIN_AC, MD5, N_PROT
          FROM (
              SELECT A.*, ROWNUM RN
              FROM ({}) A
              WHERE ROWNUM <= :max_row
            )
            WHERE RN > :min_row      
        ) A
        INNER JOIN INTERPRO_ANALYSIS_LOAD.PROTEIN P
          ON A.PROTEIN_AC = P.PROTEIN_AC
        INNER JOIN INTERPRO_ANALYSIS_LOAD.ETAXI E 
          ON P.TAX_ID = E.TAX_ID
        INNER JOIN INTERPRO_ANALYSIS_LOAD.PROTEIN_DESC PD 
          ON P.PROTEIN_AC = PD.PROTEIN_AC
        INNER JOIN INTERPRO_ANALYSIS_LOAD.DESC_VALUE D 
          ON PD.DESC_ID = D.DESC_ID
        INNER JOIN INTERPRO_ANALYSIS_LOAD.MATCH MA 
          ON A.PROTEIN_AC = MA.PROTEIN_AC
        INNER JOIN INTERPRO_ANALYSIS_LOAD.METHOD ME 
          ON MA.METHOD_AC = ME.METHOD_AC
        LEFT OUTER JOIN INTERPRO_ANALYSIS_LOAD.ENTRY2METHOD EM 
          ON MA.METHOD_AC = EM.METHOD_AC
        """.format(query),
        params
    )

    proteins = {}
    for row in cur:
        protein_acc = row[0]

        if protein_acc in proteins:
            p = proteins[protein_acc]
        else:
            if row[3] == 'S':
                is_reviewed = True
                link = "//sp.isb-sib.ch/uniprot/{}".format(protein_acc)
            else:
                is_reviewed = False
                link = "//www.uniprot.org/uniprot/{}".format(protein_acc)

            p = proteins[protein_acc] = {
                "accession": protein_acc,
                "md5": row[1],
                "num_similar": row[2] - 1 if row[2] is not None else None,
                "reviewed": is_reviewed,
                "link": link,
                "length": row[4],
                "taxon": row[5],
                "name": row[6],
                "signatures": {}
            }

        signature_acc = row[7]
        if signature_acc in p["signatures"]:
            s = p["signatures"][signature_acc]
        else:
            database = xref.find_ref(row[10], signature_acc)
            s = p["signatures"][signature_acc] = {
                "accession": signature_acc,
                "name": row[8],
                "candidate": row[9] == 'Y',
                "link": database.gen_link(),
                "color": database.color,
                "integrated": row[11],
                "matches": [],
                "active": signature_acc in signatures
            }

        fragments = []
        if row[14] is not None:
            for f in row[14].split(','):
                pos_start, pos_end, _ = f.split('-')
                pos_start = int(pos_start)
                pos_end = int(pos_end)

                if pos_start < pos_end:
                    fragments.append({"start": pos_start, "end": pos_end})

        if fragments:
            # Sort discontinuous fragments (in case they are not sorted in DB)
            fragments.sort(key=lambda x: (x["start"], x["end"]))
        else:
            fragments.append({"start": row[12], "end": row[13]})

        s["matches"].append(fragments)

    cur.close()

    # Sort proteins by number of similar proteins (desc) then accession (asc)
    _proteins = []
    for p in sorted(proteins.values(), key=_prot_key):

        # Sort signatures by integrated and accession
        signatures = []
        for s in sorted(p["signatures"].values(), key=_sign_key):
            # Sort matches by the position of the leftmost fragment
            s["matches"].sort(key=lambda x: (x[0]["start"], x[0]["end"]))

            signatures.append(s)

        p["signatures"] = signatures
        _proteins.append(p)

    return jsonify({
        "count": n_proteins,
        "proteins": _proteins,
        "source_database": dbcode,
        "page_info": {
            "page": page,
            "page_size": page_size
        },
    })


def _prot_key(p):
    if p["num_similar"] is None:
        return p["accession"]
    else:
        return -p["num_similar"], p["accession"]


def _sign_key(s):
    return 0 if s["integrated"] else 1, s["accession"]