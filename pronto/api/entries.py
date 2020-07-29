# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify

from pronto import utils


bp = Blueprint("api.entries", __name__, url_prefix="/api/entries")


def _get_unfreeze_date(cur, days=7):
    cur.execute(
        f"""
        SELECT FILE_DATE
        FROM (
          SELECT FILE_DATE
          FROM (
            SELECT FILE_DATE - INTERVAL '{days}' DAY AS FILE_DATE
            FROM DB_VERSION_AUDIT
            WHERE DBCODE = 'I'
            ORDER BY FILE_DATE DESC
          )
          WHERE ROWNUM <= 2
        )
        WHERE FILE_DATE < SYSDATE
        """
    )
    date, = cur.fetchall()[0]
    return date


@bp.route("/news/")
def get_recent_entries():
    con = utils.connect_oracle()
    cur = con.cursor()
    date = _get_unfreeze_date(cur)
    cur.execute(
        """
        SELECT
          E.ENTRY_AC, E.ENTRY_TYPE, E.SHORT_NAME, A.TIMESTAMP,
          NVL(U.NAME, A.DBUSER), E.CHECKED, NVL(EM.NUM_METHODS, 0)
        FROM INTERPRO.ENTRY E
        INNER JOIN (
          -- First audit event
          SELECT
            ENTRY_AC, DBUSER, TIMESTAMP,
            ROW_NUMBER() OVER (
              PARTITION BY ENTRY_AC
              ORDER BY TIMESTAMP
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
            "user": row[4],
            "checked": row[5] == 'Y',
            "signatures": row[6]
        })
    cur.close()
    con.close()
    return jsonify({
        "date": date.strftime("%d %b %Y"),
        "entries": entries,
    })


@bp.route("/unchecked/")
def get_unchecked_entries():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT * FROM (
            SELECT
              E.ENTRY_AC, E.ENTRY_TYPE, E.SHORT_NAME, 
              NVL(FAE.TIMESTAMP, E.TIMESTAMP) AS CREATED_TIME,
              NVL(LAE.TIMESTAMP, E.TIMESTAMP) AS UPDATED_TIME, 
              NVL(U.NAME, E.USERSTAMP), 
              NVL(EM.NUM_METHODS, 0) AS NUM_METHODS,
              NVL(EC.NUM_COMMENTS, 0) AS NUM_COMMENTS
            FROM INTERPRO.ENTRY E
            LEFT OUTER JOIN (
              -- First audit event
              SELECT
                ENTRY_AC, TIMESTAMP,
                ROW_NUMBER() OVER (
                  PARTITION BY ENTRY_AC
                  ORDER BY TIMESTAMP
                ) RN
              FROM INTERPRO.ENTRY_AUDIT
            ) FAE ON E.ENTRY_AC = FAE.ENTRY_AC AND FAE.RN = 1
            LEFT OUTER JOIN (
                -- Latest audit event when entry was unchecked
                SELECT 
                    ENTRY_AC, DBUSER, TIMESTAMP, 
                    ROW_NUMBER() OVER (PARTITION BY ENTRY_AC 
                                       ORDER BY TIMESTAMP DESC) RN
                FROM INTERPRO.ENTRY_AUDIT
                WHERE CHECKED = 'N' 
            ) LAE ON E.ENTRY_AC = LAE.ENTRY_AC AND LAE.RN = 1
            LEFT OUTER JOIN INTERPRO.PRONTO_USER U 
                ON LAE.DBUSER = U.DB_USER
            LEFT OUTER JOIN (
              SELECT ENTRY_AC, COUNT(*) AS NUM_METHODS
              FROM INTERPRO.ENTRY2METHOD
              GROUP BY ENTRY_AC
            ) EM ON E.ENTRY_AC = EM.ENTRY_AC
            LEFT OUTER JOIN (
                SELECT ENTRY_AC, COUNT(*) AS NUM_COMMENTS
                FROM INTERPRO.ENTRY_COMMENT
                GROUP BY ENTRY_AC
            ) EC ON E.ENTRY_AC = EC.ENTRY_AC
            WHERE E.CHECKED = 'N'
        ) E
        WHERE E.NUM_METHODS > 0
        ORDER BY UPDATED_TIME DESC
        """
    )
    entries = []
    for row in cur:
        entries.append({
            "accession": row[0],
            "type": row[1],
            "short_name": row[2],
            "created_date": row[3].strftime("%d %b %Y"),
            "update_date": row[4].strftime("%d %b %Y"),
            "user": row[5],
            "signatures": row[6],
            "comments": row[7]
        })
    cur.close()
    con.close()
    return jsonify(entries)
