# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify

from pronto import utils


bp = Blueprint("api.entries", __name__, url_prefix="/api/entries")


@bp.route("/")
def get_recent_entries():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT FILE_DATE - INTERVAL '7' DAY
        FROM INTERPRO.DB_VERSION
        WHERE DBCODE = 'I'
        """
    )
    date, = cur.fetchone()
    cur.execute(
        """
        SELECT
          E.ENTRY_AC, E.ENTRY_TYPE, E.SHORT_NAME, A.TIMESTAMP,
          NVL(U.NAME, A.DBUSER), E.CHECKED, NVL(EM.NUM_METHODS, 0)
        FROM INTERPRO.ENTRY E
        INNER JOIN (
          SELECT
            ENTRY_AC, DBUSER, TIMESTAMP,
            ROW_NUMBER() OVER (
              PARTITION BY ENTRY_AC
              ORDER BY TIMESTAMP ASC
            ) RN
          FROM INTERPRO.ENTRY_AUDIT
        ) A ON E.ENTRY_AC = A.ENTRY_AC AND A.RN = 1
        LEFT OUTER JOIN INTERPRO.PRONTO_USER U ON A.DBUSER = U.DB_USER
        LEFT OUTER JOIN (
          SELECT ENTRY_AC, COUNT(*) AS NUM_METHODS
          FROM INTERPRO.ENTRY2METHOD
          GROUP BY ENTRY_AC
        ) EM ON E.ENTRY_AC = EM.ENTRY_AC
        WHERE A.TIMESTAMP >= :1
        ORDER BY A.TIMESTAMP DESC
        """, (date,)
    )
    entries = []
    for row in cur:
        entries.append({
            "accession": row[0],
            "type": row[1],
            "short_name": row[2],
            "date": row[3].strftime("%d %b %Y"),
            "author": row[4],
            "checked": row[5] == 'Y',
            "signatures": row[6]
        })
    cur.close()
    con.close()
    return jsonify({
        "date": date.strftime("%d %b %Y"),
        "entries": entries,
    })
