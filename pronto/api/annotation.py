import re
from datetime import datetime
from xml.dom.minidom import parseString
from xml.parsers.expat import ExpatError

import oracledb
from oracledb import Cursor, DatabaseError, STRING
from flask import Blueprint, jsonify, request

from pronto import auth, utils
from pronto.api.checks.utils import load_global_exceptions

bp = Blueprint("api_annotation", __name__, url_prefix="/api/annotation")


class Annotation(object):
    def __init__(self, text: str):
        self.text = text
        self.error = None
        self.references = {}  # PMID -> Pub ID

        # Remove U+00AD (soft-hyphen)
        # http://www.fileformat.info/info/unicode/char/00AD/index.htm
        self.text = self.text.replace("\xad", "")
        self.text = self.text.replace("\u00ad", "")

    def validate_html(self) -> bool:
        # Find missing opening/closing tags
        for el in ("b", "i", "li", "ol", "p", "pre", "sub", "sup", "ul"):
            is_open = False
            for tag in re.findall(f"</?{el}>", self.text):
                if tag[1] != '/':
                    # is an opening tag
                    if is_open:
                        # Already open
                        self.error = f"Mismatched <{el}> element."
                        return False
                    else:
                        is_open = True
                elif is_open:
                    # Closing tag after an opening tag
                    is_open = False
                else:
                    # Missing opening tag
                    self.error = f"Mismatched </{el}> element."
                    return False

            if is_open:
                # Missing closing tag
                self.error = f"Mismatched <{el}> element."
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
                self.error = (f"{tag} elements are not allowed "
                              f"inside a paragraph.")
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
                    self.error = ("Nested <ol> element must be contained "
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

        # Final check: ensure the abstract is XML-compliant (i.e. parsable)
        try:
            parseString(f"<abstract>{self.text}</abstract>")
        except ExpatError as exc:
            self.error = "Abstract is not a well-formed XML element."
            return False
        else:
            return True

    def validate_xref_tags(self) -> bool:
        pattern = r"\[(\s*[a-z0-9]+\s*):([^\]]+)]"
        for match in re.finditer(pattern, self.text, re.I):
            ref_db, ref_id = match.groups()

            if ref_db.upper() != "CITE" and ref_db.upper() not in utils.XREFS:
                self.error = f"Invalid tag: '{ref_db}'."
                return False
            elif ref_id != ref_id.strip():
                self.error = (f"Invalid cross-reference accession: "
                              f"'{ref_id}'.")
                return False

        return True

    def validate_encoding(self, exceptions: set[str]) -> bool:
        errors = []
        for i, line in enumerate(self.text.splitlines(keepends=False)):
            for j, char in enumerate(line):
                if not char.isascii() and str(ord(char)) not in exceptions:
                    errors.append(f"'{char}' (line {i + 1}, position {j + 1}, "
                                  f"code: {ord(char)})")

        if errors:
            self.error = f"Invalid character(s): {', '.join(errors)}"

        return len(errors) == 0

    def update_references(self, cur: Cursor) -> bool:
        matches = []
        lookup_pmids = set()

        prog_pub = re.compile(r"PUB\d+$", re.I)
        for match in re.finditer(r"\[cite:([^\]]+)\]", self.text, re.I):
            pmids = []
            pub_ids = set()
            for ref_id in match.group(1).split(','):
                ref_id = ref_id.strip()
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
                    self.error = f"Invalid reference: '{ref_id}'."
                    return False

                if pmid not in pmids:
                    pmids.append(pmid)
                    lookup_pmids.add(pmid)
                    self.references[pmid] = None  # do not know the pub ID yet

            # Store the entire match, PMIDs found, and PUB IDs found
            matches.append((match.group(0), pmids, pub_ids))

        if lookup_pmids:
            # Get the Pub IDs for the PMIDs found
            args = ','.join(':' + str(i + 1) for i in range(len(lookup_pmids)))
            cur.execute(
                f"""
                SELECT PUB_ID, PUBMED_ID
                FROM INTERPRO.CITATION
                WHERE PUBMED_ID IN ({args})
                """,
                tuple(lookup_pmids)
            )

            for pub_id, pmid in cur:
                lookup_pmids.remove(pmid)
                self.references[pmid] = pub_id

            if lookup_pmids:
                # One or more PMID not found in our database -> use LITPUB
                new_citations = get_citations(cur, list(lookup_pmids))
                lookup_pmids -= set(new_citations.keys())

                if lookup_pmids:
                    # Still unknown PubMed ID: cannot proceed
                    pmids = ", ".join(map(str, sorted(lookup_pmids)))
                    self.error = f"Invalid PubMed IDs: {pmids}"
                    return False

                error = insert_citations(cur, new_citations)
                if error:
                    self.error = error
                    return False

                self.references.update(new_citations)

        # Replace PMIDs by Pub IDs
        for match, pmids, pub_ids in matches:
            cite_tags = []
            for pmid in pmids:
                pub_ids.add(self.references[pmid])

            for pub_id in sorted(pub_ids):
                cite_tags.append(f"[cite:{pub_id}]")

            self.text = self.text.replace(match, ", ".join(cite_tags))

        return True

    @staticmethod
    def _wrap_bef(match: re.Match) -> str:
        text, tag = match.groups()
        text = text.strip()
        if text:
            return f"<p>{text}</p>\n\n{tag}"
        else:
            return tag

    @staticmethod
    def _wrap_mid(match: re.Match) -> str:
        closing_tag, text, opening_tag = match.groups()
        text = text.strip()
        if text:
            return f"{closing_tag}\n\n<p>{text}</p>\n\n{opening_tag}"
        else:
            return f"{closing_tag}\n\n{opening_tag}"

    @staticmethod
    def _wrap_aft(match: re.Match) -> str:
        tag, text = match.groups()
        text = text.strip()
        if text:
            return f"{tag}\n\n<p>{text}</p>"
        else:
            return tag

    def wrap(self):
        text = self.text
        if re.search(r"(<(?:p|ul|ol|li)>)", text):
            # Wrap text before first block
            # (re.S: dot '.' also matches new lines)
            pattern = r"^(.*?)(<(?:p|pre|ul|ol)>)"
            text = re.sub(pattern, self._wrap_bef, text, flags=re.S)

            # Wrap text between two blocks
            pattern = r"(</(?:p|pre|ul|ol)>)(.*?)(<(?:p|pre|ul|ol)>)"
            text = re.sub(pattern, self._wrap_mid, text, flags=re.S)

            """
            Wrap trailing text, i.e. after last block
            Use a negative-lookahead to ensure the closing tag is the last one,
            i.e. not followed by an opening tag  
            """
            pattern = r"(</(?:p|pre|ul|ol)>)(?!.*<(?:p|pre|ul|ol)>)(.*?)$"
            text = re.sub(pattern, self._wrap_aft, text, flags=re.S)
        else:
            paragraphs = text.split("\n")
            text = ""
            for i, block in enumerate(paragraphs):
                block = block.strip()
                if not block:
                    continue
                elif text:
                    text += f"\n\n"

                text += f"<p>{block}</p>"

        self.text = text

    def strip(self):
        text = re.sub(r"(<(?:p|ul|ol|li)>)\s+", r"\1", self.text)
        self.text = re.sub(r"\s+(</(?:p|ul|ol|li)>)", r"\1", text)

    def get_references(self, text: str | None = None) -> set:
        return {
            m.group(1)
            for m
            in re.finditer(r"\[cite:(PUB\d+)\]", text or self.text, re.I)
        }


def insert_annotation(
        text: str,
        con: oracledb.Connection,
        user: dict,
        is_llm: bool = False,
        is_checked: bool = False,
) -> tuple[str | None, dict, int]:
    """
    Insert a new annotation into the hooked up oracle db (e.g. IPPRO)

    When adding AI generated entry, automatically add AI generated description to
    COMMON_ANNOTATION, and link to ENTRY via entry2common relationship table

    Con closing should be handled in the func that calls this func.

    :param text: str, description of annotation
    :param con: oracle db connection
    :param user: dict, user authentication dict
    :param is_llm: bool, whether the annotation is an AI-generated annotation
    :param is_checked: bool, whether the annotation has been reviewed by a curator

    Return tuple:
    * annotation id (ann_id) if successful, None if fails
    * None if successful, error obj (dict) if fails
    * http status code
    """
    ann = Annotation(text)
    if not ann.validate_html():
        return (
            None,
            {
                "status": False,
                "error": {
                    "title": "Text error",
                    "message": ann.error
                }
            },
            400
        )
    elif not ann.validate_xref_tags():
        return (
            None,
            {
                "status": False,
                "error": {
                    "title": "Text error",
                    "message": ann.error
                }
            },
            400,
        )

    cur = con.cursor()
    if not ann.validate_encoding(load_global_exceptions(cur, "encoding")):
        cur.close()
        return (
            None,
            {
                "status": False,
                "error": {
                    "title": "Text error",
                    "message": ann.error
                }
            },
            400,
        )

    if not ann.update_references(cur):
        cur.close()
        return (
            None,
            {
                "status": False,
                "error": {
                    "title": "Text error",
                    "message": ann.error
                }
            },
            400,  # could be 500 (if INSERT failed)
        )

    ann.strip()
    ann.wrap()
    text = ann.text

    cur.execute(
        """
        SELECT ANN_ID
        FROM INTERPRO.COMMON_ANNOTATION
        WHERE TEXT = :1
        """,
        [text]
    )
    row = cur.fetchone()
    if row:
        ann_id, = row
        return (
            ann_id,
            {
                "status": True,
                "id": ann_id
            },
            200,
        )

    action = "Imported" if is_llm else "Created"
    comment = (f"{action} by {user['name'].split()[0]} "
               f"on {datetime.now():%Y-%m-%d %H:%M:%S}")
    ann_id = cur.var(STRING)
    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.COMMON_ANNOTATION 
                (ANN_ID, TEXT, COMMENTS, LLM, CHECKED)
            VALUES (INTERPRO.NEW_ANN_ID(), :1, :2, :3, :4)
            RETURNING ANN_ID INTO :5
            """,
            [text, comment, "Y" if is_llm else "N",
             "Y" if is_checked else "N", ann_id]
        )
    except DatabaseError as exc:
        # error, = exc.args
        # if error.code == 1:
        #     # ORA-00001: unique constraint violated
        #     pass

        return (
            None,
            {
                "status": False,
                "error": {
                    "title": "Database error",
                    "message": f"The annotation could not be created: {exc}."
                }
            },
            500,
        )
    else:
        ann_id = ann_id.getvalue()[0]
        return (
            ann_id,
            {
                "status": True,
                "id": ann_id
            },
            200,
        )
    finally:
        cur.close()


@bp.route("/", methods=["PUT"])
def create_annotation():
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this operation."
            }
        }), 401

    try:
        text = request.form["text"].strip()
        is_llm = request.form["llm"].strip()
        is_checked = request.form["checked"].strip()
        assert (len(text) and
                is_llm in ("true", "false") and
                is_checked in ("true", "false"))
    except (AssertionError, KeyError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    is_llm = is_llm == "true"
    is_checked = is_checked == "true"

    con = utils.connect_oracle_auth(user)

    anno_id, err_obj, http_status = insert_annotation(
        text,
        con,
        user,
        is_llm,
        is_checked,
    )

    if anno_id is not None:
        con.commit()

    con.close()
    return jsonify(err_obj), http_status


@bp.route("/search/")
def search_annotations():
    search_query = request.args.get("q", "").strip()
    hits = []

    con = utils.connect_oracle()
    cur = con.cursor()

    if re.fullmatch(r"AB\d+", search_query, re.I):
        cur.execute(
            """
            SELECT CA.ANN_ID, CA.TEXT, CA.LLM, CA.CHECKED, NVL(EC.CNT, 0)
            FROM INTERPRO.COMMON_ANNOTATION CA
            LEFT OUTER JOIN (
                SELECT ANN_ID, COUNT(*) AS CNT
                FROM INTERPRO.ENTRY2COMMON
                GROUP BY ANN_ID
            ) EC ON CA.ANN_ID = EC.ANN_ID 
            WHERE CA.ANN_ID = :1
            """,
            [search_query.upper()]
        )
        row = cur.fetchone()
        if row:
            hits.append({
                "id": row[0],
                "text": row[1],
                "is_llm": row[2] == "Y",
                "is_checked": row[3] == "Y",
                "num_entries": row[4]
            })
    elif search_query:
        if search_query.isdigit():
            # Could be PubMed ID
            cur.execute(
                """
                SELECT PUB_ID 
                FROM INTERPRO.CITATION 
                WHERE PUBMED_ID = :1
                """, [int(search_query)]
            )
            row = cur.fetchone()
            if row:
                search_query, = row

        cur.execute(
            """
            SELECT CA.ANN_ID, CA.TEXT, MIN(CA.LLM), MIN(CA.CHECKED), 
                   COUNT(EC.ENTRY_AC) AS CNT
            FROM INTERPRO.COMMON_ANNOTATION CA
            LEFT OUTER JOIN INTERPRO.ENTRY2COMMON EC 
              ON CA.ANN_ID = EC.ANN_ID
            WHERE CA.ANN_ID IN (
                SELECT DISTINCT CA.ANN_ID
                FROM INTERPRO.COMMON_ANNOTATION CA
                LEFT OUTER JOIN INTERPRO.ENTRY2COMMON EC 
                  ON CA.ANN_ID = EC.ANN_ID
                WHERE REGEXP_LIKE (CA.TEXT, :q, 'i') 
                  OR EC.ENTRY_AC = :q
            )
            GROUP BY CA.ANN_ID, CA.TEXT
            ORDER BY CNT DESC, CA.ANN_ID
            """,
            dict(q=search_query.upper())
        )

        for row in cur:
            hits.append({
                "id": row[0],
                "text": row[1],
                "is_llm": row[2] == "Y",
                "is_checked": row[3] == "Y",
                "num_entries": row[4]
            })

    cur.close()
    con.close()
    return jsonify({
        "query": search_query,
        "hits": hits
    })


@bp.route("/<ann_id>/")
def get_annotation(ann_id):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT A.TEXT, A.COMMENTS, A.LLM, A.CHECKED, S.CT
        FROM INTERPRO.COMMON_ANNOTATION A
        LEFT OUTER JOIN (
          SELECT ANN_ID, COUNT(*) CT
          FROM INTERPRO.ENTRY2COMMON
          GROUP BY ANN_ID
        ) S ON A.ANN_ID = S.ANN_ID
        WHERE A.ANN_ID = :1
        """,
        [ann_id]
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify(), 404

    prog_ref = re.compile(r"\[([a-z0-9]+):([a-z0-9\-.]+)]", re.I)
    text, comment, is_llm, is_checked, n_entries = row
    ext_refs = {}

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

    return jsonify({
        "id": ann_id,
        "text": text,
        "comment": comment,
        "is_llm": is_llm == "Y",
        "is_checked": is_checked == "Y",
        "num_entries": n_entries,
        "cross_references": list(ext_refs.values())
    }), 200


@bp.route("/<ann_id>/", methods=["POST"])
def update_annotation(ann_id):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this operation."
            }
        }), 401

    try:
        text = request.form["text"].strip()
        comment = request.form["reason"].strip()
        is_llm = request.form["llm"].strip()
        is_checked = request.form["checked"].strip()
    except KeyError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    if len(text) == 0:
        return jsonify({
            "status": False,
            "error": {
                "title": "Empty annotation",
                "message": "An annotation cannot be left empty."
            }
        }), 400
    elif len(comment) == 0:
        return jsonify({
            "status": False,
            "error": {
                "title": "Empty comment",
                "message": "A comment/reason is required when "
                           "updating an annotation."
            }
        }), 400
    elif is_llm not in ("true", "false"):
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid value for 'llm'",
                "message": "The value of 'llm' must be 'true' or 'false'."
            }
        }), 400
    elif is_checked not in ("true", "false"):
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid value for 'checked'",
                "message": "The value of 'checked' must be 'true' or 'false'."
            }
        }), 400

    is_llm = is_llm == "true"
    is_checked = is_checked == "true"

    ann = Annotation(text)
    if not ann.validate_html():
        return jsonify({
            "status": False,
            "error": {
                "title": "Text error",
                "message": ann.error
            }
        }), 400
    elif not ann.validate_xref_tags():
        return jsonify({
            "status": False,
            "error": {
                "title": "Text error",
                "message": ann.error
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    if not ann.validate_encoding(load_global_exceptions(cur, "encoding")):
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Text error",
                "message": ann.error
            }
        }), 400

    if not ann.update_references(cur):
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Text error",
                "message": ann.error
            }
        }), 400  # could be 500 (if INSERT failed)

    cur.execute(
        """
        SELECT TEXT, LLM
        FROM INTERPRO.COMMON_ANNOTATION
        WHERE ANN_ID = :1
        """,
        [ann_id]
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid annotation",
                "message": f"{ann_id} is not a valid annotation ID."
            }
        }), 400

    current_text = row[0]
    is_currently_llm = row[1] == "Y"

    # TODO: remove following block if allowing to change LLM->human
    if is_currently_llm != is_llm:
        return jsonify({
            "status": False,
            "error": {
                "title": "Action not permitted",
                "message": f"Changing the origin of annotations is forbidden."
            }
        }), 403

    """
    Compare references, 
    to see if there are references to add/delete in ENTRY2PUB
    """
    pre_references = ann.get_references(current_text)
    now_references = ann.get_references()

    # references that do not exist anymore
    old_references = pre_references - now_references

    # references that need to be inserted in ENTRY2PUB
    new_references = now_references - pre_references

    if old_references or new_references:
        # Difference in references in text

        """
        Find supplementary annotations, 
        as we want to delete suppl. references that are now in the text
        """
        cur.execute(
            """
            SELECT ENTRY_AC, PUB_ID
            FROM INTERPRO.SUPPLEMENTARY_REF
            WHERE ENTRY_AC IN (
                SELECT ENTRY_AC
                FROM INTERPRO.ENTRY2COMMON
                WHERE ANN_ID = :1                  
            )
            """,
            [ann_id]
        )
        to_delete = []
        for entry_ac, pub_id in cur:
            if pub_id in now_references:
                # reference in the text: remove it from suppl. references
                to_delete.append((entry_ac, pub_id))

        if to_delete:
            try:
                cur.executemany(
                    """
                    DELETE FROM INTERPRO.SUPPLEMENTARY_REF
                    WHERE ENTRY_AC = :1 AND PUB_ID = :2
                    """,
                    to_delete
                )
            except DatabaseError as exc:
                cur.close()
                con.close()
                return jsonify({
                    "status": False,
                    "error": {
                        "title": "Database error",
                        "message": str(exc)
                    }
                }), 500

        """
        Parse all annotations associated to entries associated 
        to the annotation we are updating for cases such as:
          - new references (in this annotation) must be associated 
            to all its entries, unless they already have that reference 
            in another annotation
          - old references must be removed in all entries, 
            unless they have the reference in another annotation
        """
        cur.execute(
            """
            SELECT CA.ANN_ID, CA.TEXT, EC.ENTRY_AC
            FROM INTERPRO.COMMON_ANNOTATION CA
            INNER JOIN INTERPRO.ENTRY2COMMON EC 
              ON CA.ANN_ID = EC.ANN_ID
            WHERE EC.ENTRY_AC IN (
                SELECT DISTINCT ENTRY_AC
                FROM INTERPRO.ENTRY2COMMON
                WHERE ANN_ID = :1            
            )
            """, [ann_id]
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

        # Find publications currently in ENTRY2PUB
        cur.execute(
            """
            SELECT ENTRY_AC, PUB_ID
            FROM INTERPRO.ENTRY2PUB
            WHERE ENTRY_AC IN (
                SELECT DISTINCT ENTRY_AC
                FROM INTERPRO.ENTRY2COMMON
                WHERE ANN_ID = :1            
            )
            """,
            [ann_id]
        )
        in_entry2pub = set(cur.fetchall())

        # Find publications currently in SUPPLEMENTARY_REF
        cur.execute(
            """
            SELECT ENTRY_AC, PUB_ID
            FROM INTERPRO.SUPPLEMENTARY_REF
            WHERE ENTRY_AC IN (
                SELECT DISTINCT ENTRY_AC
                FROM INTERPRO.ENTRY2COMMON
                WHERE ANN_ID = :1            
            )
            """,
            [ann_id]
        )
        in_suppl_ref = set(cur.fetchall())

        to_move = set()
        to_insert = set()
        for entry_ac, references in entries.items():
            for pub_id in old_references:
                if pub_id not in references:
                    # old reference not in any annotation: move to suppl. refs
                    cur.execute(
                        """
                        DELETE FROM INTERPRO.ENTRY2PUB
                        WHERE ENTRY_AC = :1 AND PUB_ID = :2
                        """,
                        [entry_ac, pub_id]
                    )

                    if (entry_ac, pub_id) not in in_suppl_ref:
                        cur.execute(
                            """
                            INSERT INTO INTERPRO.SUPPLEMENTARY_REF
                            VALUES (:1, :2)
                            """,
                            [entry_ac, pub_id]
                        )

            for pub_id in new_references:
                if pub_id not in references:
                    # new reference not in ENTRY2PUB yet
                    to_insert.add((entry_ac, pub_id))

        for entry_ac, pub_id in to_insert - in_entry2pub:
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
            except DatabaseError as exc:
                cur.close()
                con.close()
                return jsonify({
                    "status": False,
                    "error": {
                        "title": "Could not add literature reference to entry",
                        "message": str(exc)
                    }
                }), 500

    comment += (f" updated by {user['name'].split()[0]} "
                f"on {datetime.now():%Y-%m-%d %H:%M:%S}")

    ann.strip()
    ann.wrap()
    try:
        cur.execute(
            """
            UPDATE INTERPRO.COMMON_ANNOTATION
            SET TEXT = :1, COMMENTS = :2, LLM = :3, CHECKED = :4
            WHERE ANN_ID = :5
            """,
            [ann.text, comment, "Y" if is_llm else "N",
             "Y" if is_checked else "N", ann_id]
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": f"Could not update {ann_id}",
                "message": str(exc)
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


@bp.route("/<ann_id>/review/", methods=["POST"])
def approve_annotation(ann_id):
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
    cur.execute(
        """
        SELECT LLM, CHECKED
        FROM INTERPRO.COMMON_ANNOTATION
        WHERE ANN_ID = :1
        """,
        [ann_id]
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid annotation",
                "message": f"{ann_id} is not a valid annotation ID."
            }
        }), 400

    if row[0] == "N":
        # Not an LLM-generated annotation: cannot be flagged as "reviewed"
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Action not permitted",
                "message": f"{ann_id} has not been generated using a LLM, "
                           f"and therefore cannot be reviewed."
            }
        }), 403

    try:
        cur.execute(
            """
            UPDATE INTERPRO.COMMON_ANNOTATION
               SET CHECKED = 'Y'
             WHERE ANN_ID = :1
            """,
            [ann_id]
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": f"Could not flagged {ann_id} as reviewed",
                "message": str(exc)
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


@bp.route("/<ann_id>/", methods=["DELETE"])
def delete_annotations(ann_id):
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
        FROM (
            SELECT ENTRY_AC 
            FROM INTERPRO.ENTRY2COMMON
            WHERE ANN_ID = :annid
            MINUS 
            SELECT DISTINCT ENTRY_AC 
            FROM INTERPRO.ENTRY2COMMON
            WHERE ANN_ID != :annid
        )
        """, dict(annid=ann_id)
    )
    num_entries, = cur.fetchone()

    if num_entries:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Cannot deletion annotation",
                "message": f"This annotation cannot be deleted as it is "
                           f"the only annotation for {num_entries} entries."
            }
        }), 409

    try:
        del_entry2pub, new_suppl = track_references(cur, ann_id)

        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY2COMMON
            WHERE ANN_ID = :1
            """,
            [ann_id]
        )

        cur.execute(
            """
            DELETE FROM INTERPRO.COMMON_ANNOTATION
            WHERE ANN_ID = :1
            """,
            [ann_id]
        )

        if del_entry2pub:
            cur.executemany(
                """
                DELETE FROM INTERPRO.ENTRY2PUB
                WHERE ENTRY_AC = :1 AND PUB_ID = :2
                """,
                del_entry2pub
            )

        if new_suppl:
            cur.executemany(
                """
                INSERT INTO INTERPRO.SUPPLEMENTARY_REF
                VALUES (:1, :2)
                """,
                new_suppl
            )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(exc)
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        })
    finally:
        cur.close()
        con.close()


def track_references(cur: Cursor, ann_id: str):
    cur.execute(
        """
            SELECT ENTRY_AC, PUB_ID
            FROM INTERPRO.ENTRY2PUB
            WHERE ENTRY_AC IN (
                SELECT ENTRY_AC
                FROM INTERPRO.ENTRY2COMMON
                WHERE ANN_ID = :1
            )
            """, [ann_id]
    )
    entry2pub = {}
    for entry_acc, pub_id in cur.fetchall():
        try:
            entry2pub[entry_acc].add(pub_id)
        except KeyError:
            entry2pub[entry_acc] = {pub_id}

    cur.execute(
        """
        SELECT ENTRY_AC, PUB_ID
        FROM INTERPRO.SUPPLEMENTARY_REF
        WHERE ENTRY_AC IN (
            SELECT ENTRY_AC
            FROM INTERPRO.ENTRY2COMMON
            WHERE ANN_ID = :1
        )
        """, [ann_id]
    )
    entry2suppl = {}
    for entry_acc, pub_id in cur.fetchall():
        try:
            entry2suppl[entry_acc].add(pub_id)
        except KeyError:
            entry2suppl[entry_acc] = {pub_id}

    cur.execute(
        """
        SELECT CA.ANN_ID, CA.TEXT, EC.ENTRY_AC
        FROM INTERPRO.COMMON_ANNOTATION CA
        INNER JOIN INTERPRO.ENTRY2COMMON EC ON CA.ANN_ID = EC.ANN_ID
        WHERE CA.ANN_ID != :1
         AND EC.ENTRY_AC IN (
            SELECT ENTRY_AC
            FROM INTERPRO.ENTRY2COMMON
            WHERE ANN_ID = :2
        )
        """, (ann_id, ann_id)
    )
    annotations = {}
    for ann_id, text, entry_acc in cur.fetchall():
        try:
            annotations[ann_id]["entries"].append(entry_acc)
        except KeyError:
            annotations[ann_id] = {
                "text": text,
                "entries": [entry_acc]
            }

    prog_ref = re.compile(r"\[cite:(PUB\d+)\]", re.I)
    for ann in annotations.values():
        pubs = set()
        for m in prog_ref.finditer(ann["text"]):
            pubs.add(m.group(1))

        for entry_acc in ann["entries"]:
            try:
                entry2pub[entry_acc] -= pubs
            except KeyError:
                continue

    del_entry2pub = []
    new_suppl = []
    for entry_acc, pubs in entry2pub.items():
        for pub_id in pubs:
            del_entry2pub.append((entry_acc, pub_id))

            if pub_id not in entry2suppl.get(entry_acc, []):
                new_suppl.append((entry_acc, pub_id))

    return del_entry2pub, new_suppl


@bp.route("/<ann_id>/entries/")
def get_annotation_entries(ann_id):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT EC.ENTRY_AC, E.NAME, E.ENTRY_TYPE
        FROM INTERPRO.ENTRY2COMMON EC
        INNER JOIN INTERPRO.ENTRY E 
          ON EC.ENTRY_AC = E.ENTRY_AC
        WHERE EC.ANN_ID = :1
        ORDER BY EC.ENTRY_AC
        """, [ann_id]
    )

    entries = []
    for row in cur:
        entries.append({
            "accession": row[0],
            "name": row[1],
            "type": row[2]
        })

    cur.close()
    return jsonify(entries)


def get_citations(cur: Cursor, pmids: list[int | str]) -> dict:
    keys = []
    params = []
    for i, pmid in enumerate(map(str, set(pmids))):
        keys.append(f":{i + 1}")
        params.append(pmid)

    cur.execute(
        f"""
        SELECT 
            EXTERNAL_ID, VOLUME, ISSUE, PUBYEAR, TITLE, PAGE_INFO, 
            MEDLINE_ABBREVIATION, ISO_ABBREVIATION, AUTHORS, URL
        FROM (
            SELECT
                C.EXTERNAL_ID, I.VOLUME, I.ISSUE, I.PUBYEAR, C.TITLE,
                C.PAGE_INFO, J.MEDLINE_ABBREVIATION, J.ISO_ABBREVIATION,
                A.AUTHORS, U.URL,
                ROW_NUMBER() OVER (
                    PARTITION BY C.EXTERNAL_ID
                    ORDER BY U.DATE_UPDATED DESC
                ) R
            FROM CDB.CITATIONS@LITPUB C
            LEFT OUTER JOIN CDB.JOURNAL_ISSUES@LITPUB I
                ON C.JOURNAL_ISSUE_ID = I.ID
            LEFT JOIN CDB.CV_JOURNALS@LITPUB J
                ON I.JOURNAL_ID = J.ID
            LEFT OUTER JOIN CDB.FULLTEXT_URL_MEDLINE@LITPUB U
                ON (C.EXTERNAL_ID = U.EXTERNAL_ID AND UPPER(U.SITE) = 'DOI')
            LEFT OUTER JOIN CDB.AUTHORS@LITPUB A
                ON (C.ID = A.CITATION_ID AND A.HAS_SPECIAL_CHARS = 'N')
            WHERE C.EXTERNAL_ID IN ({','.join(keys)})
        ) 
        WHERE R = 1
        """,
        params
    )

    citations = {}
    for row in cur:
        # tuple does not support item assignment
        row = list(row)

        # PMID stored as VARCHAR2 in LITPUB
        row[0] = int(row[0])

        citations[row[0]] = row

    return citations


def insert_citations(cur: Cursor, citations: dict) -> int | None:
    for pmid, row in citations.items():
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
            return pmid
        else:
            # RETURNING -> getvalue() returns an array
            citations[pmid] = pub_id.getvalue()[0]

    return None
