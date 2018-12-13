from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify, request

from pronto import app, db, get_user, xref


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
