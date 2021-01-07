# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api.entries", __name__, url_prefix="/api/entries")


def get_recent_entries(cur, date):
    """
    Get recent entries, i.e. entries created after the last production freeze
    (for release N), and meant to be part of the next InterPro release (N+1).

    :param cur: Oracle cursor
    :param date: date of last production freeze
    :return: list of entries
    """
    cur.execute(
        """
        SELECT
          E.ENTRY_AC, E.ENTRY_TYPE, E.SHORT_NAME, A.TIMESTAMP,
          NVL(U.NAME, A.DBUSER), E.CHECKED, NVL(EC.CNT, 0), NVL(MC.CNT, 0)
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
          SELECT ENTRY_AC, COUNT(*) AS CNT
          FROM INTERPRO.ENTRY_COMMENT
          WHERE STATUS = 'Y'
          GROUP BY ENTRY_AC
        ) EC ON E.ENTRY_AC = EC.ENTRY_AC
        LEFT OUTER JOIN (
          SELECT EM.ENTRY_AC, COUNT(*) AS CNT
          FROM INTERPRO.ENTRY2METHOD EM
          INNER JOIN INTERPRO.METHOD_COMMENT MC 
            ON EM.METHOD_AC = MC.METHOD_AC
          WHERE MC.STATUS = 'Y'
          GROUP BY EM.ENTRY_AC
        ) MC ON E.ENTRY_AC = MC.ENTRY_AC
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
            "comments": {
                "entry": row[6],
                "signatures": row[7]
            }
        })

    return entries


@bp.route("/unchecked/")
def get_unchecked_entries():
    mem_db = request.args.get("db", "any")

    con = utils.connect_oracle()
    cur = con.cursor()

    if mem_db == "any":
        filter_sql = "E.NUM_METHODS > 0"
        params = ()
    elif mem_db == "none":
        filter_sql = "E.NUM_METHODS = 0"
        params = ()
    else:
        cur.execute(
            """
            SELECT DBCODE
            FROM INTERPRO.CV_DATABASE
            WHERE LOWER(DBSHORT) = :1
            """, (mem_db.lower(),)
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Bad request",
                    "message": "Invalid or missing parameters."
                }
            }), 400

        dbcode, = row

        filter_sql = """
            E.ENTRY_AC IN (
                SELECT DISTINCT EM.ENTRY_AC
                FROM INTERPRO.ENTRY2METHOD EM
                INNER JOIN INTERPRO.METHOD M
                  ON EM.METHOD_AC = M.METHOD_AC
                  AND M.DBCODE = :1
            )
        """
        params = (dbcode,)

    cur.execute(
        f"""
        SELECT * FROM (
            SELECT
              E.ENTRY_AC, E.ENTRY_TYPE, E.SHORT_NAME, 
              NVL(FAE.TIMESTAMP, E.TIMESTAMP) AS CREATED_TIME,
              NVL(LAE.TIMESTAMP, E.TIMESTAMP) AS UPDATED_TIME, 
              NVL(U.NAME, E.USERSTAMP), 
              NVL(EM.CNT, 0) AS NUM_METHODS,
              NVL(EC.CNT, 0) AS NUM_ECOMMENTS,
              NVL(MC.CNT, 0) AS NUM_MCOMMENTS
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
              SELECT ENTRY_AC, COUNT(*) AS CNT
              FROM INTERPRO.ENTRY2METHOD
              GROUP BY ENTRY_AC
            ) EM ON E.ENTRY_AC = EM.ENTRY_AC
            LEFT OUTER JOIN (
                SELECT ENTRY_AC, COUNT(*) AS CNT
                FROM INTERPRO.ENTRY_COMMENT
                WHERE STATUS = 'Y'
                GROUP BY ENTRY_AC
            ) EC ON E.ENTRY_AC = EC.ENTRY_AC
            LEFT OUTER JOIN (
                SELECT EM.ENTRY_AC, COUNT(*) AS CNT
                FROM INTERPRO.ENTRY2METHOD EM
                INNER JOIN INTERPRO.METHOD_COMMENT MC 
                    ON EM.METHOD_AC = MC.METHOD_AC
                WHERE MC.STATUS = 'Y'
                GROUP BY EM.ENTRY_AC
            ) MC ON E.ENTRY_AC = MC.ENTRY_AC
            WHERE E.CHECKED = 'N'
        ) E
        WHERE {filter_sql}
        ORDER BY UPDATED_TIME DESC
        """, params
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
            "comments": {
                "entry": row[7],
                "signatures": row[8],
            }
        })
    cur.close()
    con.close()
    return jsonify(entries)
