from flask import jsonify, request

from pronto import app, db, get_user
from . import database, entry, interpro, protein, signature, uniprot


@app.route("/api/user/")
def user():
    return jsonify({"user": get_user()})


def search_entry(cur, query):
    cur.execute(
        """
        SELECT ENTRY_AC
        FROM {}.ENTRY
        WHERE ENTRY_AC = :q
        """.format(app.config["DB_SCHEMA"]),
        {"q": query}
    )
    return cur.fetchone()


def search_protein(cur, query):
    cur.execute(
        """
        SELECT PROTEIN_AC
        FROM {}.PROTEIN
        WHERE PROTEIN_AC = :q OR NAME = :q
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
    search_query = request.args.get("q", "").strip().upper()
    hit = None
    if search_query:
        cur = db.get_oracle().cursor()
        funcs = (search_entry, search_protein, search_signature)
        types = ("entry", "protein", "method")
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
