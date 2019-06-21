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


class Abstract(object):
    def __init__(self, ann_id, text, entry_acc):
        self.id = ann_id
        self.text = text
        self.entry_acc = entry_acc
        self.too_short = False
        self.has_empty_block = False
        self.typos = []
        self.bad_abbrs = []
        self.spaces_before_symbol = 0
        self.invalid_gram = []
        self.bad_ref = []
        self.punctuation = []
        self.substitutions = []
        self.bad_characters = []
        self.bad_urls = []

    @property
    def is_valid(self):
        return not any((
            self.too_short,
            self.has_empty_block,
            self.bad_abbrs,
            self.typos,
            self.bad_ref,
            self.punctuation,
            self.substitutions,
            self.bad_characters,
            self.bad_urls
        ))

    def dump(self):
        return {
            "id": self.id,
            "entry": self.entry_acc,
            "errors": {
                "is_too_short": self.too_short,
                "has_has_empty_block": self.has_empty_block,
                "abbreviations": self.bad_abbrs,
                "characters": self.bad_characters,
                "punctuations": self.punctuation,
                "references": self.bad_ref,
                "spelling": self.typos,
                "substitutions": self.substitutions,
                "urls": self.bad_urls
            }
        }

    def check_basic(self):
        if len(self.text) < 25 or re.search('no\s+abs', self.text, re.I):
            self.too_short = True

        if re.search("<p>\s*</p>", self.text, re.I):
            self.has_empty_block = True

    def check_spelling(self, terms: dict):
        for match in re.findall('|'.join(terms), self.text, re.I):
            if self.id not in terms.get(match, []):
                self.typos.append(match)

    def check_abbreviations(self, terms: dict):
        for _ in re.findall("\d+\s+kDa", self.text):
            self.spaces_before_symbol += 1

        valid_cases = ("N-terminal", "C-terminal", "C terminus", "N terminus")
        for match in re.findall("\b[cn][\-\s]termin(?:al|us)", self.text, re.I):
            if match not in valid_cases:
                self.bad_abbrs.append(match)

        for match in re.findall('|'.join(terms), self.text):
            if self.id not in terms.get(match, []):
                self.bad_abbrs.append(match)

    def check_gram(self):
        terms = ("gram\s*-(?!negative|positive)", "gram\s*\+", "gram pos",
                 "gram neg", "g-positive", "g-negative")

        for match in re.findall('|'.join(terms), self.text, re.I):
            self.invalid_gram.append(match)

    def check_citations(self, terms: dict):
        for match in re.findall('|'.join(terms), self.text, re.I):
            if self.id not in terms.get(match, []):
                self.bad_ref.append(match)

        for match in re.findall("\[(?:PMID:)?\d*\]", self.text, re.I):
            self.bad_ref.append(match)

    def check_punctuation(self, terms: dict):
        for term, exceptions in terms.items():
            if term in self.text and self.id not in exceptions:
                self.punctuation.append(term)

        prog = re.compile(r"[a-z]{3}|\d[\]\d]\]|\d\]\)", flags=re.I)
        for match in re.finditer(r"\. \[", self.text):
            i, j = match.span()

            if self.text[i - 3:i] == "e.g":
                continue  # e.g. [
            elif self.text[i - 2:i] == "sp":
                continue  # sp. [
            elif self.text[i - 5:i] == "et al":
                continue  # et al. [
            elif prog.match(self.text[i - 3:i]):
                """
                [a-z]{3}
                    ent. [

                \d[\]\d]\]
                    22]. [
                    3]]. [

                \d\]\)
                    7]). [
                """
                continue
            else:
                self.punctuation.append(match.group(0))

    def check_substitutions(self, terms: dict):
        for term, exceptions in terms.items():
            if term in self.text and self.id not in exceptions:
                self.substitutions.append(term)

    def check_characters(self, characters: dict):
        try:
            self.text.encode("ascii")
        except UnicodeEncodeError:
            pass
        else:
            return

        for c in self.text:
            try:
                c.encode("ascii")
            except UnicodeEncodeError:
                if self.id not in characters.get(c, []):
                    self.bad_characters.append(c)

    def check_link(self):
        for url in re.findall(r"https?://[\w\-@:%.+~#=/?&]+", self.text, re.I):
            try:
                res = urlopen(url)
            except URLError:
                self.bad_urls.append(url)
            else:
                if res.status != 200:
                    self.bad_urls.append(url)


def check_abstracts(cur, types):
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

        abstract = Abstract(ann_id, text, entry_acc)
        abstract.check_basic()
        abstract.check_abbreviations(types.get("abbreviation", {}))
        abstract.check_characters(types.get("ascii", {}))
        abstract.check_citations(types.get("citation", {}))
        abstract.check_link()
        abstract.check_punctuation(types.get("punctuation", {}))
        abstract.check_spelling(types.get("spelling", {}))
        abstract.check_substitutions(types.get("substitution", {}))

        if abstract.is_valid:
            passed.add(ann_id)
        else:
            failed[ann_id] = abstract.dump()

    return list(failed.values())


def check_entries(cur, types):
    failed = []
    cur.execute(
        """
        SELECT ENTRY_AC, NAME, SHORT_NAME
        FROM INTERPRO.ENTRY
        """
    )
    for acc, name, short_name in cur:
        e = Abstract(acc, acc)
        # todo accession in long name

        # todo add exceptions for entries
        e.check_spelling(name, content["spelling-err"])
        e.check_spelling(short_name, content["spelling-err"])

        # todo forbidden words
        # todo abbreviations
        # todo incorrect use of underscore

        if not e.is_valid:
            failed.append(e.dump())

    return failed


def get_sanity_checks(cur):
    cur.execute(
        """
        SELECT ER.CHECK_TYPE, ER.ERROR, EX.ANN_ID
        FROM INTERPRO.SANITY_ERROR ER
          LEFT OUTER JOIN INTERPRO.SANITY_EXCEPTION EX
          ON ER.CHECK_TYPE = EX.CHECK_TYPE
          AND ER.ID = EX.ID
        """
    )
    types = {}
    for err_type, term, ann_id in cur:
        if err_type in types:
            terms = types[err_type]
        else:
            terms = types[err_type] = {}

        if term in terms:
            exceptions = terms[term]
        else:
            exceptions = terms[term] = []

        if ann_id:
            exceptions.append(ann_id)
    return types


def check_all(user, dsn):
    con = db.connect_oracle(user, dsn)
    cur = con.cursor()
    types = get_sanity_checks(cur)
    abstracts = check_abstracts(cur, types)
    entries = check_entries(cur, types)
    num_errors = sum(map(len, (abstracts, entries)))

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
          WHERE ROWNUM <= 4
        )
        """
    )

    print(entries)

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
