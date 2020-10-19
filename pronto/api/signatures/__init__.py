# -*- coding: utf-8 -*-

import re

from flask import Blueprint, jsonify, request


bp = Blueprint("api.signatures", __name__, url_prefix="/api/signatures")

from pronto import utils
from . import comments
from . import descriptions
from . import go
from . import matrices
from . import proteins
from . import taxonomy


def get_recent_integrations(cur, date):
    """
    Get signatures recently integrated.

    :param cur: Oracle cursor
    :param date: date of the last production freeze
    :return: dictionary of member databases (name -> number of integrations)
    """
    cur.execute(
        """
        SELECT D.DBNAME, COUNT(*)
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.METHOD M ON EM.METHOD_AC = M.METHOD_AC
        INNER JOIN INTERPRO.CV_DATABASE D ON M.DBCODE = D.DBCODE
        WHERE EM.TIMESTAMP >= :1
        GROUP BY D.DBNAME
        """, (date,)
    )
    return dict(cur.fetchall())


@bp.route("/recommendations/")
def get_recommendations():
    min_sim = float(request.args.get("minsim", 0.9))
    no_panther_sf = "nopanthersf" in request.args
    no_commented = "nocommented" in request.args

    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT EM.METHOD_AC, E.ENTRY_AC, E.ENTRY_TYPE, E.NAME, E.CHECKED
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.ENTRY E ON EM.ENTRY_AC = E.ENTRY_AC
        """
    )
    integrated = {}
    for row in cur:
        integrated[row[0]] = {
            "accession": row[1],
            "type": row[2],
            "name": row[3],
            "checked": row[4] == 'Y'
        }

    if no_commented:
        cur.execute(
            """
            SELECT DISTINCT METHOD_AC
            FROM INTERPRO.METHOD_COMMENT
            WHERE STATUS = 'Y'
            """
        )
        commented = {acc for acc, in cur}
    else:
        commented = set()

    cur.close()
    con.close()

    con = utils.connect_pg()
    with con.cursor() as cur:
        cur.execute(
            f"""
            SELECT *
            FROM (
              SELECT
                s1.accession, d1.name, d1.name_long,
                s2.accession, d2.name, d2.name_long,
                CAST(p.residue_overlaps as decimal) / (s1.num_residues + s2.num_residues - p.residue_overlaps) AS sim_res
              FROM interpro.signature s1
              INNER JOIN interpro.prediction p ON s1.accession = p.signature_acc_1
              INNER JOIN interpro.signature s2 ON p.signature_acc_2 = s2.accession
              INNER JOIN interpro.database d1 ON s1.database_id = d1.id
              INNER JOIN interpro.database d2 ON s2.database_id = d2.id
              WHERE
                s1.accession < s2.accession
              AND
                s1.database_id != s2.database_id
              AND (
                (s1.type = 'Homologous_superfamily' AND s2.type = 'Homologous_superfamily')
                OR
                (s1.type != 'Homologous_superfamily' AND s2.type != 'Homologous_superfamily')
              )
            ) p
            WHERE p.sim_res >= %s
            """, (min_sim,)
        )

        pthr_sf = re.compile(r"PTHR\d+:SF\d+")
        results = []
        for acc1, dbkey1, dbname1, acc2, dbkey2, dbname2, sim in cur:
            entry1 = integrated.get(acc1)
            entry2 = integrated.get(acc2)
            if entry1 and entry2:
                continue
            elif entry2:
                # We want entry1 (query) to be the integrated one
                _acc, _dbkey, _dbname, _entry = acc1, dbkey1, dbname1, entry1
                acc1, dbkey1, dbname1, entry1 = acc2, dbkey2, dbname2, entry2
                acc2, dbkey2, dbname2, entry2 = _acc, _dbkey, _dbname, _entry

            if acc2 in commented:
                continue  # ignore commented (assume no_commented == True)
            elif no_panther_sf and (pthr_sf.match(acc1) or pthr_sf.match(acc2)):
                continue

            results.append({
                "query": {
                    "accession": acc1,
                    "database": {
                        "color": utils.get_database_obj(dbkey1).color,
                        "name": dbname1
                    },
                    "entry": entry1,
                },
                "target": {
                    "accession": acc2,
                    "database": {
                        "color": utils.get_database_obj(dbkey2).color,
                        "name": dbname2
                    },
                    "entry": entry2,
                },
                "similarity": float(sim)
            })

    con.close()
    results.sort(key=lambda x: -x["similarity"])

    return jsonify({
        "count": len(results),
        "results": results[(page-1)*page_size:page*page_size],
        "page_info": {
            "page": page,
            "page_size": page_size
        }
    })
