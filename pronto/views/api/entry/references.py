from cx_Oracle import DatabaseError
from flask import jsonify

from pronto import app, db, get_user
from ..annotation import get_citations, insert_citations


@app.route('/api/entry/<accession>/references/')
def get_suppl_references(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT 
          S.PUB_ID, C.TITLE, C.YEAR, C.VOLUME, C.RAWPAGES, C.DOI_URL,
          C.PUBMED_ID, C.ISO_JOURNAL, C.MEDLINE_JOURNAL, C.AUTHORS
        FROM INTERPRO.SUPPLEMENTARY_REF S
        INNER JOIN INTERPRO.CITATION C
        ON S.PUB_ID = C.PUB_ID
        WHERE S.ENTRY_AC = :1      
        """, (accession,)
    )
    references = []
    for row in cur:
        references.append({
            "id": row[0],
            "title": row[1],
            "year": row[2],
            "volume": row[3],
            "pages": row[4],
            "doi": row[5],
            "pmid": row[6],
            "journal": row[7] if row[7] else row[8],
            "authors": row[9]
        })
    cur.close()
    return jsonify(references)


@app.route("/api/entry/<accession>/reference/<int:pmid>/", methods=["PUT"])
def link_reference(accession, pmid):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": 'Please <a href="/login/">log in</a> '
                           'to perform this operation.'
            }
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT PUB_ID
        FROM INTERPRO.CITATION
        WHERE PUBMED_ID = :1
        """, (pmid,)
    )
    row = cur.fetchone()
    if row:
        pub_id = row[0]
    else:
        citations = get_citations(cur, [pmid])
        if pmid not in citations:
            cur.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Invalid reference",
                    "message": "<strong>{}</strong> is not "
                               "a valid PubMed ID".format(pmid)
                }
            }), 400

        error = insert_citations(cur, citations)
        if error:
            cur.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Database error",
                    "message": error
                }
            }), 500

        pub_id = citations[pmid]

    cur.execute(
        """
        SELECT PUB_ID
        FROM INTERPRO.ENTRY2PUB
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    pub_ids = {row[0] for row in cur}
    if pub_id in pub_ids:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Existing reference",
                "message": "<strong>{}</strong> cannot be a supplementary "
                           "reference because it is already "
                           "in the main references.".format(pmid)
            }
        }), 400

    cur.execute(
        """
        SELECT COUNT(*) FROM INTERPRO.SUPPLEMENTARY_REF
        WHERE ENTRY_AC = :1 AND PUB_ID = :2
        """, (accession, pub_id)
    )

    if cur.fetchone()[0]:
        # Already inserted: ignore
        cur.close()
        return jsonify({"status": True}), 200

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.SUPPLEMENTARY_REF (ENTRY_AC, PUB_ID) 
            VALUES (:1, :2)
            """, (accession, pub_id)
        )
    except DatabaseError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not add {} to {}.".format(pmid, accession)
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()


@app.route("/api/entry/<accession>/reference/<pub_id>/", methods=["DELETE"])
def unlink_reference(accession, pub_id):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": 'Please <a href="/login/">log in</a> '
                           'to perform this operation.'
            }
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.SUPPLEMENTARY_REF
            WHERE ENTRY_AC = :1 AND PUB_ID = :2
            """, (accession, pub_id)
        )
    except DatabaseError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not unlink reference."
            }
        }), 500
    else:
        if cur.rowcount:
            con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
