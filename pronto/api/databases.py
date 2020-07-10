# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify

from pronto import utils


bp = Blueprint("api.databases", __name__, url_prefix="/api/databases")


@bp.route("/")
def get_member_databases():
    # Get number of signatures and integrated signatures
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute("SELECT METHOD_AC FROM INTERPRO.ENTRY2METHOD")
    integrated = {row[0] for row in cur}
    cur.close()
    con.close()

    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, name, name_long, version, updated
        FROM interpro.database
        WHERE name NOT IN ('interpro', 'mobidblt', 'uniprot')
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
                "total": 0,
                "integrated": 0
            }
        }

    cur.execute(
        """
        SELECT database_id, accession
        FROM interpro.signature
        """
    )
    for dbid, accession in cur:
        try:
            db = databases[dbid]
        except KeyError:
            continue

        db["signatures"]["total"] += 1
        if accession in integrated:
            db["signatures"]["integrated"] += 1

    cur.close()
    con.close()
    return jsonify(sorted(databases.values(),
                          key=lambda x: x["name"].lower()))
