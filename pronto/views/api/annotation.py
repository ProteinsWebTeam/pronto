from datetime import datetime
import re

from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify, request

from pronto import app, db, get_user, xref


def verify_text(text):
    # Find missing opening/closing tags
    for tag in ("b", "i", "li", "ol", "p", "pre", "sub", "sup", "ul"):
        open_tag = "<{}>".format(tag)
        close_tag = "</{}>".format(tag)
        is_open = False
        for m in re.findall(r"</?{}>".format(tag), text, re.I):
            m = m.lower()
            if m == open_tag:
                if is_open:
                    return "Mismatched {} element.".format(open_tag)
                else:
                    is_open = True
            elif is_open:
                is_open = False
            else:
                return "Mismatched {} element.".format(close_tag)

        if is_open:
            return "Mismatched {} element.".format(open_tag)

    # Find list items outside list
    lists = []
    is_open = False  # for items
    for tag in re.findall(r"</?(?:li|ul|ol)>", text, re.I):
        tag = tag.lower()

        if tag == "<ul>":
            if lists and not is_open:
                # Can only start a nested list inside a list element
                return "Nested <ul> element must be contained in a parent <li> element."
            else:
                lists.append("ul")
        elif tag == "</ul>":
            if is_open:
                return "Mismatched <li> element."
            elif lists.pop(-1) != "ul":
                return "Mismatched <ol> element."
        elif tag == "<ol>":
            if lists and not is_open:
                # Can only start a nested list inside a list element
                return "Nested <ol> element must be contained in a parent <li> element."
            else:
                lists.append("ol")
        elif tag == "</ol>":
            if is_open:
                return "Mismatched <li> element."
            elif lists.pop(-1) != "ol":
                return "Mismatched <ul> element."
        elif tag == "<li>":
            if is_open:
                return "Mismatched <li> element."
            elif not lists:
                return "<li> element must be contained in a parent <ol>, or <ul> element."
            else:
                is_open = True
        elif is_open:
            is_open = False
        else:
            return "Mismatched <li> element."

    # Test <cite> elements
    citations = set()
    prog = re.compile(r'<cite\sid="([a-z0-9]+)"/>', re.I)
    for hit in re.findall(r'<cite\s+id="[^"]+"\s*/?>', text, re.I):
        m = prog.search(hit)
        if m is None:
            return "Malformed citation: {}.".format(hit)

        citations.add(m.group(1))

    cur = db.get_oracle().cursor()

    if citations:
        # Test citations
        cur.execute(
            """
            SELECT PUB_ID 
            FROM INTERPRO.CITATION
            WHERE PUB_ID IN ({})
            """.format(",".join([":" + str(i+1) for i in range(len(citations))])),
            tuple(citations)
        )
        citations -= set([row[0] for row in cur])

        if citations:
            cur.close()
            return "Invalid reference(s): {}.".format(", ".join(sorted(citations)))

    # Test <dbxref> elements
    prog = re.compile(r'<dbxref\sdb="(\w+)"\sid="([\w.\-]+)"/>', re.I)
    for hit in re.findall(r"<dbxref[^>]+>", text, re.I):
        m = prog.search(hit)
        if m is None:
            cur.close()
            return "Malformed cross-reference: {}.".format(hit)

        dbcode = m.group(1).upper()
        xref_id = m.group(2)

        if not xref.find_xref(dbcode):
            cur.close()
            return "Invalid cross-reference(s): {}.".format(dbcode)

    # Test <taxon> elements
    taxons = set()
    prog = re.compile(r'<taxon\stax_id="(\d+)">[^<]+</taxon>')
    for hit in re.findall(r'<taxon\s+tax_id="[^"]+">[^<]*</taxon>', text, re.I):
        m = prog.search(hit)
        if m is None:
            cur.close()
            return "Malformed taxon: {}.".format(hit)

        taxons.add(int(m.group(1)))

    if taxons:
        cur.execute(
            """
            SELECT TAX_ID
            FROM {}.ETAXI
            WHERE TAX_ID IN ({})
            """.format(
                app.config["DB_SCHEMA"],
                ",".join([":" + str(i+1) for i in range(len(taxons))])
            ),
            tuple(taxons)
        )
        taxons -= set([row[0] for row in cur])

    cur.close()

    if taxons:
        return "Invalid taxon ID(s): {}.".format(", ".join(map(str, sorted(taxons))))

    return None


def lookup_pmid(text):
    cur = db.get_oracle().cursor()

    citations = {}
    subs = []
    for m in re.finditer(r"PMID:([,\d+]+)", text, re.I):
        pmids = []
        for pmid in m.group(1).split(','):
            if pmid:
                pmid = int(pmid)
                citations[pmid] = None
                pmids.append(pmid)

        subs.append({
            "ori": m.group(0),
            "pmids": pmids
        })

    if citations:
        cur.execute(
            """
            SELECT PUB_ID, PUBMED_ID
            FROM INTERPRO.CITATION
            WHERE PUBMED_ID IN ({})
            """.format(','.join([':' + str(i + 1) for i in range(len(citations))])),
            tuple(citations)
        )
        for pub_id, pmid in cur:
            citations[pmid] = pub_id

        invalid = [pmid for pmid, pub_id in citations.items() if pub_id is None]
        if not all(citations.values()):
            cur.close()
            return False, "Invalid PubMed ID(s): {}.".format(", ".join(map(str, sorted(invalid))))

        for sub in subs:
            repl = ", ".join(['<cite id="{}"/>'.format(citations[pmid]) for pmid in sub["pmids"]])
            text = text.replace(sub["ori"], repl)

    cur.close()
    return True, text


@app.route("/api/annotation/", methods=["PUT"])
def create_annotation():
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    try:
        text = request.form["text"].strip()
    except (AttributeError, KeyError):
        return jsonify({
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    error = verify_text(text)
    if error:
        return jsonify({
            "status": False,
            "title": "Text error",
            "message": error
        }), 400

    status, text = lookup_pmid(text)
    if not status:
        return jsonify({
            "status": False,
            "title": "Invalid reference",
            "message": text
        }), 400

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT MAX(ANN_ID) 
        FROM INTERPRO.COMMON_ANNOTATION
        """
    )
    row = cur.fetchone()
    ann_id = "AB" + str(int(row[0][2:]) + 1)
    comment = "Created by {} on {}".format(
        user["name"].split()[0],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.COMMON_ANNOTATION (ANN_ID, TEXT, COMMENTS)
            VALUES (:1, :2, :3)
            """,
            (ann_id, text, comment)
        )
    except IntegrityError:
        res = {
            "status": False,
            "title": "Database error",
            "message": "The annotation could not be created. "
                       "Another annotation with the same text "
                       "may already exist."
        }

        cur.execute(
            """
            SELECT ANN_ID
            FROM INTERPRO.COMMON_ANNOTATION
            WHERE TEXT = :1
            """, (text,)
        )
        row = cur.fetchone()

        if row is not None:
            res["id"] = row[0]

        return jsonify(res), 400
    except DatabaseError:
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "The annotation could not be created. "
                       "Another annotation with the same text "
                       "may already exist."
        }), 400
    else:
        con.commit()
        return jsonify({
            "status": True,
            "id": ann_id
        }), 200
    finally:
        cur.close()


@app.route("/api/annotation/<ann_id>/", methods=["POST"])
def update_annotations(ann_id):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    try:
        text = request.form["text"].strip()
        comment = request.form["reason"].strip()
    except (AttributeError, KeyError):
        return jsonify({
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    error = verify_text(text)
    if error:
        return jsonify({
            "status": False,
            "title": "Text error",
            "message": error
        }), 400

    comment += ' updated by {} on {}'.format(
        user['name'].split()[0],
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

    status, text = lookup_pmid(text)
    if not status:
        return jsonify({
            "status": False,
            "title": "Invalid reference",
            "message": text
        }), 400

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE INTERPRO.COMMON_ANNOTATION
            SET TEXT = :1, COMMENTS = :2
            WHERE ANN_ID = :3
            """,
            (text, comment, ann_id)
        )
    except DatabaseError:
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "Changes could not be saved."
        }), 400
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route("/api/annotation/<ann_id>/entries/")
def get_annotation_entries(ann_id):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT EC.ENTRY_AC, E.NAME, E.ENTRY_TYPE
        FROM INTERPRO.ENTRY2COMMON EC
        INNER JOIN INTERPRO.ENTRY E 
          ON EC.ENTRY_AC = E.ENTRY_AC
        WHERE EC.ANN_ID = :1
        ORDER BY EC.ENTRY_AC
        """, (ann_id,)
    )

    entries = []
    for row in cur:
        entries.append({
            "accession": row[0],
            "name": row[1],
            "type": row[2]
        })

    cur.close()
    return jsonify(entries), 200


@app.route("/api/annotation/search/")
def search_annotations():
    search_query = request.args.get("q", "").strip()
    hits = []

    if search_query:
        cur = db.get_oracle().cursor()
        cur.execute(
            """
            SELECT CA.ANN_ID, CA.TEXT, COUNT(EC.ENTRY_AC) AS CNT
            FROM INTERPRO.COMMON_ANNOTATION CA
            LEFT OUTER JOIN INTERPRO.ENTRY2COMMON EC 
              ON CA.ANN_ID = EC.ANN_ID
            WHERE REGEXP_LIKE (CA.TEXT, :q, 'i') OR EC.ENTRY_AC = UPPER(:q) 
            GROUP BY CA.ANN_ID, CA.TEXT
            ORDER BY CNT DESC, CA.ANN_ID
            """,
            dict(q=search_query)
        )

        for row in cur:
            hits.append({
                "id": row[0],
                "text": row[1],
                "num_entries": row[2]
            })

        cur.close()

    return jsonify(hits), 200
