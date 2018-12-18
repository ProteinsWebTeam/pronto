from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify, request

from pronto import app, db, get_user, xref
from .signatures import build_method2protein_query


@app.route("/api/signature/<accession>/predictions/")
def get_signature_predictions(accession):
    try:
        overlap = float(request.args["overlap"])
    except (KeyError, ValueError):
        overlap = 0.3

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          MO.C_AC,
          DB.DBCODE,

          E.ENTRY_AC,
          E.CHECKED,
          E.ENTRY_TYPE,
          E.NAME,

          MO.N_PROT_OVER,
          MO.N_OVER,          

          MO.Q_N_PROT,
          MO.Q_N_MATCHES,
          MO.C_N_PROT,
          MO.C_N_MATCHES,

          MP.RELATION
        FROM (
            SELECT
              MMQ.METHOD_AC Q_AC,
              MMQ.N_PROT Q_N_PROT,
              MMQ.N_MATCHES Q_N_MATCHES,
              MMC.METHOD_AC C_AC,
              MMC.N_PROT C_N_PROT,
              MMC.N_MATCHES C_N_MATCHES,
              MO.N_PROT_OVER,
              MO.N_OVER
            FROM (
                SELECT 
                  METHOD_AC1, METHOD_AC2, N_PROT_OVER, 
                  N_OVER, AVG_FRAC1, AVG_FRAC2
                FROM {0}.METHOD_OVERLAP
                WHERE METHOD_AC1 = :accession
            ) MO
            INNER JOIN {0}.METHOD_MATCH MMQ 
              ON MO.METHOD_AC1 = MMQ.METHOD_AC
            INNER JOIN {0}.METHOD_MATCH MMC 
              ON MO.METHOD_AC2 = MMC.METHOD_AC
            WHERE ((MO.N_PROT_OVER >= (:overlap * MMQ.N_PROT)) 
            OR (MO.N_PROT_OVER >= (:overlap * MMC.N_PROT)))        
        ) MO
        LEFT OUTER JOIN {0}.METHOD_PREDICTION MP 
          ON (MO.Q_AC = MP.METHOD_AC1 AND MO.C_AC = MP.METHOD_AC2)
        LEFT OUTER JOIN {0}.METHOD M 
          ON MO.C_AC = M.METHOD_AC
        LEFT OUTER JOIN {0}.CV_DATABASE DB 
          ON M.DBCODE = DB.DBCODE
        LEFT OUTER JOIN {0}.ENTRY2METHOD E2M 
          ON MO.C_AC = E2M.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY E 
          ON E2M.ENTRY_AC = E.ENTRY_AC
        ORDER BY MO.N_PROT_OVER DESC, MO.N_OVER DESC, MO.C_AC
        """.format(app.config["DB_SCHEMA"]),
        dict(accession=accession, overlap=overlap)
    )

    signatures = []
    for row in cur:
        database = xref.find_ref(dbcode=row[1], ac=row[0])

        signatures.append({
            # Signature
            "accession": row[0],
            "link": database.gen_link() if database else None,

            # Entry
            "entry": {
                "accession": row[2],
                "hierarchy": [],
                "checked": row[3] == 'Y',
                "type_code": row[4],
                "name": row[5]
            },

            # number of proteins where query and candidate overlap
            "n_proteins": row[6],

            # number of matches where query and candidate overlap
            "n_overlaps": row[7],

            # number of proteins/matches for query and candidate
            "query": {
                "n_proteins": row[8],
                "n_matches": row[9],
            },
            "candidate": {
                "n_proteins": row[10],
                "n_matches": row[11],
            },

            # Predicted relationship
            "relation": row[12]
        })

    cur.execute(
        """
        SELECT ENTRY_AC, PARENT_AC
        FROM {}.ENTRY2ENTRY
        """.format(app.config['DB_SCHEMA'])
    )
    parent_of = dict(cur.fetchall())
    cur.close()

    for s in signatures:
        entry_acc = s["entry"]["accession"]
        if entry_acc:
            hierarchy = []

            while entry_acc in parent_of:
                entry_acc = parent_of[entry_acc]
                hierarchy.append(entry_acc)

            # Transform child -> parent into parent -> child
            s["entry"]["hierarchy"] = hierarchy[::-1]

    return jsonify(signatures)


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
        INNER JOIN INTERPRO.USER_PRONTO U ON C.USERNAME = U.USERNAME
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
            "message": "Please log in to perform this action."
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
            "message": "Could not delete comment "
                       "for {}: {}".format(accession, e)
        }), 400
    else:
        con.commit()
        cur.close()
        return jsonify({
            "status": True,
            "message": None
        }), 200


@app.route("/api/signature/<accession>/comment/", methods=["PUT"])
def add_signature_comment(accession):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "message": "Please log in to perform this action."
        }), 401

    content = request.get_json()
    text = content.get("text", "")
    if len(text) < 3:
        return jsonify({
            "status": False,
            "message": "Comment too short (must be at least "
                       "three characters long)."
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
            "message": "Could not add comment "
                       "for {}: {}".format(accession, e)
        }), 400
    else:
        con.commit()
        cur.close()
        return jsonify({
            "status": True,
            "message": None
        }), 200


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
        """.format(app.config['DB_SCHEMA'], query),
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
                if pos_start < pos_end:
                    fragments.append({"start": pos_start, "end": pos_end})

                fragments.sort(key=lambda x: (x["start"], x["end"]))

        if not fragments:
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
    return jsonify(proteins)


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