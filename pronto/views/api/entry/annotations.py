import re

from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify

from pronto import app, db, get_user, xref


def update_references(accession):
    con = db.get_oracle()
    cur = con.cursor()

    # Get references from the entry-pub table (may need to be updated)
    cur.execute(
        """
        SELECT PUB_ID, ORDER_IN
        FROM INTERPRO.ENTRY2PUB
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    # Keep order_in to now the highest order
    cur_references = dict(cur.fetchall())

    # Get references from annotations
    cur.execute(
        """
        SELECT TEXT
        FROM INTERPRO.COMMON_ANNOTATION
        WHERE ANN_ID IN (
          SELECT ANN_ID
          FROM INTERPRO.ENTRY2COMMON
          WHERE ENTRY_AC = :1
        )
        """,
        (accession, )
    )

    new_references = set()
    prog_ref = re.compile(r"\[cite:(PUB\d+)\]", re.I)
    for row in cur:
        for m in prog_ref.finditer(row[0]):
            new_references.add(m.group(1))

    # Get supplementary references to delete (because in text)
    cur.execute(
        """
        SELECT PUB_ID
        FROM INTERPRO.SUPPLEMENTARY_REF
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    supp = {row[0] for row in cur}
    to_delete = supp & new_references
    if to_delete:
        cur.execute(
            """
            DELETE FROM INTERPRO.SUPPLEMENTARY_REF
            WHERE ENTRY_AC = :1
            AND PUB_ID IN ({})
            """.format(
                ','.join([':' + str(i+2) for i in range(len(to_delete))])
            ),
            (accession,) + tuple(to_delete)
        )

    old_references = set()
    for pub_id, order_id in cur_references.items():
        if pub_id in new_references:
            # reference in table is still in text: all good
            new_references.remove(pub_id)
        else:
            # has to be deleted from the table
            old_references.add(pub_id)

    if old_references:
        # Move reference to SUPPLEMENTARY_REF table
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY2PUB
            WHERE ENTRY_AC = :1
            AND PUB_ID IN ({})
            """.format(
                # i+2: 1-index and +1 for ENTRY_ACC param
                ','.join([':' + str(i+2) for i in range(len(old_references))])
            ),
            (accession,) + tuple(old_references)
        )

        cur.executemany(
            """
            INSERT INTO INTERPRO.SUPPLEMENTARY_REF (ENTRY_AC, PUB_ID)
            VALUES (:1, :2)
            """, [(accession, pub_id) for pub_id in old_references]
        )

    if new_references:
        # references to be inserted into ENTRY2PUB
        start = max(cur_references.values()) + 1 if cur_references else 1
        params = []
        for i, pub_id in enumerate(new_references):
            params.append((accession, start + i, pub_id))

        cur.executemany(
            """
            INSERT INTO INTERPRO.ENTRY2PUB (ENTRY_AC, ORDER_IN, PUB_ID) 
            VALUES (:1, :2, :3)
            """,
            params
        )

    con.commit()
    cur.close()


@app.route('/api/entry/<acc>/annotation/<ann_id>/', methods=["DELETE"])
def unlink_annotation(acc, ann_id):
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
            DELETE FROM INTERPRO.ENTRY2COMMON
            WHERE ENTRY_AC = :1 AND ANN_ID = :2 
            """,
            (acc, ann_id)
        )
    except DatabaseError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not unlink annotation."
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()
        update_references(acc)


@app.route('/api/entry/<acc>/annotation/<ann_id>/', methods=["PUT"])
def link_annotation(acc, ann_id):
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
        SELECT MAX(ORDER_IN)
        FROM INTERPRO.ENTRY2COMMON
        WHERE ENTRY_AC = :1
        """, (acc,)
    )
    order_in = cur.fetchone()[0]
    if order_in is None:
        order_in = 0
    else:
        order_in += 1

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY2COMMON (ENTRY_AC, ANN_ID, ORDER_IN)
            VALUES (:1, :2, :3) 
            """,
            (acc, ann_id, order_in)
        )
    except (DatabaseError, IntegrityError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not link annotation."
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        update_references(acc)
        cur.close()


@app.route('/api/entry/<acc>/annotation/<ann_id>/order/<x>/', methods=["POST"])
def reorder_annotation(acc, ann_id, x):
    try:
        x = int(x)
    except ValueError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid parameters",
                "message": "Expected an integer."
            }
        }), 400

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

    # Get the position of every annotation
    cur.execute(
        """
        SELECT ANN_ID, ORDER_IN
        FROM INTERPRO.ENTRY2COMMON
        WHERE ENTRY_AC = :1
        """,
        (acc,)
    )
    annotations = dict(cur.fetchall())

    if ann_id not in annotations:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid parameters",
                "message": "{} is not linked by {}".format(ann_id, acc)
            }
        }), 400

    max_order = max(annotations.values())
    min_order = min(annotations.values())

    # Annotations in the current order
    annotations = sorted(annotations, key=lambda k: annotations[k])

    # Current index of the annotation to move
    idx = annotations.index(ann_id)

    # New index, forced to stay in the range [0, num_annotations-1]
    new_idx = min(max(0, idx + x), len(annotations)-1)

    if idx == new_idx:
        # Nothing to change
        cur.close()
        return jsonify({
            "status": True
        }), 200

    # Remove the annotation, then insert it at its new index
    annotations.pop(idx)
    annotations.insert(new_idx, ann_id)

    """
    We would like to use the range [0, num_annotations[
    but that is only possible if max_order > min_order >= num_annotations.
    If it is not, we are using the range [max_order+1, max_order+1+num_annotations[
    """
    if max_order > min_order >= len(annotations):
        offset = 0
    else:
        offset = max_order + 1

    for i, ann_id in enumerate(annotations):
        cur.execute(
            """
            UPDATE INTERPRO.ENTRY2COMMON
            SET ORDER_IN = :1
            WHERE ENTRY_AC = :2 AND ANN_ID = :3
            """, (i + offset, acc, ann_id)
        )

    con.commit()
    cur.close()

    return jsonify({
        "status": True
    }), 200


@app.route('/api/entry/<accession>/annotations/')
def get_annotations_(accession):
    cur = db.get_oracle().cursor()

    # Annotations
    cur.execute(
        """
        SELECT A.ANN_ID, A.TEXT, A.COMMENTS, S.CT
        FROM INTERPRO.COMMON_ANNOTATION A
        INNER JOIN INTERPRO.ENTRY2COMMON E ON A.ANN_ID = E.ANN_ID
        LEFT OUTER JOIN (
          SELECT ANN_ID, COUNT(*) CT
          FROM INTERPRO.ENTRY2COMMON
          GROUP BY ANN_ID
        ) S ON A.ANN_ID = S.ANN_ID
        WHERE E.ENTRY_AC = :1
        ORDER BY E.ORDER_IN
        """,
        (accession,)
    )

    annotations = []
    prog_ref = re.compile(r"\[([a-z0-9]+):([a-z0-9\-.]+)]", re.I)

    for ann_id, text, comment, n_entries in cur:
        ext_refs = {}

        for match in prog_ref.finditer(text):
            ref_db, ref_id = match.groups()
            ref_db = ref_db.upper()
            base_url = xref.find_xref(ref_db)
            if base_url:
                whole_match = match.group()

                ext_refs[whole_match] = {
                    "match": whole_match,
                    "id": ref_id,
                    "url": base_url.format(ref_id)
                }

        annotations.append({
            "id": ann_id,
            "text": text,
            "comment": comment,
            "num_entries": n_entries,
            "xrefs": list(ext_refs.values())
        })

    cur.execute(
        """
        SELECT 
          E.PUB_ID, C.TITLE, C.YEAR, C.VOLUME, C.RAWPAGES, C.DOI_URL,
          C.PUBMED_ID, C.ISO_JOURNAL, C.MEDLINE_JOURNAL, C.AUTHORS
        FROM INTERPRO.ENTRY2PUB E
        INNER JOIN INTERPRO.CITATION C
        ON E.PUB_ID = C.PUB_ID
        WHERE E.ENTRY_AC = :1
        """, (accession,)
    )

    references = {}
    for row in cur:
        pub_id = row[0]
        references[pub_id] = {
            "id": pub_id,
            "title": row[1],
            "year": row[2],
            "volume": row[3],
            "pages": row[4],
            "doi": row[5],
            "pmid": row[6],
            "journal": row[7] if row[7] else row[8],
            "authors": row[9]
        }

    cur.close()
    return jsonify({
        "annotations": annotations,
        "references": references
    })
