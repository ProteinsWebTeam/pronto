from flask import Blueprint, jsonify

from pronto import utils


bp = Blueprint("api.databases", __name__, url_prefix="/api/databases")


@bp.route("/")
def get_member_databases():
    # Get number of signatures and integrated signatures
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT LOWER(D.DBSHORT), COUNT(*)
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.METHOD M ON EM.METHOD_AC = M.METHOD_AC
        INNER JOIN INTERPRO.CV_DATABASE D ON M.DBCODE = D.DBCODE
        GROUP BY D.DBSHORT
        """
    )
    num_integrated = dict(cur.fetchall())
    cur.close()
    con.close()

    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT database_id, COUNT(*)
        FROM interpro.signature
        GROUP BY database_id
        """
    )
    num_signatures = dict(cur.fetchall())

    cur.execute(
        f"""
        SELECT id, name, name_long, version, updated
        FROM interpro.database
        WHERE id IN ({','.join(['%s' for _ in num_signatures])})
        """,
        list(num_signatures.keys())
    )
    databases = {}
    for dbid, name, name_long, version, updated in cur:
        db = utils.get_database_obj(name)
        databases[dbid] = {
            "id": name,
            "name": name_long,
            "version": version,
            "date": updated.strftime("%b %Y"),
            "link": db.home,
            "color": db.color,
            "signatures": {
                "total": num_signatures.get(dbid, 0),
                "integrated": num_integrated.get(name, 0),
            },
        }

    cur.close()
    con.close()
    return jsonify(sorted(databases.values(), key=lambda x: x["name"].lower()))


@bp.route("/updates/")
def get_recent_updates():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT LOWER(D.DBSHORT), D.DBNAME, A.VERSION, A.TIMESTAMP
        FROM (
            SELECT DBCODE, VERSION, TIMESTAMP, ROW_NUMBER() OVER (
                PARTITION BY DBCODE, VERSION 
                ORDER BY TIMESTAMP DESC
            ) RN
            FROM INTERPRO.DB_VERSION_AUDIT
            WHERE TIMESTAMP >= ADD_MONTHS(SYSDATE, -12)
        ) A
        INNER JOIN INTERPRO.CV_DATABASE D ON A.DBCODE = D.DBCODE
        WHERE A.RN = 1
        ORDER BY TIMESTAMP DESC
        """
    )

    results = []
    for identifier, name, version, date in cur:
        try:
            db = utils.get_database_obj(identifier)
        except KeyError:
            continue
        else:
            results.append(
                {
                    "name": name,
                    "color": db.color,
                    "version": version,
                    "date": date.strftime("%b %Y"),
                }
            )

    cur.close()
    con.close()

    return jsonify({"results": results}), 200

