import re
from datetime import datetime


import oracledb
from flask import Blueprint, jsonify, request

from pronto.api.entry.utils import sanitize_description, sanitize_name, sanitize_short_name, sanitize_domain

bp = Blueprint("api_entry", __name__, url_prefix="/api/entry")

from pronto import auth, utils
from pronto.api import annotation
from pronto.api.entry.annotations import relate_entry_to_anno
from pronto.api.signature import is_amr
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
          E.LLM,
          E.LLM_CHECKED,
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
                "name": row[3].replace("_", " ")
            },
            "status": {
                "checked": row[4] == "Y",
                "llm": row[5] == "Y",
                "reviewed": row[6] == "Y"
            },
            "creation": {
                "user": row[7],
                "date": row[8].strftime("%d %b %Y")
            },
            "last_modification": {
                "user": row[9],
                "date": row[10].strftime("%d %b %Y")
            }
        }
        return jsonify(entry), 200
    else:
        return jsonify(None), 404


@bp.route("/<accession>/", methods=["POST"])
def update_entry(accession):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401
    elif utils.get_states().frozen:
        return jsonify({
            "status": False,
            "error": {
                "title": "Forbidden",
                "message": "Curation is disabled due to release procedures."
            }
        }), 403

    try:
        entry_type = request.json["type"].strip()
        entry_name = request.json["name"].strip()
        entry_short_name = request.json["short-name"].strip()
        entry_checked = bool(request.json["checked"])
        entry_llm = bool(request.json["llm"])
        entry_llm_reviewed = bool(request.json["llm-reviewed"])
    except KeyError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    if len(entry_name) > 100:
        return jsonify({
            "status": False,
            "error": {
                "title": "Name too long",
                "message": "Entry names cannot be longer than 100 characters."
            }
        }), 400
    elif len(entry_short_name) > 30:
        return jsonify({
            "status": False,
            "error": {
                "title": "Short name too long",
                "message": "Entry short names cannot be longer than "
                           "30 characters."
            }
        }), 400
    elif re.search(r"\s{2,}", entry_name):
        return jsonify({
            "status": False,
            "error": {
                "title": "Multiple space detected",
                "message": "Entry names cannot contain multiple consecutive "
                           "spaces."
            }
        }), 400
    elif not entry_llm:
        entry_llm_reviewed = False

    errors = set()
    for char in entry_name:
        if not char.isascii():
            errors.add(char)

    for char in entry_short_name:
        if not char.isascii():
            errors.add(char)

    if errors:
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid name or short name",
                "message": f"Invalid character(s): {', '.join(errors)}"
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC != :1 AND UPPER(NAME) = :2
        """,
        [accession, entry_name.upper()]
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid name",
                "message": f"Name already used by another entry ({row[0]}). "
                           f"Names must be unique."
            }
        }), 400

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC != :1 AND UPPER(SHORT_NAME) = :1
        """,
        [accession, entry_short_name.upper()]
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid short name",
                "message": f"Short name already used by another entry "
                           f"({row[0]}). Short names must be unique."
            }
        }), 400

    cur.execute(
        """
        SELECT ENTRY_TYPE, NAME, SHORT_NAME, CHECKED, LLM, LLM_CHECKED
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC = :1
        """,
        [accession]
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Entry not found",
                "message": f"InterPro entry {accession} does not exist."
            }
        }), 400

    row = list(row)
    current_name = row[1]
    current_short_name = row[2]
    is_llm = row[4] == "Y"
    is_llm_reviewed = row[5] == "Y"

    if not is_llm and entry_llm:
        # Human -> AI: not allowed
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Action not permitted",
                "message": f"{accession} is a human-curated entry, "
                           f"it cannot be marked as AI-generated."
            }
        }), 400
    elif entry_llm and not entry_llm_reviewed and is_llm_reviewed:
        return jsonify({
            "status": False,
            "error": {
                "title": "Action not permitted",
                "message": f"{accession} is an AI-generated entry that "
                           f"has already been reviewed. "
                           f"Unreviewing is not permitted."
            }
        }), 400

    commit = False
    if not entry_llm or entry_llm_reviewed:
        if not entry_llm:
            set_sql = "LLM = 'N', CHECKED = 'N'"
            where_sql = "LLM = 'Y'"
            action = "Curated"
        else:
            set_sql = "CHECKED = 'Y'"
            where_sql = "LLM = 'Y' AND CHECKED = 'N'"
            action = "Reviewed"

        comment = (f"{action} by {user['name'].split()[0]} "
                   f"on {datetime.now():%Y-%m-%d %H:%M:%S}")

        try:
            cur.execute(
                f"""
                UPDATE INTERPRO.COMMON_ANNOTATION
                SET {set_sql}, COMMENTS = :1
                WHERE ANN_ID IN (
                    SELECT ANN_ID
                    FROM INTERPRO.ENTRY2COMMON
                    WHERE ENTRY_AC = :2
                )
                AND {where_sql}
                """,
                [comment, accession]
            )
        except oracledb.DatabaseError as exc:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Database error",
                    "message": f"Could not mark AI-generated annotations "
                               f"as reviewed for entry {accession}: {exc}."
                }
            }), 500
        else:
            commit = True

    unchanged = True
    for now, new in zip(row, [entry_type, entry_name, entry_short_name,
                              "Y" if entry_checked else "N",
                              "Y" if entry_llm else "N",
                              "Y" if entry_llm_reviewed else "N"]):
        if now != new:
            unchanged = False
            break

    if unchanged:
        if commit:
            con.commit()
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
            [accession]
        )
        integrated = [acc for acc, in cur]
        if not integrated:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "No annotations",
                    "message": f"{accession} does not have annotations. "
                               f"Entries without annotations "
                               f"cannot be checked."
                }
            }), 409

        con2 = utils.connect_pg(utils.get_pg_url())
        cur2 = con2.cursor()
        cur2.execute(
            f"""
            SELECT COUNT(*)
            FROM interpro.signature
            WHERE accession IN ({','.join('%s' for _ in integrated)})
            AND num_sequences = 0
            """,
            integrated
        )
        cnt, = cur2.fetchone()
        cur2.close()
        con2.close()

        if cnt:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Integrated signatures with no matches",
                    "message": f"{accession} integrates one or more signatures"
                               f" not matching any protein."
                }
            }), 409

    if (is_llm and
            (current_name != entry_name or
             current_short_name != entry_short_name)):
        # LLM and difference in name/short name: mark as reviewed
        entry_llm_reviewed = True

    try:
        cur.execute(
            """
            UPDATE INTERPRO.ENTRY
            SET ENTRY_TYPE = :1, 
                NAME = :2, 
                SHORT_NAME = :3, 
                CHECKED = :4,
                LLM = :5,
                LLM_CHECKED = :6,
                TIMESTAMP = SYSDATE,
                USERSTAMP = USER
            WHERE ENTRY_AC = :7
            """,
            [entry_type, entry_name, entry_short_name,
             "Y" if entry_checked else "N",
             "Y" if entry_llm else "N",
             "Y" if entry_llm_reviewed else "N",
             accession]
        )
    except oracledb.DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not update entry {accession}: {exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True})
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/", methods=["DELETE"])
def delete_entry(accession):
    delete_annotations = "delete-annotations" in request.args
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401
    elif utils.get_states().frozen:
        return jsonify({
            "status": False,
            "error": {
                "title": "Forbidden",
                "message": "Curation is disabled due to release procedures."
            }
        }), 403

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY2METHOD
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    if cur.fetchone()[0]:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Cannot delete entry",
                "message": f"{accession} cannot be deleted because "
                           f"it integrates one or more signatures."
            }
        }), 409

    cur.close()
    con.close()

    url = utils.get_oracle_url(user)
    task = utils.executor.submit(url, f"delete:{accession}", _delete_entry,
                                 url, accession, delete_annotations)
    return jsonify({
        "status": True,
        "task": task
    }), 202


def _delete_entry(url: str, accession: str, delete_annotations: bool):
    con = oracledb.connect(url)
    cur = con.cursor()

    if delete_annotations:
        try:
            cur.execute(
                """
                DELETE FROM INTERPRO.COMMON_ANNOTATION
                WHERE ANN_ID IN (
                    SELECT DISTINCT EC1.ANN_ID
                    FROM INTERPRO.ENTRY2COMMON EC1
                    LEFT JOIN INTERPRO.ENTRY2COMMON EC2 
                           ON EC1.ANN_ID = EC2.ANN_ID 
                          AND EC2.ENTRY_AC != :entry
                    WHERE EC1.ENTRY_AC = :entry
                      AND EC2.ANN_ID IS NULL
                )
                """,
                dict(entry=accession)
            )
        except oracledb.DatabaseError as exc:
            cur.close()
            con.close()
            raise exc

    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY
            WHERE ENTRY_AC = :1
            """, (accession,)
        )
    except oracledb.DatabaseError as exc:
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
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401
    elif utils.get_states().frozen:
        return jsonify({
            "status": False,
            "error": {
                "title": "Forbidden",
                "message": "Curation is disabled due to release procedures."
            }
        }), 403

    try:
        entry_type = request.json["type"].strip()
        entry_name = request.json["name"].strip()
        entry_short_name = request.json["short_name"].strip()
        entry_llm = request.json["is_llm"]
    except KeyError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    try:
        is_llm_reviewed = request.json["is_llm_reviewed"]
    except KeyError:
        is_llm_reviewed = entry_llm

    try:
        is_checked = request.json["is_checked"]
    except KeyError:
        is_checked = False

    try:
        automatic = request.json["automatic"]
    except KeyError:
        automatic = False

    entry_signatures = list(set(request.json.get("signatures", [])))
    if not entry_signatures:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Creating an InterPro entry requires at least "
                           "one signature."
            }
        }), 400

    if len(entry_name) > 100:
        return jsonify({
            "status": False,
            "error": {
                "title": "Name too long",
                "message": "Entry names cannot be longer than 100 characters."
            }
        }), 400
    elif len(entry_short_name) > 30:
        return jsonify({
            "status": False,
            "error": {
                "title": "Short name too long",
                "message": "Entry short names cannot be longer than "
                           "30 characters."
            }
        }), 400

    errors = set()
    for char in entry_name:
        if not char.isascii():
            errors.add(char)

    for char in entry_short_name:
        if not char.isascii():
            errors.add(char)

    if errors:
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid name or short name",
                "message": f"Invalid character(s): {', '.join(errors)}"
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    if len(entry_signatures) > 1:
        for sig_acc in entry_signatures:
            if is_amr(cur, sig_acc):
                cur.close()
                con.close()
                return jsonify({
                    "status": False,
                    "error": {
                        "title": "AMR model",
                        "message": f"{sig_acc} is an AMR model. AMR models cannot be integrated with other signatures."
                    }
                }), 400

    entries = check_uniqueness(cur, entry_name, entry_short_name)
    if entries:
        if automatic:
            count = 2
            while True:
                temp_name = f"{entry_name} {count}"
                temp_short_name = f"{entry_short_name}_{count}"
                if not check_uniqueness(cur, temp_name, temp_short_name):
                    entry_name = temp_name
                    entry_short_name = temp_short_name
                    break
                count += 1
        else:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Bad request",
                    "message": "The name or short name is already in use.",
                    "entries": entries
                }
            }), 400

    stmt = [':'+str(i+1) for i in range(len(entry_signatures))]
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
        list(entry_signatures)
    )
    existing_signatures = {}
    for row in cur:
        existing_signatures[row[0]] = (
            row[1],
            row[2] == 'Y',
            row[3]
        )

    to_unintegrate = []
    not_found = []
    invalid = []
    for signature_acc in entry_signatures:
        try:
            entry_acc, entry_checked, cnt = existing_signatures[signature_acc]
        except KeyError:
            not_found.append(signature_acc)
        else:
            if entry_acc is not None:
                if entry_checked and cnt == 1:
                    invalid.append(signature_acc)
                else:
                    to_unintegrate.append((entry_acc, signature_acc))

    if not_found:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid signature(s)",
                "message": f"One or more parameters are not valid "
                           f"member database signatures "
                           f"{', '.join(sorted(not_found))}."
            }
        }), 400
    # June 2023: curators no longer want it to be possible to transfer
    #            integrated signature to a new entry
    elif invalid or to_unintegrate:
        cur.close()
        con.close()
        invalid += [signature_acc for (entry_acc, signature_acc)
                    in to_unintegrate]
        return jsonify({
            "status": False,
            "error": {
                "title": "Integrated signature(s)",
                "message": f"The following signatures are already "
                           f"integrated: {', '.join(sorted(invalid))}."
            }
        }), 409
    # elif invalid:
    #     cur.close()
    #     con.close()
    #     return jsonify({
    #         "status": False,
    #         "error": {
    #             "title": "Cannot unintegrate signature(s)",
    #             "message": f"One or more signatures are integrated "
    #                        f"in checked entries that only have "
    #                        f"one signature: {', '.join(invalid)}. "
    #                        f"Checked entries cannot be left "
    #                        f"with no signatures."
    #         }
    #     }), 409

    if to_unintegrate:
        # Unintegrate signatures
        try:
            cur.executemany(
                """
                DELETE FROM INTERPRO.ENTRY2METHOD
                WHERE ENTRY_AC = :1 AND METHOD_AC = :2
                """,
                to_unintegrate
            )
        except oracledb.DatabaseError as exc:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Database error",
                    "message": f"Signature(s) could not be unintegrated: "
                               f"{exc}."
                }
            }), 500

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE UPPER(NAME) = :1
        """,
        [entry_name.upper()]
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid name",
                "message": f"Name already used by another entry ({row[0]}). "
                           f"Names must be unique."
            }
        }), 400

    # Get signatures references
    cur.execute(
        f"""
        SELECT DISTINCT PUB_ID
        FROM INTERPRO.METHOD2PUB
        WHERE METHOD_AC IN ({','.join(stmt)})
        """,
        list(entry_signatures)
    )
    new_references = [pub_id for pub_id, in cur.fetchall()]

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE UPPER(SHORT_NAME) = :1
        """,
        [entry_short_name.upper()]
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid short name",
                "message": f"Short name already used by another entry "
                           f"({row[0]}). Short names must be unique."
            }
        }), 400

    if automatic:
        """ 
        During autointegration, infer type from name 
        Check for "containing protein" first, as it can be found also in domains. 
        Then, check:
            - Pfam repeats
            - name (description) ending with "domain"
            - name (description) containing "terminal region" or "conserved region"
        """ 

        is_pfam_repeat = re.match(r"^PF\d{5}$", entry_signatures[0]) and entry_type == 'R'
        has_region_expressions = any([key in entry_name for 
                                    key in ["terminal region", "conserved region"]])
        
        if "containing protein" in entry_name:
            entry_type = 'F'
        
        if entry_name.endswith("domain") or has_region_expressions or is_pfam_repeat:
            entry_type = 'D'

        entry_short_name = sanitize_short_name(entry_short_name)
        entry_name = sanitize_name(entry_name)

    entry_var = cur.var(oracledb.STRING)
    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY (
                ENTRY_AC,
                ENTRY_TYPE,
                NAME,
                SHORT_NAME,
                LLM,
                LLM_CHECKED,
                CHECKED
            )
            VALUES (INTERPRO.NEW_ENTRY_AC(), :1, :2, :3, :4, :5, :6)
            RETURNING ENTRY_AC INTO :7
            """,
            [
                entry_type,
                entry_name,
                entry_short_name,
                "Y" if entry_llm else "N",
                "Y" if is_llm_reviewed else "N",
                "Y" if is_checked else "N",
                entry_var,
            ]
        )

        entry_acc = entry_var.getvalue()[0]
        cur.executemany(
            """
            INSERT INTO INTERPRO.ENTRY2METHOD (ENTRY_AC, METHOD_AC, EVIDENCE) 
            VALUES (:1, :2, 'MAN')
            """,
            [(entry_acc, s_acc) for s_acc in entry_signatures]
        )

        if new_references:

            # During autointegration, add them directly to ENTRY2PUB instead of SUPPLEMENTARY_REF
            # to later append them to the description (see below)
            if automatic:
                cur.executemany(
                    """
                    INSERT INTO INTERPRO.ENTRY2PUB (ENTRY_AC, ORDER_IN, PUB_ID)
                    VALUES (:1, :2, :3)
                    """,
                    [(entry_acc, idx + 1, pub_id) for idx, pub_id in enumerate(new_references)]
                )
            else:
                cur.executemany(
                    """
                    INSERT INTO INTERPRO.SUPPLEMENTARY_REF (ENTRY_AC, PUB_ID)
                    VALUES (:1, :2)
                    """,
                    [(entry_acc, pub_id) for pub_id in new_references]
                )

        if automatic:
            pg_con = utils.connect_pg(utils.get_pg_url())
            with pg_con.cursor() as pg_cur:
                col = "llm_abstract" if entry_llm else "abstract"
                pg_cur.execute(
                    f"""
                    SELECT s.{col}
                    FROM signature s
                    WHERE s.accession = %s
                    """,
                    [entry_signatures[0]]
                )
                row = pg_cur.fetchone()

            pg_con.close()
            anno_text = row[0]

            if anno_text is None:
                return jsonify({
                    "status": False,
                    "error": {
                        "title": "Missing description",
                        "message": f"No description found "
                                   f"for {entry_signatures[0]}."
                    }
                }), 400

            # During autointegration, append supplementary references to description,
            # instead of adding them to SUPPLEMENTARY_REF (see above)
            in_text_references = re.findall(r"\[cite:(PUB\d+)\]", anno_text, re.I)
            not_in_text_references = set(new_references) - set(in_text_references)
            if not_in_text_references:
                    cite_items = [f"[cite:{pub_id}]" for pub_id in not_in_text_references]
                    anno_text += f"Supplementary references: [{', '.join(cite_items)}]"

            anno_text = sanitize_description(anno_text)
            if entry_type == 'Domain':
                anno_text = sanitize_domain(anno_text)

            anno_id, response, code = annotation.insert_annotation(
                anno_text,
                con,
                user,
                is_llm=entry_llm,
                is_checked=False
            )
            if anno_id is None:
                return jsonify(response), code

            response, code = relate_entry_to_anno(anno_id, entry_acc, con)
            if code != 200:
                return jsonify(response), code

    except oracledb.DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not create entry: {exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True,
            "accession": entry_acc
        })

    finally:
        cur.close()
        con.close()


def check_uniqueness(
        cur: oracledb.Cursor,
        name: str,
        short_name: str
) -> list[dict]:
    """Check if name and/or short name are already used by an InterPro entry

    :param cur: Oracle cursor
    :param name: str, name of new entry to be created
    :param short_name: str, short_name of entry to be created

    Return list of existing entries with the same name/short name or None
    """
    cur.execute(
        """
        SELECT ENTRY_AC, NAME, SHORT_NAME
        FROM INTERPRO.ENTRY
        WHERE LOWER(NAME) = :1 OR LOWER(SHORT_NAME) = :2
        """,
        [name.lower(), short_name.lower()]
    )
    cols = ("accession", "name", "short_name")
    return [dict(zip(cols, row)) for row in cur.fetchall()]
