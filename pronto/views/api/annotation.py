import re
from datetime import datetime
from typing import Optional, Sized

from cx_Oracle import DatabaseError, IntegrityError, STRING
from flask import jsonify, request

from pronto import app, db, get_user, xref


class Annotation(object):
    def __init__(self, text: str):
        self.text = text
        self.error = None
        self.references = {}  # PMID -> Pub ID

    def validate_html(self) -> bool:
        # Find missing opening/closing tags
        for el in ("b", "i", "li", "ol", "p", "pre", "sub", "sup", "ul"):
            is_open = False
            for tag in re.findall(r"</?{}>".format(el), self.text, re.I):
                if tag[1] != '/':
                    # is an opening tag
                    if is_open:
                        # Already open
                        self.error = "Mismatched <{}> element.".format(el)
                        return False
                    else:
                        is_open = True
                elif is_open:
                    # Closing tag after an opening tag
                    is_open = False
                else:
                    # Missing opening tag
                    self.error = "Mismatched </{}> element.".format(el)
                    return False

            if is_open:
                # Missing closing tag
                self.error = "Mismatched <{}> element.".format(el)
                return False

        # Find tags not allowed to be inside paragraphs
        in_paragraph = False
        for tag in re.findall(r"</?(?:p|ul|ol|li)>", self.text, re.I):
            tag = tag.lower()
            if tag == "<p>":
                in_paragraph = True
            elif tag == "</p>":
                in_paragraph = False
            elif in_paragraph:
                self.error = ("{} elements are not allowed "
                              "inside a paragraph.".format(tag))
                return False

        # Find list items outside list
        lists = []
        is_open = False  # for items
        for tag in re.findall(r"</?(?:li|ul|ol)>", self.text, re.I):
            tag = tag.lower()

            if tag == "<ul>":
                if lists and not is_open:
                    # Can only start a nested list inside a list element
                    self.error = ("Nested <ul> element must be contained "
                                  "in a parent <li> element.")
                    return False
                else:
                    lists.append("ul")
            elif tag == "</ul>":
                if is_open:
                    self.error = "Mismatched <li> element."
                    return False
                elif lists.pop(-1) != "ul":
                    self.error = "Mismatched <ol> element."
                    return False
            elif tag == "<ol>":
                if lists and not is_open:
                    # Can only start a nested list inside a list element
                    self.error =  ("Nested <ol> element must be contained "
                                   "in a parent <li> element.")
                    return False
                else:
                    lists.append("ol")
            elif tag == "</ol>":
                if is_open:
                    self.error = "Mismatched <li> element."
                    return False
                elif lists.pop(-1) != "ol":
                    self.error = "Mismatched <ul> element."
                    return False
            elif tag == "<li>":
                if is_open:
                    self.error = "Mismatched <li> element."
                    return False
                elif not lists:
                    self.error = ("<li> element must be contained "
                                  "in a parent <ol>, or <ul> element.")
                    return False
                else:
                    is_open = True
            elif is_open:
                is_open = False
            else:
                self.error = "Mismatched <li> element."
                return False

        return True

    def validate_xref_tags(self) -> bool:
        pattern = r"\[(\s*[a-z0-9]+\s*):([^\]]+)]"
        for match in re.finditer(pattern, self.text, re.I):
            ref_db, ref_id = match.groups()

            if ref_db.upper() != "CITE" and not xref.find_xref(ref_db.upper()):
                self.error = ("Invalid cross-reference database: "
                              "'{}'.".format(ref_db))
                return False
            elif ref_id != ref_id.strip():
                self.error = ("Invalid cross-reference accession: "
                              "'{}'.".format(ref_id))
                return False

        return True

    def update_references(self) -> bool:
        s_refs = set()
        matches = []

        prog_pub = re.compile(r"PUB\d+$", re.I)

        for match in re.finditer(r"\[cite:([^\]]+)\]", self.text, re.I):
            pmids = []
            pub_ids = set()
            for ref_id in match.group(1).split(','):
                if not ref_id:
                    # e.g. [cite:1533,,1464]
                    continue
                elif prog_pub.match(ref_id):
                    # Pub ID
                    pub_ids.add(ref_id)
                    continue

                try:
                    pmid = int(ref_id)
                except ValueError:
                    self.error = "'{}': not a valid reference.".format(ref_id)
                    return False

                if pmid not in pmids:
                    pmids.append(pmid)
                    self.references[pmid] = None  # do not know the pub ID yet
                    s_refs.add(pmid)

            # Store the entire match, PMIDs found, and PUB IDs found
            matches.append((match.group(0), pmids, pub_ids))

        if s_refs:
            # Get the Pub IDs for the PMIDs found
            con = db.get_oracle()
            cur = con.cursor()
            cur.execute(
                """
                SELECT PUB_ID, PUBMED_ID
                FROM INTERPRO.CITATION
                WHERE PUBMED_ID IN ({})
                """.format(self.format_in(s_refs)),
                tuple(s_refs)
            )

            for pub_id, pmid in cur:
                s_refs.remove(pmid)
                self.references[pmid] = pub_id

            if s_refs:
                # One or more PMID not found in our database -> use LITPUB
                cur.execute(
                    """
                    SELECT 
                      C.EXTERNAL_ID, I.VOLUME, I.ISSUE, I.PUBYEAR, C.TITLE, 
                      C.PAGE_INFO, J.MEDLINE_ABBREVIATION, J.ISO_ABBREVIATION, 
                      A.AUTHORS, U.URL
                    FROM CDB.CITATIONS@LITPUB C
                      LEFT OUTER JOIN CDB.JOURNAL_ISSUES@LITPUB I
                        ON C.JOURNAL_ISSUE_ID = I.ID
                      LEFT JOIN CDB.CV_JOURNALS@LITPUB J
                        ON I.JOURNAL_ID = J.ID
                      LEFT OUTER JOIN CDB.FULLTEXT_URL@LITPUB U
                        ON (
                            C.EXTERNAL_ID = U.EXTERNAL_ID AND
                            U.DOCUMENT_STYLE  ='DOI' AND
                            U.SOURCE = 'MED'
                        )
                      LEFT OUTER JOIN CDB.AUTHORS@LITPUB A
                        ON (
                          C.ID = A.CITATION_ID AND 
                          A.HAS_SPECIAL_CHARS = 'N'
                        )
                    WHERE C.EXTERNAL_ID IN ({})
                    """.format(self.format_in(s_refs)),
                    tuple(map(str, s_refs))
                )

                new_citations = []
                for row in cur:
                    # tuple does not support item assignment
                    row = list(row)

                    # PMID stored as VARCHAR2 in LITPUB
                    row[0] = int(row[0])

                    s_refs.remove(row[0])
                    new_citations.append(row)

                if s_refs:
                    # Still unknown PubMed ID: cannot proceed
                    cur.close()
                    pmids = ", ".join(map(str, sorted(s_refs)))
                    self.error = "Invalid PubMed IDs: {}".format(pmids)
                    return False

                # Insert new citation
                for row in new_citations:
                    """
                    CITATION.TITLE: VARCHAR2(740)
                        -> we may have to truncate the title
                    """
                    if len(row[4]) > 740:
                        row[4] = row[4][:737] + "..."

                    pub_id = cur.var(STRING)

                    try:
                        cur.execute(
                            """
                            INSERT INTO INTERPRO.CITATION (
                              PUB_ID, PUB_TYPE, PUBMED_ID, VOLUME, ISSUE, 
                              YEAR, TITLE, RAWPAGES, MEDLINE_JOURNAL, 
                              ISO_JOURNAL, AUTHORS, DOI_URL
                            ) VALUES (
                              INTERPRO.NEW_PUB_ID(), 'J', :1, :2, :3, :4, :5, 
                              :6, :7, :8, :9, :10
                            )
                            RETURNING PUB_ID INTO :11
                            """,
                            (*row, pub_id)
                        )
                    except DatabaseError:
                        cur.close()
                        self.error = ("Could not insert citation "
                                      "for PubMed ID {}".format(row[0]))
                        return False
                    else:
                        self.references[row[0]] = pub_id.getvalue()

                con.commit()
                cur.close()

        # Replace PMIDs by Pub IDs
        for match, pmids, pub_ids in matches:
            cite_tags = []
            for pmid in pmids:
                pub_id = self.references[pmid]
                cite_tags.append("[cite:{}]".format(pub_id))

            for pub_id in pub_ids:
                cite_tags.append("[cite:{}]".format(pub_id))

            self.text = self.text.replace(match, ", ".join(cite_tags))

        return True

    def wrap(self) -> str:
        blocks = []
        for block in self.text.split("\n\n"):
            block = block.strip()

            if re.match(r"<(?:li|ol|p|pre|ul)>", block, re.I) is None:
                # Does not start with a tag that cannot be included in <p></p>
                blocks.append("<p>" + block + "</p>")
            else:
                blocks.append(block)

        return "\n\n".join(blocks)

    def get_references(self, text: Optional[str]=None) -> set:
        return {
            m.group(1)
            for m
            in re.finditer(r"\[cite:(PUB\d+)\]", text or self.text, re.I)
        }

    @staticmethod
    def format_in(args: Sized) -> str:
        return ','.join([':' + str(i+1) for i in range(len(args))])


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

    ann = Annotation(text)
    if not ann.validate_html():
        return jsonify({
            "status": False,
            "title": "Text error",
            "message": ann.error
        }), 400
    elif not ann.validate_xref_tags():
        return jsonify({
            "status": False,
            "title": "Text error",
            "message": ann.error
        }), 400
    elif not ann.update_references():
        return jsonify({
            "status": False,
            "title": "Text error",
            "message": ann.error
        }), 400

    con = db.get_oracle()
    cur = con.cursor()
    ann_id = cur.var(STRING)
    comment = "Created by {} on {}".format(
        user["name"].split()[0],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.COMMON_ANNOTATION (ANN_ID, TEXT, COMMENTS)
            VALUES (INTERPRO.NEW_ANN_ID(), :1, :2)
            RETURNING ANN_ID INTO :3
            """,
            (text, comment, ann_id)
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

        return jsonify(res), 500
    except DatabaseError:
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "The annotation could not be created. "
                       "Another annotation with the same text "
                       "may already exist."
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True,
            "id": ann_id.getvalue()
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
        assert len(text) and len(comment)
    except (AssertionError, KeyError):
        return jsonify({
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    ann = Annotation(text)
    if not ann.validate_html():
        return jsonify({
            "status": False,
            "title": "Text error",
            "message": ann.error
        }), 400
    elif not ann.validate_xref_tags():
        return jsonify({
            "status": False,
            "title": "Text error",
            "message": ann.error
        }), 400
    elif not ann.update_references():
        return jsonify({
            "status": False,
            "title": "Text error",
            "message": ann.error
        }), 400

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT TEXT
        FROM INTERPRO.COMMON_ANNOTATION
        WHERE ANN_ID = :1
        """, (ann_id,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({
            "status": False,
            "title": "Invalid annotation",
            "message": "{} is not a valid annotation ID.".format(ann_id)
        }), 400

    """
    Compare references, 
    to see if there are references to add/delete in ENTRY2PUB
    """
    cur_references = ann.get_references(row[0])
    new_references = ann.get_references()
    old_references = cur_references - new_references
    new_references = new_references - cur_references

    if old_references or new_references:
        # Difference in references in text

        """
        Parse all annotations associated to entries associated 
        to the annotation we are updating 
        (a new reference in *this* annotation might be already associated 
        to an entry from *another* annotation)
        """
        cur.execute(
            """
            SELECT CA.ANN_ID, CA.TEXT, EC.ENTRY_AC
            FROM INTERPRO.COMMON_ANNOTATION CA
            INNER JOIN INTERPRO.ENTRY2COMMON EC 
              ON CA.ANN_ID = EC.ANN_ID
            WHERE EC.ENTRY_AC IN (
                SELECT ENTRY_AC
                FROM INTERPRO.ENTRY2COMMON
                WHERE ANN_ID = :1            
            )
            """, (ann_id, )
        )

        entries = {}
        annotations = {}
        for _ann_id, text, entry_ac in cur:
            if _ann_id == ann_id:
                """
                We do not consider references for the annotation
                that we are updating
                """
                annotations[_ann_id] = set()
            elif _ann_id not in annotations:
                annotations[_ann_id] = ann.get_references(text)

            if entry_ac in entries:
                entries[entry_ac] |= annotations[_ann_id]
            else:
                entries[entry_ac] = annotations[_ann_id]

        to_delete = []
        to_insert = []
        for entry_ac, references in entries.items():
            for pub_id in old_references:
                if pub_id not in references:
                    to_delete.append((entry_ac, pub_id))

            for pub_id in new_references:
                if pub_id not in references:
                    to_insert.append((entry_ac, pub_id))

        for entry_ac, pub_id in to_delete:
            try:
                cur.execute(
                    """
                    DELETE FROM INTERPRO.ENTRY2PUB
                    WHERE ENTRY_AC = :1 AND PUB_ID = :2
                    """, (entry_ac, pub_id)
                )
            except DatabaseError as e:
                cur.close()
                return jsonify({
                    "status": False,
                    "title": "Database error",
                    "message": str(e)
                }), 500

        for entry_ac, pub_id in to_insert:
            try:
                cur.execute(
                    """
                    INSERT INTO INTERPRO.ENTRY2PUB (ENTRY_AC, ORDER_IN, PUB_ID)
                    VALUES (
                      :acc, 
                      (
                        SELECT NVL(MAX(ORDER_IN), 0)+1 
                        FROM INTERPRO.ENTRY2PUB 
                        WHERE ENTRY_AC = :acc
                      ), 
                      :pub
                    )
                    """, dict(acc=entry_ac, pub=pub_id)
                )
            except DatabaseError as e:
                cur.close()
                return jsonify({
                    "status": False,
                    "title": "Database error",
                    "message": str(e)
                }), 500

    comment += ' updated by {} on {}'.format(
        user['name'].split()[0],
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

    try:
        cur.execute(
            """
            UPDATE INTERPRO.COMMON_ANNOTATION
            SET TEXT = :1, COMMENTS = :2
            WHERE ANN_ID = :3
            """,
            (ann.wrap(), comment, ann_id)
        )
    except DatabaseError:
        return jsonify({
            "status": False,
            "title": "Database error",
            "message": "Changes could not be saved."
        }), 500
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

        if search_query.isdigit():
            # Could be PubMed ID
            cur.execute(
                """
                SELECT PUB_ID 
                FROM INTERPRO.CITATION 
                WHERE PUBMED_ID = :1
                """,
                (int(search_query),)
            )
            row = cur.fetchone()
            if row:
                search_query = row[0]

        cur.execute(
            """
            SELECT CA.ANN_ID, CA.TEXT, COUNT(EC.ENTRY_AC) AS CNT
            FROM INTERPRO.COMMON_ANNOTATION CA
            LEFT OUTER JOIN INTERPRO.ENTRY2COMMON EC 
              ON CA.ANN_ID = EC.ANN_ID
            WHERE CA.ANN_ID IN (
                SELECT DISTINCT CA.ANN_ID
                FROM INTERPRO.COMMON_ANNOTATION CA
                LEFT OUTER JOIN INTERPRO.ENTRY2COMMON EC 
                  ON CA.ANN_ID = EC.ANN_ID
                WHERE REGEXP_LIKE (CA.TEXT, :q, 'i') 
                OR EC.ENTRY_AC = UPPER(:q)             
            )
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

    return jsonify({
        "query": search_query,
        "hits": hits
    }), 200
