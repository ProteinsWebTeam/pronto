import re

from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify, request

from pronto import app, db, get_user, xref


@app.route("/api/entry/<accession>/")
def get_entry(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          E.NAME,
          E.SHORT_NAME,
          E.ENTRY_TYPE,
          ET.ABBREV,
          E.CHECKED,
          E.TIMESTAMP
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.CV_ENTRY_TYPE ET 
          ON E.ENTRY_TYPE = ET.CODE
        WHERE E.ENTRY_AC = :1
        """,
        (accession,)
    )

    row = cur.fetchone()
    cur.close()
    if row:
        entry = {
            "accession": accession,
            "name": row[0],
            "short_name": row[1],
            "type": {
                "code": row[2],
                "name": row[3].replace('_', ' ')
            },
            "is_checked": row[4] == 'Y',
            "last_modification": row[5].strftime("%d %b %Y")
        }
        return jsonify(entry), 200
    else:
        return jsonify(None), 404


@app.route("/api/entry/<accession>/signatures/")
def get_entry_signatures(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          DBCODE,
          METHOD_AC,
          NAME
        FROM {0}.METHOD
        WHERE METHOD_AC IN (
          SELECT METHOD_AC
          FROM {0}.ENTRY2METHOD
          WHERE ENTRY_AC = :1
        )
        ORDER BY METHOD_AC
        """.format(app.config['DB_SCHEMA']),
        (accession,)
    )

    signatures = []
    for row in cur:
        database = xref.find_ref(row[0], row[1])

        signatures.append({
            "accession": row[1],
            "name": row[2],
            "num_proteins": 0,  # TODO: get count from METHOD.PROTEIN_COUNT
            "link": database.gen_link(),
            "color": database.color,
            "database": database.name
        })

    cur.close()
    return jsonify(signatures), 200


@app.route("/api/entry/<accession>/go/")
def get_entry_go_terms(accession):
    cur = db.get_oracle().cursor()

    cur.execute(
        """
        SELECT 
          T.GO_ID, T.NAME, T.CATEGORY, T.DEFINITION, 
          T.IS_OBSOLETE, T.REPLACED_BY
        FROM INTERPRO.INTERPRO2GO I
          INNER JOIN {}.TERM T ON I.GO_ID = T.GO_ID
        WHERE I.ENTRY_AC = :1
        ORDER BY T.GO_ID
        """.format(app.config["DB_SCHEMA"]),
        (accession,)
    )

    terms = []
    for row in cur:
        terms.append({
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "definition": row[3],
            "is_obsolote": row[4] == 'Y',
            "replaced_by": row[5]
        })

    cur.close()

    return jsonify(terms), 200


@app.route("/api/entry/<accession>/relationships/")
def get_entry_relationships(accession):
    cur = db.get_oracle().cursor()

    cur.execute(
        """
        SELECT 
          R.PARENT_AC, E1.NAME, E1.ENTRY_TYPE, 
          R.ENTRY_AC, E2.NAME, E2.ENTRY_TYPE
        FROM (
            SELECT PARENT_AC, ENTRY_AC
            FROM {0}.ENTRY2ENTRY
            START WITH ENTRY_AC = :accession
            CONNECT BY PRIOR PARENT_AC = ENTRY_AC
            UNION ALL
            SELECT PARENT_AC, ENTRY_AC
            FROM {0}.ENTRY2ENTRY
            START WITH PARENT_AC = :accession
            CONNECT BY PRIOR ENTRY_AC = PARENT_AC        
        ) R
        INNER JOIN {0}.ENTRY E1 ON R.PARENT_AC = E1.ENTRY_AC
        INNER JOIN {0}.ENTRY E2 ON R.ENTRY_AC = E2.ENTRY_AC
        """.format(app.config["DB_SCHEMA"]),
        dict(accession=accession)
    )

    parents = {}
    hierarchy = {}
    for row in cur:
        parent_acc = row[0]
        parent_name = row[1]
        parent_type = row[2]
        child_acc = row[3]
        child_name = row[4]
        child_type = row[5]

        parents[child_acc] = parent_acc

        if parent_acc in parents:
            _parents = []
            root_acc = parent_acc
            while root_acc in parents:
                root_acc = parents[parent_acc]
                _parents.append(root_acc)

            children = {}
            for acc in reversed(_parents):
                if not children:
                    children = hierarchy[acc]["children"]
                else:
                    children = children[acc]["children"]

            node = children[parent_acc]
        elif parent_acc in hierarchy:
            node = hierarchy[parent_acc]
        else:
            node = hierarchy[parent_acc] = {
                "accession": parent_acc,
                "name": parent_name,
                "type": parent_type,
                "children": {}
            }

        if child_acc in hierarchy:
            child = hierarchy.pop(child_acc)
        else:
            child = {
                "accession": child_acc,
                "name": child_name,
                "type": child_type,
                "children": {}
            }

        node["children"][child_acc] = child

    cur.close()
    return jsonify(hierarchy), 200


@app.route("/api/entry/<accession>/references/")
def get_entry_references(accession):
    cur = db.get_oracle().cursor()

    cur.execute(
        """
        SELECT 
          T.GO_ID, T.NAME, T.CATEGORY, T.DEFINITION, 
          T.IS_OBSOLETE, T.REPLACED_BY
        FROM INTERPRO.INTERPRO2GO I
          INNER JOIN {}.TERM T ON I.GO_ID = T.GO_ID
        WHERE I.ENTRY_AC = :1
        ORDER BY T.GO_ID
        """.format(app.config["DB_SCHEMA"]),
        (accession,)
    )

    terms = []
    for row in cur:
        terms.append({
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "definition": row[3],
            "is_obsolote": row[4] == 'Y',
            "replaced_by": row[5]
        })

    cur.close()

    return jsonify(terms), 200


@app.route("/api/entry/<accession>/check/", methods=["POST"])
def check_entry(accession):
    content = request.get_json()
    try:
        is_checked = bool(int(content["checked"]))
    except (KeyError, ValueError):
        return jsonify({
            "status": False,
            "message": "Invalid or missing parameters."
        }), 400

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
            UPDATE INTERPRO.ENTRY
            SET CHECKED = :1
            WHERE ENTRY_AC = :2
            """,
            ('Y' if is_checked else 'N', accession)
        )
    except DatabaseError as e:
        cur.close()
        return jsonify({
            "status": False,
            "message": "Could not update {}: {}".format(accession, e)
        }), 400
    else:
        con.commit()
        cur.close()
        return jsonify({
            "status": True,
            "message": None
        }), 200


@app.route("/api/entry/<accession>/comments/")
def get_entry_comments(accession):
    try:
        n = int(request.args["max"])
    except (KeyError, ValueError):
        n = 0

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.ENTRY_COMMENT C
        INNER JOIN INTERPRO.USER_PRONTO U ON C.USERNAME = U.USERNAME
        WHERE C.ENTRY_AC = :1
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
    n_comments = len(comments)

    if n:
        comments = comments[:n]

    for c in comments:
        c["text"] = re.sub(
            r"#(\d+)",
            r'<a href="https://github.com/geneontology/go-annotation/issues/\1">#\1</a>',
            c["text"]
        )

    return jsonify({
        "count": n_comments,
        "comments": comments
    })


@app.route("/api/entry/<accession>/comment/<_id>/", methods=["DELETE"])
def delete_entry_comment(accession, _id):
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
            UPDATE INTERPRO.ENTRY_COMMENT 
            SET STATUS = 'N' 
            WHERE ENTRY_AC = :1 AND ID = :2
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


@app.route("/api/entry/<accession>/comment/", methods=["PUT"])
def add_entry_comment(accession):
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
        FROM INTERPRO.ENTRY_COMMENT
        """
    )
    max_id = cur.fetchone()[0]
    next_id = max_id + 1 if max_id else 1

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY_COMMENT (
              ID, ENTRY_AC, USERNAME, VALUE
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
