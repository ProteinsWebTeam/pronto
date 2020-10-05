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
        "oracle": utils.get_oracle_dsn().rsplit('/')[-1],
        "postgresql": utils.get_pg_url().rsplit('/')[-1],
        "uniprot": version,
        "user": user,
    })


@bp.route("/news/")
def get_recent_actions():
    """
    Returns recently created InterPro entries and integrated signatures.
    :return:
    """
    con = utils.connect_oracle()
    cur = con.cursor()

    """
    Get the date of the last time a record for InterPro was inserted into the
    DB_VERSION_AUDIT table (triggered by an action for InterPro in DB_VERSION).
    This roughly corresponds to the date of the last production freeze.
    """
    cur.execute(
        """
        SELECT TIMESTAMP
        FROM (
            SELECT TIMESTAMP, ROWNUM AS RN
            FROM (
                SELECT TIMESTAMP
                FROM DB_VERSION_AUDIT
                WHERE DBCODE = 'I'
                ORDER BY TIMESTAMP DESC
            )
        )
        WHERE RN = 1
        """
    )
    date, = cur.fetchone()

    result = {
        "date": date.strftime("%d %B"),
        "entries": entries.get_recent_entries(cur, date),
        "signatures": signatures.get_recent_integrations(cur, date)
    }

    cur.close()
    con.close()

    return jsonify(result)


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
