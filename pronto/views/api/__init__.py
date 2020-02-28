from cx_Oracle import DatabaseError
from flask import jsonify, request

from pronto import app, db, executor, get_user, xref
from . import (annotation, database, entry, protein, sanitychecks,
               signature, signatures, uniprot)


@app.route("/api/databases/")
def get_databases():
    """
    Retrieves the number of signatures (all, integrated into InterPro, and unintegrated) for each member database.
    """
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          M.DBCODE,
          MIN(DB.DBNAME),
          MIN(DB.DBSHORT),
          MIN(DB.VERSION),
          MIN(DB.FILE_DATE),
          COUNT(M.METHOD_AC),
          SUM(CASE WHEN E2M.ENTRY_AC IS NOT NULL THEN 1 ELSE 0 END),
          SUM(CASE WHEN E2M.ENTRY_AC IS NULL THEN 1 ELSE 0 END)
        FROM {0}.METHOD M
        LEFT OUTER JOIN {0}.CV_DATABASE DB
          ON M.DBCODE = DB.DBCODE
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M
          ON M.METHOD_AC = E2M.METHOD_AC
        GROUP BY M.DBCODE
        """.format(app.config["DB_SCHEMA"])
    )

    databases = []
    for row in cur:
        dbcode = row[0]
        _database = xref.find_ref(dbcode)

        databases.append({
            "code": row[0],
            "name": row[1],
            "short_name": row[2].lower(),
            "version": row[3],
            "date": row[4].strftime("%b %Y"),
            "home": xref.find_ref(row[0]).home,
            "count_signatures": row[5],
            "count_integrated": row[6],
            "count_unintegrated": row[7],
            "color": _database.color
        })

    cur.close()

    return jsonify(sorted(databases, key=lambda x: x["name"].lower()))


@app.route("/api/entries/")
def get_recent_entries():
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT FILE_DATE - INTERVAL '7' DAY
        FROM INTERPRO.DB_VERSION 
        WHERE DBCODE = 'I'
        """
    )
    date, = cur.fetchone()
    cur.execute(
        """
        SELECT 
          E.ENTRY_AC, E.ENTRY_TYPE, E.SHORT_NAME, A.TIMESTAMP, 
          NVL(U.NAME, A.DBUSER), E.CHECKED, NVL(EM.NUM_METHODS, 0)
        FROM INTERPRO.ENTRY E
        INNER JOIN (
          SELECT 
            ENTRY_AC, DBUSER, TIMESTAMP, 
            ROW_NUMBER() OVER (
              PARTITION BY ENTRY_AC 
              ORDER BY TIMESTAMP ASC
            ) RN
          FROM INTERPRO.ENTRY_AUDIT
        ) A ON E.ENTRY_AC = A.ENTRY_AC AND A.RN = 1
        LEFT OUTER JOIN INTERPRO.PRONTO_USER U ON A.DBUSER = U.DB_USER
        LEFT OUTER JOIN (
          SELECT ENTRY_AC, COUNT(*) AS NUM_METHODS
          FROM INTERPRO.ENTRY2METHOD
          GROUP BY ENTRY_AC
        ) EM ON E.ENTRY_AC = EM.ENTRY_AC
        WHERE A.TIMESTAMP >= :1
        ORDER BY A.TIMESTAMP DESC
        """, (date,)
    )
    entries = []
    for row in cur:
        entries.append({
            "accession": row[0],
            "type": row[1],
            "short_name": row[2],
            "date": row[3].strftime("%d %b %Y"),
            "author": row[4],
            "checked": row[5] == 'Y',
            "num_signatures": row[6]
        })
    cur.close()
    return jsonify({
        "date": date.strftime("%d %b %Y"),
        "results": entries,
    })


@app.route("/api/user/")
def _get_user():
    user = get_user()
    if user:
        user = {k: v for k, v in user.items() if k != "password"}

    return jsonify({"user": user})


@app.route("/api/instance/")
def get_instance():
    dsn = app.config["ORACLE_DB"]["dsn"]
    return jsonify({
        "instance": dsn.split("/")[-1].upper(),
        "schema": "#1" if app.config["DB_SCHEMA"].lower().endswith('load') else "#2"
    })


@app.route("/api/status/")
def get_status():
    status = 503
    cur = db.get_oracle().cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM {}.CV_DATABASE
            WHERE IS_READY = 'Y'
            """.format(app.config["DB_SCHEMA"])
        )
    except DatabaseError:
        pass
    else:
        if cur.fetchone()[0]:
            status = 200
    finally:
        cur.close()
        return '', status


@app.route("/api/tasks/")
def get_tasks():
    return jsonify(executor.tasks)


def search_entry(cur, query):
    try:
        i = int(query)
    except ValueError:
        pass
    else:
        query = "IPR{:06}".format(i)

    cur.execute(
        """
        SELECT ENTRY_AC
        FROM {}.ENTRY
        WHERE UPPER(ENTRY_AC) = :q
        OR UPPER(SHORT_NAME) = :q
        """.format(app.config["DB_SCHEMA"]),
        dict(q=query.upper())
    )
    row = cur.fetchone()
    return row[0] if row else None


def search_protein(cur, query):
    cur.execute(
        """
        SELECT PROTEIN_AC
        FROM {}.PROTEIN
        WHERE PROTEIN_AC = UPPER(:q) OR NAME = UPPER(:q)
        """.format(app.config["DB_SCHEMA"]),
        {"q": query}
    )
    row = cur.fetchone()
    return row[0] if row else None


def search_signature(cur, query):
    cur.execute(
        """
        SELECT METHOD_AC
        FROM {}.METHOD
        WHERE METHOD_AC = :q
        """.format(app.config["DB_SCHEMA"]),
        {"q": query}
    )
    row = cur.fetchone()
    return row[0] if row else None


def search_abstract(cur, query):
    cur.execute(
        """
        SELECT MIN(ENTRY_AC)
        FROM INTERPRO.ENTRY2COMMON
        WHERE UPPER(ANN_ID) = :q
        """,
        dict(q=query.upper())
    )
    row = cur.fetchone()
    return row[0] if row and row[0] else None


@app.route("/api/search/")
def api_search():
    search_query = request.args.get("q", "").strip()
    if search_query:
        cur = db.get_oracle().cursor()

        accession = search_entry(cur, search_query)
        if accession:
            cur.close()
            return jsonify({"hit": {"accession": accession, "type": "entry"}})

        accession = search_protein(cur, search_query)
        if accession:
            cur.close()
            return jsonify({"hit": {"accession": accession, "type": "protein"}})

        accession = search_signature(cur, search_query)
        if accession:
            cur.close()
            return jsonify({"hit": {"accession": accession, "type": "prediction"}})

        accession = search_abstract(cur, search_query)
        if accession:
            cur.close()
            return jsonify({"hit": {"accession": accession, "type": "entry"}})

        cur.close()

    return jsonify({"hit": None})
