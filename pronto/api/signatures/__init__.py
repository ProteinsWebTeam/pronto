# -*- coding: utf-8 -*-

import re

from flask import Blueprint, jsonify, request

from pronto import utils

bp = Blueprint("api_signatures", __name__, url_prefix="/api/signatures")


def get_sig2interpro(accessions):
    args = ','.join(':' + str(i + 1) for i in range(len(accessions)))
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT METHOD_AC, ENTRY_AC
        FROM INTERPRO.ENTRY2METHOD
        WHERE METHOD_AC IN ({args})
        """, tuple(accessions)
    )
    sig2entry = dict(cur.fetchall())
    cur.close()
    con.close()
    return sig2entry


from . import comments
from . import descriptions
from . import go
from . import matrices
from . import proteins
from . import structures
from . import taxonomy


@bp.route("/recommendations/")
def get_recommendations():
    min_sim = float(request.args.get("minsim", 0.9))

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

    cur.execute(
        """
        SELECT METHOD_AC, COUNT(*)
        FROM INTERPRO.METHOD_COMMENT
        WHERE STATUS = 'Y'
        GROUP BY METHOD_AC
        """
    )
    comments = dict(cur.fetchall())

    cur.close()
    con.close()

    con = utils.connect_pg()
    with con.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM (
              SELECT
                s1.accession, d1.name, d1.name_long,
                s2.accession, d2.name, d2.name_long,
                CAST(p.num_residue_overlaps as decimal) / (s1.num_residues + s2.num_residues - p.num_residue_overlaps) AS sim_res
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
            ) x
            WHERE x.sim_res >= %s
            """, (min_sim,)
        )

        pthr_sf = re.compile(r"PTHR\d+:SF\d+")
        results = []
        for acc1, dbkey1, dbname1, acc2, dbkey2, dbname2, sim in cur:
            entry1 = integrated.get(acc1)
            entry2 = integrated.get(acc2)

            if entry1 and entry2:
                continue  # Both integrated: ignore
            elif entry1:
                # entry1 (query) is integrated: swap query and target
                (
                    acc1, dbkey1, dbname1, entry1,
                    acc2, dbkey2, dbname2, entry2
                ) = (
                    acc2, dbkey2, dbname2, entry2,
                    acc1, dbkey1, dbname1, entry1
                )

            if pthr_sf.match(acc1) or pthr_sf.match(acc2):
                continue  # Always ignore PANTHER subfamilies

            results.append({
                "query": {
                    "accession": acc1,
                    "database": {
                        "color": utils.get_database_obj(dbkey1).color,
                        "name": dbname1
                    },
                    "comments": comments.get(acc1, 0)
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
