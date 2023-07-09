# -*- coding: utf-8 -*-

import re

from oracledb import DatabaseError
from flask import jsonify, request

from pronto import auth, utils
from . import bp


def hashrepl(match: re.Match) -> str:
    issue_id = match.group(1)
    url = f"//github.com/geneontology/go-annotation/issues/{issue_id}"
    return f'<a target="_blank" href="{url}">#{issue_id}</a>'


@bp.route("/<accession>/comments/")
def get_entry_comments(accession):
    try:
        n = int(request.args["max"])
    except (KeyError, ValueError):
        n = 0

    signatures = "signatures" in request.args

    con = utils.connect_oracle()
    cur = con.cursor()
    comments = []

    cur.execute(
            """
            SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME, C.ENTRY_AC
            FROM INTERPRO.ENTRY_COMMENT C
            INNER JOIN INTERPRO.PRONTO_USER U ON C.USERNAME = U.USERNAME
            WHERE C.ENTRY_AC = :1
            ORDER BY C.CREATED_ON DESC
            """, (accession,)
        )

    comments = [
        {
            "id": row[0],
            "text": row[1],
            "date": row[2].strftime("%Y-%m-%d %H:%M:%S"),
            "status": row[3] == "Y",
            "author": row[4],
            "accession": row[5],
        } for row in cur
    ]

    if signatures:
        cur.execute(
            """
            SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME, C.METHOD_AC
            FROM INTERPRO.METHOD_COMMENT C
            INNER JOIN INTERPRO.PRONTO_USER U 
            ON C.USERNAME = U.USERNAME
            INNER JOIN INTERPRO.ENTRY2METHOD E2M ON E2M.METHOD_AC=C.METHOD_AC
            WHERE E2M.ENTRY_AC = :1
            ORDER BY C.CREATED_ON DESC
            """, (accession,)
        )
        for row in cur:
            comments.append({
                "id": row[0],
                "text": row[1],
                "date": row[2].strftime("%Y-%m-%d %H:%M:%S"),
                "status": row[3] == "Y",
                "author": row[4],
                "accession": row[5],
            })
    
    cur.close()
    con.close()
    n_comments = len(comments)

    if n:
        comments = comments[:n]

    for c in comments:
        c["text"] = re.sub(r"#(\d+)", hashrepl, c["text"])

    return jsonify({
        "count": n_comments,
        "results": comments
    })


@bp.route("/<accession>/comment/", methods=["PUT"])
def add_entry_comment(accession):
    user = auth.get_user()
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
                "title": "Bad request",
                "message": "Comment too short (must be at least "
                           "three characters long)."
            }
        }), 400

    con = utils.connect_oracle_auth(user)
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
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(exc)
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/comment/<commentid>/", methods=["DELETE"])
def delete_entry_comment(accession, commentid):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE INTERPRO.ENTRY_COMMENT
            SET STATUS = 'N'
            WHERE ENTRY_AC = :1 AND ID = :2
            """, (accession, commentid)
        )
    except DatabaseError as e:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(e)
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()
