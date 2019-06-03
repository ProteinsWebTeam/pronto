from cx_Oracle import DatabaseError
from flask import jsonify, request

from pronto import app, db, executor, get_user
from . import (annotation, database, entry, interpro, protein,
               signature, signatures, uniprot)


@app.route("/api/user/")
def _get_user():
    return jsonify({"user": get_user()})


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
    return cur.fetchone()


def search_protein(cur, query):
    cur.execute(
        """
        SELECT PROTEIN_AC
        FROM {}.PROTEIN
        WHERE PROTEIN_AC = UPPER(:q) OR NAME = UPPER(:q)
        """.format(app.config["DB_SCHEMA"]),
        {"q": query}
    )
    return cur.fetchone()


def search_signature(cur, query):
    cur.execute(
        """
        SELECT METHOD_AC
        FROM {}.METHOD
        WHERE METHOD_AC = :q
        """.format(app.config["DB_SCHEMA"]),
        {"q": query}
    )
    return cur.fetchone()


@app.route("/api/search/")
def api_search():
    search_query = request.args.get("q", "").strip()
    hit = None
    if search_query:
        cur = db.get_oracle().cursor()
        funcs = (search_entry, search_protein, search_signature)
        types = ("entry", "protein", "prediction")
        for f, t in zip(funcs, types):
            row = f(cur, search_query)
            if row is not None:
                hit = {
                    "accession": row[0],
                    "type": t
                }
                break

        cur.close()

    return jsonify({
        "hit": hit
    })
