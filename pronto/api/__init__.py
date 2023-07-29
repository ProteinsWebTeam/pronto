from flask import Blueprint, jsonify, request

from pronto import auth, utils
from . import annotation
from . import checks
from . import database
from . import databases
from . import entries
from . import entry
from . import interproscan
from . import protein
from . import search
from . import signature
from . import signatures
from . import taxon
from . import proteome


bp = Blueprint("api", __name__,  url_prefix="/api")

blueprints = [bp, annotation.bp, checks.bp, database.bp, databases.bp,
              entries.bp, entry.bp, interproscan.bp, protein.bp, search.bp,
              signature.bp, signatures.bp, taxon.bp, proteome.bp]


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
    cur.execute("SELECT ready FROM interpro.database WHERE name='interpro'")
    is_ready, = cur.fetchone()
    cur.close()
    con.close()

    return jsonify({
        "oracle": utils.get_oracle_dsn().rsplit('/')[-1],
        "postgresql": utils.get_pg_url().rsplit('/')[-1],
        "uniprot": version,
        "ready": is_ready,
        "user": user,
    })


@bp.route("/activity/")
def get_activity():
    seconds = int(request.args.get('s', 24 * 3600))

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT A.TYPE, A.PRIMARY_ID, A.SECONDARY_ID, NVL(U.NAME, A.DBUSER), 
               A.ACTION, A.TIMESTAMP
        FROM (
            SELECT 'CA' AS TYPE, ANN_ID AS PRIMARY_ID, NULL AS SECONDARY_ID, 
                   DBUSER, ACTION, TIMESTAMP
            FROM INTERPRO.COMMON_ANNOTATION_AUDIT
            UNION ALL
            SELECT 'E2C', ENTRY_AC, ANN_ID, DBUSER, ACTION, TIMESTAMP
            FROM INTERPRO.ENTRY2COMMON_AUDIT
            UNION ALL
            SELECT 'E2E', ENTRY_AC, PARENT_AC, DBUSER, ACTION, TIMESTAMP
            FROM INTERPRO.ENTRY2ENTRY_AUDIT
            UNION ALL
            SELECT 'E2M', ENTRY_AC, METHOD_AC, DBUSER, ACTION, TIMESTAMP
            FROM INTERPRO.ENTRY2METHOD_AUDIT
            UNION ALL
            SELECT 'E', ENTRY_AC, NULL, DBUSER, ACTION, TIMESTAMP
            FROM INTERPRO.ENTRY_AUDIT
            UNION ALL
            SELECT 'I2G', ENTRY_AC, GO_ID, DBUSER, ACTION, TIMESTAMP
            FROM INTERPRO.INTERPRO2GO_AUDIT
        ) A
        LEFT OUTER JOIN INTERPRO.PRONTO_USER U ON A.DBUSER = U.DB_USER
        WHERE A.TIMESTAMP >= SYSDATE - INTERVAL '{seconds}' SECOND
        ORDER BY A.TIMESTAMP DESC
        """
    )

    activity = []
    for t, id1, id2, user, action, ts in cur.fetchall():
        activity.append({
            "type": t,
            "primary_id": id1,
            "secondary_id": id2,
            "action": action,
            "user": user,
            "timestamp": ts.strftime("%d %b %Y at %H:%M")
        })

    cur.close()
    con.close()

    return jsonify(activity)


@bp.route("/tasks/")
def get_tasks():
    return jsonify(utils.executor.get_tasks(
        seconds=int(request.args.get('s', 0)),
        get_result=False
    ))


@bp.route("/task/<string:task_id>/")
def get_task(task_id):
    tasks = utils.executor.get_tasks(task_id=task_id,
                                     get_result="results" in request.args)
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

