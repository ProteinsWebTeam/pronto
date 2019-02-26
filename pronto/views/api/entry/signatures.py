import re
from cx_Oracle import DatabaseError
from flask import jsonify, request

from pronto import app, db, get_user, xref


@app.route("/api/entry/<e_acc>/signature/<s_acc>/", methods=['PUT'])
def integrate_signature(e_acc, s_acc):
    # If True, move a signature from one entry to another
    move_signature = request.form.get("confirm") is not None

    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC = :1
        """,
        (e_acc,)
    )
    if not cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid entry",
            "message": "<strong>{}</strong> is not "
                       "a valid InterPro accession".format(s_acc)
        }), 401

    cur.execute(
        """
        SELECT M.METHOD_AC, EM.ENTRY_AC
        FROM {}.METHOD M
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
          ON M.METHOD_AC = EM.METHOD_AC
        WHERE UPPER(M.METHOD_AC) = :acc 
        OR UPPER(M.NAME) = :acc
        """.format(app.config["DB_SCHEMA"]),
        dict(acc=s_acc.upper())
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid signature",
            "message": "<strong>{}</strong> is not a valid member database "
                       "accession or name.".format(s_acc)
        }), 401

    """
    Set to True if:
        - the signature is already integrated into another entry
        - we move the signature from this entry to `e_acc`
        - the signature was the *last* signature of the other entry
                -> the other entry must be unchecked 
    """
    unchecked = False

    s_acc, in_entry_acc = row
    if in_entry_acc == e_acc:
        # Already integrated in this entry: do noting
        cur.close()
        return jsonify({"status": True}), 200
    elif in_entry_acc:
        # Already integrated in an other entry

        if move_signature:
            try:
                cur.execute(
                    """
                    DELETE FROM INTERPRO.ENTRY2METHOD
                    WHERE ENTRY_AC = :1 AND METHOD_AC = :2
                    """,
                    (in_entry_acc, s_acc)
                )
            except DatabaseError:
                cur.close()
                return jsonify({
                    "status": False,
                    "title": "Database error",
                    "message": "Could not unintegrated "
                               "{} from {}".format(s_acc, in_entry_acc)
                }), 500

            cur.execute(
                """
                SELECT COUNT(*)
                FROM INTERPRO.ENTRY2METHOD
                WHERE ENTRY_AC  =:1
                """,
                (in_entry_acc,)
            )

            if not cur.fetchone()[0]:
                # Need to uncheck the entry
                try:
                    cur.execute(
                        """
                        UPDATE INTERPRO.ENTRY
                        SET CHECKED = 'N'
                        WHERE ENTRY_AC = :1
                        """,
                        (in_entry_acc,)
                    )
                except DatabaseError:
                    cur.close()
                    return jsonify({
                        "status": False,
                        "title": "Database error",
                        "message": "Could not uncheck {}".format(in_entry_acc)
                    }), 500
                else:
                    unchecked = True
        else:
            # Ask for confirmation
            cur.close()
            return jsonify({
                "status": True,
                "signature": s_acc,
                "entry": in_entry_acc
            }), 200

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY2METHOD (ENTRY_AC, METHOD_AC, EVIDENCE) 
            VALUES (:1, :2, 'MAN')
            """,
            (e_acc, s_acc)
        )
    except DatabaseError:
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "Could not integrated "
                       "{} into {}".format(s_acc, e_acc)
        }), 500
    else:
        con.commit()
        if unchecked:
            res = {
                "status": True,
                "unchecked": unchecked,
                "entry": in_entry_acc
            }
        else:
            res = {
                "status": True
            }

        return jsonify(res), 200
    finally:
        cur.close()


@app.route("/api/entry/<e_acc>/signature/<s_acc>/", methods=['DELETE'])
def unintegrate_signature(e_acc, s_acc):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC = :1
        """,
        (e_acc,)
    )
    if not cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid entry",
            "message": "<strong>{}</strong> is not "
                       "a valid InterPro accession".format(s_acc)
        }), 401

    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY2METHOD
            WHERE ENTRY_AC = :1 
            AND METHOD_AC = :2
            """,
            (e_acc, s_acc)
        )
    except DatabaseError:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "Could not unintegrated "
                       "{} from {}".format(s_acc, e_acc)
        }), 500

    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY2METHOD
        WHERE ENTRY_AC  =:1
        """,
        (e_acc,)
    )

    unchecked = False
    if not cur.fetchone()[0]:
        # Need to uncheck the entry
        try:
            cur.execute(
                """
                UPDATE INTERPRO.ENTRY
                SET CHECKED = 'N'
                WHERE ENTRY_AC = :1
                """,
                (e_acc,)
            )
        except DatabaseError:
            con.rollback()  # rollback pending transactions
            cur.close()
            return jsonify({
                "status": False,
                "title": "Database error",
                "message": "Could not uncheck {}".format(e_acc)
            }), 500
        else:
            unchecked = True

    con.commit()
    cur.close()
    return jsonify({
        "status": True,
        "unchecked": unchecked
    }), 200


@app.route("/api/entry/<accession>/signatures/")
def get_entry_signatures(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          DBCODE,
          METHOD_AC,
          NAME,
          PROTEIN_COUNT
        FROM {}.METHOD
        WHERE METHOD_AC IN (
          SELECT METHOD_AC
          FROM INTERPRO.ENTRY2METHOD
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
            "num_proteins": row[3],
            "link": database.gen_link(),
            "color": database.color,
            "database": database.name
        })

    cur.close()
    return jsonify(signatures), 200


def repl_dbxref(match):
    db = match.group(1).lower().strip()
    ac = match.group(2).strip()

    if db == "ec":
        db = "intenz"
    elif db == "ssf":
        db = "superfamily"

    return "[{}:{}]".format(db, ac)


def format_abstract(text):
    text = re.sub(r"PMID:(\d+)", r"[cite:\1]", text, flags=re.I)
    text = re.sub(r'<\s*cite\s*id="(PUB\d+)"\s*/?\s*>', r"[cite:\1]", text, flags=re.I)
    return re.sub(r'<\s*dbxref\s*db="(.*?)"\s*id="(.*?)"\s*/>', repl_dbxref, text, flags=re.I)


@app.route("/api/entry/<accession>/signatures/annotations/")
def get_entry_signatures_annotations(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          METHOD_AC,
          NAME,
          ABSTRACT,
          ABSTRACT_LONG
        FROM {}.METHOD
        WHERE METHOD_AC IN (
          SELECT METHOD_AC
          FROM INTERPRO.ENTRY2METHOD
          WHERE ENTRY_AC = :1
        )
        ORDER BY METHOD_AC
        """.format(app.config['DB_SCHEMA']),
        (accession,)
    )

    signatures = []
    for row in cur:
        if row[2] is not None:
            text = row[2]
        elif row[3] is not None:
            text = row[3].read()  # CLOB object
        else:
            text = None

        signatures.append({
            "accession": row[0],
            "name": row[1],
            "text": format_abstract(text)
        })

    cur.close()
    return jsonify(signatures), 200
