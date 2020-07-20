# -*- coding: utf-8 -*-

import re

from cx_Oracle import DatabaseError
from flask import jsonify, request

from pronto import auth, utils
from . import bp


@bp.route("/<accession>/signatures/")
def get_signatures(accession):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT METHOD_AC, EM.TIMESTAMP, NVL(U.NAME, EM.USERSTAMP)
        FROM INTERPRO.ENTRY2METHOD EM
        LEFT OUTER JOIN INTERPRO.PRONTO_USER U 
            ON EM.USERSTAMP = U.DB_USER
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    integrated = {row[0]: f"{row[2]} ({row[1]:%d %b %Y})" for row in cur}

    cur.close()
    con.close()

    signatures = []
    if integrated:
        accessions = list(integrated.keys())
        con = utils.connect_pg(utils.get_pg_url())
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT 
              s.accession, s.name, s.num_sequences, s.num_complete_sequences,
              d.name, d.name_long
            FROM interpro.signature s
            INNER JOIN interpro.database d
            ON s.database_id = d.id
            WHERE s.accession IN ({','.join('%s' for _ in accessions)})
            ORDER BY accession
            """, accessions
        )

        for row in cur:
            db = utils.get_database_obj(row[4])
            signatures.append({
                "accession": row[0],
                "name": row[1],
                "sequences": {
                    "all": row[2],
                    "complete": row[3]
                },
                "database": {
                    "color": db.color,
                    "link": db.gen_link(row[0]),
                    "name": row[5]
                },
                "date": integrated[row[0]]
            })

        cur.close()
        con.close()
    return jsonify(signatures)


@bp.route("/<e_acc>/signature/<s_acc>/", methods=["PUT"])
def integrate_signature(e_acc, s_acc):
    confirmed = request.form.get("confirmed") is not None

    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this operation."
            }
        }), 401

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT M.METHOD_AC, EM.ENTRY_AC, E.CHECKED
        FROM INTERPRO.METHOD M 
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
          ON M.METHOD_AC = EM.METHOD_AC 
        LEFT OUTER JOIN INTERPRO.ENTRY E 
          ON EM.ENTRY_AC = E.ENTRY_AC
        WHERE M.METHOD_AC = :1
        """, (s_acc,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid signature",
                "message": f"{s_acc} is not a valid member database signature."
            }
        }), 400

    _, from_entry, is_checked = row
    if from_entry:
        if from_entry == e_acc:
            # Signature already integrated in desired entry
            cur.close()
            con.close()
            return jsonify({"status": True}), 200

        is_checked = is_checked == 'Y'

        cur.execute(
            """
            SELECT COUNT(*)
            FROM INTERPRO.ENTRY2METHOD
            WHERE ENTRY_AC = :1
            """, (from_entry,)
        )
        num_signatures, = cur.fetchone()
        if is_checked and num_signatures == 1:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Cannot unintegrate signature",
                    "message": f"{s_acc} is integrated in {e_acc}, "
                               f"and cannot be unintegrated because "
                               f"it would leave a checked entry "
                               f"without signatures."
                }
            }), 409
        elif not confirmed:
            cur.close()
            con.close()
            return jsonify({
                "status": True,
                "confirm_for": from_entry
            }), 200

        try:
            cur.execute(
                """
                DELETE FROM INTERPRO.ENTRY2METHOD
                WHERE ENTRY_AC = :1 AND METHOD_AC = :2
                """, (from_entry, s_acc)
            )
        except DatabaseError as exc:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Database error",
                    "message": f"Could not unintegrated {s_acc} "
                               f"from {from_entry}: {exc}."
                }
            }), 500

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY2METHOD (ENTRY_AC, METHOD_AC, EVIDENCE) 
            VALUES (:1, :2, 'MAN')
            """, (e_acc, s_acc)
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not integrate {s_acc} into {e_acc}: {exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<e_acc>/signature/<s_acc>/", methods=["DELETE"])
def unintegrate_signature(e_acc, s_acc):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this operation."
            }
        }), 401

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT CHECKED
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC = :1
        """, (e_acc,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid entry",
                "message": f"{e_acc} is not a valid InterPro entry."
            }
        }), 400
    is_checked = row[0] == 'Y'

    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY2METHOD
        WHERE ENTRY_AC = :1 AND METHOD_AC != :2
        """, (e_acc, s_acc)
    )
    other_signatures, = cur.fetchone()
    if is_checked and not other_signatures:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Cannot unintegrate signature",
                "message": f"Unintegrating {s_acc} would leave {e_acc} "
                           f"without signatures. Checked entries must "
                           f"have at least one signature."
            }
        }), 409

    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY2METHOD
            WHERE ENTRY_AC = :1 
            AND METHOD_AC = :2
            """,
            (e_acc, s_acc)
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not unintegrated {s_acc} from {e_acc}: "
                           f"{exc}"
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True,
        }), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/signatures/annotations/")
def get_signatures_annotations(accession):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT METHOD_AC 
        FROM INTERPRO.ENTRY2METHOD 
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    signatures = [acc for acc, in cur]
    cur.close()
    con.close()

    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT accession, name, abstract
        FROM interpro.signature
        WHERE accession IN ({','.join('%s' for _ in signatures)})
        ORDER BY accession
        """, signatures
    )

    signatures = []
    for accession, name, text in cur:
        signatures.append({
            "accession": accession,
            "name": name,
            "text": text
        })

    cur.close()
    con.close()
    return jsonify(signatures)
