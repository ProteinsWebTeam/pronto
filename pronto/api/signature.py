# -*- coding: utf-8 -*-

from cx_Oracle import DatabaseError
from flask import Blueprint, jsonify, request

from pronto import auth, utils


bp = Blueprint("api.signature", __name__, url_prefix="/api/signature")


@bp.route("/<accession>/")
def get_signature(accession):
    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT 
          s.accession,
          s.name, 
          s.description, 
          s.type, 
          s.abstract, 
          s.num_sequences, 
          s.num_complete_sequences,
          d.name,
          d.name_long,
          d.version
        FROM signature s
        INNER JOIN database d ON s.database_id = d.id
        WHERE UPPER(s.accession) = %(str)s
          OR UPPER(s.name) = %(str)s
        """, {"str": accession.upper()}
    )
    row = cur.fetchone()
    cur.close()
    con.close()

    if not row:
        return jsonify(), 404

    db = utils.get_database_obj(row[7])
    result = {
        "accession": row[0],
        "name": row[1],
        "description": row[2],
        "type": row[3],
        "abstract": row[4],
        "proteins": {
            "total": row[5],
            "complete": row[6],
        },
        "database": {
            "name": row[8],
            "home": db.home,
            "link": db.gen_link(accession),
            "color": db.color,
            "version": row[9]
        },
        "entry": None
    }

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT E.ENTRY_AC, E.NAME, 
               E.ENTRY_TYPE, E.CHECKED, EE.PARENT_AC
        FROM INTERPRO.ENTRY2METHOD EM 
        LEFT OUTER JOIN INTERPRO.ENTRY E 
          ON EM.ENTRY_AC = E.ENTRY_AC
        LEFT OUTER JOIN INTERPRO.ENTRY2ENTRY EE
          ON E.ENTRY_AC = EE.ENTRY_AC
        WHERE EM.METHOD_AC = :1
        """, (result["accession"],)
    )
    row = cur.fetchone()
    cur.close()
    con.close()

    if row:
        result["entry"] = {
            "accession": row[0],
            "name": row[1],
            "type": row[2],
            "checked": row[3] == 'Y',
            "parent": row[4]
        }

    return jsonify(result)


@bp.route("/<accession>/comments/")
def get_signature_comments(accession):
    try:
        n = int(request.args["max"])
    except (KeyError, ValueError):
        n = 0

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.METHOD_COMMENT C
        INNER JOIN INTERPRO.PRONTO_USER U 
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
            "date": row[2].strftime("%d %B %Y at %H:%M"),
            "status": row[3] == "Y",
            "author": row[4],
        } for row in cur
    ]
    cur.close()
    con.close()

    return jsonify({
        "count": len(comments),
        "results": comments[:n] if n else comments
    })


@bp.route("/<accession>/comment/", methods=["PUT"])
def add_signature_comment(accession):
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
def delete_signature_comment(accession, commentid):
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
            UPDATE INTERPRO.METHOD_COMMENT 
            SET STATUS = 'N' 
            WHERE METHOD_AC = :1 AND ID = :2
            """,
            (accession, commentid)
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


@bp.route("/<accession>/go/<term_id>/")
def get_term_citations(accession, term_id):
    con = utils.connect_pg()
    with con.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, published
            FROM publication
            WHERE id IN (
                SELECT DISTINCT ref_db_id
                FROM protein2go
                WHERE term_id = %s
                AND protein_acc IN (
                    SELECT DISTINCT protein_acc
                    FROM signature2protein
                    WHERE signature_acc = %s
                )
                AND ref_db_code = 'PMID'
            )
            ORDER BY published
            """, (term_id, accession)
        )

        results = []
        for row in cur:
            results.append({
                "id": row[0],
                "title": row[1],
                "date": row[2].strftime("%d %b %Y")
            })

    con.close()

    return jsonify({
        "count": len(results),
        "results": results
    })


@bp.route("/<accession>/predictions/")
def get_signature_predictions(accession):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT EM.METHOD_AC, E.ENTRY_AC, E.ENTRY_TYPE, E.NAME, E.CHECKED
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.ENTRY E ON EM.ENTRY_AC = E.ENTRY_AC
        """
    )
    integrated = {row[0]: row[1:] for row in cur}

    if accession in integrated:
        query_entry = integrated[accession][0]

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
    cur.close()
    con.close()

    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT
          p.signature_acc_2,
          s.num_complete_sequences,
          d.name,
          d.name_long,
          p.collocation,
          p.overlap,
          p.similarity,
          p.relationship
        FROM interpro.prediction p
        INNER JOIN interpro.signature s
          ON p.signature_acc_2 = s.accession
        INNER JOIN interpro.database d
          ON s.database_id = d.id
        WHERE p.signature_acc_1 = %s
        """, (accession,)
    )

    targets = {}
    for row in cur:
        target_acc = row[0]
        num_proteins = row[1]
        db_key = row[2]
        db_name = row[3]
        collocations = row[4]
        overlaps = row[5]
        similarity = row[6]
        relationship = row[7]

        try:
            obj = integrated[target_acc]
        except KeyError:
            entry = None
        else:
            entry = {
                "accession": obj[0],
                "type": obj[1],
                "name": obj[2],
                "checked": obj[3] == 'Y'
            }

        database = utils.get_database_obj(db_key)
        targets[target_acc] = {
            "accession": target_acc,
            "database": {
                "name": db_name,
                "color": database.color,
                "link": database.gen_link(target_acc)
            },
            "proteins": num_proteins,
            "collocations": collocations,
            "overlaps": overlaps,
            "entry": entry,
            "relationship": relationship or "dissimilar",
            "similarity": similarity
        }
    cur.close()
    con.close()

    def _sort(s):
        if s["entry"]:
            entry_acc = s["entry"]["accession"]

            if entry_acc in ancestors:
                return 0, -s["similarity"], -s["overlaps"]
            elif entry_acc == query_entry:
                return 1, -s["similarity"], -s["overlaps"]
            elif entry_acc in descendants:
                return 2, -s["similarity"], -s["overlaps"]

        return 3, -s["similarity"], -s["overlaps"]

    results = []
    for s in sorted(targets.values(), key=_sort):
        del s["similarity"]

        if s["entry"]:
            entry_acc = s["entry"]["accession"]
            hierarchy = []

            while entry_acc in parent_of:
                entry_acc = parent_of[entry_acc]
                hierarchy.append(entry_acc)

            # Transform child -> parent into parent -> child
            s["entry"]["hierarchy"] = hierarchy[::-1]

        results.append(s)

    return jsonify(results)
