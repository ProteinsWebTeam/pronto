# -*- coding: utf-8 -*-

import re
import uuid
from urllib.error import URLError
from urllib.request import urlopen

from cx_Oracle import DatabaseError
from flask import json, jsonify, request

from pronto import app, db, executor, get_user

_ERR_TYPES = {
    # key: (label, accepts exceptions, use specific terms)
    "abbr": ("Abbreviation", True, True),
    "acc_in_name": ("Accession", True, False),
    "ascii": ("Character", True, False),
    "citation": ("Citation", True, True),
    "double_quotes": ("Double quotes", False, False),
    "empty_block": ("Empty block", False, False),
    "gene_symbol": ("Gene symbol", True, False),
    "illegal_term": ("Illegal term", True, True),
    "invalid_signature": ("Invalid signature", False, False),
    "link": ("Link", False, False),
    "lower_case": ("Lower case", False, False),
    "same_names": ("Name clash", False, False),
    "similar_names": ("Similar names", True, False),
    "no_signatures": ("No signatures", False, False),
    "punctuation": ("Punctuation", True, True),
    "spelling": ("Spelling", True, True),
    "substitution": ("Substitution", True, True),
    "too_short": ("Too short", False, False),
    "unchecked_child": ("Unchecked child", False, False),
    "unchecked_parent": ("Unchecked parent", False, False),
    "underscore": ("Underscore", True, False),
}


def check_abbreviations(text, checks, exceptions, id):
    bad_abbrs = []
    for match in re.findall(r"\d+\s+kDa", text):
        bad_abbrs.append(match)

    valid_cases = ("N-terminal", "C-terminal", "C terminus", "N terminus")
    for match in re.findall(r"\b[cn][\-\s]termin(?:al|us)", text, re.I):
        if match not in valid_cases:
            bad_abbrs.append(match)

    if checks:
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
    if checks:
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
    if checks:
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
    if checks:
        return re.findall("_(?:" + '|'.join(checks) + r")\b", text)
    else:
        return []


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


def wrap_errors(errors):
    _errors = {}
    for key, val in errors.items():
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

        is_too_short, has_empty_block = check_basic(text)
        errors = {
            "abbr": check_abbreviations(
                text,
                checks=checks.get("abbr", []),
                exceptions=exceptions.get("abbr", {}),
                id=ann_id),
            "too_short": is_too_short,
            "empty_block": has_empty_block,
            "ascii": check_characters(
                text,
                exceptions=exceptions.get("ascii", [])),
            "citation": check_citations(
                text,
                checks=checks.get("citation", []),
                exceptions=exceptions.get("citation", {}),
                id=ann_id),
            "spelling": check_spelling(
                text,
                checks=checks.get("spelling", []),
                exceptions=exceptions.get("spelling", {}),
                id=ann_id) + check_gram(text),
            "link": check_links(text),
            "punctuation": check_punctuation(
                text,
                checks=checks.get("punctuation", []),
                exceptions=exceptions.get("punctuation", {}),
                id=ann_id),
            "substitution": check_substitutions(
                text,
                checks=checks.get("substitution", []),
                exceptions=exceptions.get("substitution", {}),
                id=ann_id
            )
        }

        if any(errors.values()):
            failed[ann_id] = {
                "ann_id": ann_id,
                "entry_ac": entry_acc,
                "errors": wrap_errors(errors)
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
    same_names = {}
    for acc1, acc2 in cur:
        if acc1 in same_names:
            same_names[acc1].append(acc2)
        else:
            same_names[acc1] = [acc2]

    exc = exceptions.get("similar_name", {})
    cur.execute(
        """
        SELECT A.ENTRY_AC, B.ENTRY_AC
        FROM INTERPRO.ENTRY A
        INNER JOIN INTERPRO.ENTRY B
          ON (
            A.ENTRY_AC < B.ENTRY_AC
            AND (
              REGEXP_REPLACE(A.NAME, '[^a-zA-Z0-9]+', '') = 
                REGEXP_REPLACE(B.NAME, '[^a-zA-Z0-9]+', '')
              OR REGEXP_REPLACE(A.SHORT_NAME, '[^a-zA-Z0-9]+', '') = 
                REGEXP_REPLACE(B.SHORT_NAME, '[^a-zA-Z0-9]+', '')
            )
          )
        """
    )
    similar_names = {}
    for acc1, acc2 in cur:
        if acc2 in exc.get(acc1, []):
            continue
        elif acc1 in similar_names:
            similar_names[acc1].append(acc2)
        else:
            similar_names[acc1] = [acc2]

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
    lower_case_excs = tuple(exceptions.get("lower_case", []))

    failed = []
    for acc, (name, short_name, checked) in entries.items():
        errors = {
            "no_signatures": (checked == 'Y'
                              and acc not in entries_w_signatures),
            "acc_in_name": check_accession(
                name,
                exceptions=exceptions.get("acc_in_name", {}),
                id=acc
            ),
            "spelling": check_spelling(
                name,
                checks=checks.get("spelling", []),
                exceptions=exceptions.get("spelling", {}),
                id=acc
            ) + check_spelling(
                short_name,
                checks=checks.get("spelling", []),
                exceptions=exceptions.get("spelling", {}),
                id=acc
            ),
            "illegal_term": check_illegal_terms(
                name, checks=checks.get("illegal_term", []),
                exceptions=exceptions.get("illegal_term", {}),
                id=acc
            ),
            "abbr": check_abbreviations(
                name,
                checks=checks.get("abbr", []),
                exceptions=exceptions.get("abbr", {}),
                id=acc
            ) + check_abbreviations(
                short_name,
                checks=checks.get("abbr", []),
                exceptions=exceptions.get("abbr", {}),
                id=acc
            ),
            "underscore": check_underscore_to_hyphen(
                short_name,
                ("binding", "bd", "related", "rel", "like")
            ) + check_underscore(
                name,
                exceptions=exceptions.get("underscore", []),
                id=acc
            ),
            "same_names": same_names.get(acc),
            "similar_names": similar_names.get(acc),
            "lower_case": (
                    (lc_prog.match(name) and not name.startswith(lower_case_excs))
                    or
                    (lc_prog.match(short_name) and not short_name.startswith(lower_case_excs))
            ),
            "gene_symbol": check_gene_symbol(
                name, short_name,
                exceptions=exceptions.get("gene_symbol", [])
            ),
            "double_quotes": '"' in name,
            "unchecked_child": children_unchecked.get(acc),
            "unchecked_parent": parent_unchecked.get(acc),
            "invalid_signature": invalid_signatures.get(acc)
        }

        if any(errors.values()):
            failed.append({
                "ann_id": None,
                "entry_ac": acc,
                "errors": wrap_errors(errors)
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
            excpts = abstr_excpts[err_type]
            exc_id = exc_ann_id
        elif exc_entry_ac:
            excpts = entry_excpts[err_type]
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

            _errors = {}
            for err_type, err_object in json.loads(row[3].read()).items():
                label, accept_excs, user_terms = _ERR_TYPES[err_type]
                _errors[label] = {
                    "accept_exceptions": accept_excs,
                    "errors": err_object
                }

            run["errors"].append({
                "id": row[0],
                "ann_id": row[1],
                "entry_ac": row[2],
                "errors": _errors,
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

    add_exc = request.args.get("exception") is not None

    con = db.get_oracle()
    cur = con.cursor()
    if add_exc:
        cur.execute(
            """
            SELECT ANN_ID, ENTRY_AC, ERRORS
            FROM INTERPRO.SANITY_ERROR
            WHERE RUN_ID = :1 AND ID = :2
            """, (run_id, err_id)
        )
        row = cur.fetchone()

        if not row:
            # Nothing to do here
            cur.close()
            return '', 404

        ann_id = row[0]
        entry_acc = row[1]
        err_types = json.loads(row[2].read())
        if len(err_types) > 1:
            # We don't want to add exceptions for multiple errors
            cur.close()
            return '', 400

        err_type, errors = err_types.popitem()
        label, accept_exceptions, term_based = _ERR_TYPES[err_type]
        if not accept_exceptions:
            # Exceptions not allowed for this type
            cur.close()
            return '', 403
        elif not isinstance(errors, bool) and len(errors) > 1:
            # We don't want to add exceptions for multiple errors (bis)
            cur.close()
            return '', 400

        # Error to add to exception
        err_string = errors[0]["error"]
        err_extra = None
        if err_type == "ascii":
            """
            For encoding errors, the character to allow is the fourth argument,
            so we overwrite the entry accession/abstract ID which we don't need
            """
            ann_id = entry_acc = err_string
        elif err_type == "similar_names":
            """
            For similar names, the error string is the accession of the second entry,
            which should be passed as fifth argument. 
            """
            err_extra = err_string

        res, code = add_exception(err_type, term_based, err_string,
                                  ann_id or entry_acc, err_extra)
        if code != 200:
            cur.close()
            return '', code

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
    err_types = {}
    for err_type, (label, accept_exceptions, use_term) in _ERR_TYPES.items():
        err_types[err_type] = {
            "use_term": use_term,
            "strings": {}
        }

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
    for row in cur:
        err_type = row[0]
        err_checks = err_types[err_type]["strings"]

        ck_string = row[1]
        if ck_string in err_checks:
            ck = err_checks[ck_string]
        else:
            ck = err_checks[ck_string] = {
                "string": ck_string,
                "date": row[2].strftime("%d %b %Y"),
                "exceptions": []
            }

        exc_id = row[3]
        if exc_id is None:
            continue

        exc_string = chr(int(row[4])) if err_type == "ascii" else row[4]
        exc_ann_id = row[5]
        exc_entry_ac = row[6]
        exc_entry_ac2 = row[7]
        if exc_string or exc_ann_id or exc_entry_ac or exc_entry_ac2:
            ck["exceptions"].append({
                "id": exc_id,
                "string": exc_string,
                "ann_id": exc_ann_id,
                "entry_acc": exc_entry_ac,
                "entry_acc2": exc_entry_ac2
            })
    cur.close()
    con.commit()

    for err_type, err in err_types.items():
        err["strings"] = sorted(err["strings"].values(),
                                key=lambda i: i["string"])

    return jsonify(err_types), 200


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


def add_exception(check_type, term_based, exc_term, exc_string, exc_extra):
    user = get_user()
    if not user:
        return {
            "status": False,
            "title": "Access denied",
            "message": 'Please <a href="/login/">log in</a> '
                       'to perform this operation.'
        }, 401

    if term_based:
        # Exception for specific checked term found in abstract/entry
        if not exc_term or not exc_string:
            return {
                "error": {
                    "title": "Bad request",
                    "message": "Invalid or missing parameters."
                }
            }, 400
        elif re.match("AB\d+$", exc_string):
            params = (check_type, exc_term, exc_string, None, None)
        elif re.match("IPR\d+$", exc_string):
            params = (check_type, exc_term, None, exc_string, None)
        else:
            return {
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid InterPro entry "
                               "or abstract ID.".format(exc_string)
                }
            }, 400
    elif check_type == "acc_in_name":
        # Requires a valid entry accession
        if re.match("IPR\d+$", exc_string):
            """
            `exc_extra` becomes the excused term, 
            as it can be a signature accession
            """
            params = (check_type, exc_extra, None, exc_string, None)
        else:
            return {
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid "
                               "InterPro entry.".format(exc_string)
                }
            }, 400
    elif check_type == "similar_names":
        # Requires two valid entry accessions
        if not re.match("IPR\d+$", exc_string):
            return {
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid "
                               "InterPro entry.".format(exc_string)
                }
            }, 400
        elif not re.match("IPR\d+$", exc_extra):
            return {
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid "
                               "InterPro entry.".format(exc_extra)
                }
            }, 400
        elif exc_string > exc_extra:
            exc_string, exc_extra = exc_extra, exc_string
        params = (check_type, None, None, exc_string, exc_extra)
    elif check_type == "ascii":
        """
        Requires a non-ascii character
        `exc_string` is NOT an InterPro entry or abstract ID, 
        but the non-ASCII character to allow
        """
        try:
            integer = ord(exc_string)
        except TypeError:
            return {
                "error": {
                    "title": "Bad request",
                    "message": "Expected a character, but string "
                               "of length {} found.".format(len(exc_string))
                }
            }, 400

        try:
            exc_string.encode("ascii")
        except UnicodeEncodeError:
            pass
        else:
            return {
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is a ASCII character. Please enter "
                               "non-ASCII characters only.".format(exc_string)
                }
            }, 400

        params = (check_type, str(integer), None, None, None)
    elif check_type == "underscore":
        # Requires a valid entry accession
        if re.match("IPR\d+$", exc_string):
            params = (check_type, None, None, exc_string, None)
        else:
            return {
                "error": {
                    "title": "Bad request",
                    "message": "'{}' is not a valid "
                               "InterPro entry.".format(exc_string)
                }
            }, 400
    elif len(exc_string):
        params = (check_type, exc_string, None, None, None)
    else:
        return {
            "error": {
                "title": "Bad request",
                "message": "Please enter at least one character."
            }
        }, 400

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
        return {
            "error": {
                "status": False,
                "title": "Database error",
                "message": "Could not add exception ({}).".format(exc)
            }
        }, 500
    else:
        con.commit()
        return {
            "status": True
        }, 200
    finally:
        cur.close()


@app.route("/api/sanitychecks/exception/<check_type>/", methods=["PUT"])
def api_add_exception(check_type):
    try:
        exc_term = request.json["term"]
        exc_string = request.json["string"]
        exc_extra = request.json["extra"]
        label, accept_exceptions, term_based = _ERR_TYPES[check_type]
    except KeyError:
        return jsonify({
            "error": {
                "title": "Bad request",
                "message": "Invalid or missing parameters."
            }
        }), 400

    obj, code = add_exception(check_type, term_based, exc_term, exc_string, exc_extra)
    return jsonify(obj), code


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
