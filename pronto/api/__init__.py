# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify, request

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
from . import taxon


bp = Blueprint("api", __name__,  url_prefix="/api")

blueprints = [bp, annotation.bp, checks.bp, database.bp, databases.bp,
              entries.bp, entry.bp, protein.bp, search.bp, signature.bp,
              signatures.bp, taxon.bp]


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
        "oracle": utils.get_oracle_dsn().rsplit('/')[-1],
        "postgresql": utils.get_pg_url().rsplit('/')[-1],
        "uniprot": version,
        "user": user,
    })


@bp.route("/tasks/")
def get_tasks():
    return jsonify(utils.executor.get_tasks(
        seconds=int(request.args.get('s', 0)),
        get_result=False
    ))


@bp.route("/task/<string:task_id>/")
def get_task(task_id):
    tasks = utils.executor.get_tasks(task_id=task_id, get_result=True)
    return jsonify(tasks[0])


# def add_cors(response):
#     response.headers["Access-Control-Allow-Origin"] = '*'
#     return response
#
#
# for _bp in [bp, annotation.bp, checks.bp, database.bp, databases.bp,
#             entries.bp, entry.bp, protein.bp, search.bp, signature.bp,
#             signatures.bp]:
#     _bp.after_request(add_cors)

