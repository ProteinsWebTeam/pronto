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
            FROM {}.METHOD2PROTEIN
            WHERE METHOD_AC IN ({})        
        """.format(
            app.config["DB_SCHEMA"],
            ','.join([":may" + str(i) for i in range(len(may))])
        )
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
              FROM {}.METHOD2PROTEIN
              WHERE METHOD_AC IN ({})
              GROUP BY PROTEIN_AC
            )   
            WHERE CT = :n_must    
        """.format(
            app.config["DB_SCHEMA"],
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


@app.route("/api/signatures/<path:accessions_str>/proteins/")
def get_overlapping_proteins(accessions_str):
    accessions = set()
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc:
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
            FROM {}.ETAXI
            WHERE TAX_ID = :1
            """.format(app.config["DB_SCHEMA"]),
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

    if md5:
        # Do not group by match structure
        query = """
            SELECT PROTEIN_AC, MD5, NULL N_PROT
            FROM ({})
            ORDER BY PROTEIN_AC
        """.format(query)

        n_groups = n_proteins
    else:
        # Group proteins by match structure
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

        # Then count the number of groups
        cur.execute(
            """
            SELECT COUNT(*)
            FROM ({})
            """.format(query),
            params
        )
        n_groups = cur.fetchone()[0]

        # Adding order clause (for pagination)
        query += " ORDER BY N_PROT DESC, PROTEIN_AC"

    params.update({
        "min_row": max(0, (page - 1) * page_size),
        "max_row": min(n_groups, page * page_size)
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
              FROM ({0}) A
              WHERE ROWNUM <= :max_row
            )
            WHERE RN > :min_row      
        ) A
        INNER JOIN {1}.PROTEIN P
          ON A.PROTEIN_AC = P.PROTEIN_AC
        INNER JOIN {1}.ETAXI E 
          ON P.TAX_ID = E.TAX_ID
        INNER JOIN {1}.PROTEIN_DESC PD 
          ON P.PROTEIN_AC = PD.PROTEIN_AC
        INNER JOIN {1}.DESC_VALUE D 
          ON PD.DESC_ID = D.DESC_ID
        INNER JOIN {1}.MATCH MA 
          ON A.PROTEIN_AC = MA.PROTEIN_AC
        INNER JOIN {1}.METHOD ME 
          ON MA.METHOD_AC = ME.METHOD_AC
        LEFT OUTER JOIN {1}.ENTRY2METHOD EM 
          ON MA.METHOD_AC = EM.METHOD_AC
        """.format(query, app.config["DB_SCHEMA"]),
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
            ON E.LEFT_NUMBER = L.LEFT_NUMBER 
            AND L.TAX_ID = :taxid
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
    if dbcode not in ("S", "T"):
        dbcode = None

    query = """
        SELECT
          EZ.ECNO,
          MP.METHOD_AC,
          COUNT(DISTINCT MP.PROTEIN_AC)
        FROM {0}.METHOD2PROTEIN MP
          INNER JOIN {0}.ENZYME EZ 
          ON MP.PROTEIN_AC = EZ.PROTEIN_AC
        WHERE MP.METHOD_AC IN ({1})    
    """.format(
        app.config["DB_SCHEMA"],
        ','.join([":acc" + str(i) for i in range(len(accessions))])
    )
    params = {":acc" + str(i): acc for i, acc in enumerate(accessions)}

    if dbcode:
        query += " AND MP.DBCODE = :dbcode"
        params["dbcode"] = dbcode

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
