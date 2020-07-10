# -*- coding: utf-8 -*-

from flask import Blueprint
from flask import jsonify

from pronto import auth, utils
from . import annotation
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
        "uniprot": version,
        "user": user,
    })


@bp.route("/tasks/")
def get_task():
    return jsonify(utils.executor.tasks)
