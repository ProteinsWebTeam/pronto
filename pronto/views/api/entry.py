import re

from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify, request

from pronto import app, db, get_user


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
