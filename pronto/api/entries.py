# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from pronto import utils
from pronto.api.database import get_latest_freeze


bp = Blueprint("api.entries", __name__, url_prefix="/api/entries")


@bp.route("/counts/")
def get_counts():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT YEAR, COUNT(*), SUM(CHECKED)
        FROM (
            SELECT ENTRY_AC, 
                   CASE WHEN CHECKED = 'Y' THEN 1 ELSE 0 END CHECKED,
                   EXTRACT(YEAR FROM CREATED) YEAR
            FROM INTERPRO.ENTRY
        )
        GROUP BY YEAR
        ORDER BY YEAR
        """
    )

    results = []
    for year, total, checked in cur:
        results.append({
            "year": year,
            "total": total,
            "checked": checked
        })

    cur.close()
    con.close()

    return jsonify({
        "results": results
    }), 200


@bp.route("/counts/citations/")
def get_citations_count():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*) 
        FROM INTERPRO.ENTRY2PUB P
        INNER JOIN INTERPRO.ENTRY E ON P.ENTRY_AC = E.ENTRY_AC
        WHERE E.CHECKED = 'Y'
        """
    )
    cnt, = cur.fetchone()
    cur.close()
    con.close()

    return jsonify({
        "count": cnt
    }), 200


@bp.route("/counts/go/")
def get_go_count():
    con = utils.connect_oracle()
    cur = con.cursor()

    # Checked entries with at least one GO term
    cur.execute(
        """
        SELECT IG.N_TERMS, COUNT(*)
        FROM (
            SELECT E.ENTRY_AC, COUNT(*) N_TERMS
            FROM INTERPRO.INTERPRO2GO G
            INNER JOIN INTERPRO.ENTRY E ON G.ENTRY_AC = E.ENTRY_AC
            WHERE E.CHECKED = 'Y'
            GROUP BY E.ENTRY_AC
        ) IG
        GROUP BY N_TERMS
        """
    )
    counts = dict(cur.fetchall())

    # Checked entries without GO terms
    cur.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT ENTRY_AC
            FROM INTERPRO.ENTRY
            WHERE CHECKED = 'Y'
            MINUS SELECT DISTINCT ENTRY_AC
            FROM INTERPRO.INTERPRO2GO
        )        
        """
    )
    counts[0], = cur.fetchone()
    cur.close()
    con.close()

    return jsonify({
        "results": [{
            "terms": n_terms,
            "entries": counts[n_terms]
        } for n_terms in sorted(counts)]
    })


@bp.route("/counts/signatures/")
def get_signature_count():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*), 
               SUM(CASE WHEN CHECKED = 'Y' THEN 1 ELSE 0 END)
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.ENTRY E ON EM.ENTRY_AC = E.ENTRY_AC
        """
    )
    total, checked = cur.fetchone()

    cur.execute(
        """
        SELECT EM.METHOD_AC, EM.TIMESTAMP
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.ENTRY E ON EM.ENTRY_AC = E.ENTRY_AC
        WHERE EM.TIMESTAMP >= ADD_MONTHS(SYSDATE, -12)
        AND E.CHECKED = 'Y'
        """,
    )

    weeks = {}
    for acc, date in cur:
        # ISO calendar format (%G -> year, %V -> week, 1 -> Monday)
        iso_cal = date.strftime("%G%V1")

        try:
            weeks[iso_cal].add(acc)
        except KeyError:
            weeks[iso_cal] = {acc}

    cur.close()
    con.close()

    results = []
    for iso_cal in sorted(weeks):
        # Get timestamps from ISO calendar day
        ts = datetime.strptime(iso_cal, "%G%V%u").timestamp()

        results.append({
            "timestamp": ts,
            "week": int(iso_cal[4:6]),  # week number
            "count": len(weeks[iso_cal])
        })
    return jsonify({
        "total": total,
        "checked": checked,
        "results": results
    })


@bp.route("/news/")
def get_recent_entries():
    con = utils.connect_oracle()
    cur = con.cursor()

    try:
        days = int(request.args["days"])
    except (KeyError, ValueError):
        date = get_latest_freeze(cur)
    else:
        date = datetime.today() - timedelta(days=days)

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
    cur.close()
    con.close()

    return jsonify({
        "date": date.strftime("%d %B"),
        "results": entries
    })


@bp.route("/news/go/")
def get_recent_go_terms():
    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, name, category
        FROM interpro.term
        """
    )
    terms = {}
    for term_id, name, category in cur:
        terms[term_id] = {
            "id": term_id,
            "name": name,
            "category": category
        }
    cur.close()
    con.close()

    con = utils.connect_oracle()
    cur = con.cursor()
    try:
        days = int(request.args["days"])
    except (KeyError, ValueError):
        date = get_latest_freeze(cur)
    else:
        date = datetime.today() - timedelta(days=days)

    cur.execute(
        """
        SELECT A.ENTRY_AC, A.SHORT_NAME, A.ENTRY_TYPE, A.GO_ID,
               A.TIMESTAMP, NVL(U.NAME, A.DBUSER)
        FROM (
            SELECT E.ENTRY_AC, E.SHORT_NAME, E.ENTRY_TYPE, A.GO_ID, A.ACTION,
                   A.TIMESTAMP, A.DBUSER, ROW_NUMBER() OVER (
                       PARTITION BY E.ENTRY_AC, A.GO_ID
                       ORDER BY A.TIMESTAMP DESC
                   ) RN
            FROM INTERPRO.INTERPRO2GO_AUDIT A
            INNER JOIN INTERPRO.ENTRY E ON A.ENTRY_AC = E.ENTRY_AC
            WHERE A.TIMESTAMP >= :1
        ) A
        LEFT OUTER JOIN INTERPRO.PRONTO_USER U ON A.DBUSER = U.DB_USER
        WHERE A.RN = 1
        AND A.ACTION = 'I'
        ORDER BY A.TIMESTAMP DESC
        """, (date,)
    )

    interpro2go = []
    for row in cur:
        interpro2go.append({
            "entry": {
                "accession": row[0],
                "short_name": row[1],
                "type": row[2]
            },
            "term": terms[row[3]],
            "date": row[4].strftime("%d %b %Y"),
            "user": row[5]
        })
    cur.close()
    con.close()

    return jsonify({
        "date": date.strftime("%d %B"),
        "results": interpro2go
    })


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


def _get_quarterly_entries(cur, date):
    cur.execute(
        """
        SELECT ENTRY_AC, ACTION, TIMESTAMP
        FROM INTERPRO.ENTRY_AUDIT
        WHERE TIMESTAMP >= :1
        AND ACTION IN ('I', 'D')
        """, (date,)
    )

    quarters = {}
    for entry_acc, action, date in cur:
        key = f"{date.year} Q{date.month //4 + 1}"
        try:
            entries = quarters[key]
        except KeyError:
            entries = quarters[key] = set()

        if action == 'I':
            entries.add(entry_acc)
        else:
            try:
                entries.remove(entry_acc)
            except KeyError:
                pass

    for key, entries in quarters.items():
        quarters[key] = len(entries)

    return quarters


def _get_quarterly_signatures(cur, date):
    cur.execute(
        """
        SELECT METHOD_AC, ACTION, TIMESTAMP
        FROM INTERPRO.ENTRY2METHOD_AUDIT
        WHERE TIMESTAMP >= :1 
        AND ACTION IN ('I', 'D')
        """, (date,)
    )

    quarters = {}
    for acc, action, date in cur:
        key = f"{date.year} Q{date.month //4 + 1}"
        try:
            entries = quarters[key]
        except KeyError:
            entries = quarters[key] = {}

        i = 1 if action == 'I' else -1
        try:
            entries[acc] += i
        except KeyError:
            entries[acc] = i

    for key, entries in quarters.items():
        quarters[key] = len([i for i in entries.values() if i > 0])

    return quarters


def _get_quarterly_go(cur, date):
    cur.execute(
        """
        SELECT ENTRY_AC || GO_ID, ACTION, TIMESTAMP
        FROM INTERPRO.INTERPRO2GO_AUDIT A
        WHERE TIMESTAMP >= :1
        AND ACTION IN ('I', 'D')
        """, (date,)
    )

    quarters = {}
    for entry2go, action, date in cur:
        key = f"{date.year} Q{date.month //4 + 1}"
        try:
            entries = quarters[key]
        except KeyError:
            entries = quarters[key] = {}

        i = 1 if action == 'I' else -1
        try:
            entries[entry2go] += i
        except KeyError:
            entries[entry2go] = i

    for key, entries in quarters.items():
        quarters[key] = len([i for i in entries.values() if i > 0])

    return quarters


@bp.route("/stats/")
def get_quarterly_stats():
    date = datetime(datetime.today().year - 1, 1, 1)

    con = utils.connect_oracle()
    cur = con.cursor()
    entries = _get_quarterly_entries(cur, date)
    signatures = _get_quarterly_signatures(cur, date)
    terms = _get_quarterly_go(cur, date)
    cur.close()
    con.close()

    keys = set(entries.keys()) | set(signatures.keys()) | set(terms.keys())

    quarters = []
    for key in sorted(keys):
        quarters.append({
            "quarter": key,
            "entries": entries.get(key, 0),
            "signatures": signatures.get(key, 0),
            "terms": terms.get(key, 0)
        })

    return jsonify(quarters)
