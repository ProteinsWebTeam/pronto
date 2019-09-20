from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify

from pronto import app, db, get_user


@app.route("/api/entry/<accession>/go/")
def get_entry_go_terms(accession):
    cur = db.get_oracle().cursor()

    cur.execute(
        """
        SELECT 
          T.GO_ID, T.NAME, T.CATEGORY, T.DEFINITION, 
          T.IS_OBSOLETE, T.REPLACED_BY, T.NUM_CONSTRAINTS
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
            "is_obsolete": row[4] == 'Y',
            "secondary": row[5] is not None,
            "taxon_constraints": row[6]
        })

    cur.close()

    return jsonify(terms), 200


@app.route("/api/entry/<accession>/go/<term_id>/", methods=['DELETE'])
def delete_go_term(accession, term_id):
    user = get_user()

    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": 'Please <a href="/login/">log in</a> '
                           'to perform this operation.'
            }
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.INTERPRO2GO
            WHERE ENTRY_AC = :1 AND GO_ID = :2
            """,
            (accession, term_id)
        )
    except IntegrityError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not delete GO term {} "
                           "from InterPro entry {}".format(accession, term_id)
            }
        }), 500
    else:
        # row_count = cur.rowcount  # TODO: check that row_count == 1?
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route("/api/entry/<accession>/go/<term_id>/", methods=["PUT"])
def add_go_term(accession, term_id):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": 'Please <a href="/login/">log in</a> '
                           'to perform this operation.'
            }
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*) 
        FROM INTERPRO.ENTRY 
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    if not cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid entry",
                "message": "{} is not a valid InterPro accession.".format(accession)
            }
        }), 400

    cur.execute(
        """
        SELECT COUNT(*) 
        FROM {}.TERM 
        WHERE GO_ID = :1
        """.format(app.config["DB_SCHEMA"]), (term_id,)
    )
    if not cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid GO term",
                "message": "{} is not a valid GO term ID".format(term_id)
            }
        }), 401

    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.INTERPRO2GO
        WHERE ENTRY_AC = :1 AND GO_ID = :2
        """, (accession, term_id)
    )
    if cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": True
        }), 200

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.INTERPRO2GO (ENTRY_AC, GO_ID, SOURCE)
            VALUES (:1, :2, :3)
            """, (accession, term_id, "MANU")
        )
    except (DatabaseError, IntegrityError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not add {} to {}".format(term_id, accession)
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()
