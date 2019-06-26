# -*- coding: utf-8 -*-

import re
import uuid
from urllib.error import URLError
from urllib.request import urlopen

from flask import json, jsonify, request

from pronto import app, db, executor, get_user, xref
from pronto.db import get_oracle


@app.route("/api/interpro/databases/")
def get_databases():
    """
    Retrieves the number of signatures (all, integrated into InterPro, and unintegrated) for each member database.
    """

    # Previous SUM statements were:
    ## SUM(CASE WHEN E2M.ENTRY_AC IS NOT NULL  AND FS.FEATURE_ID IS NOT NULL THEN 1 ELSE 0 END),
    ## SUM(CASE WHEN M.CANDIDATE != 'N' AND E2M.ENTRY_AC IS NULL AND FS.FEATURE_ID IS NOT NULL THEN 1 ELSE 0 END)

    # Removed the join with FEATURE_SUMMARY:
    ## LEFT OUTER JOIN {}.FEATURE_SUMMARY FS ON M.METHOD_AC = FS.FEATURE_ID
    # that can be used to get the number of methods without matches:
    ## sum(case when m.method_ac is not null and feature_id is null then 1 else 0 end) nomatch,
    cur = get_oracle().cursor()
    cur.execute(
        """
        SELECT
          M.DBCODE,
          MIN(DB.DBNAME),
          MIN(DB.DBSHORT),
          MIN(DB.VERSION),
          MIN(DB.FILE_DATE),
          COUNT(M.METHOD_AC),
          SUM(CASE WHEN E2M.ENTRY_AC IS NOT NULL THEN 1 ELSE 0 END),
          SUM(CASE WHEN E2M.ENTRY_AC IS NULL THEN 1 ELSE 0 END)
        FROM {0}.METHOD M
        LEFT OUTER JOIN {0}.CV_DATABASE DB
          ON M.DBCODE = DB.DBCODE
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M
          ON M.METHOD_AC = E2M.METHOD_AC
        GROUP BY M.DBCODE
        """.format(app.config["DB_SCHEMA"])
    )

    databases = []
    for row in cur:
        databases.append({
            "code": row[0],
            "name": row[1],
            "short_name": row[2].lower(),
            "version": row[3],
            "date": row[4].strftime("%b %Y"),
            "home": xref.find_ref(row[0]).home,
            "count_signatures": row[5],
            "count_integrated": row[6],
            "count_unintegrated": row[7],
        })

    cur.close()

    return jsonify(sorted(databases, key=lambda x: x["name"].lower()))


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


def check_characters(text, exceptions, id):
    errors = []
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        pass
    else:
        return errors

    for c in text:
        try:
            c.encode("ascii")
        except UnicodeEncodeError:
            if id not in exceptions.get(ascii(c), []):
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


def check_name_crash(cur, acc, name, short_name):
    cur.execute(
        """
        SELECT ENTRY_AC
        FROM INTERPRO.ENTRY
        WHERE ENTRY_AC != :1
        AND (LOWER(NAME)=LOWER(:2) OR LOWER(SHORT_NAME)=:3)
        """, (acc, name, short_name)
    )
    return [row[0] for row in cur]


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

        err = checks.get("abbreviation", [])
        exc = exceptions.get("abbreviation", {})
        bad_abbrs = check_abbreviations(text, err, exc, ann_id)

        exc = exceptions.get("ascii", {})
        bad_characters = check_characters(text, exc, ann_id)

        err = checks.get("citation", [])
        exc = exceptions.get("citation", {})
        bad_citations = check_citations(text, err, exc, ann_id)

        bad_gram = check_gram(text)
        bad_links = check_links(text)

        err = checks.get("punctuation", [])
        exc = exceptions.get("punctuation", {})
        bad_punctuations = check_punctuation(text, err, exc, ann_id)

        err = checks.get("spelling", [])
        exc = exceptions.get("spelling", {})
        typos = check_spelling(text, err, exc, ann_id)

        err = checks.get("substitution", [])
        exc = exceptions.get("substitution", {})
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
    keys = ("No signature", "Accession (name)", "Spelling (name)",
            "Spelling (short name)", "Illegal term (name)",
            "Abbreviation (name)", "Abbreviation (short name)",
            "Underscore (short name)", "Underscore (name)")
    failed = []
    for acc, (name, short_name, checked) in entries.items():
        no_signatures = checked == 'Y' and acc not in entries_w_signatures

        exc = exceptions.get("accession", {})
        accessions_in_name = check_accession(name, exc, acc)

        err = checks.get("spelling", [])
        exc = exceptions.get("spelling", {})
        typos1 = check_spelling(name, err, exc, acc)
        typos2 = check_spelling(short_name, err, exc, acc)

        err = checks.get("word", [])
        exc = exceptions.get("word", {})
        illegal_terms = check_illegal_terms(name, err, exc, acc)

        err = checks.get("abbreviation", [])
        exc = exceptions.get("abbreviation", {})
        bad_abbrs1 = check_abbreviations(name, err, exc, acc)
        bad_abbrs2 = check_abbreviations(short_name, err, exc, acc)

        missing_hyphens = check_underscore_to_hyphen(short_name,
                                                     ("binding", "bd",
                                                      "related", "rel",
                                                      "like"))

        exc = exceptions.get("underscore", [])
        underscores = check_underscore(name, exc, acc)

        # same_names = []
        # similar_names = []
        # nwc = re.compile(r"[^a-zA-Z0-9]+")  # non-word characters
        # print(acc)
        # for _acc, (_name, _short_name, _checked) in entries.items():
        #     if acc >= _acc:
        #         continue
        #
        #     if (name.lower() == _name.lower()
        #             or short_name.lower() == _short_name.lower()):
        #         same_names.append(_acc)
        #
        #     if (nwc.sub('', name) == nwc.sub('', _name)
        #             or nwc.sub('', short_name) == nwc.sub('', _short_name)):
        #         similar_names.append(_acc)
        #
        # if similar_names:
        #     print(acc, similar_names)

        #todo: same_names, similar_names
        values = [no_signatures, accessions_in_name,
                  typos1, typos2, illegal_terms,
                  bad_abbrs1, bad_abbrs2,
                  missing_hyphens, underscores]
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
        SELECT SC.CHECK_TYPE, SC.STRING, SE.ANN_ID, SE.ENTRY_AC
        FROM INTERPRO.SANITY_CHECK SC
          LEFT OUTER JOIN INTERPRO.SANITY_EXCEPTION SE
          ON SC.CHECK_TYPE = SE.CHECK_TYPE
          AND SC.ID = SE.ID
        """
    )
    checks = {}
    abstract_exceptions = {}
    entry_exceptions = {}
    for err_type, term, ann_id, entry_ac in cur:
        if err_type in checks:
            terms = checks[err_type]
        else:
            terms = checks[err_type] = set()
            abstract_exceptions[err_type] = {}
            entry_exceptions[err_type] = {} if term else set()

        if term:
            terms.add(term)

        if ann_id:
            entity_id = ann_id
            exceptions = abstract_exceptions[err_type]
        elif entry_ac:
            entity_id = entry_ac
            exceptions = entry_exceptions[err_type]
        else:
            continue

        if term:
            if term in exceptions:
                exceptions[term].append(entity_id)
            else:
                exceptions[term] = [entity_id]
        else:
            exceptions.add(entity_id)

    return checks, abstract_exceptions, entry_exceptions


def check_all(user, dsn):
    con = db.connect_oracle(user, dsn)
    cur = con.cursor()
    checks, abstract_exceptions, entry_exceptions = load_sanity_checks(cur)
    abstracts = check_abstracts(cur, checks, abstract_exceptions)
    entries = check_entries(cur, checks, entry_exceptions)

    # # Delete old runs (keeping the nine most recent)
    # cur.execute(
    #     """
    #     DELETE FROM INTERPRO.SANITY_RUN
    #     WHERE ID NOT IN (
    #       SELECT ID
    #       FROM (
    #           SELECT ID
    #           FROM INTERPRO.SANITY_RUN
    #           ORDER BY TIMESTAMP DESC
    #       )
    #       WHERE ROWNUM <= 9
    #     )
    #     """
    # )

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


@app.route("/api/interpro/sanitychecks/")
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


@app.route("/api/interpro/sanitychecks/", methods=["PUT"])
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


@app.route("/api/interpro/sanitychecks/<run_id>/")
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


@app.route("/api/interpro/sanitychecks/<run_id>/<int:err_id>/", methods=["POST"])
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
