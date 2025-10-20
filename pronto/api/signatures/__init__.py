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


@bp.route("/unintegrated/similar/")
def get_similar_unintegrated():
    min_sprot = float(request.args.get("min-sprot", 1))
    min_trembl = float(request.args.get("min-trembl", 0.85))
    database = request.args.get("database")
    allow_same_database = "allow-same-database" in request.args

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
        SELECT EM.METHOD_AC, E.ENTRY_AC, E.ENTRY_TYPE, E.NAME, E.SHORT_NAME, E.CHECKED
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
            "short_name": row[4],
            "checked": row[5] == 'Y'
        }

    cur.execute(
        """
        SELECT METHOD_AC, COUNT(*)
        FROM INTERPRO.METHOD_COMMENT
        WHERE STATUS = 'Y'
        GROUP BY METHOD_AC
        """
    )
    num_comments = dict(cur.fetchall())
    cur.close()
    con.close()

    con = utils.connect_pg()
    cur = con.cursor()
    try:
        filters = [
            "s1.num_complete_sequences > 0",
            "s2.num_complete_sequences > 0",
        ]
        params = []

        database_id = None
        if database:
            cur.execute(
                """
                SELECT id, name
                FROM interpro.database
                WHERE LOWER(name) = %s
                """,
                [database.lower()]
            )
            row = cur.fetchone()
            if not row:
                return (
                    jsonify({
                        "error": {
                            "title": "Bad Request",
                            "message": f"Invalid database parameter: {database}",
                        }
                    }),
                    400
                )

            database_id, database = row

        if database_id is not None:
            filters.append("d1.id = %s")
            params.append(database_id)

        cur.execute(
            f"""
            SELECT *
            FROM (
                SELECT x.accession1, x.name1, x.description1,
                       x.db_id1, x.db_name1,
                       x.sprot1, x.trembl1,
                       x.accession2, x.name2, x.description2,
                       x.db_id2, x.db_name2,
                       x.sprot2, x.trembl2,
                       x.ovl_sprot,
                       COALESCE(x.ovl_sprot::float / NULLIF(x.sprot1 + x.sprot2 - x.ovl_sprot, 0), 1) AS f_ovl_sprot,
                       x.ovl_trembl,
                       COALESCE(x.ovl_trembl::float / NULLIF(x.trembl1 + x.trembl2 - x.ovl_trembl, 0), 1) AS f_ovl_trembl
                FROM (
                  SELECT
                    s1.accession AS accession1,
                    s1.name AS name1,
                    s1.description AS description1,
                    d1.name AS db_id1,
                    d1.name_long AS db_name1,
                    s1.num_complete_reviewed_sequences AS sprot1,
                    (s1.num_complete_sequences - s1.num_complete_reviewed_sequences) AS trembl1,
                    s2.accession AS accession2,
                    s2.name AS name2,
                    s2.description AS description2,
                    d2.name AS db_id2,
                    d2.name_long AS db_name2,
                    s2.num_complete_reviewed_sequences AS sprot2,
                    (s2.num_complete_sequences - s2.num_complete_reviewed_sequences) AS trembl2,
                    c.num_reviewed_80pc_overlaps AS ovl_sprot,
                    (c.num_80pc_overlaps - c.num_reviewed_80pc_overlaps) AS ovl_trembl
                  FROM interpro.signature s1
                  INNER JOIN interpro.comparison c ON s1.accession = c.signature_acc_1
                  INNER JOIN interpro.signature s2 ON c.signature_acc_2 = s2.accession
                  INNER JOIN interpro.database d1 ON s1.database_id = d1.id
                  INNER JOIN interpro.database d2 ON s2.database_id = d2.id
                  WHERE (
                    (s1.type = 'Homologous_superfamily' AND s2.type = 'Homologous_superfamily')
                    OR
                    (s1.type != 'Homologous_superfamily' AND s2.type != 'Homologous_superfamily')
                  )
                  AND {' AND '.join(filters)}
                ) x
            ) x
            WHERE f_ovl_sprot >= %s
              AND f_ovl_trembl >= %s
            """,
            params + [min_sprot, min_trembl]
        )

        pthr_sf = re.compile(r"PTHR\d+:SF\d+")
        candidates = {}
        exclude = set()
        for row in cur:
            if row[0] in integrated or pthr_sf.match(row[0]):
                # Exclude candidates that are integrated or PANTHER subfams
                continue
            elif not allow_same_database and row[3] == row[10]:
                # Skip candidate signatures where the target is from the same DB
                exclude.add(row[0])
                continue

            entry = integrated.get(row[7])
            if not entry:
                # Target is not integrated: skip it
                continue

            try:
                obj = candidates[row[0]]
            except KeyError:
                obj = candidates[row[0]] = {
                    "accession": row[0],
                    "name": row[1],
                    "description": row[2],
                    "database": {
                        "color": utils.get_database_obj(row[3]).color,
                        "name": row[4]
                    },
                    "proteins": {
                        "reviewed": row[5],
                        "unreviewed": row[6]
                    },
                    "comments": num_comments.get(row[0], 0),
                    "targets": []
                }

            obj["targets"].append({
                "accession": row[7],
                "name": row[8],
                "description": row[9],
                "database": {
                    "color": utils.get_database_obj(row[10]).color,
                    "name": row[11]
                },
                "entry": entry,
                "proteins": {
                    "reviewed": row[12],
                    "unreviewed": row[13],
                    "overlapping": {
                        "reviewed": row[14],
                        "fraction_reviewed": row[15],
                        "unreviewed": row[16],
                        "fraction_unreviewed": row[17],
                    }
                },
            })
    finally:
        cur.close()
        con.close()

    results = []
    for c in candidates.values():
        if c["accession"] not in exclude:
            c["targets"].sort(key=lambda t: (
                -t["proteins"]["overlapping"]["fraction_reviewed"],
                -t["proteins"]["overlapping"]["fraction_unreviewed"],
                -t["proteins"]["overlapping"]["reviewed"],
                -t["proteins"]["overlapping"]["unreviewed"],
            ))
            results.append(c)

    results.sort(key=lambda c: (
        -c["targets"][0]["proteins"]["overlapping"]["fraction_reviewed"],
        -c["targets"][0]["proteins"]["overlapping"]["fraction_unreviewed"],
        -c["targets"][0]["proteins"]["overlapping"]["reviewed"],
        -c["targets"][0]["proteins"]["overlapping"]["unreviewed"],
    ))

    return jsonify({
        "count": len(results),
        "results": results[(page-1)*page_size:page*page_size],
        "page_info": {
            "page": page,
            "page_size": page_size
        },
        "filters": {
            "min-sprot": min_sprot,
            "min-trembl": min_trembl,
            "database": database
        },
    })


def get_very_similar_unintegrated():
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
    num_comments = dict(cur.fetchall())

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
                c.num_res_overlaps::float / (s1.num_residues + s2.num_residues - c.num_res_overlaps) AS sim_res
              FROM interpro.signature s1
              INNER JOIN interpro.comparison c ON s1.accession = c.signature_acc_1
              INNER JOIN interpro.signature s2 ON c.signature_acc_2 = s2.accession
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
            """,
            [min_sim]
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
                    "comments": num_comments.get(acc1, 0)
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


@bp.route("/unintegrated/specific/")
def get_specific_unintegrated():
    max_sprot = float(request.args.get("max-sprot", 0.01))
    max_trembl = float(request.args.get("max-trembl", 0.05))
    database = request.args.get("database")
    with_annotations = request.args.get("with-annotations", "")

    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 20

    if with_annotations == "true":
        with_annotations = True
    elif with_annotations == "false":
        with_annotations = False
    else:
        with_annotations = None

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute("SELECT METHOD_AC FROM INTERPRO.ENTRY2METHOD")
    integrated = {row[0] for row in cur.fetchall()}

    cur.execute(
        """
        SELECT METHOD_AC, COUNT(*)
        FROM INTERPRO.METHOD_COMMENT
        WHERE STATUS = 'Y'
        GROUP BY METHOD_AC
        """
    )
    num_comments = dict(cur.fetchall())

    cur.close()
    con.close()

    con = utils.connect_pg()
    cur = con.cursor()
    try:
        filters = ["s.num_complete_sequences > 0"]
        params = []

        if with_annotations is True:
            filters += [
                "s.name IS NOT NULL",
                "s.description IS NOT NULL",
                "s.abstract IS NOT NULL",
            ]
        elif with_annotations is False:
            filters.append("(s.name IS NULL "
                           "OR s.description IS NULL "
                           "OR s.abstract IS NULL)")

        database_id = None
        if database:
            cur.execute(
                """
                SELECT id, name 
                FROM interpro.database 
                WHERE LOWER(name) = %s
                """,
                [database.lower()]
            )
            row = cur.fetchone()
            if not row:
                return (
                    jsonify({
                        "error": {
                            "title": "Bad Request",
                            "message": f"Invalid database parameter: {database}",
                        }
                    }),
                    400
                )

            database_id, database = row

        if database_id is not None:
            filters.append("d.id = %s")
            params.append(database_id)

        cur.execute(
            f"""
            SELECT *
            FROM (
                SELECT s.db_name,
                       s.db_id,
                       s.accession,
                       s.name,
                       s.description,
                       s.type,
                       s.sprot,
                       s.ovl_sprot,
                       COALESCE((s.ovl_sprot::float / NULLIF(s.sprot, 0)), 0) AS f_ovl_sprot,
                       s.trembl,
                       s.ovl_trembl,
                       COALESCE((s.ovl_trembl::float / NULLIF(s.trembl, 0)), 0) AS f_ovl_trembl
                FROM (
                    SELECT d.name_long AS db_name,
                           d.name AS db_id,
                           s.accession,
                           s.name,
                           s.description,
                           s.type,
                           s.num_complete_reviewed_sequences AS sprot,
                           (s.num_complete_sequences - s.num_complete_reviewed_sequences) AS trembl,
                           s.num_50pc_overlapped_complete_reviewed_sequences AS ovl_sprot,
                           (s.num_50pc_overlapped_complete_sequences - s.num_50pc_overlapped_complete_reviewed_sequences) AS ovl_trembl
                    FROM interpro.signature s
                    JOIN interpro.database d ON d.id = s.database_id
                    WHERE {' AND '.join(filters)}
                ) s
            ) r
            WHERE r.f_ovl_sprot <= %s 
              AND r.f_ovl_trembl <= %s
            """,
            params + [max_sprot, max_trembl]
        )

        pthr_sf = re.compile(r"PTHR\d+:SF\d+")
        results = []
        for row in cur:
            if row[2] in integrated or pthr_sf.match(row[1]):
                continue

            results.append({
                "database": {
                    "color": utils.get_database_obj(row[1]).color,
                    "name": row[0]
                },
                "accession": row[2],
                "name": row[3],
                "description": row[4],
                "type": row[5],
                "comments": num_comments.get(row[2], 0),
                "proteins": {
                    "reviewed": row[6],
                    "unreviewed": row[9],
                    "overlapping": {
                        "reviewed": row[7],
                        "fraction_reviewed": row[8],
                        "unreviewed": row[10],
                        "fraction_unreviewed": row[11],
                    }
                },
            })
    finally:
        cur.close()
        con.close()

    results.sort(key=lambda x: (x["proteins"]["overlapping"]["fraction_reviewed"],
                                x["proteins"]["overlapping"]["fraction_unreviewed"],
                                -x["proteins"]["reviewed"],
                                -x["proteins"]["unreviewed"]))

    return jsonify({
        "count": len(results),
        "results": results[(page-1)*page_size:page*page_size],
        "page_info": {
            "page": page,
            "page_size": page_size
        },
        "filters": {
            "max-sprot": max_sprot,
            "max-trembl": max_trembl,
            "database": database
        },
    })
