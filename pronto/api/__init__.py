# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify

from pronto import auth, utils
from . import annotation
from . import checks
from . import database
from . import databases
from . import entries
from . import entry
from . import protein
from . import search
from . import signature
from . import signatures


bp = Blueprint("api", __name__,  url_prefix="/api")


@bp.route("/")
def api_index():
    user = auth.get_user()
    if user:
        # Make a copy of the user dictionary and remove its password
        user = user.copy()
        del user["password"]

    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute("SELECT version FROM interpro.database WHERE name='uniprot'")
    version, = cur.fetchone()
    cur.close()
    con.close()

    return jsonify({
        "oracle": utils.get_oracle_dsn().split('/')[-1],
        "uniprot": version,
        "user": user,
    })


@bp.route("/tasks/")
def get_task():
    return jsonify(utils.executor.tasks)


# def add_cors(response):
#     response.headers["Access-Control-Allow-Origin"] = '*'
#     return response
#
#
# for _bp in [bp, annotation.bp, checks.bp, database.bp, databases.bp,
#             entries.bp, entry.bp, protein.bp, search.bp, signature.bp,
#             signatures.bp]:
#     _bp.after_request(add_cors)
