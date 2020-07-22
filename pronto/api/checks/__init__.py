# -*- coding: utf-8 -*-

import uuid

import cx_Oracle
from flask import Blueprint, jsonify, request

bp = Blueprint("api.checks", __name__, url_prefix="/api/checks")

from .annotations import check as check_annotations
from .entries import check as check_entries
from .utils import CHECKS
from pronto import auth, utils


def run_checks(user: dict, dsn: str):
    run_id = uuid.uuid1().hex

    con = cx_Oracle.connect(user["dbuser"], user["password"], dsn)
    cur = con.cursor()

    counts = {}
    for check_type, (entry_acc, error) in check_entries(cur):
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

    args = (user, utils.get_oracle_dsn())
    submitted = utils.executor.submit(user, "checks", run_checks, *args)

    return jsonify({
        "status": True,
        "submitted": submitted,
        "task": "checks"
    }), 202 if submitted else 409


@bp.route("/run/<run_id>/")
def get_run(run_id):
    con = utils.connect_oracle()
    cur = con.cursor()
    if run_id == "last":
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
            label, add_terms, add_excs, add_glob_excs = CHECKS[check_type]
            run["errors"].append({
                "id": _id,
                "annotation": ann_id,
                "entry": entry_acc,
                "type": label,
                "exceptions": add_excs,
                "error": error,
                "count": cnt,
                "resolution": {
                    "date": ts.strftime("%d %b %Y, %H:%M") if ts else None,
                    "user": user
                }
            })
    else:
        run = {}

    cur.close()
    con.close()
    return jsonify(run), 200 if run else 404


@bp.route("/run/<run_id>/<int:err_id>/", methods=["POST"])
def resolve_error(run_id, err_id):
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
    cur.execute(
        """
        UPDATE INTERPRO.SANITY_ERROR
        SET TIMESTAMP = SYSDATE,
            USERNAME = USER
        WHERE RUN_ID = :1 AND ID = :2 AND TIMESTAMP IS NULL
        """, (run_id, err_id)
    )
    affected = cur.rowcount
    if affected:
        con.commit()

    cur.close()
    con.close()

    return jsonify({"status": True})

    # if affected:
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
