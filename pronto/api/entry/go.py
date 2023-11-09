# -*- coding: utf-8 -*-
import sys
import re
import json
import ssl
from flask import jsonify
from oracledb import DatabaseError
from urllib import request
from urllib.error import HTTPError
from time import sleep

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


@bp.route("/<accession>/go/<term_id>/", methods=["CONSTRAINT"])
def term_constraints(accession, term_id):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT METHOD_AC FROM INTERPRO.ENTRY2METHOD
        WHERE ENTRY_AC = :1
        """, (accession,)
    )

    list_methods = [row[0] for row in cur]
    constraints = get_go_constraint(term_id)
    mapping = get_taxonomy_origins(list_methods, constraints)

    cur.close()
    con.close()

    return jsonify({
        "status": True,
        "term_id": term_id,
        "results": mapping
    })


def get_go_constraint(term_id):
    term_id_url = term_id.replace(':', '%3A')

    next = f"https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/{term_id_url}/constraints"
    context = ssl._create_unverified_context()

    attempts = 0
    constraints_data = []

    while next:
        try:
            req = request.Request(next, headers={"Accept": "application/json"})
            res = request.urlopen(req, context=context)

            if res.status == 408:
                sleep(61)
                continue
            elif res.status == 204:
                break
            payload = json.loads(res.read().decode())
            next = ""
            attempts = 0
        except HTTPError as e:
            if e.code == 408:
                sleep(61)
                continue
            else:
                if attempts < 3:
                    attempts += 1
                    sleep(61)
                    continue
                else:
                    sys.stderr.write("LAST URL: " + next)
                    raise e

        constraints_data = []
        for value in payload["results"]:
            constraints_data = value["taxonConstraints"]

    constraints = dict()
    for constraint in constraints_data:
        try:
            constraints[constraint['taxId']] = {'name': constraint['taxName'], 'relationship': constraint['relationship'].replace(
                '_', ' '), 'count_match': 0, 'count_all': 0}
        except KeyError:
            constraints = {constraint['taxId']: {'name': constraint['taxName'], 'relationship': constraint['relationship'].replace(
                '_', ' '), 'count_match': 0, 'count_all': 0}}

    return constraints


def get_taxonomy_origins(accessions, go_list):

    con = utils.connect_pg()
    cur = con.cursor()

    params = tuple(accessions)

    sql = f"""
            SELECT sp.signature_acc, sp.protein_acc, t.lineage
            FROM signature2protein sp
            INNER JOIN protein p ON p.accession=sp.protein_acc
            INNER JOIN taxon t on t.id = p.taxon_id
            WHERE sp.signature_acc IN ({','.join('%s' for _ in accessions)})
            AND p.is_fragment = 'f'
            group by sp.signature_acc, sp.protein_acc, t.lineage
    """

    cur.execute(sql, params)

    for row in cur:
        lineage = row[2].strip('[').strip(']').split(', ')
        for tax_id in go_list:
            if re.search(',', tax_id):  # case of Prokaryota where tax_id = '2, 2157'
                list_ids = tax_id.split(',')
                for item in list_ids:
                    if item in lineage:
                        go_list[tax_id]['count_match'] += 1
                        break
            elif tax_id in lineage:
                go_list[tax_id]['count_match'] += 1
            go_list[tax_id]['count_all'] += 1
    cur.close()
    con.close()

    return go_list
