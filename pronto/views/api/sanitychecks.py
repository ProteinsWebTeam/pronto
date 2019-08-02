# -*- coding: utf-8 -*-

import re
import uuid
from urllib.error import URLError
from urllib.request import urlopen

from cx_Oracle import DatabaseError
from flask import json, jsonify, request

from pronto import app, db, executor, get_user

_TERM_TYPES = ("invalid_abbr", "invalid_citation", "invalid_punct",
               "misspelling", "bad_subst", "illegal_word")


def check_abbreviations(text, checks, exceptions, id):
    bad_abbrs = []
    for match in re.findall(r"\d+\s+kDa", text):
        bad_abbrs.append(match)

    valid_cases = ("N-terminal", "C-terminal", "C terminus", "N terminus")
    for match in re.findall(r"\b[cn][\-\s]termin(?:al|us)", text, re.I):
        if match not in valid_cases:
            bad_abbrs.append(match)

    for match in re.findall('|'.join(checks), text):
        if id not in exceptions.get(match, []):
            bad_abbrs.append(match)

    return bad_abbrs


def check_accession(text, exceptions, id):
    terms = ("G3DSA:[\d.]", "IPR\d", "MF_\d", "PF\d", "PIRSF\d", "PR\d",
             "PS\d", "PTHR\d", "SFLD[FGS]\d", "SM\d", "SSF\d", "TIGR\d",
             "cd\d", "sd\d")
    terms = [t + "{4,}" for t in terms]

    errors = []
    for match in re.findall(r"\b(?:" + '|'.join(terms) + r")\b", text):
        if id not in exceptions.get(match, []):
            errors.append(match)

    return errors


def check_basic(text):
    too_short = has_empty_block = False
    if len(text) < 25 or re.search(r'no\s+abs', text, re.I):
        too_short = True

    if re.search(r"<p>\s*</p>", text, re.I):
        has_empty_block = True

    return too_short, has_empty_block


def check_characters(text, exceptions):
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        pass
    else:
        return []

    errors = []
    for c in text:
        try:
            c.encode("ascii")
        except UnicodeEncodeError:
            if str(ord(c)) not in exceptions:
                errors.append(c)

    return errors


def check_citations(text, checks, exceptions, id):
    errors = []
    for match in re.findall('|'.join(map(re.escape, checks)), text, re.I):
        if id not in exceptions.get(match, []):
            errors.append(match)

    for match in re.findall(r"\[(?:PMID:)?\d*\]", text, re.I):
        errors.append(match)

    return errors


def check_gram(text):
    terms = ("gram\s*-(?!negative|positive)", "gram\s*\+", "gram pos",
             "gram neg", "g-positive", "g-negative")
    return re.findall('|'.join(terms), text, re.I)


def check_illegal_terms(text, checks, exceptions, id):
    errors = []
    for term in checks:
        if term in text and id not in exceptions.get(term, []):
            errors.append(term)

    return errors


def check_links(text):
    errors = []
    for url in re.findall(r"https?://[\w\-@:%.+~#=/?&]+", text, re.I):
        try:
            res = urlopen(url)
        except URLError:
            errors.append(url)
        else:
            if res.status != 200:
                errors.append(url)
    return errors


def check_punctuation(text, checks, exceptions, id):
    errors = []
    for term in checks:
        if term in text and id not in exceptions.get(term, []):
            errors.append(term)

    prog = re.compile(r"[a-z]{3}|\d[\]\d]\]|\d\]\)", flags=re.I)
    for match in re.finditer(r"\. \[", text):
        i, j = match.span()

        if text[i-3:i] == "e.g":
            continue  # e.g. [
        elif text[i-2:i] == "sp":
            continue  # sp. [
        elif text[i-5:i] == "et al":
            continue  # et al. [
        elif prog.match(text[i-3:i]):
            """
            [a-z]{3}            ent. [
            \d[\]\d]\]          22]. [
                                3]]. [
            \d\]\)              7]). [
            """
            continue
        else:
            errors.append(match.group(0))

    return errors


def check_spelling(text, checks, exceptions, id):
    errors = []
    for match in re.findall(r"\b(?:" + '|'.join(checks) + r")\b", text, re.I):
        if id not in exceptions.get(match, []):
            errors.append(match)

    return errors


def check_substitutions(text, checks, exceptions, id):
    errors = []
    for term in checks:
        if term in text and id not in exceptions.get(term, []):
            errors.append(term)

    return errors


def check_underscore_to_hyphen(text, checks):
    return re.findall("_(?:" + '|'.join(checks) + r")\b", text)


def check_underscore(text, exceptions, id):
    errors = []
    for match in re.findall(r"\w*_\w*", text):
        if id not in exceptions:
            errors.append(match)
    return errors


def check_gene_symbol(name, short_name, exceptions):
    gene_symbols = set()
    gene = re.search(r"(?:^|_)[a-z]{3}[A-Z]\b", short_name)
    if gene:
        gene = gene.group()
        if gene not in exceptions:
            gene_symbols.add(gene)

    gene = re.search(r"\b[a-z]{3}[A-Z]\b", name)
    if gene:
        gene = gene.group()
        if gene not in exceptions:
            gene_symbols.add(gene)

    return list(gene_symbols)


def group_errors(keys, values):
    _errors = {}
    for key, val in zip(keys, values):
        if not val:
            continue  # no errors for this type
        elif isinstance(val, bool):
            _errors[key] = val
        else:
            items = {}
            for item in val:
                if item in items:
                    items[item]["count"] += 1
                else:
                    items[item] = {
                        "error": item,
                        "count": 1
                    }

            if key in _errors:
                _errors[key] += list(items.values())
            else:
                _errors[key] = list(items.values())

    return _errors


def check_abstracts(cur, checks, exceptions):
    passed = set()
    failed = {}
    keys = ("Too short", "Empty block", "Abbreviation",
            "Character", "Citation", "Spelling",
            "Link", "Punctuation", "Spelling",
            "Substitution")
    cur.execute(
        """
        SELECT CA.ANN_ID, CA.TEXT, EC.ENTRY_AC
        FROM INTERPRO.COMMON_ANNOTATION CA
        INNER JOIN INTERPRO.ENTRY2COMMON EC
          ON CA.ANN_ID = EC.ANN_ID
        """
    )
    for ann_id, text, entry_acc in cur:
        if ann_id in passed or ann_id in failed:
            continue

        too_short, has_empty_block = check_basic(text)

        err = checks.get("invalid_abbr", [])
        exc = exceptions.get("invalid_abbr", {})
        bad_abbrs = check_abbreviations(text, err, exc, ann_id)

        exc = exceptions.get("non_ascii", [])
        bad_characters = check_characters(text, exc)

        err = checks.get("invalid_citation", [])
        exc = exceptions.get("invalid_citation", {})
        bad_citations = check_citations(text, err, exc, ann_id)

        bad_gram = check_gram(text)
        bad_links = check_links(text)

        err = checks.get("invalid_punct", [])
        exc = exceptions.get("invalid_punct", {})
        bad_punctuations = check_punctuation(text, err, exc, ann_id)

        err = checks.get("misspelling", [])
        exc = exceptions.get("misspelling", {})
        typos = check_spelling(text, err, exc, ann_id)

        err = checks.get("bad_subst", [])
        exc = exceptions.get("bad_subst", {})
        bad_substitutions = check_substitutions(text, err, exc, ann_id)

        values = [too_short, has_empty_block, bad_abbrs,
                  bad_characters, bad_citations, bad_gram,
                  bad_links, bad_punctuations, typos,
                  bad_substitutions]

        if any(values):
            failed[ann_id] = {
                "ann_id": ann_id,
                "entry_ac": entry_acc,
                "errors": group_errors(keys, values)
            }
        else:
            passed.add(ann_id)

    return list(failed.values())


def check_entries(cur, checks, exceptions):
    cur.execute("SELECT DISTINCT ENTRY_AC FROM INTERPRO.ENTRY2METHOD")
    entries_w_signatures = {row[0] for row in cur}
    cur.execute(
        """
        SELECT ENTRY_AC, NAME, SHORT_NAME, CHECKED
        FROM INTERPRO.ENTRY
        """
    )
    entries = {row[0]: row[1:] for row in cur}

    cur.execute(
        """
        SELECT A.ENTRY_AC, B.ENTRY_AC
        FROM INTERPRO.ENTRY A
        INNER JOIN INTERPRO.ENTRY B
          ON (
            A.ENTRY_AC < B.ENTRY_AC
            AND (LOWER(A.NAME) = LOWER(B.SHORT_NAME))
          )
        """
    )
    name_clashes = {}
    for acc1, acc2 in cur:
        if acc1 in name_clashes:
            name_clashes[acc1].append(acc2)
        else:
            name_clashes[acc1] = [acc2]

    exc = exceptions.get("similar_name", {})
    cur.execute(
        """
        SELECT A.ENTRY_AC, B.ENTRY_AC
        FROM INTERPRO.ENTRY A
        INNER JOIN INTERPRO.ENTRY B
          ON (
            A.ENTRY_AC < B.ENTRY_AC
            AND (REGEXP_REPLACE(A.NAME, '[^a-zA-Z0-9]+', '')
              = REGEXP_REPLACE(B.NAME, '[^a-zA-Z0-9]+', ''))
          )
        """
    )
    diff_names = {}
    for acc1, acc2 in cur:
        if acc2 in exc.get(acc1, []):
            continue
        elif acc1 in diff_names:
            diff_names[acc1].append(acc2)
        else:
            diff_names[acc1] = [acc2]

    cur.execute(
        """
        SELECT A.ENTRY_AC, B.ENTRY_AC
        FROM INTERPRO.ENTRY A
        INNER JOIN INTERPRO.ENTRY B
          ON (
            A.ENTRY_AC < B.ENTRY_AC
            AND (REGEXP_REPLACE(A.SHORT_NAME, '[^a-zA-Z0-9]+', '')
              = REGEXP_REPLACE(B.SHORT_NAME, '[^a-zA-Z0-9]+', ''))
          )
        """
    )
    diff_short_names = {}
    for acc1, acc2 in cur:
        if acc2 in exc.get(acc1, []):
            continue
        elif acc1 in diff_short_names:
            diff_short_names[acc1].append(acc2)
        else:
            diff_short_names[acc1] = [acc2]

    # Detect if a parent entry is checked and not a child (or reverse)
    cur.execute(
        """
        SELECT EE.PARENT_AC, E2.CHECKED, EE.ENTRY_AC, E1.CHECKED
        FROM INTERPRO.ENTRY2ENTRY EE
        INNER JOIN INTERPRO.ENTRY E1 ON EE.ENTRY_AC = E1.ENTRY_AC
        INNER JOIN INTERPRO.ENTRY E2 ON EE.PARENT_AC = E2.ENTRY_AC
        WHERE (E1.CHECKED = 'Y' AND E2.CHECKED = 'N') 
          OR (E2.CHECKED = 'Y' AND E1.CHECKED = 'N')
        """
    )
    parent_unchecked = {}
    children_unchecked = {}
    for parent_acc, parent_checked, child_acc, child_checked in cur:
        if parent_checked == 'Y':
            if parent_acc in children_unchecked:
                children_unchecked[parent_acc].append(child_acc)
            else:
                children_unchecked[parent_acc] = [child_acc]
        else:
            if child_acc in parent_unchecked:
                parent_unchecked[child_acc].append(parent_acc)
            else:
                parent_unchecked[child_acc] = [parent_acc]

    """
    Detect in an homologous superfamily entry contains signatures 
    that are not from CATH-Gene3D/SUPERFAMILY
    """
    cur.execute(
        """
        SELECT E.ENTRY_AC, M.METHOD_AC
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2METHOD EM 
          ON (E.ENTRY_AC = EM.ENTRY_AC AND E.ENTRY_TYPE = 'H')
        INNER JOIN INTERPRO.METHOD M 
          ON (EM.METHOD_AC = M.METHOD_AC AND M.DBCODE NOT IN ('X', 'Y'))
        """
    )
    invalid_signatures = {}
    for entry_acc, signature_acc in cur:
        if entry_acc in invalid_signatures:
            invalid_signatures[entry_acc].append(signature_acc)
        else:
            invalid_signatures[entry_acc] = [signature_acc]

    lc_prog = re.compile("[a-z]")
    lc_excs = tuple(exceptions.get("lowercase_name", []))

    gene_excs = tuple(exceptions.get("gene_symbol", []))

    keys = ("No signature", "Accession (name)", "Spelling (name)",
            "Spelling (short name)", "Illegal term (name)",
            "Abbreviation (name)", "Abbreviation (short name)",
            "Underscore (short name)", "Underscore (name)",
            "Name/short name clash", "Name clash",
            "Short name clash", "Lower case", "Gene symbol", "Double quotes",
            "Unchecked parent", "Unchecked child", "Invalid signature")
    failed = []
    for acc, (name, short_name, checked) in entries.items():
        no_signatures = checked == 'Y' and acc not in entries_w_signatures

        exc = exceptions.get("acc_in_name", {})
        accessions_in_name = check_accession(name, exc, acc)

        err = checks.get("misspelling", [])
        exc = exceptions.get("misspelling", {})
        typos1 = check_spelling(name, err, exc, acc)
        typos2 = check_spelling(short_name, err, exc, acc)

        err = checks.get("illegal_word", [])
        exc = exceptions.get("illegal_word", {})
        illegal_terms = check_illegal_terms(name, err, exc, acc)

        err = checks.get("invalid_abbr", [])
        exc = exceptions.get("invalid_abbr", {})
        bad_abbrs1 = check_abbreviations(name, err, exc, acc)
        bad_abbrs2 = check_abbreviations(short_name, err, exc, acc)

        missing_hyphens = check_underscore_to_hyphen(short_name,
                                                     ("binding", "bd",
                                                      "related", "rel",
                                                      "like"))

        exc = exceptions.get("underscore_in_name", [])
        underscores = check_underscore(name, exc, acc)

        # Normally names cannot start with a lower case character
        starts_w_lc = False
        for text in (short_name, name):
            if lc_prog.match(text) and not text.startswith(lc_excs):
                starts_w_lc = True

        # Gene symbol (nnnN) instead of protein (NnnN)
        genes = check_gene_symbol(name, short_name, gene_excs)

        # Double quote in name
        dq = '"' in name

        values = [no_signatures, accessions_in_name,
                  typos1, typos2, illegal_terms,
                  bad_abbrs1, bad_abbrs2,
                  missing_hyphens, underscores,
                  name_clashes.get(acc), diff_names.get(acc),
                  diff_short_names.get(acc), starts_w_lc, genes, dq,
                  parent_unchecked.get(acc, []),
                  children_unchecked.get(acc, []),
                  invalid_signatures.get(acc, [])]

        if any(values):
            failed.append({
                "ann_id": None,
                "entry_ac": acc,
                "errors": group_errors(keys, values)
            })

    return failed


def load_sanity_checks(cur):
    cur.execute(
        """
        SELECT 
          C.CHECK_TYPE, C.TERM, E.TERM, E.ANN_ID, E.ENTRY_AC, E.ENTRY_AC2
        FROM INTERPRO.SANITY_CHECK C
        LEFT OUTER JOIN INTERPRO.SANITY_EXCEPTION E
          ON C.CHECK_TYPE = E.CHECK_TYPE
        """
    )
    checks = {}
    abstr_excpts = {}
    entry_excpts = {}
    for row in cur:
        err_type = row[0]
        err_str = row[1]
        exc_str = row[2]
        exc_ann_id = row[3]
        exc_entry_ac = row[4]
        exc_entry_ac2 = row[5]

        if err_type in checks:
            check = checks[err_type]
        else:
            check = checks[err_type] = set()
            abstr_excpts[err_type] = {}
            entry_excpts[err_type] = {}

        if err_str:
            check.add(err_str)

        if exc_ann_id:
            excpts = abstr_excpts
            exc_id = exc_ann_id
        elif exc_entry_ac:
            excpts = entry_excpts
            exc_id = exc_entry_ac
        else:
            exc_id = None
            excpts = None

        if exc_str and exc_id:
            if exc_str in excpts:
                excpts[exc_str].add(exc_id)
            else:
                excpts[exc_str] = {exc_id}
        elif exc_str:
            abstr_excpts[err_type][exc_str] = None
            entry_excpts[err_type][exc_str] = None
        elif exc_id:
            if exc_id in excpts:
                excpts[exc_id].add(exc_entry_ac2)
            else:
                excpts[exc_id] = {exc_entry_ac}

    return checks, abstr_excpts, entry_excpts


def check_all(user, dsn):
    con = db.connect_oracle(user, dsn)
    cur = con.cursor()
    checks, abstract_exceptions, entry_exceptions = load_sanity_checks(cur)
    abstracts = check_abstracts(cur, checks, abstract_exceptions)
    entries = check_entries(cur, checks, entry_exceptions)

    # Delete old runs (keeping the nine most recent)
    cur.execute(
        """
        DELETE FROM INTERPRO.SANITY_RUN
        WHERE ID NOT IN (
          SELECT ID
          FROM (
              SELECT ID
              FROM INTERPRO.SANITY_RUN
              ORDER BY TIMESTAMP DESC
          )
          WHERE ROWNUM <= 9
        )
        """
    )

    # Add new run
    run_id = uuid.uuid1().hex
    cur.execute(
        """
        INSERT INTO INTERPRO.SANITY_RUN (ID, NUM_ERRORS) VALUES (:1, :2)
        """, (run_id, sum(map(len, (abstracts, entries))))
    )

    errors = []
    for i, obj in enumerate(abstracts + entries):
        errors.append((
            run_id,
            i,
            obj["ann_id"],
            obj["entry_ac"],
            json.dumps(obj["errors"])
        ))

    cur.executemany(
        """
        INSERT INTO INTERPRO.SANITY_ERROR 
        (RUN_ID, ID, ANN_ID, ENTRY_AC, ERRORS) 
        VALUES (:1, :2, :3, :4, :5)
        """, errors
    )

    con.commit()
    cur.close()
    con.close()


@app.route("/api/sanitychecks/runs/")
def get_sanitychecks():
    num_rows = int(request.args.get("limit", 10))
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT *
        FROM (
            SELECT SR.ID, SR.NUM_ERRORS, SR.TIMESTAMP, NVL(UP.NAME, SR.USERNAME)
            FROM INTERPRO.SANITY_RUN SR
              LEFT OUTER JOIN INTERPRO.USER_PRONTO UP
              ON SR.USERNAME = UP.DB_USER
            ORDER BY SR.TIMESTAMP DESC
        )
        WHERE ROWNUM <= :1
        """, (num_rows,)
    )
    reports = []
    for row in cur:
        reports.append({
            "id": row[0],
            "errors": row[1],
            "date": row[2].strftime("%d %b %Y, %H:%M"),
            "user": row[3]
        })

    return jsonify(reports)


@app.route("/api/sanitychecks/runs/", methods=["PUT"])
def submit_sanitychecks():
    user = get_user()
    if user:
        dsn = app.config["ORACLE_DB"]["dsn"]
        if executor.enqueue("Sanity checks", check_all, user, dsn):
            return jsonify({"status": True}), 202
        else:
            return jsonify({"status": False}), 409
    else:
        return jsonify({"status": False}), 401


@app.route("/api/sanitychecks/runs/<run_id>/")
def get_sanitychecks_report(run_id):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT NUM_ERRORS, TIMESTAMP
        FROM INTERPRO.SANITY_RUN
        WHERE ID = :1
        """, (run_id,)
    )
    row = cur.fetchone()
    if row:
        run = {
            "num_errors": row[0],
            "num_resolved": 0,
            "date": row[1].strftime("%d %b %Y, %H:%M"),
            "errors": []
        }

        cur.execute(
            """
            SELECT SE.ID, SE.ANN_ID, SE.ENTRY_AC, SE.ERRORS, 
              SE.TIMESTAMP, NVL(UP.NAME, SE.USERNAME)
            FROM INTERPRO.SANITY_ERROR SE
            LEFT OUTER JOIN INTERPRO.USER_PRONTO UP
              ON SE.USERNAME = UP.DB_USER
            WHERE RUN_ID=:1
            ORDER BY ANN_ID, ENTRY_AC
            """, (run_id,)
        )

        for row in cur:
            if row[4]:
                run["num_resolved"] += 1
                resolved_on = row[4].strftime("%d %b %Y, %H:%M")
            else:
                resolved_on = None

            run["errors"].append({
                "id": row[0],
                "ann_id": row[1],
                "entry_ac": row[2],
                "errors": json.loads(row[3].read()),
                "resolved_on": resolved_on,
                "resolved_by": row[5]
            })

    else:
        run = {}

    cur.close()

    return jsonify(run), 200 if run else 404


@app.route("/api/sanitychecks/runs/<run_id>/<int:err_id>/", methods=["POST"])
def resolve_error(run_id, err_id):
    user = get_user()
    if not user:
        return '', 401

    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        UPDATE INTERPRO.SANITY_ERROR
        SET TIMESTAMP  = SYSDATE, USERNAME = USER
        WHERE RUN_ID = :1 AND ID = :2
        """, (run_id, err_id)
    )
    n = cur.rowcount
    cur.close()
    con.commit()
    return '', 200 if n else 404


@app.route("/api/sanitychecks/checks/")
def get_type_checks():
    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT SC.CHECK_TYPE, SC.TERM, SC.TIMESTAMP, SE.ID, SE.TERM, SE.ANN_ID, SE.ENTRY_AC, SE.ENTRY_AC2
        FROM INTERPRO.SANITY_CHECK SC
        LEFT OUTER JOIN INTERPRO.SANITY_EXCEPTION SE
          ON SC.CHECK_TYPE = SE.CHECK_TYPE 
            AND (
              (SC.TERM = SE.TERM) OR 
              (SC.TERM IS NULL AND SE.TERM IS NOT NULL) OR 
              (SC.TERM IS NULL AND SE.TERM IS NULL )
            )
        ORDER BY SE.ANN_ID, SE.ENTRY_AC, SE.ENTRY_AC2, SE.TERM
        """
    )
    checks = {}
    for row in cur:
        err_type = row[0]
        if err_type in checks:
            err_checks = checks[err_type]
        else:
            err_checks = checks[err_type] = {}

        err_str = row[1]
        err_date = row[2].strftime("%d %b %Y")
        if err_str in err_checks:
            err = err_checks[err_str]
        else:
            err = err_checks[err_str] = {
                "string": err_str,
                "date": err_date,
                "exceptions": []
            }

        exc_id = row[3]
        if err_type == "non_ascii":
            exc_str = chr(int(row[4]))
        else:
            exc_str = row[4]

        exc_ann_id = row[5]
        exc_entry_ac = row[6]
        exc_entry_ac2 = row[7]
        if exc_str or exc_ann_id or exc_entry_ac or exc_entry_ac2:
            err["exceptions"].append({
                "id": exc_id,
                "string": exc_str,
                "ann_id": exc_ann_id,
                "entry_acc": exc_entry_ac,
                "entry_acc2": exc_entry_ac2
            })
    cur.close()
    con.commit()

    for err_type, err_checks in checks.items():
        checks[err_type] = sorted(err_checks.values(), key=lambda i: i["string"])

    return jsonify(checks), 200


@app.route("/api/sanitychecks/term/<check_type>/", methods=["PUT"])
def add_check_term(check_type):
    try:
        term = request.args["term"]
        assert len(term) > 0
    except (AssertionError, KeyError):
        return jsonify({
            "status": False,
            "title": "Missing parameter",
            "message": "Invalid or missing parameters."
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
    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.SANITY_CHECK (CHECK_TYPE, TERM)
            VALUES (:1, :2)
            """, (check_type, term)
        )
    except DatabaseError as exc:
        return jsonify({
            "error": {
                "status": False,
                "title": "Database error",
                "message": "Could not add exception ({}).".format(exc)
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route("/api/sanitychecks/term/<check_type>/", methods=["DELETE"])
def delete_check_term(check_type):
    term = request.args.get("str", "")
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
            DELETE FROM INTERPRO.SANITY_CHECK
            WHERE CHECK_TYPE = :1 AND TERM = :2
            """, (check_type, term)
        )
        deleted = cur.rowcount > 0

        cur.execute(
            """
            DELETE FROM INTERPRO.SANITY_EXCEPTION
            WHERE CHECK_TYPE = :1 AND TERM = :2
            """, (check_type, term)
        )
    except DatabaseError as exc:
        return jsonify({
            "error": {
                "status": False,
                "title": "Database error",
                "message": "Could not add exception ({}).".format(exc)
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True,
            "deleted": deleted
        }), 200
    finally:
        cur.close()


@app.route("/api/sanitychecks/exception/<check_type>/", methods=["PUT"])
def add_exception(check_type):
    try:
        value1 = request.json["value1"]
        value2 = request.json["value2"]
        term = request.json["term"]
    except KeyError:
        return jsonify({
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }), 401

    if check_type in _TERM_TYPES:
        # Exception for specific checked term
        if not term or not value1:
            return jsonify({
                "error": {
                    "title": "Bad request",
                    "message": "Invalid or missing parameters."
                }
            }), 400
        elif re.match("IPR\d+$", value1):
            params = (check_type, term, None, value1, None)
        elif re.match("AB\d+$", value1):
            params = (check_type, term, value1, None, None)
        else:
            return jsonify({
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid InterPro entry "
                               "or abstract ID.".format(value1)
                }
            }), 400
    elif check_type == "acc_in_name":
        if re.match("IPR\d+$", value1):
            params = (check_type, None, None, value1, value2)
        else:
            return jsonify({
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid InterPro entry.".format(value1)
                }
            }), 400
    elif check_type == "similar_name":
        if not re.match("IPR\d+$", value1):
            return jsonify({
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid InterPro entry.".format(value1)
                }
            }), 400
        elif not re.match("IPR\d+$", value2):
            return jsonify({
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid InterPro entry.".format(value2)
                }
            }), 400
        elif value1 < value2:
            params = (check_type, None, None, value1, value2)
        else:
            params = (check_type, None, None, value2, value1)
    elif check_type == "non_ascii":
        try:
            integer = ord(value1)
        except TypeError:
            return jsonify({
                "error": {
                    "title": "Bad request",
                    "message": "Expected a character, but string of length {} found.".format(len(value1))
                }
            }), 400

        try:
            value1.encode("ascii")
        except UnicodeEncodeError:
            pass
        else:
            return jsonify({
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is a ASCII character. Please enter non-ASCII characters only.".format(value1)
                }
            }), 400

        params = (check_type, value1, None, None, None)
    elif check_type == "underscore_in_name":
        if re.match("IPR\d+$", value1):
            params = (check_type, None, None, value1, None)
        else:
            return jsonify({
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid InterPro entry.".format(value1)
                }
            }), 400
    elif len(value1):
        params = (check_type, value1, None, None, None)
    else:
        return jsonify({
            "error": {
                "title": "Bad request",
                "message": "Please enter at least one character."
            }
        }), 400

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.SANITY_EXCEPTION (ID, CHECK_TYPE, TERM, ANN_ID, ENTRY_AC, ENTRY_AC2)
            VALUES ((SELECT NVL(MAX(ID), 0)+1 from INTERPRO.SANITY_EXCEPTION), :1, :2, :3, :4, :5)
            """, params
        )
    except DatabaseError as exc:
        return jsonify({
            "error": {
                "status": False,
                "title": "Database error",
                "message": "Could not add exception ({}).".format(exc)
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route("/api/sanitychecks/exception/<int:exc_id>/", methods=["DELETE"])
def delete_exception(exc_id):
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
            DELETE FROM INTERPRO.SANITY_EXCEPTION
            WHERE ID = :1 
            """, (exc_id,)
        )
    except DatabaseError as exc:
        return jsonify({
            "error": {
                "status": False,
                "title": "Database error",
                "message": "Could not add exception ({}).".format(exc)
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True,
            "deleted": cur.rowcount > 0
        }), 200
    finally:
        cur.close()
