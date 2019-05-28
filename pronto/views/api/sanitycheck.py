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
        self.punctuation = []
        self.substitutions = []
        self.bad_characters = []

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
            self.bad_characters
        ))

    @property
    def errors(self):
        return {
            "is_too_short": self.too_short,
            "has_empty_paragraph": self.empty_paragraph,
            "invalid_abbreviations": self.abbreviations,
            "typos": self.typos,
            "invalid_references": self.citations,
            "punctuations_errors": self.punctuation,
            "bad_substitutions": self.substitutions,
            "invalid_charachters": self.bad_characters
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

        for match in re.findall("znf|ZnF[^\d]|kDA|KDa|Kda|\d+\s+kDa|-kDa",
                                text):
            if match not in exceptions or self.id not in exceptions[match]:
                self.abbreviations.append(match)

    def check_citations(self, text, exceptions={}):
        terms = ("PMID", "PubMed", "unpub", "Bateman", "(?:personal )?obs\.",
                 "personal ", "and others", "and colleagues", " et al\.?")

        for match in re.findall('|'.join(terms), text, re.I):
            if match not in exceptions or self.id not in exceptions[match]:
                self.citations.append(match)

    def check_punctuation(self, text, exceptions={}):
        errors = [']</p>', '] </p>', '..', ' ;', ' )', '( ', ' :', ' .',
                  '[ ', ' ] ', ' !', '[ <', '[< ', '> ]', ' >]&', ' > ',
                  ' < ', '[ <', '[< ', '> ]', ' >]&', '.[', '>] [<', '{ ',
                  ' }', '" P', '>], <cite']

        for err in errors:
            if err in text:
                if err not in exceptions or self.id not in exceptions[err]:
                    self.punctuation.append(err)

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

    abbr_exc = {
        "zf": ["AB04953", "AB18958", "AB25101", "AB28478", "AB29641",
               "AB34960"],
        "kD": ["AB07521", "AB07522", "AB10981", "AB11599", "AB24026",
               "AB24696", "AB25135", "AB28862", "AB38195", "AB39366"],
        "ZnF": ["AB42360"]
    }
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
    punctuation_exc = {
        "..": ["AB14711", "AB14142", "AB04260", "AB18182", "AB21792",
               "AB38461", "AB14142"],
        " .": ["AB14711"],
        " > ": ["AB02618", "AB05478", "AB05476", "AB05481", "AB05480",
                "AB05479", "AB21752", "AB28969", "AB43597"],
        ".[": ["AB18182"],
    }
    character_exceptions = ["ö", "ü"]

    for ann_id, text, entry_acc in cur:
        if ann_id in passed or ann_id in failed:
            continue

        abstract = Abstract(ann_id, entry_acc)
        abstract.check_basic(text)
        abstract.check_spelling(text, words, words_exc)
        abstract.check_abbreviations(text, abbr_exc)
        abstract.check_citations(text, citations_exc)
        abstract.check_punctuation(text, punctuation_exc)
        abstract.check_substitutions(text)
        abstract.check_characters(text, character_exceptions)

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
    if executor.enqueue("Sanity checks", run_all, user, dsn):
        return jsonify({"status": True}), 202
    else:
        return jsonify({"status": False}), 409
