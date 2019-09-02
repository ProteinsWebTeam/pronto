import json
from flask import jsonify, request

from pronto import app, db


def get_database(dbshort):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT DBNAME, DBCODE, VERSION
        FROM {}.CV_DATABASE
        WHERE LOWER(DBSHORT) = LOWER(:1)
        """.format(app.config["DB_SCHEMA"]),
        (dbshort,)
    )

    row = cur.fetchone()

    if row:
        name, code, version = row
    else:
        name = code = version = None

    cur.close()

    return name, code, version


@app.route("/api/database/<dbshort>/")
def api_integrated_signatures(dbshort):
    db_name, db_code, db_version = get_database(dbshort)
    if not db_name:
        return jsonify({
            "results": [],
            "count": 0,
            "database": None
        }), 404

    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

    try:
        integrated = bool(int(request.args["integrated"]))
    except (KeyError, ValueError):
        integrated = None

    try:
        checked = bool(int(request.args["checked"]))
    except (KeyError, ValueError):
        checked = None

    try:
        commented = bool(int(request.args["commented"]))
    except (KeyError, ValueError):
        commented = None

    search_query = request.args.get("search", "").strip()

    base_sql = """
            FROM {0}.METHOD M
            LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
                ON M.METHOD_AC = EM.METHOD_AC
            LEFT OUTER JOIN INTERPRO.ENTRY E 
                ON E.ENTRY_AC = EM.ENTRY_AC
            LEFT OUTER JOIN (
                SELECT
                    C.METHOD_AC,
                    C.VALUE,
                    P.NAME,
                    C.CREATED_ON,
                    ROW_NUMBER() OVER (
                        PARTITION BY METHOD_AC 
                        ORDER BY C.CREATED_ON DESC
                    ) R
                FROM INTERPRO.METHOD_COMMENT C
                INNER JOIN INTERPRO.USER_PRONTO P 
                    ON C.USERNAME = P.USERNAME
            ) C ON (M.METHOD_AC = C.METHOD_AC AND C.R = 1)
            WHERE DBCODE = :dbcode
        """.format(app.config["DB_SCHEMA"])

    if search_query:
        base_sql += " AND M.METHOD_AC LIKE :q"
        params = {
            "dbcode": db_code,
            "q": search_query.upper() + "%"
        }
    else:
        params = {
            "dbcode": db_code,
        }

    if integrated:
        base_sql += " AND EM.ENTRY_AC IS NOT NULL"
    elif integrated is False:
        base_sql += " AND EM.ENTRY_AC IS NULL"

    if checked:
        base_sql += " AND E.CHECKED = 'Y'"
    elif checked is False:
        base_sql += " AND E.CHECKED = 'N'"

    if commented:
        base_sql += " AND C.VALUE IS NOT NULL"
    elif commented is False:
        base_sql += " AND C.VALUE IS NULL"

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        {}
        """.format(base_sql),
        params
    )

    num_rows = cur.fetchone()[0]
    params.update({
        "i_start": (page - 1) * page_size,
        "i_end": page * page_size
    })

    cur.execute(
        """
        SELECT *
        FROM (
            SELECT M.*, ROWNUM RN
            FROM (
                SELECT 
                    M.METHOD_AC,
                    EM.ENTRY_AC,
                    E.CHECKED,
                    E.ENTRY_TYPE,
                    M.PROTEIN_COUNT,
                    C.VALUE,
                    C.NAME,
                    C.CREATED_ON
                {}
                ORDER BY M.METHOD_AC
            ) M
            WHERE ROWNUM <= :i_end        
        )
        WHERE RN > :i_start
        """.format(base_sql),
        params
    )

    signatures = []
    match_counts = {}
    for row in cur:
        match_counts[row[0]] = None
        signatures.append({
            "accession": row[0],
            "entry": {
                "accession": row[1],
                "checked": row[2] == "Y",
                "type": row[3]
            } if row[1] else None,
            "count_now": row[4],
            "count_then": None,
            "latest_comment": {
                "text": row[5],
                "author": row[6],
                "date": row[7].strftime("%Y-%m-%d %H:%M:%S")
            } if row[5] else None
        })

    cur.close()

    if match_counts:
        # Get the count from the latest InterPro release (using the MySQL DW)
        cur = db.get_mysql_db().cursor()
        cur.execute(
            """
            SELECT UPPER(accession), counts
            FROM webfront_entry
            WHERE accession IN ({})
            """.format(",".join(["%s" for _ in match_counts])),
            list(match_counts.keys())
        )

        for accession, counts in cur:
            try:
                counts = json.loads(counts)
            except TypeError:
                continue
            else:
                match_counts[accession] = counts.get("matches")

        cur.close()

        for s in signatures:
            s["count_then"] = match_counts.get(s["accession"])

    return jsonify({
        "page_info": {
            "page": page,
            "page_size": page_size
        },
        "signatures": signatures,
        "count": num_rows,
        "database": {
            "name": db_name,
            "version": db_version
        }
    })


@app.route("/api/database/<dbshort>/unintegrated/<mode>/")
def api_unintegrated_signatures(dbshort, mode):
    if mode not in ("integrated", "candidate", "norelation"):
        return jsonify({
            "results": [],
            "count": 0,
            "database": None
        }), 400

    db_name, db_code, db_version = get_database(dbshort)
    if not db_name:
        return jsonify({
            "results": [],
            "count": 0,
            "database": None
        }), 404

    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

    search_query = request.args.get("search", "").strip()

    params = {
        "dbcode": db_code
    }

    if mode == "integrated":
        # Signature with at least one InterPro prediction
        base_sql = """
            SELECT DISTINCT MP.METHOD_AC1 AS METHOD_AC
            FROM {0}.METHOD_PREDICTION MP
            INNER JOIN INTERPRO.ENTRY2METHOD EM
              ON MP.METHOD_AC2 = EM.METHOD_AC
            WHERE MP.RELATION = 'ADD_TO'
              AND MP.METHOD_AC1 IN (
                SELECT METHOD_AC
                FROM {0}.METHOD
                WHERE DBCODE = :dbcode
              )
              AND MP.METHOD_AC1 NOT IN (
                SELECT METHOD_AC
                FROM INTERPRO.ENTRY2METHOD
              )    
        """.format(app.config["DB_SCHEMA"])

        if search_query:
            base_sql += " AND MP.METHOD_AC1 LIKE :q"
            params["q"] = search_query.upper() + "%"
    elif mode == "candidate":
        """
        Signature with at least one prediction 
        that is an unintegrated candidate signature
        """
        base_sql = """
            SELECT DISTINCT MP.METHOD_AC1 AS METHOD_AC
            FROM {0}.METHOD_PREDICTION MP
            INNER JOIN {0}.METHOD M
              ON MP.METHOD_AC2 = M.METHOD_AC
            WHERE MP.RELATION = 'ADD_TO'
              AND MP.METHOD_AC1 IN (
                SELECT METHOD_AC
                FROM {0}.METHOD
                WHERE DBCODE = :dbcode
              )
              AND MP.METHOD_AC1 NOT IN (
                SELECT METHOD_AC
                FROM INTERPRO.ENTRY2METHOD
              )
              AND M.CANDIDATE = 'Y'
              AND MP.METHOD_AC2 NOT IN (
                SELECT METHOD_AC
                FROM INTERPRO.ENTRY2METHOD
              )    
        """.format(app.config["DB_SCHEMA"])

        if search_query:
            base_sql += " AND MP.METHOD_AC1 LIKE :q"
            params["q"] = search_query.upper() + "%"
    else:
        # Signature without relations
        base_sql = """
            SELECT METHOD_AC
            FROM {0}.METHOD_MATCH
            WHERE METHOD_AC IN (
              SELECT METHOD_AC 
              FROM {0}.METHOD 
              WHERE DBCODE = :dbcode
            )
            AND METHOD_AC NOT IN (
              SELECT METHOD_AC 
              FROM INTERPRO.ENTRY2METHOD
            )
            AND METHOD_AC NOT IN (
              SELECT DISTINCT METHOD_AC1 
              FROM {0}.METHOD_PREDICTION
            )
        """.format(app.config["DB_SCHEMA"])

        if search_query:
            base_sql += " AND METHOD_AC LIKE :q"
            params["q"] = search_query.upper() + "%"

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM ({})
        """.format(base_sql),
        params
    )

    num_rows = cur.fetchone()[0]
    params.update({
        "i_start": (page - 1) * page_size,
        "i_end": page * page_size
    })

    cur.execute(
        """
        WITH FILTERV AS (
            SELECT *
            FROM (
                SELECT T.*, ROWNUM RN
                FROM (
                    {0}
                    ORDER BY METHOD_AC
                ) T
                WHERE ROWNUM <= :i_end
            )
            WHERE RN > :i_start
        )
        SELECT MM.METHOD_AC, MP.METHOD_AC2, MP.RELATION, E.ENTRY_AC, E.ENTRY_TYPE
        FROM {1}.METHOD_MATCH MM
        LEFT OUTER JOIN {1}.METHOD_PREDICTION MP
          ON MM.METHOD_AC = MP.METHOD_AC1
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
          ON MP.METHOD_AC2 = EM.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E 
          ON EM.ENTRY_AC = E.ENTRY_AC
        WHERE MM.METHOD_AC IN (SELECT METHOD_AC FROM FILTERV)
        """.format(base_sql, app.config["DB_SCHEMA"]),
        params
    )

    signatures = {}
    for method_acc1, method_acc2, relation, entry_acc, entry_type in cur:
        if method_acc1 in signatures:
            s = signatures[method_acc1]
        else:
            s = signatures[method_acc1] = {
                "add_to": {},
                "parents": set(),
                "children": set()
            }

        acc = entry_acc if entry_acc else method_acc2
        if relation == "ADD_TO":
            s["add_to"][acc] = entry_type
        elif relation == "PARENT_OF":
            s["children"].add(acc)
        elif relation == "CHILD_OF":
            s["parents"].add(acc)

    _signatures = []
    for method_acc1 in sorted(signatures):
        s = signatures[method_acc1]
        _signatures.append({
            "accession": method_acc1,
            "add_to": [{
                "accession": acc,
                "type": s["add_to"][acc]
            } for acc in sorted(s["add_to"])],
            "parents": list(sorted(s["parents"])),
            "children": list(sorted(s["children"]))
        })

    return jsonify({
        "page_info": {
            "page": page,
            "page_size": page_size
        },
        "signatures": _signatures,
        "count": num_rows,
        "database": {
            "name": db_name,
            "version": db_version
        }
    })

