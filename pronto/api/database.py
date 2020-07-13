# -*- coding: utf-8 -*-

import json

from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api.database", __name__, url_prefix="/api/database")


@bp.route("/<db_name>/signatures/")
def get_integrated_signatures(db_name):
    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

    try:
        integrated = bool(int(request.args["integrated"]))
    except (KeyError, ValueError):
        integrated = None

    try:
        checked = bool(int(request.args["checked"]))
    except (KeyError, ValueError):
        checked = None

    try:
        commented = bool(int(request.args["commented"]))
    except (KeyError, ValueError):
        commented = None

    search_query = request.args.get("search", "").strip()

    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, name_long, version
        FROM database
        WHERE name = %s
        """, (db_name,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify({
            "results": [],
            "count": 0,
            "database": None
        }), 404
    db_identifier, db_full_name, db_version = row

    sql = """
        SELECT accession, num_sequences
        FROM interpro.signature
        WHERE database_id = %s
    """

    if search_query:
        sql += "AND LOWER(accession) LIKE %s"
        params = (db_identifier, f"{search_query.lower()}%")
    else:
        params = (db_identifier,)

    cur.execute(f"{sql} ORDER BY accession", params)
    pg_signatures = cur.fetchall()
    cur.close()
    con.close()

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT 
          M.METHOD_AC, 
          E.ENTRY_AC, 
          E.ENTRY_TYPE, 
          E.CHECKED,
          C.VALUE,
          C.NAME,
          C.CREATED_ON
        FROM INTERPRO.CV_DATABASE D
        INNER JOIN INTERPRO.METHOD M
          ON D.DBCODE = M.DBCODE
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
          ON M.METHOD_AC = EM.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E 
          ON E.ENTRY_AC = EM.ENTRY_AC
        LEFT OUTER JOIN (
          SELECT
            C.METHOD_AC,
            C.VALUE,
            P.NAME,
            C.CREATED_ON,
            ROW_NUMBER() OVER (
              PARTITION BY METHOD_AC 
              ORDER BY C.CREATED_ON DESC
            ) R
            FROM INTERPRO.METHOD_COMMENT C
            INNER JOIN INTERPRO.PRONTO_USER P 
              ON C.USERNAME = P.USERNAME
        ) C ON (M.METHOD_AC = C.METHOD_AC AND C.R = 1)
        WHERE LOWER(D.DBSHORT) = :1

        """, (db_name,)
    )
    ora_signatures = {row[0]: row[1:] for row in cur}
    cur.close()
    con.close()

    results = []
    for acc, cnt in pg_signatures:
        try:
            info = ora_signatures[acc]
        except KeyError:
            info = [None] * 5

        if integrated is True and not info[0]:
            continue
        elif integrated is False and info[0]:
            continue

        if checked is True and info[2] != 'Y':
            continue
        elif checked is False and info[2] != 'N':
            continue

        if commented is True and not info[3]:
            continue
        elif commented is False and info[3]:
            continue

        results.append({
            "accession": acc,
            "entry": {
                "accession": info[0],
                "type": info[1],
                "checked": info[2] == 'Y',
            } if info[1] else None,
            "proteins": {
                "then": None,
                "now": cnt
            },
            "latest_comment": {
                "text": info[3],
                "author": info[4],
                "date": info[5].strftime("%d %B %Y at %H:%M")
            } if info[5] else None
        })

    num_results = len(results)
    results = results[(page - 1) * page_size:page * page_size]

    if results:
        # Get the count from the latest InterPro release (using the MySQL DW)
        accessions = [res["accession"] for res in results]
        counts = {}

        con = utils.connect_mysql()
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT accession, counts
            FROM webfront_entry
            WHERE accession IN ({','.join('%s' for _ in accessions)})
            """, accessions
        )

        for row in cur:
            counts[row[0]] = json.loads(row[1])["proteins"]

        cur.close()
        con.close()

        for res in results:
            acc = res["accession"]
            res["proteins"]["then"] = counts.get(acc, 0)

    return jsonify({
        "page_info": {
            "page": page,
            "page_size": page_size
        },
        "results": results,
        "count": num_results,
        "database": {
            "name": db_full_name,
            "version": db_version
        }
    })


@bp.route("/<db_name>/unintegrated/")
def get_unintegrated_signatures(db_name):
    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

    search_query = request.args.get("search", "").strip().lower()

    try:
        sort_by = request.args["sort"]
    except KeyError:
        sort_by = "accession"
    else:
        if sort_by not in ("accession", "similarity"):
            return jsonify({
                "error": {
                    "title": "Bad Request (invalid sort parameter)",
                    f"message": "Accepted values are: "
                                "accession, similarity."
                }
            }), 400

    rel_filter = request.args.get("relationship", "similar")
    if rel_filter not in ("similar", "parent", "child", "none"):
        return jsonify({
            "error": {
                "title": "Bad Request (invalid relationship parameter)",
                f"message": "Accepted values are: "
                            "similar, parent, child, none."
            }
        }), 400

    try:
        integ_filter = request.args["target"]
    except KeyError:
        integ_filter = None
    else:
        if integ_filter not in ("integrated", "unintegrated"):
            return jsonify({
                "error": {
                    "title": "Bad Request (invalid target parameter)",
                    f"message": "Accepted values are: "
                                "integrated, unintegrated."
                }
            }), 400

    con = utils.connect_oracle()
    cur = con.cursor()
    # cur.execute(
    #     """
    #     SELECT METHOD_AC, COUNT(*)
    #     FROM INTERPRO.METHOD_COMMENT
    #     GROUP BY METHOD_AC
    #     """
    # )
    # num_comments = dict(cur.fetchall())

    cur.execute(
        """
        SELECT EM.METHOD_AC, E.ENTRY_AC, E.NAME, E.ENTRY_TYPE, E.CHECKED
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.ENTRY E ON EM.ENTRY_AC = E.ENTRY_AC
        """
    )

    integrated = {}
    for row in cur:
        integrated[row[0]] = {
            "accession": row[1],
            "name": row[2],
            "type": row[3],
            "checked": row[4] == 'Y',
        }

    cur.close()
    con.close()

    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, name_long, version
        FROM database
        WHERE name = %s
        """, (db_name,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify({
            "results": [],
            "count": 0,
            "database": None
        }), 404
    db_identifier, db_full_name, db_version = row

    if search_query:
        search_stmt = "AND (LOWER(accession) LIKE %s OR LOWER(name) LIKE %s)"
        params = (db_identifier, search_query, search_query)
    else:
        search_stmt = ""
        params = (db_identifier,)

    cur.execute(
        f"""
        SELECT accession
        FROM signature
        WHERE database_id = %s
        {search_stmt}
        """, params
    )
    unintegrated = {acc for acc, in cur if acc not in integrated}

    cur.execute(
        """
        SELECT s.accession, s.name, s.type, s.num_complete_sequences,
               d.name, d.name_long
        FROM signature s
        INNER JOIN database d ON s.database_id = d.id
        """
    )
    signatures = {}
    for acc, name, _type, num_proteins, db_key, db_name in cur:
        database = utils.get_database_obj(db_key)
        signatures[acc] = {
            "accession": acc,
            "database": {
                "name": db_name,
                "color": database.color
            },
            "type": _type,
            "proteins": num_proteins,
            "entry": integrated.get(acc)
        }

    if rel_filter != "none":
        rel_sql = "AND c.relationship = %s"
        params = (db_identifier, rel_filter)
    elif rel_filter == "none":
        rel_sql = "AND c.relationship IS NULL"
        params = (db_identifier,)
    else:
        rel_sql = ""
        params = (db_identifier,)

    cur.execute(
        f"""
        SELECT q.accession, t.accession, p.collocation,p.overlap,
               p.similarity, p.relationship
        FROM interpro.signature q
        INNER JOIN interpro.prediction p ON q.accession = p.signature_acc_1
        INNER JOIN interpro.signature t ON p.signature_acc_2 = t.accession
        WHERE q.database_id = %s {rel_sql}
        """, params
    )

    queries = {}
    for row in cur:
        query_acc = row[0]
        target_acc = row[1]
        collocations = row[2]
        overlaps = row[3]
        similarity = row[4]
        relationship = row[5]

        if query_acc not in unintegrated:
            continue
        elif target_acc in integrated:
            if integ_filter == "unintegrated":
                continue  # we want unintegrated targets only: skip
        elif integ_filter == "integrated":
            continue      # we want integrated targets only: skip

        query = signatures[query_acc]
        target = signatures[target_acc]

        q_is_hs = query["type"] == "Homologous_superfamily"
        t_is_hs = target["type"] == "Homologous_superfamily"
        if q_is_hs != t_is_hs:
            continue

        try:
            q = queries[query_acc]
        except KeyError:
            q = queries[query_acc] = []
        finally:
            q.append({
                "accession": target_acc,
                "relationship": relationship,
                "similarity": similarity,
                "collocations": collocations,
                "overlaps": overlaps
            })

    cur.close()
    con.close()

    def _sort(s):
        return -s["similarity"], -s["overlaps"]

    results = []
    for acc in unintegrated:
        query = signatures[acc].copy()
        query.update({
            # "comments": num_comments.get(acc, 0),
            "targets": []
        })

        try:
            targets = queries[acc]
        except KeyError:
            if rel_filter == "none":
                results.append(query)
            continue

        for t in sorted(targets, key=_sort):
            target = signatures[t["accession"]].copy()
            target.update({
                "relationship": t["relationship"],
                "collocations": t["collocations"],
                "overlaps": t["overlaps"],
                "similarity": t["similarity"]
            })

            query["targets"].append(target)
        results.append(query)

    if sort_by == "accession":
        results.sort(key=lambda x: x["accession"])
    else:
        results.sort(key=lambda x: -max(t["similarity"] for t in x["targets"]))

    num_results = len(results)
    results = results[(page-1)*page_size:page*page_size]

    # Remove similarity from targets
    for r in results:
        for t in r["targets"]:
            del t["similarity"]

    return jsonify({
        "page_info": {
            "page": page,
            "page_size": page_size
        },
        "results": results,
        "count": num_results,
        "database": {
            "name": db_full_name,
            "version": db_version
        },
        "parameters": {
            "relationship": rel_filter,
            "target": integ_filter,
            "sort": sort_by
        }
    })
