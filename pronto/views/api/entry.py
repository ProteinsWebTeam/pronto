import re

from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify, request

from pronto import app, db, get_user, xref


@app.route("/api/entry/<accession>/")
def get_entry(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          E.NAME,
          E.SHORT_NAME,
          E.ENTRY_TYPE,
          ET.ABBREV,
          E.CHECKED,
          E.TIMESTAMP
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.CV_ENTRY_TYPE ET 
          ON E.ENTRY_TYPE = ET.CODE
        WHERE E.ENTRY_AC = :1
        """,
        (accession,)
    )

    row = cur.fetchone()
    cur.close()
    if row:
        entry = {
            "accession": accession,
            "name": row[0],
            "short_name": row[1],
            "type": {
                "code": row[2],
                "name": row[3].replace('_', ' ')
            },
            "is_checked": row[4] == 'Y',
            "last_modification": row[5].strftime("%d %b %Y")
        }
        return jsonify(entry), 200
    else:
        return jsonify(None), 404


@app.route('/api/entry/<acc>/annotation/<ann_id>/', methods=["DELETE"])
def unlink_annotation(acc, ann_id):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
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
            "title": "Database error",
            "message": "Could not unlink annotation."
        }), 400
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route('/api/entry/<acc>/annotation/<ann_id>/', methods=["PUT"])
def link_annotation(acc, ann_id):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
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
            "title": "Database error",
            "message": "Could not link annotation."
        }), 400
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route('/api/entry/<acc>/annotation/<annid>/order/<x>/', methods=["POST"])
def reorder_annotation(acc, annid, x):
    try:
        x = int(x)
    except ValueError:
        return jsonify({
            "status": False,
            "title": "Invalid parameter",
            "message": "'x' must be an integer"
        }), 400

    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
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

    if annid not in annotations:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid parameters",
            "message": "{} is not linked by {}".format(annid, acc)
        }), 400


    max_order = max(annotations.values())
    min_order = min(annotations.values())

    # Annotations in the current order
    annotations = sorted(annotations, key=lambda k: annotations[k])

    # Current index of the annotation to move
    idx = annotations.index(annid)

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
    annotations.insert(new_idx, annid)

    """
    We would like to use the range [0, num_annotations[
    but that is only possible if max_order > min_order >= num_annotations.
    If it is not, we are using the range [max_order+1, max_order+1+num_annotations[
    """
    if max_order > min_order >= len(annotations):
        offset = 0
    else:
        offset = max_order + 1

    for i, annid in enumerate(annotations):
        cur.execute(
            """
            UPDATE INTERPRO.ENTRY2COMMON
            SET ORDER_IN = :1
            WHERE ENTRY_AC = :2 AND ANN_ID = :3
            """, (i + offset, acc, annid)
        )

    con.commit()
    cur.close()

    return jsonify({
        "status": True
    }), 200


@app.route('/api/entry/<accession>/annotations/')
def get_entry_annotations(accession):
    cur = db.get_oracle().cursor()
    # References
    cur.execute(
        """
        SELECT
          C.PUB_ID,
          C.TITLE,
          C.YEAR,
          C.VOLUME,
          C.RAWPAGES,
          C.DOI_URL,
          C.PUBMED_ID,
          C.ISO_JOURNAL,
          C.MEDLINE_JOURNAL,
          C.AUTHORS
        FROM INTERPRO.CITATION C
        WHERE C.PUB_ID IN (
          SELECT PUB_ID
          FROM INTERPRO.ENTRY2PUB
          WHERE ENTRY_AC = :acc
          UNION
          SELECT M.PUB_ID
          FROM INTERPRO.METHOD2PUB M
          INNER JOIN INTERPRO.ENTRY2METHOD E ON E.METHOD_AC = M.METHOD_AC
          WHERE ENTRY_AC = :acc
          UNION
          SELECT PUB_ID
          FROM INTERPRO.PDB_PUB_ADDITIONAL
          WHERE ENTRY_AC = :acc
          UNION
          SELECT SUPPLEMENTARY_REF.PUB_ID
          FROM INTERPRO.SUPPLEMENTARY_REF
          WHERE ENTRY_AC = :acc
        )
        """,
        dict(acc=accession)
    )

    columns = ("id", "title", "year", "volume", "pages", "doi", "pmid",
               "journal_iso", "journal_medline", "authors")
    references = {row[0]: dict(zip(columns, row)) for row in cur}

    # annotations
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
    missing_refs = set()
    xrefs = []
    prog_ref = r'<cite\s+id="(PUB\d+)"\s*/>'
    prog_xref = r'<dbxref\s+db\s*=\s*"(\w+)"\s+id\s*=\s*"([\w\.\-]+)"\s*\/>'
    prog_taxa = r'<taxon\s+tax_id="(\d+)">([^<]+)</taxon>'

    for ann_id, text, comment, count in cur:
        # Find missing references
        for m in re.finditer(prog_ref, text):
            ref = m.group(1)

            if ref not in references:
                missing_refs.add(ref)

        # Find cross-references
        for m in re.finditer(prog_xref, text):
            match = m.group(0)
            dbcode = m.group(1).upper()
            xref_id = m.group(2)

            url = xref.find_xref(dbcode)
            if url:
                url = url.format(xref_id)
                xrefs.append({
                    "tag": match,
                    "url": url,
                    "id": xref_id
                })
            else:
                # TODO: what do we do with unknown cross-references?
                continue

        for m in re.finditer(prog_taxa, text):
            xrefs.append({
                "tag": m.group(0),
                "url": "https://www.uniprot.org/taxonomy/{}/".format(
                    m.group(1)
                ),
                "id": m.group(2)
            })

        annotations.append({
            "id": ann_id,
            "text": text,
            "comment": comment,
            "count": count
        })

    if missing_refs:
        # Some associations entry-citation are missing in ENTRY2PUB
        cur.execute(
            """
            SELECT
              PUB_ID,
              TITLE,
              YEAR,
              VOLUME,
              RAWPAGES,
              DOI_URL,
              PUBMED_ID,
              ISO_JOURNAL,
              MEDLINE_JOURNAL,
              AUTHORS
            FROM INTERPRO.CITATION
            WHERE PUB_ID IN ({})
            """.format(','.join([':'+str(i+1)
                                 for i in range(len(missing_refs))])),
            tuple(missing_refs)
        )

        references.update({
            row[0]: dict(zip(columns, row))
            for row in cur
        })

    cur.close()
    # Select journal (default: ISO, fallback to MEDLINE)
    for ref, pub in references.items():
        journal_iso = pub.pop("journal_iso")
        journal_med = pub.pop("journal_medline")
        if journal_iso:
            references[ref]["journal"] = journal_iso
        else:
            references[ref]["journal"] = journal_med

    return jsonify({
        "annotations": annotations,
        "references": references,
        "cross_references": xrefs
    }), 200


@app.route("/api/entry/<accession>/check/", methods=["POST"])
def check_entry(accession):
    content = request.get_json()
    try:
        is_checked = bool(int(content["checked"]))
    except (KeyError, ValueError):
        return jsonify({
            "status": False,
            "message": "Invalid or missing parameters."
        }), 400

    user = get_user()

    if not user:
        return jsonify({
            "status": False,
            "message": "Please log in to perform this action."
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE INTERPRO.ENTRY
            SET CHECKED = :1
            WHERE ENTRY_AC = :2
            """,
            ('Y' if is_checked else 'N', accession)
        )
    except DatabaseError as e:
        cur.close()
        return jsonify({
            "status": False,
            "message": "Could not update {}: {}".format(accession, e)
        }), 400
    else:
        con.commit()
        cur.close()
        return jsonify({
            "status": True,
            "message": None
        }), 200


@app.route("/api/entry/<parent_acc>/child/<child_acc>/", methods=["PUT"])
def add_child_relationship(parent_acc, child_acc):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT ENTRY_AC, ENTRY_TYPE
        FROM INTERPRO.ENTRY 
        WHERE ENTRY_AC = :1 OR ENTRY_AC = :2
        """, (parent_acc, child_acc)
    )
    entries = dict(cur.fetchall())

    if parent_acc not in entries:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid entry",
            "message": "{} is not "
                       "a valid InterPro accession.".format(parent_acc)
        }), 400
    elif child_acc not in entries:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid entry",
            "message": "{} is not "
                       "a valid InterPro accession.".format(child_acc)
        }), 400
    elif entries[parent_acc] != entries[child_acc]:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid relationship",
            "message": "{} and {} do not have the same type.".format(
                parent_acc, child_acc
            )
        }), 400

    cur.execute(
        """
        SELECT COUNT(*) 
        FROM INTERPRO.ENTRY2ENTRY
        WHERE PARENT_AC = :1 AND ENTRY_AC = :2
        """, (parent_acc, child_acc)
    )
    if cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": True
        }), 200

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY2ENTRY (ENTRY_AC, PARENT_AC, RELATION)
            VALUES (:1, :2, :3)
            """, (child_acc, parent_acc, "TY")
        )
    except (DatabaseError, IntegrityError):
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "Could not link {} to {}.".format(parent_acc, child_acc)
        }), 400
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route("/api/entry/<accession>/comment/", methods=["PUT"])
def add_entry_comment(accession):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "message": "Please log in to perform this action."
        }), 401

    content = request.get_json()
    text = content.get("text", "")
    if len(text) < 3:
        return jsonify({
            "status": False,
            "message": "Comment too short (must be at least "
                       "three characters long)."
        }), 400

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT MAX(ID)
        FROM INTERPRO.ENTRY_COMMENT
        """
    )
    max_id = cur.fetchone()[0]
    next_id = max_id + 1 if max_id else 1

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY_COMMENT (
              ID, ENTRY_AC, USERNAME, VALUE
            )
            VALUES (:1, :2, :3, :4)
            """,
            (next_id, accession, user["username"], text)
        )
    except IntegrityError as e:
        cur.close()
        return jsonify({
            "status": False,
            "message": "Could not add comment "
                       "for {}: {}".format(accession, e)
        }), 400
    else:
        con.commit()
        cur.close()
        return jsonify({
            "status": True,
            "message": None
        }), 200


@app.route("/api/entry/<accession>/comment/<_id>/", methods=["DELETE"])
def delete_entry_comment(accession, _id):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "message": "Please log in to perform this action."
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE INTERPRO.ENTRY_COMMENT 
            SET STATUS = 'N' 
            WHERE ENTRY_AC = :1 AND ID = :2
            """,
            (accession, _id)
        )
    except DatabaseError as e:
        cur.close()
        return jsonify({
            "status": False,
            "message": "Could not delete comment "
                       "for {}: {}".format(accession, e)
        }), 400
    else:
        con.commit()
        cur.close()
        return jsonify({
            "status": True,
            "message": None
        }), 200


@app.route("/api/entry/<accession>/comments/")
def get_entry_comments(accession):
    try:
        n = int(request.args["max"])
    except (KeyError, ValueError):
        n = 0

    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.ENTRY_COMMENT C
        INNER JOIN INTERPRO.USER_PRONTO U ON C.USERNAME = U.USERNAME
        WHERE C.ENTRY_AC = :1
        ORDER BY C.CREATED_ON DESC
        """,
        (accession,)
    )

    comments = [
        {
            "id": row[0],
            "text": row[1],
            "date": row[2].strftime("%Y-%m-%d %H:%M:%S"),
            "status": row[3] == "Y",
            "author": row[4],
        } for row in cur
    ]
    cur.close()
    n_comments = len(comments)

    if n:
        comments = comments[:n]

    for c in comments:
        c["text"] = re.sub(
            r"#(\d+)",
            r'<a href="https://github.com/geneontology/go-annotation/issues/\1">#\1</a>',
            c["text"]
        )

    return jsonify({
        "count": n_comments,
        "comments": comments
    })


@app.route("/api/entry/<accession>/go/")
def get_entry_go_terms(accession):
    cur = db.get_oracle().cursor()

    cur.execute(
        """
        SELECT 
          T.GO_ID, T.NAME, T.CATEGORY, T.DEFINITION, 
          T.IS_OBSOLETE, T.REPLACED_BY
        FROM INTERPRO.INTERPRO2GO I
          INNER JOIN {}.TERM T ON I.GO_ID = T.GO_ID
        WHERE I.ENTRY_AC = :1
        ORDER BY T.GO_ID
        """.format(app.config["DB_SCHEMA"]),
        (accession,)
    )

    terms = []
    for row in cur:
        terms.append({
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "definition": row[3],
            "is_obsolete": row[4] == 'Y',
            "secondary": row[5] is not None
        })

    cur.close()

    return jsonify(terms), 200


@app.route("/api/entry/<accession>/go/<term_id>/", methods=['DELETE'])
def delete_go_term(accession, term_id):
    user = get_user()

    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.INTERPRO2GO
            WHERE ENTRY_AC = :1 AND GO_ID = :2
            """,
            (accession, term_id)
        )
    except IntegrityError:
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "Could not delete GO term {} "
                       "from InterPro entry {}".format(accession, term_id)
        }), 400
    else:
        # row_count = cur.rowcount  # TODO: check that row_count == 1?
        con.commit()
        return jsonify({
            "status": True,
            "title": None,
            "message": None
        }), 200
    finally:
        cur.close()


@app.route("/api/entry/<accession>/go/<term_id>/", methods=["PUT"])
def add_go_term(accession, term_id):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*) 
        FROM INTERPRO.ENTRY 
        WHERE ENTRY_AC = :1
        """, (accession,)
    )
    if not cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid entry",
            "message": "{} is not a valid InterPro accession.".format(accession)
        }), 400

    cur.execute(
        """
        SELECT COUNT(*) 
        FROM {}.TERM 
        WHERE GO_ID = :1
        """.format(app.config["DB_SCHEMA"]), (term_id,)
    )
    if not cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid GO term",
            "message": "{} is not a valid GO term ID".format(term_id)
        }), 400

    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.INTERPRO2GO
        WHERE ENTRY_AC = :1 AND GO_ID = :2
        """, (accession, term_id)
    )
    if cur.fetchone()[0]:
        cur.close()
        return jsonify({
            "status": True
        }), 200

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.INTERPRO2GO (ENTRY_AC, GO_ID, SOURCE)
            VALUES (:1, :2, :3)
            """, (accession, term_id, "MANU")
        )
    except (DatabaseError, IntegrityError):
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "Could not add {} to {}".format(term_id, accession)
        }), 400
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route("/api/entry/<accession>/references/")
def get_entry_references(accession):
    pass
    # todo implement


@app.route("/api/entry/<acc1>/relationship/<acc2>/", methods=['DELETE'])
def delete_relationship(acc1, acc2):
    user = get_user()

    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY2ENTRY
            WHERE (PARENT_AC = :acc1 AND ENTRY_AC = :acc2)
            OR (PARENT_AC = :acc2 AND ENTRY_AC = :acc1)
            """,
            dict(acc1=acc1, acc2=acc2)
        )
    except IntegrityError:
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "Could not delete unlink {} and {}".format(acc1, acc2)
        }), 400
    else:
        # row_count = cur.rowcount  # TODO: check that row_count == 1?
        con.commit()
        return jsonify({
            "status": True,
            "title": None,
            "message": None
        }), 200
    finally:
        cur.close()


@app.route("/api/entry/<accession>/relationships/")
def get_entry_relationships(accession):
    cur = db.get_oracle().cursor()

    cur.execute(
        """
        SELECT 
          R.PARENT_AC, E1.NAME, E1.ENTRY_TYPE, 
          R.ENTRY_AC, E2.NAME, E2.ENTRY_TYPE
        FROM (
            SELECT PARENT_AC, ENTRY_AC
            FROM {0}.ENTRY2ENTRY
            START WITH ENTRY_AC = :accession
            CONNECT BY PRIOR PARENT_AC = ENTRY_AC
            UNION ALL
            SELECT PARENT_AC, ENTRY_AC
            FROM {0}.ENTRY2ENTRY
            START WITH PARENT_AC = :accession
            CONNECT BY PRIOR ENTRY_AC = PARENT_AC        
        ) R
        INNER JOIN {0}.ENTRY E1 ON R.PARENT_AC = E1.ENTRY_AC
        INNER JOIN {0}.ENTRY E2 ON R.ENTRY_AC = E2.ENTRY_AC
        """.format(app.config["DB_SCHEMA"]),
        dict(accession=accession)
    )

    parents = {}
    hierarchy = {}
    for row in cur:
        parent_acc = row[0]
        parent_name = row[1]
        parent_type = row[2]
        child_acc = row[3]
        child_name = row[4]
        child_type = row[5]

        parents[child_acc] = parent_acc

        if parent_acc in parents:
            _parents = []
            root_acc = parent_acc
            while root_acc in parents:
                root_acc = parents[parent_acc]
                _parents.append(root_acc)

            children = {}
            for acc in reversed(_parents):
                if not children:
                    children = hierarchy[acc]["children"]
                else:
                    children = children[acc]["children"]

            node = children[parent_acc]
        elif parent_acc in hierarchy:
            node = hierarchy[parent_acc]
        else:
            node = hierarchy[parent_acc] = {
                "accession": parent_acc,
                "name": parent_name,
                "type": parent_type,
                "children": {},
                "deletable": child_acc == accession
            }

        if child_acc in hierarchy:
            child = hierarchy.pop(child_acc)
        else:
            child = {
                "accession": child_acc,
                "name": child_name,
                "type": child_type,
                "children": {},
                "deletable": parent_acc == accession
            }

        node["children"][child_acc] = child

    cur.close()
    return jsonify(hierarchy), 200


@app.route("/api/entry/<accession>/signatures/")
def get_entry_signatures(accession):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT
          DBCODE,
          METHOD_AC,
          NAME,
          PROTEIN_COUNT
        FROM {0}.METHOD
        WHERE METHOD_AC IN (
          SELECT METHOD_AC
          FROM {0}.ENTRY2METHOD
          WHERE ENTRY_AC = :1
        )
        ORDER BY METHOD_AC
        """.format(app.config['DB_SCHEMA']),
        (accession,)
    )

    signatures = []
    for row in cur:
        database = xref.find_ref(row[0], row[1])

        signatures.append({
            "accession": row[1],
            "name": row[2],
            "num_proteins": row[3],
            "link": database.gen_link(),
            "color": database.color,
            "database": database.name
        })

    cur.close()
    return jsonify(signatures), 200

