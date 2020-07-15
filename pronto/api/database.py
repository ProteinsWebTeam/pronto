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
    cur.execute(
        """
        SELECT M.METHOD_AC, COUNT(*)
        FROM INTERPRO.METHOD_COMMENT MC
        INNER JOIN INTERPRO.METHOD M ON MC.METHOD_AC = M.METHOD_AC
        WHERE M.DBCODE = (
            SELECT DBCODE 
            FROM INTERPRO.CV_DATABASE 
            WHERE DBSHORT = :1
        )
        GROUP BY M.METHOD_AC
        """, (db_name.upper(),)
    )
    num_comments = dict(cur.fetchall())
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

    cur.execute(
        """
        SELECT accession, type, num_complete_sequences, num_residues
        FROM signature
        WHERE database_id = %s
        """, (db_identifier,)
    )
    db_unintegrated = {}
    for accession, _type, num_proteins, num_residues in cur:
        if accession not in integrated:
            db_unintegrated[accession] = (_type, num_proteins, num_residues)

    cur.execute(
        """
        SELECT s1.accession, s2.accession, s2.type, s2.num_complete_sequences, 
               s2.num_residues, d.name, d.name_long, 
               p.collocations, p.protein_overlaps, p.residue_overlaps
        FROM interpro.signature s1
        INNER JOIN interpro.prediction p ON s1.accession = p.signature_acc_1
        INNER JOIN interpro.signature s2 ON p.signature_acc_2 = s2.accession
        INNER JOIN interpro.database d ON s2.database_id = d.id
        WHERE s1.database_id = %s
        """, (db_identifier,)
    )
    queries = {}
    for row in cur:
        q_acc = row[0]
        try:
            q_type, q_proteins, q_residues = db_unintegrated[q_acc]
        except KeyError:
            continue

        t_acc = row[1]
        t_entry = integrated.get(t_acc)
        if t_entry:
            if integ_filter == "unintegrated":
                continue  # we want unintegrated targets only: skip
        elif integ_filter == "integrated":
            continue  # we want integrated targets only: skip

        t_type = row[2]
        t_proteins = row[3]
        t_residues = row[4]
        t_db_key = row[5]
        t_db_name = row[6]
        collocations = row[7]
        protein_overlaps = row[8]
        residue_overlaps = row[9]

        q_is_hs = q_type == "Homologous_superfamily"
        t_is_hs = t_type == "Homologous_superfamily"
        if q_is_hs != t_is_hs:
            continue  # Invalid type pair (HS can only be together)

        p = utils.Prediction(q_proteins, t_proteins, protein_overlaps)
        if p.relationship != rel_filter:
            continue  # not the relationship we're after

        pr = utils.Prediction(q_residues, t_residues, residue_overlaps)

        try:
            q = queries[q_acc]
        except KeyError:
            q = queries[q_acc] = []
        finally:
            q.append({
                # Target signature
                "accession": t_acc,
                "database": {
                    "name": t_db_name,
                    "color": utils.get_database_obj(t_db_key).color
                },
                "entry": t_entry,
                "proteins": t_proteins,

                # Comparison query/target
                "collocations": collocations,
                "overlaps": protein_overlaps,
                "similarity": p.similarity,
                "containment": p.containment,
                "relationship": p.relationship,
                "residues": {
                    "similarity": pr.similarity,
                    "containment": pr.containment,
                    "relationship": pr.relationship,
                }
            })

    cur.close()
    con.close()

    results = []
    for q_acc, (q_type, q_proteins, q_residues) in db_unintegrated.items():
        query = {
            "accession": q_acc,
            "proteins": q_proteins,
            "comments": num_comments.get(q_acc, 0),
            "targets": []
        }

        if q_acc in queries:
            query["targets"] = sorted(queries[q_acc], key=_sort_target)
            results.append(query)
        elif rel_filter == "none":
            results.append(query)

    results.sort(key=_sort_results)

    num_results = len(results)
    results = results[(page-1)*page_size:page*page_size]

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
            "target": integ_filter
        }
    })


def _sort_target(s):
    if s["relationship"] == "similar":
        return -s["residues"]["similarity"]
    return -s["residues"]["containment"]


def _sort_results(s):
    if s["targets"]:
        return _sort_target(s["targets"][0])
    return s["accession"]
