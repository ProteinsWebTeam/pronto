# -*- coding: utf-8 -*-

import uuid
from typing import Tuple

import oracledb
from flask import Blueprint, jsonify, request

bp = Blueprint("api.checks", __name__, url_prefix="/api/checks")

from .annotations import check as check_annotations
from .entries import check as check_entries
from .go_terms import check as check_go
from .utils import CHECKS
from pronto import auth, utils


@bp.route("/")
def get_checks():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT C.CHECK_TYPE, C.TERM, E.ID, E.TERM, E.ANN_ID, E.ENTRY_AC, E.ENTRY_AC2
        FROM INTERPRO.SANITY_CHECK C
        LEFT OUTER JOIN INTERPRO.SANITY_EXCEPTION E
          ON (C.CHECK_TYPE = E.CHECK_TYPE 
            AND (C.TERM IS NULL OR C.TERM = E.TERM))
        """
    )

    types = {}
    for ck_type, check in CHECKS.items():
        types[ck_type] = {
            "type": ck_type,
            "name": check["name"],
            "label": check["label"],
            "description": check["description"],
            "add_terms": check["terms"],
            "exception_type": check["exceptions"],
            "terms": {},
            "exceptions": [],
        }

    for row in cur:
        ck_type = row[0]
        ck_term = row[1]
        exc_id = row[2]
        exc_term = row[3]
        exc_ann_id = row[4]
        exc_entry_acc = row[5]
        exc_entry_acc2 = row[6]

        check = types[ck_type]
        
        if ck_term:
            try:
                t = check["terms"][ck_term]
            except KeyError:
                t = check["terms"][ck_term] = {
                    "value": ck_term,
                    "exceptions": []
                }

            if exc_id:
                t["exceptions"].append({
                    "id": exc_id,
                    "annotation": exc_ann_id,
                    "entry": exc_entry_acc
                })
        elif exc_id:
            if ck_type == "encoding":
                exc_term = chr(int(exc_term))

            check["exceptions"].append({
                "id": exc_id,
                "term": exc_term,
                "annotation": exc_ann_id,
                "entry": exc_entry_acc,
                "entry2": exc_entry_acc2
            })

    cur.close()
    con.close()

    for ck_obj in types.values():
        terms = []
        for t in sorted(ck_obj["terms"].values(), key=lambda x: x["value"]):
            t["exceptions"].sort(key=lambda x: x["annotation"] or x["entry"])
            terms.append(t)

        ck_obj["terms"] = terms
        ck_obj["exceptions"].sort(key=lambda x: x["term"] or x["entry"])

    return jsonify(sorted(types.values(), key=lambda x: x["name"]))


@bp.route("/", methods=["PUT"])
def submit_checks():

    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    ora_ip_url = utils.get_oracle_url(user)
    ora_goa_url = utils.get_oracle_goa_url()
    task = utils.executor.submit(ora_ip_url, "sanitychecks", run_checks,
                                 ora_ip_url, utils.get_pg_url(), ora_goa_url)

    return jsonify({
        "status": True,
        "task": task
    }), 202


def run_checks(ora_url: str, pg_url: str, ora_goa_url: str):
    run_id = uuid.uuid1().hex

    con = oracledb.connect(ora_url)
    cur = con.cursor()

    counts = {}
    for check_type, (entry_acc, error) in check_entries(cur, pg_url):
        key = (None, entry_acc, check_type, error)
        try:
            counts[key] += 1
        except KeyError:
            counts[key] = 1

    for check_type, (ann_id, error) in check_annotations(cur):
        key = (ann_id, None, check_type, error)
        try:
            counts[key] += 1
        except KeyError:
            counts[key] = 1

    for check_type, (entry_acc, error) in check_go(cur, ora_goa_url):
        key = (None, entry_acc, check_type, error)
        try:
            counts[key] += 1
        except KeyError:
            counts[key] = 1

    errors = []
    i = 1
    for (ann_id, entry_acc, check_type, error), cnt in counts.items():
        errors.append((run_id, i, ann_id, entry_acc, check_type, error, cnt))
        i += 1

    cur.execute(
        """
        INSERT INTO INTERPRO.SANITY_RUN (ID)
        VALUES (:1)
        """, (run_id,)
    )

    cur.executemany(
        """
        INSERT INTO INTERPRO.SANITY_ERROR
            (RUN_ID, ID, ANN_ID, ENTRY_AC, CHECK_TYPE, TERM, COUNT)
        VALUES (:1, :2, :3, :4, :5, :6, :7)
        """, errors
    )

    cur.execute("DELETE FROM INTERPRO.SANITY_RUN WHERE ID != :1", (run_id,))

    con.commit()
    cur.close()
    con.close()


@bp.route("/run/<run_id>/")
def get_run(run_id):
    con = utils.connect_oracle()
    cur = con.cursor()
    if run_id == "latest":
        cur.execute(
            """
            SELECT *
            FROM (
                SELECT SR.ID, SR.TIMESTAMP, NVL(PU.NAME, SR.USERNAME)
                FROM INTERPRO.SANITY_RUN SR
                LEFT OUTER JOIN INTERPRO.PRONTO_USER PU
                  ON SR.USERNAME = PU.DB_USER
                ORDER BY SR.TIMESTAMP DESC
            )
            WHERE ROWNUM = 1
            """
        )
    else:
        cur.execute(
            """
            SELECT SR.ID, SR.TIMESTAMP, NVL(PU.NAME, SR.USERNAME)
                FROM INTERPRO.SANITY_RUN SR
                LEFT OUTER JOIN INTERPRO.PRONTO_USER PU
                  ON SR.USERNAME = PU.DB_USER
            WHERE ID = :1
            """, (run_id,)
        )
    row = cur.fetchone()
    if row:
        run_id, run_date, run_user = row
        run = {
            "id": run_id,
            "date": run_date.strftime("%d %B %Y, %H:%M"),
            "user": run_user,
            "errors": []
        }
        cur.execute(
            """
            SELECT SE.ID, SE.ANN_ID, SE.ENTRY_AC, SE.CHECK_TYPE, SE.TERM, 
                   SE.COUNT, SE.TIMESTAMP, NVL(PU.NAME, SE.USERNAME)
            FROM INTERPRO.SANITY_ERROR SE
            LEFT OUTER JOIN INTERPRO.PRONTO_USER PU
              ON SE.USERNAME = PU.DB_USER
            WHERE RUN_ID = :1
            ORDER BY 
                CASE WHEN SE.ANN_ID IS NULL THEN 0 ELSE 1 END,
                SE.ANN_ID,
                SE.ENTRY_AC,
                SE.CHECK_TYPE
            
            """, (run_id,)
        )
        for _id, ann_id, entry_acc, check_type, error, cnt, ts, user in cur:
            check = CHECKS[check_type]
            run["errors"].append({
                "id": _id,
                "annotation": ann_id,
                "entry": entry_acc,
                "type": check["label"],
                "details": check.get("details"),
                "exceptions": check["exceptions"] is not None,
                "error": error,
                "count": cnt,
                "resolution": {
                    "date": ts.strftime("%d %b %Y, %H:%M") if ts else None,
                    "user": user.split()[0] if user else None
                }
            })
    else:
        run = {}

    cur.close()
    con.close()
    return jsonify(run), 200 if run else 404


@bp.route("/run/<run_id>/<int:err_id>/", methods=["POST"])
def resolve_error(run_id, err_id):
    _add_exception = "exception" in request.args
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
    if _add_exception:
        cur.execute(
            """
            SELECT CHECK_TYPE, TERM, ANN_ID, ENTRY_AC
            FROM INTERPRO.SANITY_ERROR
            WHERE RUN_ID = :1 AND ID = :2 AND TIMESTAMP IS NULL
            """, (run_id, err_id)
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Run or error not found",
                    "message": f"Error #{err_id} in run #{run_id} "
                               f"does not exist."
                }
            }), 404

        ck_type, term, ann_id, entry_acc = row
        if ck_type not in CHECKS:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Bad request",
                    "message": f"'{ck_type}' does not support terms."
                }
            }), 400

        exc_type = CHECKS[ck_type]["exceptions"]
        if exc_type == 't':
            args = (cur, ck_type, term, ann_id or entry_acc)
        elif exc_type == 'p':
            args = (cur, ck_type, entry_acc, term)
        elif exc_type == 's':
            args = (cur, ck_type, entry_acc, None)
        elif exc_type == 'g':
            args = (cur, ck_type, term, None)
        else:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Forbidden",
                    "message": f"Check '{ck_type}' does not "
                               f"support exceptions."
                }
            }), 403

        result, code = insert_exception(*args)
        if not result["status"]:
            cur.close()
            con.close()
            return jsonify(result), code

    cur.execute(
        """
        UPDATE INTERPRO.SANITY_ERROR
        SET TIMESTAMP = SYSDATE,
            USERNAME = USER
        WHERE RUN_ID = :1 AND ID = :2 AND TIMESTAMP IS NULL
        """, (run_id, err_id)
    )
    con.commit()
    cur.close()
    con.close()

    return jsonify({"status": True})

    # if cur.rowcount:
    #     return jsonify({
    #         "status": True
    #     })
    # return jsonify({
    #     "status": False,
    #     "error": {
    #         "title": "Run or error not found",
    #         "message": f"Error #{err_id} in run #{run_id} does not exist."
    #     }
    # }), 404


@bp.route("/term/", methods=["PUT"])
def add_term():
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    try:
        ck_type = request.form["type"]
        ck_term = request.form["term"]
    except KeyError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    if ck_type not in CHECKS:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": f"'{ck_type}' does not support terms."
            }
        }), 400
    elif not ck_term:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": f"Empty strings are not accepted."
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.SANITY_CHECK
            VALUES (:1, :2, SYSDATE, USER)
            """, (ck_type, ck_term)
        )
    except oracledb.IntegrityError:
        # Silencing error (term already in table)
        return jsonify({
            "status": True
        }), 200
    except oracledb.DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(exc)
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


@bp.route("/term/", methods=["DELETE"])
def delete_term():
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    try:
        ck_type = request.form["type"]
        ck_term = request.form["term"]
    except KeyError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.SANITY_EXCEPTION
            WHERE CHECK_TYPE = :1 AND TERM = :2
            """, (ck_type, ck_term)
        )
        cur.execute(
            """
            DELETE FROM INTERPRO.SANITY_CHECK
            WHERE CHECK_TYPE = :1 AND TERM = :2
            """, (ck_type, ck_term)
        )
    except oracledb.DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(exc)
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


@bp.route("/exception/", methods=["PUT"])
def add_exception():
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    try:
        ck_type = request.form["type"]
        value1 = request.form["value1"]
    except KeyError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    value2 = request.form.get("value2")

    if ck_type not in CHECKS:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": f"'{ck_type}' is not a valid check type."
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    result, code = insert_exception(cur, ck_type, value1, value2)
    if result["status"]:
        con.commit()
    cur.close()
    con.close()
    return jsonify(result), code


@bp.route("/exception/", methods=["DELETE"])
def delete_exception():
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    try:
        exception_id = int(request.form["id"])
    except (KeyError, ValueError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.SANITY_EXCEPTION
            WHERE ID = :1
            """, (exception_id,)
        )
    except oracledb.DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(exc)
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


def is_annotation(cur: oracledb.Cursor, s: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.COMMON_ANNOTATION
        WHERE ANN_ID = :1
        """, (s,)
    )
    cnt, = cur.fetchone()
    return cnt != 0


def is_entry(cur: oracledb.Cursor, s: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC = :1
        """, (s,)
    )
    cnt, = cur.fetchone()
    return cnt != 0


def insert_exception(cur, ck_type, value1, value2) -> Tuple[dict, int]:
    if ck_type not in CHECKS:
        return {
                   "status": False,
                   "error": {
                       "title": "Bad request",
                       "message": f"'{ck_type}' is not a valid check type."
                   }
               }, 400

    exc_type = CHECKS[ck_type]["exceptions"]
    if not value1 or (exc_type not in ('g', 's') and not value2):
        return {
                   "status": False,
                   "error": {
                       "title": "Bad request",
                       "message": f"Empty strings are not accepted."
                   }
               }, 400

    if exc_type == 't':
        if is_annotation(cur, value2):
            params = (ck_type, value1, value2, None, None)
        elif is_entry(cur, value2):
            params = (ck_type, value1, None, value2, None)
        else:
            return {
                       "status": False,
                       "error": {
                           "title": "Bad request",
                           "message": f"'{value2}' is not an entry accession "
                                      f"or an annotation ID."
                       }
                   }, 400
    elif exc_type == 'g':
        params = (
            ck_type,
            ord(value1) if ck_type == "encoding" else value1,
            None,
            None,
            None
        )
    elif exc_type == 'p':
        if not is_entry(cur, value1):
            return {
                       "status": False,
                       "error": {
                           "title": "Bad request",
                           "message": f"'{value1}' is not an entry accession."
                       }
                   }, 400
        elif value1 == value2:
            return {
                       "status": False,
                       "error": {
                           "title": "Bad request",
                           "message": "Two different entry accessions "
                                      "are required."
                       }
                   }, 400
        elif ck_type == "acc_in_name":
            # Second accession is signature, not entry: in TERM column
            params = (ck_type, value2, None, value1, None)
        elif not is_entry(cur, value2):
            return {
                       "status": False,
                       "error": {
                           "title": "Bad request",
                           "message": f"'{value2}' is not an entry accession."
                       }
                   }, 400
        elif value1 < value2:
            params = (ck_type, None, None, value1, value2)

        else:
            params = (ck_type, None, None, value2, value1)
    elif exc_type == 's':
        if not is_entry(cur, value1):
            return {
                       "status": False,
                       "error": {
                           "title": "Bad request",
                           "message": f"'{value1}' is not an entry accession."
                       }
                   }, 400
        params = (ck_type, None, None, value1, None)
    else:
        return {
                   "status": False,
                   "error": {
                       "title": "Forbidden",
                       "message": f"Check '{ck_type}' does not "
                                  f"support exceptions."
                   }
               }, 403

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.SANITY_EXCEPTION 
                (ID, CHECK_TYPE, TERM, ANN_ID, ENTRY_AC, ENTRY_AC2)
            VALUES (
                (SELECT NVL(MAX(ID),0)+1 FROM INTERPRO.SANITY_EXCEPTION),
                :1, :2, :3, :4, :5
            )
            """, params
        )
    except oracledb.IntegrityError:
        # Silencing error (term already in table)
        return {"status": True}, 200
    except oracledb.DatabaseError as exc:
        return {
                   "status": False,
                   "error": {
                       "title": "Database error",
                       "message": str(exc)
                   }
               }, 500
    else:
        return {"status": True}, 200
