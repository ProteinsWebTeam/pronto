from concurrent.futures import as_completed

from flask import jsonify, request

from pronto import app, db, executor, xref


def filter_proteins(user, dsn, accession, **kwargs):
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

    query = """
        SELECT PROTEIN_AC, MD5, LEN
        FROM {}.{}
        WHERE METHOD_AC = :acc
    """
    params = {"acc": accession}

    # Filter by description
    if descr_id is not None:
        query += " AND DESC_ID = :descrid"
        params["descrid"] = descr_id

    # Filter by review status
    if dbcode == "S":
        query = query.format(app.config["DB_SCHEMA"], "MV_METHOD2SWISSPROT")
    else:
        query = query.format(app.config["DB_SCHEMA"], "METHOD2PROTEIN")

        if dbcode:
            query += " AND DBCODE = :dbcode"
            params["dbcode"] = dbcode

    # Search by protein accession
    if search:
        query += " AND PROTEIN_AC LIKE :searchlike"
        params["searchlike"] = search + "%"

    # Filter by taxonomic origin
    if left_num is not None and right_num is not None:
        query += " AND LEFT_NUMBER BETWEEN :leftnum AND :rightnum"
        params.update({
            "leftnum": left_num,
            "rightnum": right_num
        })

    # Filter by MD5 (protein match structure)
    if md5 is not None:
        query += " AND MD5 = :md5"
        params["md5"] = md5

    intersects =[]

    # Filter by SwissProt comment
    if topic_id is not None and comment_id is not None:
        intersects.append(
            """
            SELECT PROTEIN_AC
            FROM {}.PROTEIN_COMMENT
            WHERE TOPIC_ID = :topicid AND COMMENT_ID = :commentid
            """.format(app.config["DB_SCHEMA"])
        )
        params.update({
            "topicid": topic_id,
            "commentid": comment_id
        })

    # Filter by GO term
    if go_id is not None:
        intersects.append(
            """
            SELECT DISTINCT PROTEIN_AC
            FROM {}.PROTEIN2GO
            WHERE GO_ID = :goid
            """.format(app.config["DB_SCHEMA"])
        )
        params["goid"] = go_id

    # Filter by EC number
    if ec_no is not None:
        intersects.append(
            """
            SELECT DISTINCT PROTEIN_AC
            FROM {}.ENZYME
            WHERE ECNO = :ecno
            """.format(app.config["DB_SCHEMA"])
        )
        params["ecno"] = ec_no

    # Filter by taxonomic rank
    if rank is not None:
        intersects.append(
            """
            SELECT DISTINCT PROTEIN_AC
            FROM {0}.METHOD2PROTEIN
            WHERE METHOD_AC = :acc
            AND LEFT_NUMBER IN (
              SELECT LEFT_NUMBER
              FROM {0}.LINEAGE
              WHERE RANK = :rank
            )
        """.format(app.config["DB_SCHEMA"])
        )
        params["rank"] = rank

    if intersects:
        query += " AND PROTEIN_AC IN ({})".format(
            " INTERSECT ".join(intersects)
        )

    con = db.connect_oracle(user, dsn)
    cur = con.cursor()
    cur.execute(query, **params)
    rows = cur.fetchall()
    cur.close()
    con.close()

    return rows


def _protein_key(d):
    return -len(d["signatures"]), d["accession"]


def _protein_key2(d):
    if d["num_similar"] is None:
        return d["accession"]
    else:
        return -d["num_similar"], d["accession"]


def _signature_key(d):
    return 0 if d["integrated"] else 1, d["accession"]


@app.route("/api/signatures/<path:accessions_str>/proteins/")
def get_overlapping_proteins(accessions_str):
    signatures = set()
    for acc in accessions_str.split("/"):
        acc = acc.strip()
        if acc:
            signatures.add(acc)

    kwargs = {}

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
        pass
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
            kwargs.update({
                "left_num": row[0],
                "right_num": row[1]
            })
        else:
            return jsonify({}), 400  # TODO: return error

    try:
        kwargs["descr_id"] = int(request.args["description"])
    except (KeyError, ValueError):
        pass

    try:
        topic_id = int(request.args["topic"])
        comment_id = int(request.args["comment"])
    except (KeyError, ValueError):
        pass
    else:
        kwargs.update({
            "topic_id": topic_id,
            "comment_id": comment_id
        })

    dbcode = request.args.get("db", "S").upper()
    if dbcode in ("S", "T"):
        kwargs["dbcode"] = dbcode

    matched_by = set()
    for acc in request.args.get("include", "").split(","):
        acc = acc.strip()
        if acc:
            matched_by.add(acc)

    not_matched_by = set()
    for acc in request.args.get("exclude", "").split(","):
        acc = acc.strip()
        if acc:
            not_matched_by.add(acc)

    md5 = request.args.get("md5")  # protein match structure
    group_proteins = md5 is None
    kwargs.update({
        "go_id": request.args.get("go"),
        "ec_no": request.args.get("ec"),
        "rank": request.args.get("rank"),
        "search": request.args.get("search", "").strip(),
        "md5": md5
    })

    user = dict(
        zip(
            ("dbuser", "password"),
            app.config["ORACLE_DB"]["credentials"].split('/')
        )
    )
    dsn = app.config["ORACLE_DB"]["dsn"]

    fs = {}
    for acc in signatures:
        f = executor.submit(filter_proteins, user, dsn, acc, **kwargs)
        fs[f] = acc

    proteins = {}
    exclude = set()
    for f in as_completed(fs):
        try:
            rows = f.result()
        except Exception as e:
            print(e)  # TODO: return error?
        else:
            signature_acc = fs[f]
            for protein_acc, md5, length in rows:
                if protein_acc in exclude:
                    continue
                elif signature_acc in not_matched_by:
                    exclude.add(protein_acc)
                elif protein_acc in proteins:
                    proteins[protein_acc]["signatures"].add(signature_acc)
                else:
                    proteins[protein_acc] = {
                        "accession": protein_acc,
                        "md5": md5,
                        "length": length,
                        "signatures": {signature_acc}
                    }

    if matched_by:
        proteins = {
            k: v
            for k, v in proteins.items()
            if not matched_by - v["signatures"]
        }

    groups = {}
    if group_proteins:
        for k, v in proteins.items():
            md5 = v["md5"]
            if md5 in groups:
                if v["length"] > groups[md5]["length"]:
                    groups[md5].update({
                        "accession": k,
                        "length": v["length"]
                    })

                groups[md5]["signatures"] |= v["signatures"]
                groups[md5]["proteins"] += 1
            else:
                groups[md5] = {
                    "accession": k,
                    "length": v["length"],
                    "signatures": v["signatures"],
                    "proteins": 1
                }

        accessions = [
            v["accession"]
            for v in sorted(groups.values(), key=_protein_key)
        ]
    else:
        accessions = [
            v["accession"]
            for v in sorted(proteins.values(), key=_protein_key)
        ]

    results = {}
    if accessions:
        start = max(0, (page - 1) * page_size)
        stop = min(len(accessions), page * page_size)
        accessions = accessions[start:stop]

        cur = db.get_oracle().cursor()
        cur.execute(
            """
            SELECT 
              P.PROTEIN_AC, P.DBCODE, P.LEN, E.FULL_NAME, 
              D.TEXT, MA.METHOD_AC, ME.NAME, ME.CANDIDATE, ME.DBCODE,
              EM.ENTRY_AC, MA.POS_FROM, MA.POS_TO, MA.FRAGMENTS
            FROM {0}.PROTEIN P
            INNER JOIN {0}.ETAXI E 
              ON P.TAX_ID = E.TAX_ID
            INNER JOIN {0}.PROTEIN_DESC PD 
              ON P.PROTEIN_AC = PD.PROTEIN_AC
            INNER JOIN {0}.DESC_VALUE D 
              ON PD.DESC_ID = D.DESC_ID
            INNER JOIN {0}.MATCH MA 
              ON P.PROTEIN_AC = MA.PROTEIN_AC
            INNER JOIN {0}.METHOD ME 
              ON MA.METHOD_AC = ME.METHOD_AC
            LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
              ON MA.METHOD_AC = EM.METHOD_AC
            WHERE P.PROTEIN_AC IN ({1})
            """.format(
                app.config["DB_SCHEMA"],
                ','.join([':' + str(i+1) for i in range(len(accessions))])
            ), accessions
        )

        for row in cur:
            protein_acc = row[0]

            if protein_acc in results:
                p = results[protein_acc]
            else:
                if row[1] == 'S':
                    is_reviewed = True
                    link = "//sp.isb-sib.ch/uniprot/{}".format(protein_acc)
                else:
                    is_reviewed = False
                    link = "//www.uniprot.org/uniprot/{}".format(protein_acc)

                md5 = proteins[protein_acc]["md5"]
                p = results[protein_acc] = {
                    "accession": protein_acc,
                    "md5": md5,
                    "num_similar": groups[md5]["proteins"] - 1 if group_proteins else None,
                    "reviewed": is_reviewed,
                    "link": link,
                    "length": row[2],
                    "taxon": row[3],
                    "name": row[4],
                    "signatures": {}
                }

            signature_acc = row[5]
            if signature_acc in p["signatures"]:
                s = p["signatures"][signature_acc]
            else:
                database = xref.find_ref(row[8], signature_acc)
                s = p["signatures"][signature_acc] = {
                    "accession": signature_acc,
                    "name": row[6],
                    "candidate": row[7] == 'Y',
                    "link": database.gen_link(),
                    "color": database.color,
                    "integrated": row[9],
                    "matches": [],
                    "active": signature_acc in signatures
                }

            fragments = []
            if row[12] is not None:
                for f in row[12].split(','):
                    pos_start, pos_end, _ = f.split('-')
                    pos_start = int(pos_start)
                    pos_end = int(pos_end)

                    if pos_start < pos_end:
                        fragments.append({"start": pos_start, "end": pos_end})

            if fragments:
                # Sort discontinuous fragments (in case they are not sorted in DB)
                fragments.sort(key=lambda x: (x["start"], x["end"]))
            else:
                fragments.append({"start": row[10], "end": row[11]})

            s["matches"].append(fragments)

        cur.close()

    # Sort proteins by number of similar proteins (desc) then accession (asc)
    _results = []
    for p in sorted(results.values(), key=_protein_key2):

        # Sort signatures by integrated and accession
        signatures = []
        for s in sorted(p["signatures"].values(), key=_signature_key):
            # Sort matches by the position of the leftmost fragment
            s["matches"].sort(key=lambda x: (x[0]["start"], x[0]["end"]))

            signatures.append(s)

        p["signatures"] = signatures
        _results.append(p)

    return jsonify({
        "num_proteins": len(proteins),
        "num_structures": len(groups),
        "proteins": _results,
        "source_database": dbcode,
        "page_info": {
            "page": page,
            "page_size": page_size
        },
    })

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
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
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
        "num_proteins": n_proteins,
        "num_structures": n_groups,
        "proteins": _proteins,
        "source_database": dbcode,
        "page_info": {
            "page": page,
            "page_size": page_size
        },
    })
