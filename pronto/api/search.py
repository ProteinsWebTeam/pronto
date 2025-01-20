from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api_search", __name__, url_prefix="/api/search")


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
        """,
        [query, query.upper()]
    )
    row = cur.fetchone()
    if row:
        cur.close()
        con.close()
        accession, = row
        return jsonify({
            "results": [{
                "accession": accession,
                "type": "entry"
            }]
        })

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM (
            SELECT MIN(ENTRY_AC) ENTRY_AC
            FROM INTERPRO.ENTRY2COMMON
            WHERE ANN_ID = :1
        )
        WHERE ENTRY_AC IS NOT NULL
        """,
        [query.upper()]
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    if row:
        accession, = row
        return jsonify({
            "results": [{
                "accession": accession,
                "type": "entry"
            }]
        })

    # Search signature(s) in PostgreSQL
    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT s.accession, s.name, s.description, d.name_long
        FROM signature AS s
        INNER JOIN interpro.database d on s.database_id = d.id
        WHERE UPPER(s.accession) = %s
        OR UPPER(s.name) = %s
        """,
        [query.upper(), query.upper()]
    )
    rows = cur.fetchall()
    if rows:
        cur.close()
        con.close()
        return jsonify({
            "results": sorted([{
                "accession": row[0],
                "name": row[1],
                "description": row[2],
                "database": row[3],
                "type": "signature"
            } for row in rows], key=lambda x: x["accession"])
        })

    cur.execute(
        """
        SELECT accession
        FROM protein
        WHERE accession = %s
        OR identifier = %s
        """,
        [query.upper(), query.upper()]
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    if row:
        accession, = row
        return jsonify({
            "results": [{
                "accession": accession,
                "type": "protein"
            }]
        })

    return jsonify({"results": []})
