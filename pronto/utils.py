# -*- coding: utf-8 -*-

import os
import pickle
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

import cx_Oracle
import MySQLdb
import psycopg2
from flask import current_app


class Executor:
    def __init__(self):
        self.executor = ThreadPoolExecutor()

    @staticmethod
    def run_task(user, dsn, name, fn, *args, **kwargs):
        con = cx_Oracle.connect(user["dbuser"], user["password"], dsn)
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO INTERPRO.PRONTO_TASK (NAME, USERNAME, STARTED) 
            VALUES (:1, USER, SYSDATE)
            """, (name,)
        )
        con.commit()
        cur.close()
        con.close()

        try:
            fn(*args, **kwargs)
        except Exception as exc:
            status = 'N'
        else:
            status = 'Y'

        con = cx_Oracle.connect(user["dbuser"], user["password"], dsn)
        cur = con.cursor()
        cur.execute(
            """
            UPDATE INTERPRO.PRONTO_TASK
            SET FINISHED = SYSDATE, STATUS = :1
            WHERE NAME = :2 AND STATUS IS NULL
            """, (status, name)
        )
        con.commit()
        cur.close()
        con.close()

    def submit(self, user: dict, task: str, fn: Callable, *args, **kwargs):
        if self.is_running(user, task):
            return False

        self.executor.submit(self.run_task, user, get_oracle_dsn(), task, fn,
                             *args, **kwargs)
        return True

    @staticmethod
    def is_running(user: dict, task: str) -> bool:
        con = connect_oracle_auth(user)
        cur = con.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM INTERPRO.PRONTO_TASK
            WHERE NAME = :1 AND STATUS IS NULL
            """, (task,)
        )
        count, = cur.fetchone()
        cur.close()
        con.close()
        return count != 0

    @property
    def tasks(self, seconds: int = 3600):
        con = connect_oracle()
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT T.NAME, U.NAME, T.STARTED, T.FINISHED, T.STATUS 
            FROM INTERPRO.PRONTO_TASK T
              INNER JOIN INTERPRO.PRONTO_USER U
              ON T.USERNAME = U.DB_USER
            WHERE T.STARTED >= SYSDATE - INTERVAL '{seconds}' SECOND
            ORDER BY T.STARTED
            """
        )
        tasks = []
        for name, user, start_time, end_time, status in cur:
            if end_time is not None:
                end_time = end_time.strftime("%d %b %Y, %H:%M")
            else:
                end_time = None

            tasks.append({
                "id": name,
                "user": user,
                "start_time": start_time.strftime("%d %b %Y, %H:%M"),
                "end_time": end_time,
                "success": status == 'Y'
            })
        cur.close()
        con.close()
        return tasks


executor = Executor()


def connect_oracle() -> cx_Oracle.Connection:
    return cx_Oracle.connect(current_app.config["ORACLE"])


def connect_oracle_auth(user: dict) -> cx_Oracle.Connection:
    dsn = current_app.config["ORACLE"].rsplit('@', 1)[-1]
    return cx_Oracle.connect(user["dbuser"], user["password"], dsn)


def get_oracle_dsn():
    return current_app.config["ORACLE"].rsplit('@', 1)[-1]


def connect_pg(url: Optional[str]=None):
    if url is None:
        url = get_pg_url()

    m = re.match(r'([^/]+)/([^@]+)@([^:]+):(\d+)/(\w+)', url)
    return psycopg2.connect(
        user=m.group(1),
        password=m.group(2),
        host=m.group(3),
        port=int(m.group(4)),
        dbname=m.group(5)
    )


def get_pg_url():
    return current_app.config["POSTGRESQL"]


def connect_mysql():
    url = current_app.config["MYSQL"]
    m = re.match(r'([^/]+)/([^@]+)@([^:]+):(\d+)/(\w+)', url)
    return MySQLdb.connect(
        user=m.group(1),
        passwd=m.group(2),
        host=m.group(3),
        port=int(m.group(4)),
        db=m.group(5)
    )


def split_path(path: str) -> List[str]:
    items = []
    for item in map(str.strip, path.split('/')):
        if item and item not in items:
            items.append(item)

    return items


XREFS = {
    'CATHGENE3D': 'http://www.cathdb.info/superfamily/{}',
    'CAZY': 'http://www.cazy.org/fam/{}.html',
    #'COG': 'http://www.ncbi.nlm.nih.gov/COG/new/release/cow.cgi?cog={}',
    'COG': 'https://ftp.ncbi.nih.gov/pub/COG/COG2014/static/byCOG/{}.html',
    'EC': 'http://www.ebi.ac.uk/intenz/query?cmd=SearchEC&ec={}',
    'INTENZ': 'http://www.ebi.ac.uk/intenz/query?cmd=SearchEC&ec={}',
    'GENPROP': 'https://www.ebi.ac.uk/interpro/genomeproperties/#{}',
    'INTERPRO': '/entry/{}',
    'PDBE': 'http://www.ebi.ac.uk/pdbe/entry/pdb/{}',
    'PFAM': 'http://pfam.xfam.org/family/{}',
    'PIRSF': 'http://pir.georgetown.edu/cgi-bin/ipcSF?id={}',
    'PROSITE': 'https://prosite.expasy.org/{}',
    'PROSITEDOC': 'https://prosite.expasy.org/{}',
    'SSF': 'http://supfam.org/SUPERFAMILY/cgi-bin/scop.cgi?ipid={}',
    'SUPERFAMILY': 'http://supfam.org/SUPERFAMILY/cgi-bin/scop.cgi?ipid={}',
    'SWISSPROT': 'http://www.uniprot.org/uniprot/{}',
    'TIGRFAMS': 'http://www.jcvi.org/cgi-bin/tigrfams/HmmReportPage.cgi?acc={}'
}


class CathGene3D:
    home = 'http://www.cathdb.info'
    color = '#d9417c'

    def gen_link(self, acc: str):
        m = re.match(r'G3DSA:(.+)', acc)
        return f"{self.home}/superfamily/{m.group(1)}"


class Cdd:
    home = 'http://www.ncbi.nlm.nih.gov/Structure/cdd/cdd.shtml'
    color = '#c6554b'

    def gen_link(self, acc: str):
        return f"http://www.ncbi.nlm.nih.gov/Structure/cdd/cddsrv.cgi?uid={acc}"


class Hamap:
    home = 'http://hamap.expasy.org'
    color = '#ce672d'

    def gen_link(self, acc: str):
        return f"{self.home}/profile/{acc}"


class MobiDbLite:
    home = 'http://mobidb.bio.unipd.it'
    color = '#cca14a'

    def gen_link(self, acc: str):
        return f"{self.home}/entries/{acc}"


class Panther:
    home = 'http://www.pantherdb.org'
    color = '#777934'

    def gen_link(self, acc: str):
        return f"{self.home}/panther/family.do?clsAccession={acc}"


class Pfam:
    home = 'http://pfam.xfam.org'
    color = '#77b341'

    def gen_link(self, acc: str):
        return f"{self.home}/family/{acc}"


class Pirsf:
    home = 'http://pir.georgetown.edu/pirwww/dbinfo/pirsf.shtml'
    color = '#51ac7e'

    def gen_link(self, acc: str):
        return f"http://pir.georgetown.edu/cgi-bin/ipcSF?id={acc}"


class Prints:
    home = 'http://www.bioinf.manchester.ac.uk/dbbrowser/PRINTS'
    color = '#59a0d5'

    def gen_link(self, acc: str):
        return (f"http://www.bioinf.manchester.ac.uk/cgi-bin/dbbrowser/"
                f"sprint/searchprintss.cgi?prints_accn={acc}&"
                f"display_opts=Prints&category=None&"
                f"queryform=false&regexpr=off")


class PrositePatterms:
    home = 'http://prosite.expasy.org'
    color = '#596dce'

    def gen_link(self, acc: str):
        return f"{self.home}/{acc}"


class PrositeProfiles:
    home = 'http://prosite.expasy.org'
    color = '#9e76bb'

    def gen_link(self, acc: str):
        return f"{self.home}/{acc}"


class Sfld:
    home = 'http://sfld.rbvi.ucsf.edu/django'
    color = '#9958cb'

    def gen_link(self, acc: str):
        if acc.startswith('SFLDF'):
            return f"{self.home}/family/{acc[5:]}"
        elif acc.startswith('SFLDS'):
            return f"{self.home}/superfamily/{acc[5:]}"
        else:
            return f"{self.home}/subgroup/{acc[5:]}"


class Smart:
    home = 'http://smart.embl-heidelberg.de'
    color = '#cd56b5'

    def gen_link(self, acc: str):
        return self.home + '/smart/do_annotation.pl?ACC={}&BLAST=DUMMY'.format(acc)


class Superfamily:
    home = 'http://supfam.org/SUPERFAMILY'
    color = '#e288a9'

    def gen_link(self, acc: str):
        return self.home + '/cgi-bin/scop.cgi?ipid=' + acc


class Tigrfams:
    home = 'http://www.jcvi.org/cgi-bin/tigrfams/index.cgi'
    color = '#a04867'

    def gen_link(self, acc: str):
        return 'http://www.jcvi.org/cgi-bin/tigrfams/HmmReportPage.cgi?acc=' + acc


def get_database_obj(key):
    databases = {
        "cathgene3d": CathGene3D,
        "cdd": Cdd,
        "hamap": Hamap,
        "mobidblt": MobiDbLite,
        "panther": Panther,
        "pfam": Pfam,
        "pirsf": Pirsf,
        "prints": Prints,
        "profile": PrositeProfiles,
        "prosite": PrositePatterms,
        "sfld": Sfld,
        "smart": Smart,
        "ssf": Superfamily,
        "tigrfams": Tigrfams,
    }
    return databases[key]()
