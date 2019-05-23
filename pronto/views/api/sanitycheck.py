# -*- coding: utf-8 -*-

import re

from flask import jsonify

from pronto import app, db, executor


class Abstract(object):
    def __init__(self, ann_id, entry_acc):
        self.id = ann_id
        self.entry_acc = entry_acc
        self.too_short = False
        self.empty_paragraph = False
        self.abbreviations = []
        self.typos = []
        self.citations = []

    @property
    def is_valid(self):
        return not any((
            self.too_short,
            self.empty_paragraph,
            self.abbreviations,
            self.typos,
            self.citations
        ))

    def check_basic(self, text):
        if len(text) < 25 or re.search('no\s+abs', text, re.I):
            self.too_short = True

        if re.search("<p>\s*</p>", text, re.I):
            self.empty_paragraph = True

    def check_spelling(self, text, words, exceptions={}):
        for match in re.findall('|'.join(words), text, re.I):
            if match not in exceptions or self.id not in exceptions[match]:
                self.typos.append(match)

    def check_abbreviations(self, text, exceptions=[]):
        terms = ("gram\s*-(?!negative|positive)", "gram\s*\+", "gram pos",
                 "gram neg", "g-positive", "g-negative")

        for match in re.findall('|'.join(terms), text, re.I):
            self.abbreviations.append(match)

        for match in re.findall("\b[cn][\-\s]termin(?:al|us)", text, re.I):
            if match not in exceptions:
                self.abbreviations.append(match)

        for match in re.findall("znf|ZnF[^\d]|kDA|KDa|Kda|\d+\s+kDa|-kDa",
                                text):
            self.abbreviations.append(match)

    def check_citations(self, text, excpetions={}):
        terms = ("PMID", "PubMed", "unpub", "Bateman", "(?:personal )?obs\.",
                 "personal ", "and others", "and colleagues", " et al\.?")

        for match in re.findall('|'.join(terms), text, re.I):
            if match not in excpetions or self.id not in excpetions[match]:
                self.citations.append(match)





def run_abstracts(cur):
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

    abbr_exc = ["N-terminal", "C-terminal", "C terminus", "N terminus"]
    words = [
        'alcholol', 'analagous', 'aparrently', 'assocaited', 'bacteriaa',
        'batcer', 'betwwen', 'caracterized', 'chlorplasts', 'conatins',
        'dependant', 'doamin', 'domainss', 'domian', 'enrty', 'fiber',
        'fsmily', 'golbin', 'haeme', 'homolog ', 'lenght', 'neighbor',
        'portein', 'potein', 'protien', 'releated', 'repersents', 'represnts',
        'reveales', 'siganture', 'specifacally', 'supress', 'variousely'
    ]
    words_exc = {
        "haeme": ['AB00308', 'AB04921', 'AB08783', 'AB08793', 'AB09892',
                  'AB09906', 'AB12871', 'AB12872']
    }
    citations_exc = {
        "and others": ["AB18638", "AB05262", "AB20443", "AB27860", "AB27870",
                       "AB31344", "AB36073", "AB36070", "AB41136"],
        "Bateman": ["AB28261", "AB16484", "AB34196"],
        "et al.": ["AB36803", "AB41396"],
        "and colleagues": ["AB31661"],
        "obs.": ["AB34196"]
    }

    for ann_id, text, entry_acc in cur:
        if ann_id in passed or ann_id in failed:
            continue

        abstract = Abstract(ann_id, entry_acc)
        abstract.check_basic(text)
        abstract.check_spelling(text, words, words_exc)
        abstract.check_abbreviations(text, abbr_exc)
        abstract.check_citations(text, citations_exc)

        if abstract.is_valid:
            passed.add(ann_id)
        else:
            failed[ann_id] = abstract

    return list(failed.values())


def run_all(user, dsn):
    con = db.connect_oracle(user, dsn)
    cur = con.cursor()
    abstracts = run_abstracts(cur)
    print(len(abstracts))

    cur.close()
    con.close()


@app.route("/api/sanitychecks/")
def submit():
    user = app.config["ORACLE_DB"]["credentials"]
    dsn = app.config["ORACLE_DB"]["dsn"]
    executor.enqueue("Sanity checks", run_all, user, dsn)
    return jsonify({"status": True}), 202
