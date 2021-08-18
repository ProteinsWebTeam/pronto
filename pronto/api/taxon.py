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
        """
    )
    integrated = {acc for acc, in cur.fetchall()}
    cur.close()
    con.close()

    con = utils.connect_pg(pg_url)
    cur = con.cursor()
    cur.execute(
        """
        SELECT s.accession, s.name, d.name, d.name_long
        FROM interpro.signature s
        INNER JOIN interpro.database d
            ON d.id = s.database_id
        """
    )
    signatures = {row[0]: row[1:] for row in cur.fetchall()}

    # Get proteins
    if lower_nodes:
        sql = """
            SELECT accession, is_reviewed
            FROM interpro.protein
            WHERE taxon_id IN (
                SELECT id
                FROM interpro.taxon
                WHERE left_number BETWEEN %s AND %s
            )        
        """
        params = (left_num, right_num)
    else:
        sql = """
            SELECT accession, is_reviewed
            FROM interpro.protein
            WHERE taxon_id IN (
                SELECT id
                FROM interpro.taxon
                WHERE left_number = %s
            )        
        """
        params = (left_num,)

    cur.execute(sql, params)

    num_proteins = 0
    reviewed = set()
    for protein_acc, is_reviewed in cur.fetchall():
        num_proteins += 1
        if is_reviewed:
            reviewed.add(protein_acc)

    # Now get matches (without PANTHER subfamilies)
    cur.execute(
        f"""
        WITH proteins AS ({sql})
        SELECT DISTINCT protein_acc, signature_acc
        FROM interpro.match
        WHERE protein_acc IN (SELECT accession FROM proteins)
        AND signature_acc !~ 'PTHR\d+:SF\d+'
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
    for protein_acc, prot_signatures in matches.items():
        is_reviewed = protein_acc in reviewed

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
                        **dict(zip(("total", "reviewed"),
                                   protein_counts[signature_acc])),
                        "unintegrated": {
                            "total": 0,
                            "reviewed": 0
                        }
                    }
                }
            finally:
                s["proteins"]["unintegrated"]["total"] += 1
                if is_reviewed:
                    s["proteins"]["unintegrated"]["reviewed"] += 1

    return {
        "id": taxon_id,
        "name": taxon_name,
        "lower_nodes": lower_nodes,
        "proteins": {
            "all": {
                "total": num_proteins,
                "integrated": num_int_proteins
            },
            "reviewed": {
                "total": len(reviewed),
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

    sql = """
        SELECT t.id, t.name, t.rank, p.name
        FROM interpro.taxon t
        INNER JOIN interpro.lineage l 
            ON t.id = l.child_id AND l.parent_rank = 'superkingdom'
        INNER JOIN interpro.taxon p 
            ON l.parent_id = p.id    
    """

    if query.isdigit():
        cur.execute(
            f"""
            {sql} 
            WHERE t.id = %s
            """, (query,)
        )
    else:
        cur.execute(
            f"""
            {sql}
            WHERE t.name ILIKE %s
            """, (query + '%',)
        )

    cols = ("id", "name", "rank", "superkingdom")
    results = [dict(zip(cols, row)) for row in cur.fetchall()]

    cur.close()
    con.close()

    return jsonify({
        "items": results
    })

