# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api.protein", __name__, url_prefix="/api/protein")


@bp.route("/<protein_acc>/")
def get_protein(protein_acc):
    inc_lineage = "lineage" in request.args
    inc_matches = "matches" in request.args
    signature_acc = request.args.get("signature")

    con = utils.connect_pg()
    cur = con.cursor()
    if protein_acc.lower() == "random":
        cur.execute(
            """
            SELECT accession 
            FROM protein 
            TABLESAMPLE SYSTEM(0.001) LIMIT 1 
            """
        )
        protein_acc, = cur.fetchone()

    cur.execute(
        """
        SELECT p.accession, p.identifier, p.length, p.is_fragment, 
               p.is_reviewed, t.id, t.name, pn.text
        FROM protein p
        INNER JOIN taxon t ON p.taxon_id = t.id
        INNER JOIN protein2name p2n ON p.accession = p2n.protein_acc
        INNER JOIN protein_name pn ON p2n.name_id = pn.name_id
        WHERE p.accession = UPPER(%s)
        """, (protein_acc,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify({}), 404

    protein = {
        "accession": row[0],
        "identifier": row[1],
        "length": row[2],
        "is_fragment": row[3],
        "is_reviewed": row[4],
        "organism": {
            "name": row[6],
            "lineage": []
        },
        "name": row[7]
    }
    taxon_id = row[5]

    matches = {}
    if inc_matches:
        if signature_acc:
            sql = "m.protein_acc = %s AND m.signature_acc = %s"
            params = (protein_acc, signature_acc)
        else:
            sql = "m.protein_acc = %s"
            params = (protein_acc,)

        cur.execute(
            f"""
            SELECT m.signature_acc, s.name, d.name, d.name_long, m.fragments
            FROM match m 
            INNER JOIN database d ON m.database_id = d.id
            INNER JOIN signature s ON m.signature_acc = s.accession
            WHERE {sql}
            """, params
        )

        for row in cur:
            try:
                s = matches[row[0]]
            except KeyError:
                db = utils.get_database_obj(row[2])
                if isinstance(db, utils.MobiDbLite):
                    link = db.gen_link(protein_acc)
                else:
                    link = db.gen_link(row[0])

                s = matches[row[0]] = {
                    "accession": row[0],
                    "name": row[1],
                    "database": row[3],
                    "color": db.color,
                    "link": link,
                    "matches": [],
                    "entry": None
                }

            fragments = []
            for frag in row[4].split(','):
                start, end, status = frag.split('-')
                fragments.append({
                    "start": int(start),
                    "end": int(end)
                })

            s["matches"].append(sorted(fragments,
                                       key=lambda x: (x["start"], x["end"])))

    if inc_lineage:
        cur.execute(
            """
            WITH RECURSIVE ancestors AS (
                SELECT id, name, parent_id, 1 AS level
                FROM interpro.taxon
                WHERE id = %s
                UNION
                SELECT t.id, t.name, t.parent_id, a.level+1
                FROM interpro.taxon t
                INNER JOIN ancestors a
                ON t.id = a.parent_id
            )
            SELECT name
            FROM ancestors
            ORDER BY level DESC            
            """, (taxon_id,)
        )
        protein["organism"]["lineage"] = [name for name, in cur]

    cur.close()
    con.close()

    if matches:
        params = tuple(matches.keys())
        con = utils.connect_oracle()
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT EM.METHOD_AC, E.ENTRY_AC, E.NAME, ET.CODE, ET.ABBREV
            FROM INTERPRO.ENTRY2METHOD EM
            INNER JOIN INTERPRO.ENTRY E ON EM.ENTRY_AC = E.ENTRY_AC
            INNER JOIN INTERPRO.CV_ENTRY_TYPE ET ON E.ENTRY_TYPE = ET.CODE
            WHERE EM.METHOD_AC IN (
                {','.join(':'+str(i+1) for i in range(len(params)))}
            )
            """, params
        )

        for row in cur:
            matches[row[0]]["entry"] = {
                "accession": row[1],
                "name": row[2],
                "type": row[3],
                "type_long": row[4].replace('_', ' ')
            }

        cur.close()
        con.close()

    protein["signatures"] = sorted(matches.values(),
                                   key=lambda x: x["accession"])
    return jsonify(protein)
