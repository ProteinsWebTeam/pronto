from flask import jsonify

from pronto import utils
from . import bp, get_sig2interpro


@bp.route("/<path:accessions>/structures/")
def get_structures(accessions):
    accessions = utils.split_path(accessions)

    con = utils.connect_pg()
    with con.cursor() as cur:
        in_stmt = ','.join("%s" for _ in accessions)

        cur.execute(
            f"""
            SELECT p.accession, p.identifier, p.is_reviewed, 
                   sp.signature_acc, ss.structure_id
            FROM interpro.signature2protein sp
            INNER JOIN interpro.signature2structure ss 
                ON sp.signature_acc = ss.signature_acc 
               AND sp.protein_acc = ss.protein_acc
            INNER JOIN interpro.protein p 
                ON sp.protein_acc = p.accession
            WHERE sp.signature_acc IN ({in_stmt})
            """,
            accessions
        )

        proteins = {}
        for row in cur:
            protein_acc = row[0]
            try:
                protein = proteins[protein_acc]
            except KeyError:
                protein = proteins[protein_acc] = {
                    "accession": protein_acc,
                    "identifier": row[1],
                    "is_reviewed": row[2],
                    "signatures": {}
                }

            signature_acc = row[3]
            structure_id = row[4]
            try:
                protein["signatures"][signature_acc].append(structure_id)
            except KeyError:
                protein["signatures"][signature_acc] = [structure_id]

    con.close()

    return jsonify({
        "results": sorted(proteins.values(), key=_hash),
        "integrated": get_sig2interpro(accessions)
    })


def _hash(protein):
    max_structs = max(len(s) for s in protein["signatures"].values())
    i = 0 if protein["is_reviewed"] else 1
    return -max_structs, i, protein["identifier"]
