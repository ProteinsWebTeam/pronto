# -*- coding: utf-8 -*-

import re
import uuid
from urllib.error import URLError
from urllib.request import urlopen

from flask import json, jsonify

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


def check_abbreviations(text, terms, id):
    bad_abbrs = []
    for match in re.findall(r"\d+\s+kDa", text):
        bad_abbrs.append(match)

    valid_cases = ("N-terminal", "C-terminal", "C terminus", "N terminus")
    for match in re.findall(r"\b[cn][\-\s]termin(?:al|us)", text, re.I):
        if match not in valid_cases:
            bad_abbrs.append(match)

    for match in re.findall('|'.join(terms), text):
        if id not in terms.get(match, []):
            bad_abbrs.append(match)

    return bad_abbrs


def check_accession(text, exceptions, id):
    terms = ("G3DSA:[\d.]", "IPR\d", "MF_\d", "PF\d", "PIRSF\d", "PR\d",
             "PS\d", "PTHR\d", "SFLD[FGS]\d", "SM\d", "SSF\d", "TIGR\d",
             "cd\d", "sd\d")

    errors = []
    for match in re.findall(r"\b(" + '|'.join(terms) + r"{4,})\b", text):
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
            if id not in exceptions.get(c, []):
                errors.append(c)

    return errors


def check_citations(text, terms, id):
    errors = []
    for match in re.findall('|'.join(map(re.escape, terms)), text, re.I):
        if id not in terms.get(match, []):
            errors.append(match)

    for match in re.findall(r"\[(?:PMID:)?\d*\]", text, re.I):
        errors.append(match)

    return errors


def check_gram(text):
    terms = ("gram\s*-(?!negative|positive)", "gram\s*\+", "gram pos",
             "gram neg", "g-positive", "g-negative")
    return re.findall('|'.join(terms), text, re.I)


def check_illegal_terms(text, terms, id):
    errors = []
    for term, exceptions in terms.items():
        if term in text and id not in exceptions:
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


def check_punctuation(text, terms, id):
    errors = []
    for term, exceptions in terms.items():
        if term in text and id not in exceptions:
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


def check_spelling(text, terms, id):
    errors = []
    for match in re.findall(r"\b(?:" + '|'.join(terms) + r")\b", text, re.I):
        if id not in terms.get(match, []):
            errors.append(match)

    return errors


def check_substitutions(text, terms, id):
    errors = []
    for term, exceptions in terms.items():
        if term in text and id not in exceptions:
            errors.append(term)

    return errors


def check_underscore_to_hyphen(text, terms):
    errors = []
    for match in re.findall("_(" + '|'.join(terms) + r")\b", text):
        errors.append(match)
    return errors


def check_underscore(text, exceptions, id):
    errors = []
    for match in re.findall(r"\b.*?_.*?\b", text):
        if id not in exceptions:
            errors.append(match)
    return errors


def group_errors(errors):
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

            _errors[key] = list(items.values())

    return _errors


def check_abstracts(cur, errors, exceptions):
    merged = {}
    for _type, terms in errors.items():
        merged[_type] = {}
        for term in terms:
            merged[_type][term] = exceptions[_type].get(term, {})

    passed = set()
    failed = {}
    keys = ("too_short", "has_empty_block", "abbreviation",
            "character", "citation", "gram",
            "link", "punctuation", "spelling",
            "substitution")
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

        terms = merged.get("abbreviation", {})
        bad_abbrs = check_abbreviations(text, terms, ann_id)

        terms = merged.get("ascii", {})
        bad_characters = check_characters(text, terms, ann_id)

        terms = merged.get("citation", {})
        bad_citations = check_citations(text, terms, ann_id)

        bad_gram = check_gram(text)
        bad_links = check_links(text)

        terms = merged.get("punctuation", {})
        bad_punctuations = check_punctuation(text, terms, ann_id)

        terms = merged.get("spelling", {})
        typos = check_spelling(text, terms, ann_id)

        terms = merged.get("substitution", {})
        bad_substitutions = check_substitutions(text, terms, ann_id)

        values = [too_short, has_empty_block, bad_abbrs,
                  bad_characters, bad_citations, bad_gram,
                  bad_links, bad_punctuations, typos,
                  bad_substitutions]

        if any(values):
            failed[ann_id] = {
                "entry": entry_acc,
                "errors": group_errors(dict(zip(keys, values)))
            }
        else:
            passed.add(ann_id)

    return failed


def check_entries(cur, errors, exceptions):
    merged = {}
    for _type, terms in errors.items():
        merged[_type] = {}
        for term in terms:
            merged[_type][term] = exceptions[_type].get(term, {})

    cur.execute("SELECT DISTINCT ENTRY_AC FROM INTERPRO.ENTRY2METHOD")
    entries_w_signatures = {row[0] for row in cur}
    cur.execute(
        """
        SELECT ENTRY_AC, NAME, SHORT_NAME, CHECKED
        FROM INTERPRO.ENTRY
        """
    )
    entries = {row[0]: row[1:] for row in cur}
    keys = ("no_signatures", "accessions_in_name", "typos1",
            "typos2", "illegal_terms", "bad_abbrs1", "bad_abbrs2",
            "missing_hyphens", "underscores")
    failed = {}
    for acc, (name, short_name, checked) in entries.items():
        no_signatures = checked == 'Y' and acc not in entries_w_signatures

        terms = merged.get("accession", {})
        accessions_in_name = check_accession(name, terms, acc)

        terms = merged.get("spelling", {})
        typos1 = check_spelling(name, terms, acc)
        typos2 = check_spelling(short_name, terms, acc)

        terms = merged.get("word", {})
        illegal_terms = check_illegal_terms(name, terms, acc)

        terms = merged.get("abbreviation", {})
        bad_abbrs1 = check_abbreviations(name, terms, acc)
        bad_abbrs2 = check_abbreviations(short_name, terms, acc)

        terms = ("binding", "bd", "related", "rel", "like")
        missing_hyphens = check_underscore_to_hyphen(short_name, terms)

        underscores = check_underscore(name, {}, acc)

        values = [no_signatures, accessions_in_name,
                  typos1, typos2, illegal_terms,
                  bad_abbrs1, bad_abbrs2,
                  missing_hyphens, underscores]
        if any(values):
            failed[acc] = group_errors(dict(zip(keys, values)))

    return failed


def load_sanity_checks(cur):
    cur.execute(
        """
        SELECT ER.CHECK_TYPE, ER.ERROR, EX.ANN_ID, EX.ENTRY_AC
        FROM INTERPRO.SANITY_ERROR ER
          LEFT OUTER JOIN INTERPRO.SANITY_EXCEPTION EX
          ON ER.CHECK_TYPE = EX.CHECK_TYPE
          AND ER.ID = EX.ID
        """
    )
    errors = {}
    entries = {}
    abstracts = {}
    for err_type, term, ann_id, entry_ac in cur:
        if err_type in errors:
            terms = errors[err_type]
        else:
            terms = errors[err_type] = set()
            abstracts[err_type] = {}
            entries[err_type] = {}

        terms.add(term)
        if ann_id:
            entity_id = ann_id
            exceptions = abstracts[err_type]
        elif entry_ac:
            entity_id = entry_ac
            exceptions = entries[err_type]
        else:
            continue

        if term in exceptions:
            exceptions[term].append(entity_id)
        else:
            exceptions[term] = [entity_id]

    return errors, abstracts, entries


def check_all(user, dsn):
    con = db.connect_oracle(user, dsn)
    cur = con.cursor()
    errors, abstract_exceptions, entry_exceptions = load_sanity_checks(cur)
    abstracts = check_abstracts(cur, errors, abstract_exceptions)
    entries = check_entries(cur, errors, entry_exceptions)
    num_errors = sum(map(len, (abstracts, entries)))

    # Add new report
    cur.execute(
        """
        INSERT INTO INTERPRO.SANITY_REPORT (ID, NUM_ERRORS, CONTENT)
        VALUES (:1, :2, :3)
        """,
        (
            uuid.uuid1().hex,
            num_errors,
            json.dumps({
                "abstracts": abstracts,
                "entries": entries
            })
        )
    )

    # Delete old reports
    cur.execute(
        """
        DELETE FROM INTERPRO.SANITY_REPORT
        WHERE ID NOT IN (
          SELECT ID
          FROM (
              SELECT ID
              FROM INTERPRO.SANITY_REPORT
              ORDER BY TIMESTAMP DESC
          )
          WHERE ROWNUM <= 10
        )
        """
    )
    con.commit()
    cur.close()
    con.close()


@app.route("/api/interpro/sanitychecks/")
def get_sanitychecks():
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT SR.ID, SR.NUM_ERRORS, SR.TIMESTAMP, NVL(UP.NAME, SR.USERNAME)
        FROM INTERPRO.SANITY_REPORT SR
          LEFT OUTER JOIN INTERPRO.USER_PRONTO UP
          ON SR.USERNAME = UP.DB_USER
        ORDER BY SR.TIMESTAMP DESC
        """
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


@app.route("/api/interpro/sanitychecks/<id>/")
def get_sanitychecks_report(id):
    cur = db.get_oracle().cursor()
    cur.execute(
        """
        SELECT SR.NUM_ERRORS, SR.CONTENT, SR.TIMESTAMP, 
          NVL(UP.NAME, SR.USERNAME)
        FROM INTERPRO.SANITY_REPORT SR
          LEFT OUTER JOIN INTERPRO.USER_PRONTO UP
          ON SR.USERNAME = UP.DB_USER
        WHERE SR.ID = :1
        """, (id,)
    )
    row = cur.fetchone()
    if row:
        report = {
            "num_errors": row[0],
            "errors": json.loads(row[1].read()),
            "date": row[2].strftime("%d %b %Y, %H:%M"),
            "user": row[3]

        }
    else:
        report = {}
    cur.close()

    return jsonify(report), 200 if report else 404
