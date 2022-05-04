# -*- coding: utf-8 -*-

import cx_Oracle
from flask import Blueprint, jsonify, request

bp = Blueprint("api.entry", __name__, url_prefix="/api/entry")

from pronto import auth, utils
from . import annotations
from . import comments
from . import go
from . import references
from . import relationships
from . import signatures


@bp.route("/<accession>/")
def get_entry(accession):
    con = utils.connect_oracle()
    cur = con.cursor()
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
          MODIFIED.TIMESTAMP
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
        """,
        dict(acc=accession),
    )

    row = cur.fetchone()
    cur.close()
    if row:
        entry = {
            "accession": accession,
            "name": row[0],
            "short_name": row[1],
            "type": {"code": row[2], "name": row[3].replace("_", " ")},
            "is_checked": row[4] == "Y",
            "creation": {"user": row[5], "date": row[6].strftime("%d %b %Y")},
            "last_modification": {"user": row[7], "date": row[8].strftime("%d %b %Y")},
        }
        return jsonify(entry), 200
    else:
        return jsonify(None), 404


@bp.route("/<accession>/", methods=["POST"])
def update_entry(accession):
    user = auth.get_user()
    if not user:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Access denied",
                        "message": "Please log in to perform this action.",
                    },
                }
            ),
            401,
        )

    try:
        entry_type = request.json["type"].strip()
        entry_name = request.json["name"].strip()
        entry_short_name = request.json["short_name"].strip()
        entry_checked = bool(request.json["checked"])
    except KeyError:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {"title": "Bad request", "message": "Invalid or missing parameters."},
                }
            ),
            400,
        )

    if len(entry_name) > 100:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Name too long",
                        "message": "Entry names cannot be longer than 100 characters.",
                    },
                }
            ),
            400,
        )
    elif len(entry_short_name) > 30:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Short name too long",
                        "message": "Entry short names cannot be longer than " "30 characters.",
                    },
                }
            ),
            400,
        )

    errors = set()
    for char in entry_name:
        if not char.isascii():
            errors.add(char)

    for char in entry_short_name:
        if not char.isascii():
            errors.add(char)

    if errors:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Invalid name or short name",
                        "message": f"Invalid character(s): {', '.join(errors)}",
                    },
                }
            ),
            400,
        )

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC != :1 AND UPPER(NAME) = :2
        """,
        (accession, entry_name.upper(),),
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Invalid name",
                        "message": f"Name already used by another entry ({row[0]}). "
                        f"Names must be unique.",
                    },
                }
            ),
            400,
        )

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC != :1 AND UPPER(SHORT_NAME) = :1
        """,
        (accession, entry_short_name.upper(),),
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Invalid short name",
                        "message": f"Short name already used by another entry "
                        f"({row[0]}). Short names must be unique.",
                    },
                }
            ),
            400,
        )

    cur.execute(
        """
        SELECT ENTRY_TYPE, NAME, SHORT_NAME, CHECKED
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC = :1
        """,
        (accession,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Entry not found",
                        "message": f"InterPro entry {accession} does not exist.",
                    },
                }
            ),
            400,
        )

    params = (entry_type, entry_name, entry_short_name, "Y" if entry_checked else "N")
    if params == row:
        # Nothing to do
        cur.close()
        con.close()
        return jsonify({"status": True})
    elif entry_checked:
        cur.execute(
            """
            SELECT METHOD_AC
            FROM INTERPRO.ENTRY2METHOD
            WHERE ENTRY_AC = :1
            """,
            (accession,),
        )
        integrated = [acc for acc, in cur]
        if not integrated:
            cur.close()
            con.close()
            return (
                jsonify(
                    {
                        "status": False,
                        "error": {
                            "title": "No annotations",
                            "message": f"{accession} does not have annotations. "
                            f"Entries without annotations "
                            f"cannot be checked.",
                        },
                    }
                ),
                409,
            )

        con2 = utils.connect_pg(utils.get_pg_url())
        cur2 = con2.cursor()
        cur2.execute(
            f"""
            SELECT COUNT(*)
            FROM interpro.signature
            WHERE accession IN ({','.join('%s' for _ in integrated)})
            AND num_sequences = 0
            """,
            integrated,
        )
        (cnt,) = cur2.fetchone()
        cur2.close()
        con2.close()

        if cnt:
            cur.close()
            con.close()
            return (
                jsonify(
                    {
                        "status": False,
                        "error": {
                            "title": "Integrated signatures with no matches",
                            "message": f"{accession} integrates one or more signatures"
                            f" not matching any protein.",
                        },
                    }
                ),
                409,
            )

    try:
        cur.execute(
            """
            UPDATE INTERPRO.ENTRY
            SET ENTRY_TYPE = :1, 
                NAME = :2, 
                SHORT_NAME = :3, 
                CHECKED = :4,
                TIMESTAMP = SYSDATE,
                USERSTAMP = USER
            WHERE ENTRY_AC = :5
            """,
            (*params, accession),
        )
    except cx_Oracle.DatabaseError as exc:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Database error",
                        "message": f"Could not update entry {accession}: {exc}.",
                    },
                }
            ),
            500,
        )
    else:
        con.commit()
        return jsonify({"status": True})
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/", methods=["DELETE"])
def delete_entry(accession):
    user = auth.get_user()
    if not user:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Access denied",
                        "message": "Please log in to perform this action.",
                    },
                }
            ),
            401,
        )

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY2METHOD
        WHERE ENTRY_AC = :1
        """,
        (accession,),
    )
    if cur.fetchone()[0]:
        cur.close()
        con.close()
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Cannot delete entry",
                        "message": f"{accession} cannot be deleted because "
                        f"it integrates one or more signatures.",
                    },
                }
            ),
            409,
        )

    cur.close()
    con.close()

    url = utils.get_oracle_url(user)
    task = utils.executor.submit(url, f"delete:{accession}", _delete_entry, url, accession)
    return jsonify({"status": True, "task": task}), 202


def _delete_entry(url: str, accession: str):
    con = cx_Oracle.connect(url)
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY
            WHERE ENTRY_AC = :1
            """,
            (accession,),
        )
    except cx_Oracle.DatabaseError as exc:
        raise exc
    else:
        con.commit()
    finally:
        cur.close()
        con.close()


@bp.route("/", methods=["PUT"])
def create_entry():
    user = auth.get_user()
    if not user:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Access denied",
                        "message": "Please log in to perform this action.",
                    },
                }
            ),
            401,
        )

    try:
        entry_type = request.json["type"].strip()
        entry_name = request.json["name"].strip()
        entry_short_name = request.json["short_name"].strip()
    except KeyError:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {"title": "Bad request", "message": "Invalid or missing parameters."},
                }
            ),
            400,
        )

    entry_signatures = set(request.json.get("signatures", []))
    if not signatures:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Bad request",
                        "message": "Creating an InterPro entry requires at least " "one signature.",
                    },
                }
            ),
            400,
        )
    elif entry_type == "U":
        # Unknown type is not allowed
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Invalid type",
                        "message": "InterPro entries cannot be of type Unknown.",
                    },
                }
            ),
            400,
        )

    if len(entry_name) > 100:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Name too long",
                        "message": "Entry names cannot be longer than 100 characters.",
                    },
                }
            ),
            400,
        )
    elif len(entry_short_name) > 30:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Short name too long",
                        "message": "Entry short names cannot be longer than " "30 characters.",
                    },
                }
            ),
            400,
        )

    errors = set()
    for char in entry_name:
        if not char.isascii():
            errors.add(char)

    for char in entry_short_name:
        if not char.isascii():
            errors.add(char)

    if errors:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Invalid name or short name",
                        "message": f"Invalid character(s): {', '.join(errors)}",
                    },
                }
            ),
            400,
        )

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    if entry_signatures:
        stmt = [":" + str(i + 1) for i in range(len(entry_signatures))]
        cur.execute(
            f"""
            SELECT M.METHOD_AC, E.ENTRY_AC, E.CHECKED, X.CNT
            FROM INTERPRO.METHOD M
            LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM
              ON M.METHOD_AC = EM.METHOD_AC 
            LEFT OUTER JOIN INTERPRO.ENTRY E
              ON EM.ENTRY_AC = E.ENTRY_AC
            LEFT OUTER JOIN (
                SELECT ENTRY_AC, COUNT(*) AS CNT
                FROM INTERPRO.ENTRY2METHOD
                GROUP BY ENTRY_AC
            ) X ON E.ENTRY_AC = X.ENTRY_AC
            WHERE M.METHOD_AC IN ({','.join(stmt)})
            """,
            tuple(entry_signatures),
        )
        existing_signatures = {}
        for row in cur:
            existing_signatures[row[0]] = (row[1], row[2] == "Y", row[3])

        to_unintegrate = []
        not_found = []
        invalid = []
        for signature_acc in entry_signatures:
            try:
                entry_acc, is_checked, cnt = existing_signatures[signature_acc]
            except KeyError:
                not_found.append(signature_acc)
            else:
                if entry_acc is not None:
                    if is_checked and cnt == 1:
                        invalid.append(signature_acc)
                    else:
                        to_unintegrate.append((entry_acc, signature_acc))

        if not_found:
            cur.close()
            con.close()
            return (
                jsonify(
                    {
                        "status": False,
                        "error": {
                            "title": "Invalid signature(s)",
                            "message": f"One or more parameters are not valid "
                            f"member database signatures "
                            f"{', '.join(sorted(not_found))}.",
                        },
                    }
                ),
                400,
            )
        elif invalid:
            cur.close()
            con.close()
            return (
                jsonify(
                    {
                        "status": False,
                        "error": {
                            "title": "Cannot unintegrate signature(s)",
                            "message": f"One or more signatures are integrated "
                            f"in checked entries that only have "
                            f"one signature: {', '.join(invalid)}. "
                            f"Checked entries cannot be left "
                            f"with no signatures.",
                        },
                    }
                ),
                409,
            )

        # Unintegrate signatures
        try:
            cur.executemany(
                """
                DELETE FROM INTERPRO.ENTRY2METHOD
                WHERE ENTRY_AC = :1 AND METHOD_AC = :2
                """,
                to_unintegrate,
            )
        except cx_Oracle.DatabaseError as exc:
            cur.close()
            con.close()
            return (
                jsonify(
                    {
                        "status": False,
                        "error": {
                            "title": "Database error",
                            "message": f"Signature(s) could not be unintegrated: " f"{exc}.",
                        },
                    }
                ),
                500,
            )

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE UPPER(NAME) = :1
        """,
        (entry_name.upper(),),
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Invalid name",
                        "message": f"Name already used by another entry ({row[0]}). "
                        f"Names must be unique.",
                    },
                }
            ),
            400,
        )

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE UPPER(SHORT_NAME) = :1
        """,
        (entry_short_name.upper(),),
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Invalid short name",
                        "message": f"Short name already used by another entry "
                        f"({row[0]}). Short names must be unique.",
                    },
                }
            ),
            400,
        )

    entry_var = cur.var(cx_Oracle.STRING)
    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY (ENTRY_AC, ENTRY_TYPE, NAME, SHORT_NAME) 
            VALUES (INTERPRO.NEW_ENTRY_AC(), :1, :2, :3)
            RETURNING ENTRY_AC INTO :4
            """,
            (entry_type, entry_name, entry_short_name, entry_var),
        )

        entry_acc = entry_var.getvalue()[0]
        cur.executemany(
            """
            INSERT INTO INTERPRO.ENTRY2METHOD (ENTRY_AC, METHOD_AC, EVIDENCE) 
            VALUES (:1, :2, 'MAN')
            """,
            [(entry_acc, s_acc) for s_acc in entry_signatures],
        )
    except cx_Oracle.DatabaseError as exc:
        return (
            jsonify(
                {
                    "status": False,
                    "error": {
                        "title": "Database error",
                        "message": f"Could not create entry: {exc}.",
                    },
                }
            ),
            500,
        )
    else:
        con.commit()
        return jsonify({"status": True, "accession": entry_acc})
    finally:
        cur.close()
        con.close()
