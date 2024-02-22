import re

import oracledb
from flask import Blueprint, jsonify, request

from pronto import auth, utils

bp = Blueprint("api_proteome", __name__, url_prefix="/api/proteome")


def _process_proteome(ora_url: str, pg_url: str, proteome_id: str,
                      proteome_name: str):
    con = oracledb.connect(ora_url)
    cur = con.cursor()
    cur.execute(
        """
        SELECT EM.METHOD_AC 
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.ENTRY E
            ON EM.ENTRY_AC = E.ENTRY_AC
        """
    )
    integrated = {acc for acc, in cur.fetchall()}
    cur.close()
    con.close()

    con = utils.connect_pg(pg_url)
    cur = con.cursor()
    cur.execute(
        """
        SELECT s.accession, s.name, s.num_complete_sequences, 
               s.num_complete_reviewed_sequences, d.name, d.name_long
        FROM interpro.signature s
        INNER JOIN interpro.database d
            ON d.id = s.database_id
        """
    )
    signatures = {row[0]: row[1:] for row in cur.fetchall()}

    # Get proteins
    sql = """
        SELECT p.accession, p.is_reviewed
        FROM interpro.protein p
        JOIN interpro.proteome2protein p2p ON p2p.protein_acc=p.accession
        WHERE p2p.id= %s 
        AND NOT is_fragment
    """
    params = (proteome_id,)

    cur.execute(sql, params)

    num_proteins = 0
    reviewed = set()
    for protein_acc, is_reviewed in cur.fetchall():
        num_proteins += 1
        if is_reviewed:
            reviewed.add(protein_acc)

    # Now get matches
    cur.execute(
        f"""
        WITH proteins AS ({sql})
        SELECT DISTINCT protein_acc, signature_acc
        FROM interpro.match
        WHERE protein_acc IN (SELECT accession FROM proteins)
        """, params
    )

    matches = {}
    protein_counts = {}
    for protein_acc, signature_acc in cur.fetchall():
        try:
            matches[protein_acc].append(signature_acc)
        except KeyError:
            matches[protein_acc] = [signature_acc]

        try:
            obj = protein_counts[signature_acc]
        except KeyError:
            obj = protein_counts[signature_acc] = [0, 0]
        finally:
            obj[0] += 1
            if protein_acc in reviewed:
                obj[1] += 1

    cur.close()
    con.close()

    # Compute coverage (i.e. proteins with at least one integrated signature)
    num_int_proteins = num_int_reviewed = 0
    results = {}

    re_antifam = re.compile(r"ANF\d+")
    re_funfam = re.compile(r"G3DSA:([0-9.]+):FF:(\d+)")
    re_subfam = re.compile(r"PTHR\d+:SF\d+")

    for protein_acc, prot_signatures in matches.items():
        is_reviewed = protein_acc in reviewed

        is_integrated = False
        unintegrated = []
        for signature_acc in prot_signatures:
            if signature_acc in integrated:
                is_integrated = True
                break
            elif (not re_antifam.fullmatch(signature_acc) and
                  not re_funfam.fullmatch(signature_acc) and
                  not re_subfam.fullmatch(signature_acc)):
                unintegrated.append(signature_acc)

        if is_integrated:
            num_int_proteins += 1
            if is_reviewed:
                num_int_reviewed += 1
            continue

        for signature_acc in unintegrated:
            try:
                s = results[signature_acc]
            except KeyError:
                (
                    sig_name,
                    num_cmpl_seqs,
                    num_cmpl_rev_seqs,
                    sig_dbkey,
                    sig_db
                ) = signatures[signature_acc]

                s = results[signature_acc] = {
                    "accession": signature_acc,
                    "name": sig_name,
                    "database": {
                        "name": sig_db,
                        "color": utils.get_database_obj(sig_dbkey).color
                    },
                    "proteins": {
                        # Proteins from all clades
                        "total_all": num_cmpl_seqs,
                        "total_reviewed": num_cmpl_rev_seqs,

                        # From this clade, regardless of integration
                        **dict(zip(("all", "reviewed"),
                                   protein_counts[signature_acc])),

                        # From this proteome,
                        # not hit by any integrated signature
                        "unintegrated_all": 0,
                        "unintegrated_reviewed": 0
                    }
                }
            finally:
                s["proteins"]["unintegrated_all"] += 1
                if is_reviewed:
                    s["proteins"]["unintegrated_reviewed"] += 1

    return {
        "id": proteome_id,
        "name": proteome_name,
        "proteins": {
            "all": num_proteins,
            "reviewed": len(reviewed),
            "integrated_all": num_int_proteins,
            "integrated_reviewed": num_int_reviewed,
        },
        "signatures": list(results.values())
    }


def _get_proteome(proteome_id):
    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()
    cur.execute(
        """
        SELECT name
        FROM interpro.proteome
        WHERE id = %s
        """,
        [proteome_id]
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    return row[0]


@bp.route("/<proteome_id>/", methods=["PUT"])
def submit_proteome(proteome_id):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    try:
        proteome_name = _get_proteome(proteome_id)
    except TypeError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Proteome not found",
                "message": f"ID '{proteome_id}' is not matching any proteome."
            }
        }), 404

    task_name = f"proteome:{proteome_id}"

    ora_url = utils.get_oracle_url(user)
    task = utils.executor.submit(ora_url, task_name, _process_proteome,
                                 ora_url, utils.get_pg_url(), proteome_id,
                                 proteome_name)

    return jsonify({
        "status": True,
        "task": task
    })


def add_comments(task):
    if not task["success"]:
        return

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
    comments = dict(cur.fetchall())
    cur.close()
    con.close()

    for sig in task["result"]["signatures"]:
        sig["comments"] = comments.get(sig["accession"], 0)


@bp.route("/<proteome_id>/")
def get_proteome(proteome_id):
    try:
        proteome_name = _get_proteome(proteome_id)
    except TypeError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Proteome not found",
                "message": f"ID '{proteome_id}' is not matching any proteome."
            }
        }), 404

    task_name = f"proteome:{proteome_id}"
    tasks = utils.executor.get_tasks(task_name=task_name, get_result=True)

    try:
        task = tasks[-1]
    except IndexError:
        return jsonify({
            "status": True,
            "id": proteome_id,
            "name": proteome_name,
            "task": None
        }), 404
    else:
        add_comments(task)
        return jsonify({
            "status": task and task["result"] is not None,
            "id": proteome_id,
            "name": proteome_name,
            "task": task
        }), 200


@bp.route("/")
def get_proteomes():
    proteomes = {}
    for task in utils.executor.get_tasks(task_prefix="proteome:",
                                         get_result=False):
        if task["success"]:
            proteome_id = task["name"].split(":")[1]
            try:
                proteomes[proteome_id].append(task["end_time"])
            except KeyError:
                proteomes[proteome_id] = [task["end_time"]]

    proteome_ids = list(proteomes.keys())
    results = []

    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()
    for i in range(0, len(proteome_ids), 100):
        params = proteome_ids[i:i+100]
        cur.execute(
            F"""
            SELECT id, name
            FROM interpro.proteome
            WHERE id IN ({','.join(['%s' for _ in params])})
            """,
            params
        )

        for proteome_id, proteome_name in cur.fetchall():
            results.append({
                "id": proteome_id,
                "name": proteome_name,
                "end_time": proteomes[proteome_id][-1]
            })

    cur.close()
    con.close()

    results.sort(key=lambda x: x["name"])

    return jsonify({
        "items": results
    })


@bp.route("/search/")
def search_proteome():
    query = request.args.get("q", "Human")
    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()

    sql = "SELECT id, name FROM interpro.proteome"

    if re.fullmatch(r"UP\d+", query):
        cur.execute(f"{sql} WHERE id = %s", [query])
    elif query.isdecimal():
        cur.execute(f"{sql} WHERE name ILIKE %s OR taxon_id = %s ",
                    [f"%{query}%", int(query)])
    else:
        cur.execute(f"{sql} WHERE name ILIKE %s", [f"%{query}%"])

    cols = ("id", "name")
    results = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    con.close()

    return jsonify({
        "items": results
    })
