import re

import oracledb

from flask import jsonify
from oracledb import Cursor, DatabaseError

from pronto import auth, utils
from . import bp


@bp.route("/<accession>/annotations/")
def get_annotations(accession):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT A.ANN_ID, A.TEXT, A.COMMENTS, A.LLM, A.CHECKED, S.CT
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
        [accession]
    )

    annotations = []
    prog_ref = re.compile(r"\[([a-z0-9]+):([a-z0-9\-.]+)]", re.I)
    prog_com = re.compile(r"\s\d\d:\d\d:\d\d$")

    for ann_id, text, comment, is_llm, is_checked, n_entries in cur:
        ext_refs = {}

        if comment is not None:
            """
            The accuracy (seconds) of comments bothers some curators:
            try to reduce the accuracy to minutes.
            """
            match = prog_com.search(comment)
            if match:
                start = match.start()
                hour = comment[start+1:]  # first character is a space
                comment = f"{comment[:start]} {hour[:5]}"

        for match in prog_ref.finditer(text):
            ref_db, ref_id = match.groups()
            try:
                url = utils.XREFS[ref_db.upper()]
            except KeyError:
                continue
            else:
                whole_match = match.group()

                ext_refs[whole_match] = {
                    "match": whole_match,
                    "id": ref_id,
                    "url": url.format(ref_id)
                }

        annotations.append({
            "id": ann_id,
            "text": text,
            "is_llm": is_llm == "Y",
            "is_checked": is_checked == "Y",
            "comment": comment,
            "num_entries": n_entries,
            "cross_references": list(ext_refs.values())
        })

    cur.execute(
        """
        SELECT
          E.PUB_ID, C.TITLE, C.YEAR, C.VOLUME, C.ISSUE, C.RAWPAGES, C.DOI_URL,
          C.PUBMED_ID, C.ISO_JOURNAL, C.MEDLINE_JOURNAL, C.AUTHORS
        FROM INTERPRO.ENTRY2PUB E
        INNER JOIN INTERPRO.CITATION C
        ON E.PUB_ID = C.PUB_ID
        WHERE E.ENTRY_AC = :1
        """,
        [accession]
    )

    references = {}
    for row in cur:
        pub_id = row[0]
        references[pub_id] = {
            "id": pub_id,
            "title": row[1],
            "year": row[2],
            "volume": row[3],
            "issue": row[4],
            "pages": row[5],
            "doi": row[6],
            "pmid": row[7],
            "journal": row[9] if row[8] else row[9],
            "authors": row[10]
        }

    cur.close()
    con.close()
    return jsonify({
        "annotations": annotations,
        "references": references
    })


def relate_entry_to_anno(
    ann_id: str,
    entry_acc: str,
    con: oracledb.Connection,
):
    """Link a newly inserted annotation to a new entry

    Con closing should be handled by the func that calls this func.

    :param ann_id: str, oracle db id for annotation record
    :param entry_acc: str, oracle db id for entry record
    :param con: open oracle db connection
    
    Return tuple:
    * None if successful, error obj (dict) if fails
    * http status code
    """
    cur = con.cursor()
    cur.execute(
        """
        SELECT MAX(ORDER_IN)
        FROM INTERPRO.ENTRY2COMMON
        WHERE ENTRY_AC = :1
        """,
        [entry_acc]
    )
    order_in, = cur.fetchone()
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
            [entry_acc, ann_id, order_in]
        )
        update_references(cur, entry_acc)
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not link annotation: {exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@bp.route('/<accession>/annotation/<ann_id>/', methods=["PUT"])
def link_annotation(accession, ann_id):
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

    err_obj, http_status = relate_entry_to_anno(
        ann_id,
        accession,
        con
    )

    con.close()
    return err_obj, http_status


@bp.route('/<accession>/annotation/<ann_id>/order/up/', methods=["POST"])
def move_annotation_up(accession, ann_id):
    return move_annotation(accession, ann_id, -1)


@bp.route('/<accession>/annotation/<ann_id>/order/down/', methods=["POST"])
def move_annotation_down(accession, ann_id):
    return move_annotation(accession, ann_id, 1)


@bp.route('/<accession>/annotation/<ann_id>/', methods=["DELETE"])
def unlink_annotation(accession, ann_id):
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

    # Check entries that would be without annotations
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY2COMMON
        WHERE ENTRY_AC = :1 AND ANN_ID != :2
        """,
        [accession, ann_id]
    )
    other_annotations, = cur.fetchone()
    if not other_annotations:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Cannot unlink annotation",
                "message": f"This annotation cannot be unlinked as it is "
                           f"the only annotation for {accession}."
            }
        }), 409

    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY2COMMON
            WHERE ENTRY_AC = :1 AND ANN_ID = :2
            """,
            [accession, ann_id]
        )
        update_references(cur, accession)
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not unlink annotation: {exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()
        con.close()


def move_annotation(accession: str, ann_id: str, x: int):
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

    # Get the position of each annotation
    cur.execute(
        """
        SELECT ANN_ID, ORDER_IN
        FROM INTERPRO.ENTRY2COMMON
        WHERE ENTRY_AC = :1
        """,
        [accession]
    )
    annotations = dict(cur.fetchall())

    if ann_id not in annotations:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid parameters",
                "message": f"Entry {accession} is not associated "
                           f"to annotation {ann_id}."
            }
        }), 400

    max_order = max(annotations.values())
    min_order = min(annotations.values())

    # Annotations in the current order
    annotations = sorted(annotations, key=lambda k: annotations[k])

    # Current index of the annotation to move
    idx = annotations.index(ann_id)

    # New index, forced to stay in the range [0, num_annotations-1]
    new_idx = min(max(0, idx + x), len(annotations) - 1)

    if idx == new_idx:
        # Nothing to change
        cur.close()
        con.close()
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
            """,
            [i + offset, accession, ann_id]
        )

    con.commit()
    cur.close()

    return jsonify({
        "status": True
    }), 200


def update_references(cur: Cursor, accession: str):
    # Get references from the entry-pub table (may need to be updated)
    cur.execute(
        """
        SELECT PUB_ID, ORDER_IN
        FROM INTERPRO.ENTRY2PUB
        WHERE ENTRY_AC = :1
        """,
        [accession]
    )
    # Keep order_in to know the highest order
    pre_references = dict(cur.fetchall())

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
        [accession]
    )

    now_references = set()
    prog_ref = re.compile(r"\[cite:(PUB\d+)\]", re.I)
    for text, in cur:
        for m in prog_ref.finditer(text):
            now_references.add(m.group(1))

    # Get supplementary references to see which ones need to be deleted
    to_delete = []
    cur.execute(
        """
        SELECT PUB_ID
        FROM INTERPRO.SUPPLEMENTARY_REF
        WHERE ENTRY_AC = :1
        """,
        [accession]
    )
    for pub_id, in cur:
        if pub_id in now_references:
            to_delete.append((accession, pub_id))

    if to_delete:
        cur.executemany(
            """
            DELETE FROM INTERPRO.SUPPLEMENTARY_REF
            WHERE ENTRY_AC = :1 AND PUB_ID = :2
            """,
            to_delete
        )

    old_references = []
    for pub_id, order_id in pre_references.items():
        try:
            now_references.remove(pub_id)
        except KeyError:
            # Not in annotations: remove from DB
            old_references.append((accession, pub_id))

    if old_references:
        # Move references to SUPPLEMENTARY_REF table
        cur.executemany(
            """
            DELETE FROM INTERPRO.ENTRY2PUB
            WHERE ENTRY_AC = :1 AND PUB_ID = :2
            """,
            old_references
        )

        cur.executemany(
            """
            INSERT INTO INTERPRO.SUPPLEMENTARY_REF
            VALUES (:1, :2)
            """,
            old_references
        )

    if now_references:
        # References to be inserted into ENTRY2PUB
        if pre_references:
            start = max(pre_references.values()) + 1
        else:
            start = 1

        params = []
        for i, pub_id in enumerate(sorted(now_references)):
            params.append((accession, start+i, pub_id))

        cur.executemany(
            """
            INSERT INTO INTERPRO.ENTRY2PUB (ENTRY_AC, ORDER_IN, PUB_ID)
            VALUES (:1, :2, :3)
            """,
            params
        )
