from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify, request

from pronto import app, db, get_user, xref
from .signatures import build_method2protein_query


@app.route("/api/signature/<accession>/")
def get_signature(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT M.METHOD_AC, M.NAME, M.DESCRIPTION, M.DBCODE, M.SIG_TYPE, 
               M.PROTEIN_COUNT, M.FULL_SEQ_COUNT, EM.ENTRY_AC, E.ENTRY_TYPE, 
               EE.PARENT_AC
        FROM {}.METHOD M
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
          ON M.METHOD_AC = EM.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E 
          ON EM.ENTRY_AC = E.ENTRY_AC
        LEFT OUTER JOIN INTERPRO.ENTRY2ENTRY EE
          ON E.ENTRY_AC = EE.ENTRY_AC
        WHERE UPPER(M.METHOD_AC) = :acc OR UPPER(M.NAME) = :acc
        """.format(app.config["DB_SCHEMA"]),
        dict(acc=accession.upper())
    )
    row = cur.fetchone()
    cur.close()

    if row:
        database = xref.find_ref(row[3], row[0])

        return jsonify({
            "accession": row[0],
            "name": row[1],
            "description": row[2],
            "num_proteins": row[5],
            "num_sequences": row[6],
            "type": row[4],
            "link": database.gen_link(),
            "color": database.color,
            "database": database.name,
            "entry": {
                "accession": row[7],
                "type": row[8],
                "parent": row[9]
            }
        }), 200
    else:
        return jsonify(None), 404


@app.route("/api/signature/<accession1>/comparison/<accession2>/<cmp_type>/")
def get_signatures_comparison(accession1, accession2, cmp_type):
    if cmp_type == "descriptions":
        column = "DESC_ID"
        table = "METHOD_DESC"
    elif cmp_type == "taxa":
        column = "TAX_ID"
        table = "METHOD_TAXA"
    elif cmp_type == "terms":
        column = "GO_ID"
        table = "METHOD_TERM"
    else:
        return jsonify({
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    query = """
      SELECT {} 
      FROM {}.{} 
      WHERE METHOD_AC = :1
    """.format(column, app.config["DB_SCHEMA"], table)

    cur = db.get_oracle().cursor()
    cur.execute(query, (accession1,))
    set1 = {row[0] for row in cur}
    cur.execute(query, (accession2,))
    set2 = {row[0] for row in cur}
    cur.close()

    return jsonify({
        accession1: len(set1),
        accession2: len(set2),
        "common": len(set1 & set2)
    }), 200


@app.route("/api/signature/<query_acc>/predictions/")
def get_signature_predictions(query_acc):
    try:
        min_colloc_sim = float(request.args["mincollocation"])
        assert 0 <= min_colloc_sim <= 1
    except KeyError:
        min_colloc_sim = 0.5
    except (ValueError, AssertionError):
        return jsonify({
            "error": {
                "title": "Bad request",
                "message": "Parameter 'mincollocation' "
                           "expects a number between 0 and 1."
            }
        }), 400

    cur = db.get_oracle().cursor()

    # Get the InterPro entry integrating the query signature (if any)
    cur.execute(
        """
        SELECT ENTRY_AC 
        FROM INTERPRO.ENTRY2METHOD 
        WHERE METHOD_AC = :1
        """, (query_acc,)
    )
    row = cur.fetchone()
    if row:
        query_entry = row[0]

        # Get ancestors
        cur.execute(
            """
            SELECT PARENT_AC
            FROM INTERPRO.ENTRY2ENTRY
            START WITH ENTRY_AC = :1
            CONNECT BY PRIOR PARENT_AC = ENTRY_AC
            """, (query_entry,)
        )
        ancestors = {row[0] for row in cur}

        # Get descendants
        cur.execute(
            """
            SELECT ENTRY_AC
            FROM INTERPRO.ENTRY2ENTRY
            START WITH PARENT_AC = :1
            CONNECT BY PRIOR ENTRY_AC = PARENT_AC
            """, (query_entry,)
        )
        descendants = {row[0] for row in cur}
    else:
        query_entry = None
        ancestors = set()
        descendants = set()

    # Get (child -> parent) relationships
    cur.execute("SELECT ENTRY_AC, PARENT_AC FROM INTERPRO.ENTRY2ENTRY")
    parent_of = dict(cur.fetchall())

    cur.execute(
        """
        SELECT MS.METHOD_AC2, MS.DBCODE2, MS.PROT_COUNT2,
               E.ENTRY_AC, E.ENTRY_TYPE, E.NAME, E.CHECKED,
               MS.COLL_COUNT, MS.PROT_OVER_COUNT, MS.PROT_SIM,
               MS.PROT_PRED, MS.RESI_PRED, MS.DESC_PRED, MS.TAXA_PRED, 
               MS.TERM_PRED
        FROM {}.METHOD_SIMILARITY MS
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM
          ON MS.METHOD_AC2 = EM.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E
          ON EM.ENTRY_AC = E.ENTRY_AC
        WHERE MS.METHOD_AC1 = :acc
        AND (MS.COLL_COUNT/MS.PROT_COUNT1 >= :mincolloc 
             OR MS.COLL_COUNT/MS.PROT_COUNT2 >= :mincolloc)
        """.format(app.config["DB_SCHEMA"]),
        dict(acc=query_acc, mincolloc=min_colloc_sim)
    )

    signatures = []
    for row in cur:
        target_acc = row[0]
        target_dbcode = row[1]
        target_count = row[2]
        entry_acc = row[3]
        entry_type = row[4]
        entry_name = row[5]
        entry_checked = row[6] == 'Y'
        colloc_cnt = row[7]
        overlp_cnt = row[8]
        similarity = row[9]
        pred_prot = row[10]
        pred_resi = row[11]
        pred_desc = row[12]
        pred_taxa = row[13]
        pred_term = row[14]

        database = xref.find_ref(dbcode=target_dbcode, ac=target_acc)
        signatures.append({
            # Signature
            "accession": target_acc,
            "link": database.gen_link() if database else None,

            # Entry
            "entry": {
                "accession": entry_acc,
                "type_code": entry_type,
                "name": entry_name,
                "checked": entry_checked,
                "hierarchy": []
            },

            "proteins": target_count,
            "common_proteins": colloc_cnt,
            "overlap_proteins": overlp_cnt,
            "predictions": {
                "proteins": pred_prot,
                "residues": pred_resi,
                "descriptions": pred_desc,
                "taxa": pred_taxa,
                "terms": pred_term,
            },

            # Will be removed later (used for sorting)
            "_similarity": similarity,
        })

    cur.close()

    def _sort(s):
        if s["entry"]["accession"]:
            if s["entry"]["accession"] in ancestors:
                return 0, -s["_similarity"], -s["overlap_proteins"]
            elif s["entry"]["accession"] == query_entry:
                return 1, -s["_similarity"], -s["overlap_proteins"]
            elif s["entry"]["accession"] in descendants:
                return 2, -s["_similarity"], -s["overlap_proteins"]

        return 3, -s["_similarity"], -s["overlap_proteins"]

    results = []
    for s in sorted(signatures, key=_sort):
        del s["_similarity"]

        entry_acc = s["entry"]["accession"]
        if entry_acc:
            hierarchy = []

            while entry_acc in parent_of:
                entry_acc = parent_of[entry_acc]
                hierarchy.append(entry_acc)

            # Transform child -> parent into parent -> child
            s["entry"]["hierarchy"] = hierarchy[::-1]

        results.append(s)

    return jsonify(results), 200


@app.route("/api/signature/<accession>/comments/")
def get_signature_comments(accession):
    try:
        n = int(request.args["max"])
    except (KeyError, ValueError):
        n = 0

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.METHOD_COMMENT C
        INNER JOIN INTERPRO.USER_PRONTO U 
          ON C.USERNAME = U.USERNAME
        WHERE C.METHOD_AC = :1
        ORDER BY C.CREATED_ON DESC
        """,
        (accession,)
    )

    comments = [
        {
            "id": row[0],
            "text": row[1],
            "date": row[2].strftime("%Y-%m-%d %H:%M:%S"),
            "status": row[3] == "Y",
            "author": row[4],
        } for row in cur
    ]
    cur.close()

    return jsonify({
        "count": len(comments),
        "comments": comments[:n] if n else comments
    })


@app.route("/api/signature/<accession>/comment/<_id>/", methods=["DELETE"])
def delete_signature_comment(accession, _id):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE INTERPRO.METHOD_COMMENT 
            SET STATUS = 'N' 
            WHERE METHOD_AC = :1 AND ID = :2
            """,
            (accession, _id)
        )
    except DatabaseError as e:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not delete comment "
                           "for {}: {}".format(accession, e)
            }
        }), 500
    else:
        con.commit()
        cur.close()
        return jsonify({"status": True}), 200


@app.route("/api/signature/<accession>/comment/", methods=["PUT"])
def add_signature_comment(accession):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    content = request.get_json()
    text = content.get("text", "")
    if len(text) < 3:
        return jsonify({
            "status": False,
            "error": {
                "message": "Comment too short (must be at least "
                           "three characters long)."
            }
        }), 400

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT MAX(ID)
        FROM INTERPRO.METHOD_COMMENT
        """
    )
    max_id = cur.fetchone()[0]
    next_id = max_id + 1 if max_id else 1

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.METHOD_COMMENT (
              ID, METHOD_AC, USERNAME, VALUE
            )
            VALUES (:1, :2, :3, :4)
            """,
            (next_id, accession, user["username"], text)
        )
    except IntegrityError as e:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not add comment "
                           "for {}: {}".format(accession, e)
            }
        }), 500
    else:
        con.commit()
        cur.close()
        return jsonify({"status": True}), 200


@app.route("/api/signature/<accession>/matches/")
def get_signature_matches(accession):
    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

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

    dbcode = request.args.get("db")
    if dbcode not in ("S", "T"):
        dbcode = None

    go_id = request.args.get("go")
    ec_no = request.args.get("ec")
    search = request.args.get("search", "").strip()
    query, params = build_method2protein_query({accession: None},
                                               left_num=left_num,
                                               right_num=right_num,
                                               dbcode=dbcode,
                                               descr_id=descr_id,
                                               topic_id=topic_id,
                                               comment_id=comment_id,
                                               go_id=go_id,
                                               ec_no=ec_no,
                                               search=search)

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM ({})
        """.format(query),
        params
    )
    n_proteins = cur.fetchone()[0]

    params.update({
        "min_row": max(0, (page - 1) * page_size),
        "max_row": min(n_proteins, page * page_size),
        "acc": accession
    })
    cur.execute(
        """
        SELECT 
          M.PROTEIN_AC, P.DBCODE, P.LEN, P.NAME, DV.TEXT, E.TAX_ID, 
          E.FULL_NAME, M.POS_FROM, M.POS_TO, M.FRAGMENTS
        FROM {0}.MATCH M
        INNER JOIN {0}.PROTEIN P 
          ON M.PROTEIN_AC = P.PROTEIN_AC
        INNER JOIN {0}.PROTEIN_DESC PD 
          ON P.PROTEIN_AC = PD.PROTEIN_AC
        INNER JOIN {0}.DESC_VALUE DV 
          ON PD.DESC_ID = DV.DESC_ID
        INNER JOIN {0}.ETAXI E
          ON P.TAX_ID = E.TAX_ID
        WHERE M.PROTEIN_AC IN (
          SELECT PROTEIN_AC
          FROM (
              SELECT A.*, ROWNUM RN
              FROM (
                {1}
                ORDER BY PROTEIN_AC
              ) A
              WHERE ROWNUM <= :max_row
          )
          WHERE RN > :min_row
        ) AND M.METHOD_AC = :acc
        """.format(app.config["DB_SCHEMA"], query),
        params
    )

    proteins = {}
    for row in cur:
        protein_acc = row[0]
        if protein_acc in proteins:
            p = proteins[protein_acc]
        else:
            if row[1] == 'S':
                is_reviewed = True
                link = "//sp.isb-sib.ch/uniprot/{}".format(protein_acc)
            else:
                is_reviewed = False
                link = "//www.uniprot.org/uniprot/{}".format(protein_acc)

            p = proteins[protein_acc] = {
                "accession": protein_acc,
                "reviewed": is_reviewed,
                "link": link,
                "length": row[2],
                "identifier": row[3],
                "name": row[4],
                "taxon": {
                    "id": row[5],
                    "name": row[6]
                },
                "matches": []
            }

        fragments = []
        if row[9] is not None:
            for f in row[9].split(','):
                pos_start, pos_end, _ = f.split('-')
                pos_start = int(pos_start)
                pos_end = int(pos_end)
                if pos_start <= pos_end:
                    fragments.append({"start": pos_start, "end": pos_end})

        if fragments:
            # Sort discontinuous fragments (in case they are not sorted in DB)
            fragments.sort(key=lambda x: (x["start"], x["end"]))
        else:
            fragments.append({"start": row[7], "end": row[8]})

        p["matches"].append(fragments)

    cur.close()

    for p in proteins.values():
        p["matches"].sort(key=lambda x: x[0]["start"])

    return jsonify({
        "count": n_proteins,
        "proteins": sorted(proteins.values(), key=lambda x: x["accession"]),
        "page_info": {
            "page": page,
            "page_size": page_size
        }
    })


@app.route("/api/signature/<accession>/proteins/")
def get_signature_proteins(accession):
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

    dbcode = request.args.get("db")
    if dbcode not in ("S", "T"):
        dbcode = None

    go_id = request.args.get("go")
    ec_no = request.args.get("ec")
    search = request.args.get("search", "").strip()
    query, params = build_method2protein_query({accession: None},
                                               left_num=left_num,
                                               right_num=right_num,
                                               dbcode=dbcode,
                                               descr_id=descr_id,
                                               topic_id=topic_id,
                                               comment_id=comment_id,
                                               go_id=go_id,
                                               ec_no=ec_no,
                                               search=search)

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT 
          P.PROTEIN_AC, P.DBCODE, P.LEN, P.NAME, DV.TEXT, E.TAX_ID, 
          E.FULL_NAME
        FROM {0}.PROTEIN P 
        INNER JOIN {0}.PROTEIN_DESC PD 
          ON P.PROTEIN_AC = PD.PROTEIN_AC
        INNER JOIN {0}.DESC_VALUE DV 
          ON PD.DESC_ID = DV.DESC_ID
        INNER JOIN {0}.ETAXI E
          ON P.TAX_ID = E.TAX_ID
        WHERE P.PROTEIN_AC IN (
          SELECT PROTEIN_AC
          FROM ({1})
        ) 
        ORDER BY P.PROTEIN_AC
        """.format(app.config['DB_SCHEMA'], query),
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


@app.route('/api/signature/<accession>/references/<go_id>/')
def get_signature_references(accession, go_id):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT ID, TITLE, FIRST_PUBLISHED_DATE
        FROM {0}.PUBLICATION
        WHERE ID IN (
          SELECT DISTINCT REF_DB_ID
          FROM {0}.PROTEIN2GO P
            INNER JOIN {0}.METHOD2PROTEIN M 
            ON P.PROTEIN_AC = M.PROTEIN_AC
          WHERE M.METHOD_AC = :1
                AND P.GO_ID = :2
                AND REF_DB_CODE = 'PMID'
        )
        ORDER BY FIRST_PUBLISHED_DATE
        """.format(app.config["DB_SCHEMA"]),
        (accession, go_id)
    )

    references = []
    for row in cur:
        references.append({
            "id": row[0],
            "title": '' if row[1] is None else row[1],
            "date": '' if row[2] is None else row[2].strftime("%d %b %Y")
        })

    cur.close()

    return jsonify(references)
