# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api.search", __name__, url_prefix="/api/search")


@bp.route("/")
def search_term():
    try:
        query = request.args["q"]
    except KeyError:
        return jsonify({
            "error": {
                "title": "Bad Request",
                "message": "'q' parameter is required."
            }
        }), 400

    # Search entry/abstract in Oracle
    con = utils.connect_oracle()
    cur = con.cursor()

    try:
        i = int(query)
    except ValueError:
        pass
    else:
        query = f"IPR{i:06}"

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC = :1
        OR UPPER(SHORT_NAME) = :2
        """, (query, query.upper())
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        accession, = row
        return jsonify({"hit": {"accession": accession, "type": "entry"}})

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM (
            SELECT MIN(ENTRY_AC) ENTRY_AC
            FROM INTERPRO.ENTRY2COMMON
            WHERE ANN_ID = :1
        )
        WHERE ENTRY_AC IS NOT NULL
        """, (query.upper(),)
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    if row:
        accession, = row
        return jsonify({"hit": {"accession": accession, "type": "entry"}})

    # Search protein/signature in PostgreSQL
    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT accession
        FROM protein
        WHERE accession = %s
        OR identifier = %s
        """, (query.upper(), query.upper())
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        accession, = row
        return jsonify({"hit": {"accession": accession, "type": "protein"}})

    cur.execute(
        """
        SELECT accession
        FROM signature
        WHERE UPPER(accession) = %s
        OR UPPER(name) = %s
        """, (query.upper(), query.upper())
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    if row:
        accession, = row
        return jsonify({"hit": {"accession": accession, "type": "signature"}})

    return jsonify({"hit": None})
