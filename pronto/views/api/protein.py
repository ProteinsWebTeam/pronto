from flask import jsonify

from pronto import app, db, xref


@app.route("/api/protein/<accession>/")
def api_protein(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          P.NAME,
          P.LEN,
          P.DBCODE,
          P.TAX_ID,
          E.FULL_NAME,
          E.SCIENTIFIC_NAME,
          P.FRAGMENT
        FROM {0}.PROTEIN P
        LEFT OUTER JOIN {0}.ETAXI E 
          ON P.TAX_ID = E.TAX_ID
        WHERE PROTEIN_AC = :1
        """.format(app.config['DB_SCHEMA']),
        (accession,)
    )

    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify(None), 404

    protein = {
        "accession": accession,
        "identifier": row[0],
        "length": row[1],
        "is_reviewed": row[2] == 'S',
        "is_fragment": row[6] == 'Y',
        "taxon": {
            "id": row[3],
            "full_name": row[4],
            "scientific_name": row[5]
        }
    }

    if protein["is_reviewed"]:
        protein["link"] = "//sp.isb-sib.ch/uniprot/{}".format(accession)
    else:
        protein["link"] = "//www.uniprot.org/uniprot/{}".format(accession)

    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.ENTRY_TYPE,
          CET.ABBREV,
          MA.METHOD_AC,
          ME.NAME,
          MA.DBCODE,
          MA.POS_FROM,
          MA.POS_TO,
          MA.FRAGMENTS
        FROM {0}.MATCH MA
        INNER JOIN {0}.METHOD ME 
          ON MA.METHOD_AC = ME.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M 
          ON MA.METHOD_AC = E2M.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E 
          ON E2M.ENTRY_AC = E.ENTRY_AC
        LEFT OUTER JOIN INTERPRO.CV_ENTRY_TYPE CET 
          ON CET.CODE = E.ENTRY_TYPE
        WHERE MA.PROTEIN_AC = :1        
        """.format(app.config['DB_SCHEMA']),
        (accession, )
    )

    entries = {}
    unintegrated = {}
    mobidblite = {}
    for row in cur:
        entry_acc = row[0]
        entry_name = row[1]
        entry_type_code = row[2]
        entry_type = row[3]
        method_acc = row[4]
        method_name = row[5]
        method_db_code = row[6]
        pos_start = row[7]
        pos_end = row[8]
        fragments = []

        if row[9] is not None:
            for f in row[9].split(','):
                s, e, _ = f.split('-')
                s = int(s)
                e = int(e)
                if s < e:
                    fragments.append({"start": s, "end": e})

        if fragments:
            # Sort discontinuous fragments (in case they are not sorted in DB)
            fragments.sort(key=lambda x: (x["start"], x["end"]))
        else:
            fragments.append({"start": pos_start, "end": pos_end})

        if entry_acc:
            if entry_acc in entries:
                entry = entries[entry_acc]
            else:
                entry = entries[entry_acc] = {
                    "accession": entry_acc,
                    "name": entry_name,
                    "type": entry_type,
                    "type_code": entry_type_code,
                    "signatures": {}
                }

            signatures = entry["signatures"]
        elif method_db_code == 'g':
            signatures = mobidblite
        else:
            signatures = unintegrated

        if method_acc in signatures:
            s = signatures[method_acc]
        else:
            database = xref.find_ref(dbcode=method_db_code, ac=method_acc)
            s = signatures[method_acc] = {
                "accession": method_acc,
                "name": method_name,
                "link": database.gen_link(),
                "database": database.name,
                "color": database.color,
                "matches": []
            }

        s["matches"].append(fragments)

    cur.close()

    for entry in entries.values():
        signatures = []
        for s in entry["signatures"].values():
            s["matches"].sort(key=lambda x: (x[0]["start"], x[0]["end"]))
            signatures.append(s)
        entry["signatures"] = sorted(signatures, key=lambda x: x["accession"])

    for s in unintegrated.values():
        s["matches"].sort(key=lambda x: (x[0]["start"], x[0]["end"]))

    for s in mobidblite.values():
        s["matches"].sort(key=lambda x: (x[0]["start"], x[0]["end"]))

    protein.update({
        "entries": sorted(entries.values(), key=lambda x: x["accession"]),
        "unintegrated": sorted(unintegrated.values(),
                               key=lambda x: x["accession"].lower()),
        "mobidblite": sorted(mobidblite.values(),
                             key=lambda x: x["accession"].lower()),
    })

    return jsonify(protein)
