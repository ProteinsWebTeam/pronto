# -*- coding: utf-8 -*-

from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api.protein", __name__, url_prefix="/api/protein")


@bp.route("/<accession>/")
def get_protein(accession):
    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT p.accession, p.identifier, p.length, p.is_fragment, 
               p.is_reviewed, t.name, pn.text
        FROM protein p
        INNER JOIN taxon t ON p.taxon_id = t.id
        INNER JOIN protein2name p2n ON p.accession = p2n.protein_acc
        INNER JOIN protein_name pn ON p2n.name_id = pn.name_id
        WHERE p.accession = UPPER(%s)
        """, (accession,)
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
        "organism": row[5],
        "name": row[6]
    }

    matches = {}
    if "matches" in request.args:
        cur.execute(
            """
            SELECT m.signature_acc, s.name, d.name, d.name_long, m.fragments
            FROM match m 
            INNER JOIN database d ON m.database_id = d.id
            INNER JOIN signature s ON m.signature_acc = s.accession
            WHERE m.protein_acc = %s
            """, (accession,)
        )

        for row in cur:
            try:
                s = matches[row[0]]
            except KeyError:
                db = utils.get_database_obj(row[2])
                s = matches[row[0]] = {
                    "accession": row[0],
                    "name": row[1],
                    "database": row[3],
                    "color": db.color,
                    "link": db.gen_link(row[0]),
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
