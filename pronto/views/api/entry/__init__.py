from cx_Oracle import DatabaseError, STRING
from flask import jsonify, request

from pronto import app, db, executor, get_user
from . import annotations, comments, go, references, relationships, signatures


def _delete_entry(user, dsn, accession):
    con = db.connect_oracle(user, dsn)
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY
            WHERE ENTRY_AC = :1
            """, (accession,)
        )
    except DatabaseError as e:
        raise e
    else:
        con.commit()
    finally:
        cur.close()
        con.close()


@app.route("/api/entry/", methods=["PUT"])
def create_entry():
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

    try:
        entry_type = request.json["type"]
        entry_name = request.json["name"]
        entry_descr = request.json["description"]
    except KeyError:
        return jsonify({
            'error': {
                'title': 'Bad request',
                'message': 'Invalid or missing parameters.'
            }
        }), 400

    if entry_type == 'U':
        # Unknown type is not allowed
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid type",
                "message": "InterPro entries cannot be of type Unknown."
            }
        }), 400

    con = db.get_oracle()
    cur = con.cursor()

    # Create the entry
    accession = cur.var(STRING)
    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY (ENTRY_AC, ENTRY_TYPE, NAME, SHORT_NAME) 
            VALUES (INTERPRO.NEW_ENTRY_AC(), :1, :2, :3)
            RETURNING ENTRY_AC INTO :4
            """,
            (entry_type, entry_descr, entry_name, accession)
        )
    except DatabaseError as e:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(e)
            }
        }), 401

    #
    """
    Get the new entry's accession
    
    Because the variable was bound to a DML returning statement, 
    getvalue() returns a list
    
    References:
    https://cx-oracle.readthedocs.io/en/latest/variable.html#Variable.getvalue
    """
    accession = accession.getvalue()[0]

    # Integrate signatures (if any to integrated)
    signatures = set(request.json.get("signatures", []))
    if signatures:
        # Check first they all exist
        cur.execute(
            """
            SELECT METHOD_AC
            FROM {}.METHOD
            WHERE METHOD_AC IN ({})
            """.format(
                app.config["DB_SCHEMA"],
                ','.join([':'+str(i+1) for i in range(len(signatures))])
            ),
            tuple(signatures)
        )
        existing_signatures = {row[0] for row in cur}

        for acc in signatures:
            if acc not in existing_signatures:
                cur.close()
                return jsonify({
                    "status": False,
                    "error": {
                        "title": "Invalid signature",
                        "message": "<strong>{}</strong> is not a valid "
                                   "member database accession.".format(acc)
                    }
                }), 401

        try:
            cur.execute(
                """
                DELETE FROM INTERPRO.ENTRY2METHOD
                WHERE METHOD_AC IN ({})
                """.format(
                    ','.join(
                        [':' + str(i + 1) for i in range(len(signatures))])
                ),
                tuple(signatures)
            )

            cur.executemany(
                """
                INSERT INTO INTERPRO.ENTRY2METHOD (
                  ENTRY_AC, METHOD_AC, EVIDENCE
                )
                VALUES (:1, :2, 'MAN')
                """,
                [(accession, acc) for acc in signatures]
            )
        except DatabaseError as e:
            cur.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Database error",
                    "message": str(e)
                }
            }), 401

    con.commit()
    cur.close()
    return jsonify({
        "status": True,
        "accession": accession
    }), 200


@app.route("/api/entry/<accession>/")
def get_entry(accession):
    if executor.has(accession):
        return jsonify(None), 404

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          E.NAME,
          E.SHORT_NAME,
          E.ENTRY_TYPE,
          ET.ABBREV,
          E.CHECKED,
          CREATED.USERSTAMP,
          CREATED.TIMESTAMP,
          MODIFIED.USERSTAMP,
          MODIFIED.TIMESTAMP,
          (
            SELECT COUNT(*) 
            FROM INTERPRO.UNIRULE UR 
            INNER JOIN INTERPRO.ENTRY2METHOD EM 
              ON UR.METHOD_AC = EM.METHOD_AC 
              WHERE UR.ENTRY_AC = :acc 
                OR EM.ENTRY_AC = :acc
          )
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.CV_ENTRY_TYPE ET
          ON E.ENTRY_TYPE = ET.CODE
        LEFT OUTER JOIN (
          SELECT 
            A.ENTRY_AC, 
            NVL(U.NAME, A.DBUSER) AS USERSTAMP, 
            A.TIMESTAMP, 
            ROW_NUMBER() OVER (ORDER BY A.TIMESTAMP ASC) RN
          FROM INTERPRO.ENTRY_AUDIT A
          LEFT OUTER JOIN INTERPRO.PRONTO_USER U 
            ON A.DBUSER = U.DB_USER
          WHERE A.ENTRY_AC = :acc
        ) CREATED ON E.ENTRY_AC = CREATED.ENTRY_AC AND CREATED.RN = 1
        LEFT OUTER JOIN (
          SELECT 
            A.ENTRY_AC, 
            NVL(U.NAME, A.DBUSER) AS USERSTAMP, 
            A.TIMESTAMP, 
            ROW_NUMBER() OVER (ORDER BY A.TIMESTAMP DESC) RN
          FROM INTERPRO.ENTRY_AUDIT A
          LEFT OUTER JOIN INTERPRO.PRONTO_USER U 
            ON A.DBUSER = U.DB_USER
          WHERE A.ENTRY_AC = :acc
        ) MODIFIED ON E.ENTRY_AC = MODIFIED.ENTRY_AC AND MODIFIED.RN = 1
        WHERE E.ENTRY_AC = :acc
        """, dict(acc=accession)
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
            "creation": {
                "user": row[5],
                "date": row[6].strftime("%d %b %Y")
            },
            "last_modification": {
                "user": row[7],
                "date": row[8].strftime("%d %b %Y")
            },
            "unirule": row[9] > 0
        }
        return jsonify(entry), 200
    else:
        return jsonify(None), 404


@app.route("/api/entry/<accession>/", methods=["POST"])
def update_entry(accession):
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

    try:
        name = request.form["name"].strip()
        assert 0 < len(name) <= 30
    except (AssertionError, KeyError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid or missing parameter",
                "message": "'name' must be between 1 and 30 characters long."
            }
        }), 400

    try:
        description = request.form["description"].strip()
        assert 0 < len(description) <= 100
    except (AssertionError, KeyError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid or missing parameter",
                "message": "'description' must be between 1 "
                           "and 100 characters long."
            }
        }), 400

    try:
        _type = request.form["type"].strip()
    except KeyError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Missing parameter",
                "message": "'type' must be provided."
            }
        }), 400

    try:
        is_checked = int(request.form["checked"].strip())
    except (KeyError, ValueError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid or missing parameter",
                "message": "'checked' must be an integer."
            }
        }), 400

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT ENTRY_TYPE
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid entry",
                "message": "{} is not a "
                           "valid InterPro accession.".format(accession)
            }
        }), 404
    current_type = row[0]
    if _type == 'U':
        # Unknown type is not allowed
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid type",
                "message": "InterPro entries cannot be of type Unknown."
            }
        }), 400
    elif _type != current_type:
        # Check that we do not have relationships with other entries
        cur.execute(
            """
            SELECT COUNT(*)
            FROM INTERPRO.ENTRY2ENTRY
            WHERE ENTRY_AC = :acc
            OR PARENT_AC = :acc
            """,
            dict(acc=accession)
        )
        if cur.fetchone()[0]:
            cur.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Cannot update type",
                    "message": "{} cannot have its type changed because "
                               "it has InterPro relationships.".format(accession)
                }
            }), 400

    if is_checked:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM INTERPRO.ENTRY2METHOD
            WHERE ENTRY_AC = :1
            """, (accession,)
        )
        if not cur.fetchone()[0]:
            cur.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Cannot check entry",
                    "message": "{} cannot be checked because it does not have "
                               "any signatures.".format(accession)
                }
            }), 400

        cur.execute(
            """
            SELECT COUNT(*)
            FROM INTERPRO.ENTRY2COMMON
            WHERE ENTRY_AC = :1
            """, (accession,)
        )
        if not cur.fetchone()[0]:
            cur.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Cannot check entry",
                    "message": "{} cannot be checked because it does not have "
                               "any annotations.".format(accession)
                }
            }), 400
    try:
        cur.execute(
            """
            UPDATE INTERPRO.ENTRY
            SET 
              ENTRY_TYPE = :1, 
              NAME = :2,
              CHECKED = :3,
              SHORT_NAME = :4,
              TIMESTAMP = SYSDATE
            WHERE ENTRY_AC = :5
            """,
            (_type, description, 'Y' if is_checked else 'N', name, accession)
        )
    except DatabaseError as e:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not update {}.".format(accession)
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route("/api/entry/<accession>/", methods=["DELETE"])
def delete_entry(accession):
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
                "message": "{} is not a "
                           "valid InterPro accession.".format(accession)
            }
        }), 404

    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY2METHOD
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    n_signatures = cur.fetchone()[0]
    cur.close()

    if n_signatures:
        return jsonify({
            "status": False,
            "error": {
                "title": "Cannot delete entry",
                "message": "{} cannot be deleted because "
                           "it has one or more signatures.".format(accession)
            }
        }), 400
    else:
        dsn = app.config["ORACLE_DB"]["dsn"]
        executor.enqueue(accession, _delete_entry, user, dsn, accession)
        return jsonify({"status": True}), 202


@app.route("/api/entry/<accession>/check/", methods=["POST"])
def check_entry(accession):
    content = request.get_json()
    try:
        is_checked = bool(int(content["checked"]))
    except (KeyError, ValueError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

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

    if is_checked:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM INTERPRO.ENTRY2METHOD
            WHERE ENTRY_AC = :1
            """, (accession,)
        )
        if not cur.fetchone()[0]:
            cur.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Cannot check entry",
                    "message": "{} cannot be checked because it does not have "
                               "any signatures.".format(accession)
                }
            }), 400

        cur.execute(
            """
            SELECT COUNT(*)
            FROM INTERPRO.ENTRY2COMMON
            WHERE ENTRY_AC = :1
            """, (accession,)
        )
        if not cur.fetchone()[0]:
            cur.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Cannot check entry",
                    "message": "{} cannot be checked because it does not have "
                               "any annotations.".format(accession)
                }
            }), 400

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
            "error": {
                "title": "Database error",
                "message": "Could not update {}: {}".format(accession, e)
            }
        }), 500
    else:
        con.commit()
        cur.close()
        return jsonify({
            "status": True,
            "message": None
        }), 200

