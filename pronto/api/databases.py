# -*- coding: utf-8 -*-

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
        """
        SELECT id, name, name_long, version, updated
        FROM interpro.database
        WHERE name NOT IN ('interpro', 'uniprot')
        """
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
                "integrated": num_integrated.get(name, 0)
            }
        }

    cur.close()
    con.close()
    return jsonify(sorted(databases.values(),
                          key=lambda x: x["name"].lower()))
