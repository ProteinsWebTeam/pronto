import json

from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api_database", __name__, url_prefix="/api/database")


def get_latest_freeze(cur):
    """
    Get the date of the last time a record for InterPro was inserted into the
    DB_VERSION_AUDIT table (triggered by an action for InterPro in DB_VERSION).
    This roughly corresponds to the date of the last production freeze.
    :param cur: Oracle cursor
    :return: datetime object
    """
    cur.execute(
        """
        SELECT TIMESTAMP
        FROM (
            SELECT TIMESTAMP, ROWNUM AS RN
            FROM (
                SELECT TIMESTAMP
                FROM INTERPRO.DB_VERSION_AUDIT
                WHERE DBCODE = 'I'
                ORDER BY TIMESTAMP DESC
            )
        )
        WHERE RN = 1
        """
    )
    date, = cur.fetchone()
    return date


@bp.route("/<db_name>/signatures/")
def get_signatures(db_name):
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
        llm = bool(int(request.args["llm"]))
    except (KeyError, ValueError):
        llm = None

    try:
        past_integrated = bool(int(request.args["pastintegrated"]))
    except (KeyError, ValueError):
        past_integrated = None

    try:
        commented = bool(int(request.args["commented"]))
    except (KeyError, ValueError):
        commented = None

    try:
        filter_type = bool(int(request.args["sametype"]))
    except (KeyError, ValueError):
        filter_type = None

    order_by = request.args.get("sort-by", "accession").lower()
    if order_by not in ("accession", "proteins", "reviewed-proteins"):
        return (
            jsonify({
                "error": {
                    "title": "Bad Request (invalid sorting parameter)",
                    "message": "Accepted values are: accession, proteins, "
                               "reviewed-proteins",
                }
            }),
            400
        )

    order_dir = request.args.get("sort-order", "asc")
    if order_dir not in ("asc", "desc"):
        return (
            jsonify({
                "error": {
                    "title": "Bad Request (invalid sorting direction)",
                    "message": "Accepted values are: asc, desc",
                }
            }),
            400
        )

    search_query = request.args.get("search", "").strip()
    details = "details" in request.args
    if "with-abstract" in request.args:
        abstract_filter = ("AND (abstract IS NOT NULL "
                           "OR llm_abstract IS NOT NULL)")
    else:
        abstract_filter = ""

    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, name_long, version
        FROM database
        WHERE name = %s
        """,
        [db_name]
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

    sql = f"""
        SELECT accession, name, type, num_sequences
        FROM interpro.signature
        WHERE database_id = %s {abstract_filter}
    """

    if search_query:
        sql += " AND (LOWER(accession) LIKE %s OR LOWER(name) LIKE %s)"
        params = [db_identifier,
                  f"{search_query.lower()}%",
                  f"{search_query.lower()}%"]
    else:
        params = [db_identifier]

    if llm is True:
        sql += """
            AND (llm_name IS NOT NULL AND 
                 llm_description IS NOT NULL
                 AND llm_abstract IS NOT NULL)
            AND (name IS NULL OR description IS NULL OR abstract IS NULL)
        """
    elif llm is False:
        sql += """
            AND llm_name IS NULL 
            AND llm_description IS NULL
            AND llm_abstract IS NULL
        """

    if order_by == "accession":
        sql += f" ORDER BY accession {order_dir}"
    elif order_by == "proteins":
        sql += f" ORDER BY num_sequences {order_dir}"
    else:
        sql += (f" ORDER BY num_reviewed_sequences {order_dir}, "
                f"num_sequences {order_dir}")

    cur.execute(sql, params)
    pg_signatures = cur.fetchall()
    cur.close()
    con.close()

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute("SELECT CODE, ABBREV FROM INTERPRO.CV_ENTRY_TYPE")
    code2type = dict(cur.fetchall())

    cur.execute(
        """
        SELECT 
          M.METHOD_AC, 
          E.ENTRY_AC, 
          E.ENTRY_TYPE,
          E.SHORT_NAME,
          E.CHECKED,
          C.VALUE,
          C.NAME,
          C.CREATED_ON, 
          NVL(EA.NUM_ENTRIES, 0)
        FROM INTERPRO.CV_DATABASE D
        INNER JOIN INTERPRO.METHOD M
          ON D.DBCODE = M.DBCODE
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM 
          ON M.METHOD_AC = EM.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E 
          ON E.ENTRY_AC = EM.ENTRY_AC
        LEFT OUTER JOIN (
          SELECT METHOD_AC, COUNT(DISTINCT ENTRY_AC) AS NUM_ENTRIES
          FROM INTERPRO.ENTRY2METHOD_AUDIT
          GROUP BY METHOD_AC
        ) EA ON M.METHOD_AC = EA.METHOD_AC
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
            WHERE C.STATUS='Y'
        ) C ON (M.METHOD_AC = C.METHOD_AC AND C.R = 1)
        WHERE LOWER(D.DBSHORT) = :1
        """,
        [db_name]
    )
    ora_signatures = {row[0]: row[1:] for row in cur}
    cur.close()
    con.close()

    results = []
    for acc, name, type_name, cnt in pg_signatures:
        try:
            info = ora_signatures[acc]
        except KeyError:
            info = [None] * 8

        entry_acc = info[0]
        type_code = info[1]
        entry_type_name = code2type[type_code] if entry_acc else None
        entry_name = info[2]
        is_checked = info[3] == "Y"
        comment_text = info[4]
        comment_author = info[5]
        comment_date = info[6]
        is_past_integrated = info[7] is not None and info[7] > 0

        if past_integrated is True and not is_past_integrated:
            continue
        elif past_integrated is False and is_past_integrated:
            continue

        if integrated is True and not entry_acc:
            continue
        elif integrated is False and entry_acc:
            continue

        if checked is True and not is_checked:
            continue
        elif checked is False and is_checked:
            continue

        if commented is True and not comment_text:
            continue
        elif commented is False and comment_text:
            continue

        if filter_type is True and type_name != entry_type_name:
            continue
        elif filter_type is False and type_name == entry_type_name:
            continue

        results.append({
            "accession": acc,
            "type": {
                "code": [k for k, v in code2type.items()
                         if v == type_name][0],
                "name": type_name.replace("_", " "),
            },
            "name": name,
            "entry": {
                "accession": entry_acc,
                "short_name": entry_name,
                "type": {
                    "code": type_code,
                    "name": entry_type_name.replace("_", " ")
                },
                "checked": is_checked,
            } if entry_acc else None,
            "proteins": {"then": 0, "now": cnt},
            "latest_comment": {
                "text": comment_text,
                "author": comment_author,
                "date": comment_date.strftime("%d %b %Y at %H:%M"),
            } if comment_text else None
        })

    num_results = len(results)
    results = results[(page - 1) * page_size : page * page_size]

    if results and details:
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
            """,
            accessions
        )

        for row in cur:
            counts[row[0]] = json.loads(row[1])["proteins"]

        cur.close()
        con.close()

        for res in results:
            acc = res["accession"]
            res["proteins"]["then"] = counts.get(acc, 0)

    return jsonify({
        "page_info": {"page": page, "page_size": page_size},
        "results": results,
        "count": num_results,
        "database": {"name": db_full_name, "version": db_version},
    })


@bp.route("/<db_name>/unintegrated/")
def get_unintegrated(db_name):
    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

    sort_col = request.args.get("sort-by", "accession")
    if sort_col not in ("accession", "proteins", "single-domain-proteins"):
        return (
            jsonify({
                "error": {
                    "title": "Bad Request (invalid sorting parameter)",
                    "message": "Accepted values are: accession, proteins, "
                               "single-domain-proteins",
                }
            }),
            400
        )

    sort_order = request.args.get("sort-order", "asc")
    if sort_order not in ("asc", "desc"):
        return (
            jsonify({
                "error": {
                    "title": "Bad Request (invalid sorting direction)",
                    "message": "Accepted values are: asc, desc",
                }
            }),
            400
        )

    rel_filter = request.args.get("relationships", "without-integrated")
    if rel_filter not in ("without", "without-integrated", "with"):
        return (
            jsonify({
                "error": {
                    "title": "Bad Request (invalid relationships parameter)",
                    "message": "Accepted values are: without, "
                               "without-integrated, with",
                }
            }),
            400
        )

    try:
        comment_filter = int(request.args["commented"]) != 0
    except KeyError:
        comment_filter = None
    except ValueError:
        return (
            jsonify({
                "error": {
                    "title": "Bad Request (invalid commented parameter)",
                    "message": "An integer is expected",
                }
            }),
            400
        )

    try:
        min_sd_ratio = int(request.args["min-sl-dom-ratio"])
    except KeyError:
        min_sd_ratio = 0
    except ValueError:
        return (
            jsonify({
                "error": {
                    "title": "Bad Request (invalid min-sl-dom-ratio parameter)",
                    "message": "An integer between 0 and 100 is expected",
                }
            }),
            400
        )

    if not 0 <= min_sd_ratio <= 100:
        return (
            jsonify({
                "error": {
                    "title": "Bad Request (invalid min-sl-dom-ratio parameter)",
                    "message": "An integer between 0 and 100 is expected",
                }
            }),
            400
        )

    if "with-abstract" in request.args:
        abstract_filter = ("AND (abstract IS NOT NULL "
                           "OR llm_abstract IS NOT NULL)")
    else:
        abstract_filter = ""

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT METHOD_AC, COUNT(*)
        FROM INTERPRO.METHOD_COMMENT
        WHERE STATUS = 'Y'
        GROUP BY METHOD_AC
        """
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
    for row in cur.fetchall():
        integrated[row[0]] = {
            "accession": row[1],
            "name": row[2],
            "type": row[3],
            "checked": row[4] == "Y"
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
        """,
        [db_name]
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
        f"""
        SELECT accession, type, num_complete_sequences, 
            num_complete_single_domain_sequences, num_residues
        FROM signature
        WHERE database_id = %s {abstract_filter}
        """,
        [db_identifier]
    )

    unintegrated = {}
    _min_sd_ratio = min_sd_ratio / 100
    for acc, _type, n_prots, n_sd_prots, n_res in cur.fetchall():
        if acc in integrated:
            continue
        elif _min_sd_ratio and (n_prots == 0 or
                                n_sd_prots / n_prots < _min_sd_ratio):
            continue

        unintegrated[acc] = (_type, n_prots, n_sd_prots, n_res)

    queries = {}
    cur.execute(
        """
        SELECT s1.accession, s2.accession, s2.type,
               s2.num_complete_sequences, s2.num_residues, s2.database_id,
               d.name, d.name_long, p.num_collocations,
               p.num_protein_overlaps, p.num_residue_overlaps
        FROM interpro.signature s1
        INNER JOIN interpro.prediction p
            ON s1.accession = p.signature_acc_1
        INNER JOIN interpro.signature s2
            ON p.signature_acc_2 = s2.accession
        INNER JOIN interpro.database d
            ON s2.database_id = d.id
        WHERE s1.database_id = %s
        """,
        [db_identifier]
    )

    for row in cur.fetchall():
        q_acc = row[0]

        try:
            q_type, q_proteins, _, q_residues = unintegrated[q_acc]
        except KeyError:
            continue

        t_acc = row[1]
        t_type = row[2]
        t_proteins = row[3]
        t_residues = row[4]
        t_db_id = row[5]
        t_db_key = row[6]
        t_db_name = row[7]
        collocations = row[8]
        protein_overlaps = row[9]
        residue_overlaps = row[10]
        t_entry = integrated.get(t_acc)

        # if not check_types(q_type, t_type):
        #     # Invalid type pair (HS can only be together)
        #     continue

        p = utils.Prediction(q_proteins, t_proteins, protein_overlaps)
        if not p.relationship:
            continue

        pr = utils.Prediction(q_residues, t_residues, residue_overlaps)

        try:
            q = queries[q_acc]
        except KeyError:
            q = queries[q_acc] = []

        q.append({
            # Target signature
            "accession": t_acc,
            "database": {
                "name": t_db_name,
                "color": utils.get_database_obj(t_db_key).color,
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
            },
        })

    cur.close()
    con.close()

    results = []
    for q_acc, obj in unintegrated.items():
        q_comments = num_comments.get(q_acc, 0)
        if comment_filter is not None:
            if comment_filter:
                if not q_comments:
                    continue
            elif q_comments:
                continue

        targets = queries.get(q_acc, [])
        if rel_filter == "without" and targets:
            continue
        elif (rel_filter == "without-integrated" and
              any([t["entry"] is not None for t in targets])):
            continue
        elif rel_filter == "with" and not targets:
            continue

        _, q_proteins, q_single_dom_proteins, _ = obj
        results.append({
            "accession": q_acc,
            "proteins": q_proteins,
            "single_domain_proteins": q_single_dom_proteins,
            "comments": q_comments,
            "targets": sorted(targets, key=lambda x: x["accession"]),
        })

    results.sort(key=lambda x: x[sort_col.replace("-", "_")],
                 reverse=sort_order == "desc")

    return jsonify({
        "page_info": {"page": page, "page_size": page_size},
        "results": results[(page - 1) * page_size:page * page_size],
        "count": len(results),
        "database": {"name": db_full_name, "version": db_version},
        "parameters": {
            "commented": (None if comment_filter is None else
                          ("1" if comment_filter else "0")),
            "relationships": rel_filter,
            "min-sl-dom-ratio": str(min_sd_ratio),
            "sort-by": sort_col,
            "sort-order": sort_order
        }
    })


def check_types(type1: str, type2: str) -> bool:
    hs = "Homologous_superfamily"
    return (type1 == hs) == (type2 == hs)
