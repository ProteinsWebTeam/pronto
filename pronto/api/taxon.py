import cx_Oracle
from flask import Blueprint, jsonify, request

from pronto import auth, utils


bp = Blueprint("api.taxonomy", __name__, url_prefix="/api/taxon")


def _process_taxon(ora_url: str, pg_url: str, taxon_id: int, taxon_name: str,
                   left_num: int, right_num: int, lower_nodes: bool = False):
    con = cx_Oracle.connect(ora_url)
    cur = con.cursor()
    cur.execute(
        """
        SELECT EM.METHOD_AC 
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.ENTRY E
            ON EM.ENTRY_AC = E.ENTRY_AC 
            AND E.CHECKED = 'Y'
        """
    )
    integrated = {acc for acc, in cur.fetchall()}
    cur.close()
    con.close()

    con = utils.connect_pg(pg_url)
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*), SUM(CASE WHEN is_reviewed THEN 1 ELSE 0 END)
        FROM interpro.protein
        WHERE taxon_id = %s AND NOT is_fragment
        """, (taxon_id,)
    )
    num_proteins, num_reviewed = cur.fetchone()

    cur.execute(
        """
        SELECT s.accession, s.name, d.name, d.name_long
        FROM interpro.signature s
        INNER JOIN interpro.database d
            ON d.id = s.database_id
        """
    )
    signatures = {row[0]: row[1:] for row in cur.fetchall()}

    if lower_nodes:
        sql = "taxon_left_num BETWEEN %s AND %s"
        params = (left_num, right_num)
    else:
        sql = "taxon_left_num = %s"
        params = (left_num,)

    cur.execute(
        f"""
        SELECT signature_acc, protein_acc, is_reviewed
        FROM interpro.signature2protein
        WHERE {sql}
        ORDER BY protein_acc
        """, params
    )
    proteins = {}
    for signature_acc, protein_acc, is_reviewed in cur.fetchall():
        try:
            proteins[protein_acc][0].append(signature_acc)
        except KeyError:
            proteins[protein_acc] = ([signature_acc], is_reviewed)

    cur.close()
    con.close()

    num_hit_proteins = num_hit_reviewed = 0
    num_int_proteins = num_int_reviewed = 0
    results = {}
    for protein_acc, (prot_signatures, is_reviewed) in proteins.items():
        num_hit_proteins += 1
        if is_reviewed:
            num_hit_reviewed += 1

        is_integrated = False
        unintegrated = []
        for signature_acc in prot_signatures:
            if signature_acc in integrated:
                is_integrated = True
                break

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
                sig_name, sig_dbkey, sig_db = signatures[signature_acc]
                s = results[signature_acc] = {
                    "accession": signature_acc,
                    "name": sig_name,
                    "database": {
                        "name": sig_db,
                        "color": utils.get_database_obj(sig_dbkey).color
                    },
                    "proteins": {
                        "total": 0,
                        "reviewed": 0
                    }
                }
            finally:
                s["proteins"]["total"] += 1
                if is_reviewed:
                    s["proteins"]["reviewed"] += 1

    return {
        "id": taxon_id,
        "name": taxon_name,
        "lower_nodes": lower_nodes,
        "proteins": {
            "all": {
                "total": num_proteins,
                "hit": num_hit_proteins,
                "integrated": num_int_proteins
            },
            "reviewed": {
                "total": num_reviewed,
                "hit": num_hit_reviewed,
                "integrated": num_int_reviewed
            }
        },
        "signatures": list(results.values())
    }


def _get_taxon(taxon_id):
    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()
    cur.execute(
        """
        SELECT name, left_number, right_number
        FROM interpro.taxon
        WHERE id = %s
        """, (taxon_id,)
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    return row


@bp.route("/<int:taxon_id>/", methods=["PUT"])
def submit_taxon(taxon_id):
    lower_nodes = 'lowernodes' in request.args

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
        name, left_num, right_num = _get_taxon(taxon_id)
    except TypeError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Taxon not found",
                "message": f"ID '{taxon_id}' is not matching any taxon."
            }
        }), 404

    task_name = f"taxon:{taxon_id}"

    ora_url = utils.get_oracle_url(user)
    task = utils.executor.submit(ora_url, task_name, _process_taxon, ora_url,
                                 utils.get_pg_url(), taxon_id, name, left_num,
                                 right_num, lower_nodes)

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


@bp.route("/<int:taxon_id>/")
def get_taxon(taxon_id):
    try:
        name, left_num, right_num = _get_taxon(taxon_id)
    except TypeError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Taxon not found",
                "message": f"ID '{taxon_id}' is not matching any taxon."
            }
        }), 404

    task_name = f"taxon:{taxon_id}"
    tasks = utils.executor.get_tasks(task_name=task_name, get_result=True)

    try:
        task = tasks[-1]
    except IndexError:
        return jsonify({
            "status": True,
            "id": taxon_id,
            "name": name,
            "task": None
        }), 404
    else:
        add_comments(task)
        return jsonify({
            "status": True,
            "id": taxon_id,
            "name": name,
            "task": task
        }), 200


@bp.route("/search/")
def search_taxon():
    query = request.args.get("q", "Homo sapiens")
    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()

    if query.isdigit():
        cur.execute(
            """
            SELECT id, name, rank
            FROM interpro.taxon
            WHERE id = %s
            ORDER BY name
            """, (query,)
        )
    else:
        cur.execute(
            """
            SELECT id, name, rank
            FROM interpro.taxon
            WHERE name ILIKE %s
            ORDER BY name
            """, (query + '%',)
        )

    cols = ("id", "name", "rank")
    results = [dict(zip(cols, row)) for row in cur.fetchall()]

    cur.close()
    con.close()

    return jsonify({
        "items": results
    })

