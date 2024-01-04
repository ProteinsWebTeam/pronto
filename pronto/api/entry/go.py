# -*- coding: utf-8 -*-

from flask import jsonify
from oracledb import DatabaseError

from pronto import auth, utils
from . import bp


@bp.route("/<accession>/go/")
def get_terms(accession):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT GO_ID
        FROM INTERPRO.INTERPRO2GO
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    terms = [go_id for go_id, in cur]
    cur.close()
    con.close()

    if terms:
        con = utils.connect_pg(utils.get_pg_url())
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT id, name, category, num_constraints, is_obsolete,
                   definition, replaced_id
            FROM interpro.term
            WHERE id IN ({','.join('%s' for _ in terms)})
            ORDER BY id
            """, terms
        )
        terms = []
        for row in cur:
            terms.append({
                "id": row[0],
                "name": row[1],
                "category": row[2],
                "definition": row[5],
                "is_obsolete": row[4],
                "is_secondary": row[6] is not None,
                "taxon_constraints": row[3]
            })

        cur.close()
        con.close()

    return jsonify(terms), 200


@bp.route("/<accession>/go/<term_id>/", methods=["PUT"])
def add_term(accession, term_id):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this operation."
            }
        }), 401

    con = utils.connect_pg(utils.get_pg_url())
    cur = con.cursor()
    cur.execute(
        """
        SELECT is_obsolete, replaced_id
        FROM interpro.term
        WHERE id = %s
        """, (term_id,)
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    if not row:
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid GO term",
                "message": f"{term_id} does not exist."
            }
        }), 400

    is_obsolete, replaced_id = row
    if is_obsolete:
        return jsonify({
            "status": False,
            "error": {
                "title": "GO term obsolete",
                "message": f"{term_id} term was made obsolete and cannot "
                           f"be applied to InterPro entries."
            }
        }), 400
    elif replaced_id:
        return jsonify({
            "status": False,
            "error": {
                "title": "GO term replaced",
                "message": f"{term_id} term was replaced by {replaced_id}. "
                           f"Please use {replaced_id} instead."
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.INTERPRO2GO
        WHERE ENTRY_AC = :1 AND GO_ID = :2
        """, (accession, term_id)
    )
    if cur.fetchone()[0]:
        cur.close()
        con.close()
        return jsonify({"status": True}), 200

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.INTERPRO2GO (ENTRY_AC, GO_ID, SOURCE)
            VALUES (:1, :2, 'MANU')
            """, (accession, term_id)
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not apply {term_id} to {accession}: {exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/go/<term_id>/", methods=["DELETE"])
def delete_term(accession, term_id):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this operation."
            }
        }), 401

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.INTERPRO2GO
            WHERE ENTRY_AC = :1 AND GO_ID = :2
            """, (accession, term_id)
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not unlink {term_id} from {accession}: "
                           f"{exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/go/<term_id>/", methods=["GET"])
def get_term_constraints(accession, term_id):
    ora_con = utils.connect_oracle()
    ora_cur = ora_con.cursor()

    ora_cur.execute(
        """
        SELECT DISTINCT METHOD_AC 
        FROM INTERPRO.ENTRY2METHOD
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    signatures = [acc for acc, in ora_cur.fetchall()]
    ora_cur.close()
    ora_con.close()

    pg_con = utils.connect_pg()
    pg_cur = pg_con.cursor()
    pg_cur.execute(
        """
        SELECT DISTINCT gc.relationship, gc.taxon, t.name, t.left_number, 
                        t.right_number
        FROM go2constraints gc
        INNER JOIN taxon t
        ON t.id = gc.taxon
        WHERE go_id = %s
        """, (term_id,)
    )
    taxon_constraints = pg_cur.fetchall()

    pg_cur.execute(
        f"""
        SELECT DISTINCT protein_acc, is_reviewed, taxon_left_num
        FROM signature2protein
        WHERE signature_acc IN ({','.join(['%s' for _ in signatures])})
        """,
        signatures
    )

    proteins = violations = violations_reviewed = 0
    for protein_acc, is_reviewed, taxon_left_num in pg_cur:
        total_proteins += 1
        only_in = []
        is_violating = False
        for info in taxon_constraints:
            relationship, taxon_id, taxon_name, left_num, right_num = info
            if relationship == "never_in":
                if left_num <= taxon_left_num <= right_num:
                    is_violating = True
            else:
                only_in.append((left_num, right_num))
        if only_in:
            is_in = False
            for constraint in only_in:
                if constraint[0] <= taxon_left_num <= constraint[1]:
                    is_in = True
            if not is_in:
                is_violating = True
        if is_violating:
            violation_total += 1
            if is_reviewed:
                violation_reviewed += 1

    pg_cur.close()
    pg_con.close()

    constraints_info = []
    for info in taxon_constraints:
        relationship, taxon_id, taxon_name, left_num, right_num = info
        constraints_info.append({
            "type": relationship,
            "taxon": {
                "id": taxon_id,
                "name": taxon_name
            }
        })

    json_result = {
        "total_proteins": total_proteins,
        "violations": {
            "total": violation_total,
            "reviewed": violation_reviewed
         },
        "constraint": constraints_info,
        "signatures": methods
    }

    return jsonify(json_result), 200
