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
    def __init__(self, ann_id, entry_acc):
        self.id = ann_id
        self.entry_acc = entry_acc
        self.too_short = False
        self.empty_paragraph = False
        self.abbreviations = []
        self.typos = []
        self.citations = []
        self.punctuation = []
        self.substitutions = []
        self.bad_characters = []
        self.bad_urls = []

    @property
    def is_valid(self):
        return not any((
            self.too_short,
            self.empty_paragraph,
            self.abbreviations,
            self.typos,
            self.citations,
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
                "has_empty_paragraph": self.empty_paragraph,
                "abbreviations": self.abbreviations,
                "characters": self.bad_characters,
                "punctuations": self.punctuation,
                "references": self.citations,
                "spelling": self.typos,
                "substitutions": self.substitutions,
                "urls": self.bad_urls
            }
        }

    def check_basic(self, text):
        if len(text) < 25 or re.search('no\s+abs', text, re.I):
            self.too_short = True

        if re.search("<p>\s*</p>", text, re.I):
            self.empty_paragraph = True

    def check_spelling(self, text, words, exceptions={}):
        for match in re.findall('|'.join(words), text, re.I):
            if match not in exceptions or self.id not in exceptions[match]:
                self.typos.append(match)

    def check_abbreviations(self, text, exceptions={}):
        terms = ("gram\s*-(?!negative|positive)", "gram\s*\+", "gram pos",
                 "gram neg", "g-positive", "g-negative")

        for match in re.findall('|'.join(terms), text, re.I):
            self.abbreviations.append(match)

        valid_cases = ("N-terminal", "C-terminal", "C terminus", "N terminus")
        for match in re.findall("\b[cn][\-\s]termin(?:al|us)", text, re.I):
            if match not in valid_cases:
                self.abbreviations.append(match)

        for match in re.findall("znf|ZnF|zf|kDA|KDa|Kda|\d+\s+kDa|-kDa",
                                text):
            if match not in exceptions or self.id not in exceptions[match]:
                self.abbreviations.append(match)

    def check_citations(self, text, errors, exceptions={}):
        for match in re.findall('|'.join(errors), text, re.I):
            if match not in exceptions or self.id not in exceptions[match]:
                self.citations.append(match)

    def check_punctuation(self, text, errors, exceptions={}):
        for err in errors:
            if err in text:
                if err not in exceptions or self.id not in exceptions[err]:
                    self.punctuation.append(err)

        prog = re.compile(r"[a-z]{3}|\d[\]\d]\]|\d\]\)", flags=re.I)
        for match in re.finditer(r"\. \[", text):
            i, j = match.span()

            if text[i - 3:i] == "e.g":
                continue  # e.g. [
            elif text[i - 2:i] == "sp":
                continue  # sp. [
            elif text[i - 5:i] == "et al":
                continue  # et al. [
            elif prog.match(text[i - 3:i]):
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

    def check_substitutions(self, text):
        errors = [",s ", ",d ", ",,", ",-"]
        for err in errors:
            if err in text:
                self.substitutions.append(err)

    def check_characters(self, text, exceptions=[]):
        try:
            text.encode("ascii")
        except UnicodeEncodeError:
            pass
        else:
            return

        for c in text:
            try:
                c.encode("ascii")
            except UnicodeEncodeError:
                if c not in exceptions:
                    self.bad_characters.append(c)

    def check_link(self, text):
        for url in re.findall(r"https?://[\w\-@:%.+~#=/?&]+", text, re.I):
            try:
                res = urlopen(url)
            except URLError:
                self.bad_urls.append(url)
            else:
                if res.status != 200:
                    self.bad_urls.append(url)


def check_abstracts(cur):
    cur.execute(
        """
        SELECT ID, CONTENT 
        FROM INTERPRO.SANITY_CHECK 
        WHERE TYPE IN ('errors', 'exceptions')
        """
    )
    content = {row[0]: json.loads(row[1].read()) for row in cur}

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

        abstract = Abstract(ann_id, entry_acc)
        abstract.check_basic(text)
        abstract.check_abbreviations(text, content["abbreviations-exc"])
        abstract.check_characters(text, content["characters-exc"])
        abstract.check_citations(text, content["citations-err"],
                                 content["citations-exc"])
        abstract.check_link(text)
        abstract.check_punctuation(text, content["punctuation-err"],
                                   content["punctuation-exc"])
        abstract.check_spelling(text, content["spelling-err"],
                                content["spelling-exc"])
        abstract.check_substitutions(text)

        if abstract.is_valid:
            passed.add(ann_id)
        else:
            failed[ann_id] = abstract.dump()

    return list(failed.values())


def check_entries(cur):
    pass


def check_all(user, dsn):
    con = db.connect_oracle(user, dsn)
    cur = con.cursor()
    abstracts = check_abstracts(cur)
    cur.execute(
        """
        INSERT INTO INTERPRO.SANITY_CHECK (ID, TYPE, NUM_ERRORS, CONTENT) 
        VALUES (:1, :2, :3, :4)
        """,
        (
            uuid.uuid1().hex,
            "results",
            len(abstracts),
            json.dumps({
                "abstracts": abstracts
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
        SELECT ID, NUM_ERRORS, TIMESTAMP, NVL(UP.NAME, SC.USERNAME)
        FROM INTERPRO.SANITY_CHECK SC
          LEFT OUTER JOIN INTERPRO.USER_PRONTO UP
          ON SC.USERNAME = UP.DB_USER
        WHERE TYPE = 'results'
        ORDER BY TIMESTAMP DESC
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
