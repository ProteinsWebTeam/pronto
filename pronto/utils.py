import gzip
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import cx_Oracle
import MySQLdb
import psycopg2
from flask import current_app


SIGNATURES = [
    r"G3DSA:[\d.]{4,}",     # CATH-Gene3D
    r"MF_\d{4,}",           # HAMAP
    r"PF\d{5,}",            # Pfam
    r"PIRSF\d{4,}",         # PIRSF
    r"PR\d{4,}",            # PROSITE
    r"PS\d{4,}",            # PROSITE
    r"PTHR\d{4,}",          # PANTHER
    r"SFLD[FGS]\d{4,}",     # SFLD
    r"SM\d{4,}",            # SMART
    r"SSF\d{4,}",           # SUPERFAMILY
    r"TIGR\d{4,}",          # TIGRFAMs
    r"cd\d{4,}",            # CDD
    r"sd\d{4,}"             # CDD
]


XREFS = {
    "CATHGENE3D": "http://www.cathdb.info/superfamily/{}",
    "CAZY": "http://www.cazy.org/fam/{}.html",
    # "COG": "http://www.ncbi.nlm.nih.gov/COG/new/release/cow.cgi?cog={}",
    "COG": "https://ftp.ncbi.nih.gov/pub/COG/COG2014/static/byCOG/{}.html",
    # "EC": "http://www.ebi.ac.uk/intenz/query?cmd=SearchEC&ec={}",
    "INTENZ": "http://www.ebi.ac.uk/intenz/query?cmd=SearchEC&ec={}",
    "GENPROP": "https://www.ebi.ac.uk/interpro/genomeproperties/#{}",
    "INTERPRO": "/entry/{}",
    "MIM": "https://www.omim.org/entry/{}",
    "PDBE": "http://www.ebi.ac.uk/pdbe/entry/pdb/{}",
    "PFAM": "https://www.ebi.ac.uk/interpro/entry/pfam/{}",
    "PIRSF": "http://pir.georgetown.edu/cgi-bin/ipcSF?id={}",
    "PROSITE": "https://prosite.expasy.org/{}",
    "PROSITEDOC": "https://prosite.expasy.org/{}",
    "SSF": "http://supfam.org/SUPERFAMILY/cgi-bin/scop.cgi?ipid={}",
    "SUPERFAMILY": "http://supfam.org/SUPERFAMILY/cgi-bin/scop.cgi?ipid={}",
    "SWISSPROT": "https://www.uniprot.org/uniprotkb/{}/entry",
    "TIGRFAMS": "https://www.ncbi.nlm.nih.gov/genome/annotation_prok/evidence/{}/"
}


class Executor:
    def __init__(self):
        self._executor = ThreadPoolExecutor()
        self._submit = self._executor.submit

    @staticmethod
    def _run_task(url: str, task_id: str, fn: Callable, *args, **kwargs):
        result = None
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            status = 'N'
        else:
            status = 'Y'

        result_obj = gzip.compress(json.dumps(result).encode("utf-8"))

        con = cx_Oracle.connect(url)
        cur = con.cursor()
        cur.execute(
            """
            UPDATE INTERPRO.PRONTO_TASK
            SET
                FINISHED = SYSDATE,
                STATUS = :1,
                RESULT = :2
            WHERE ID = :3
            """, (status, result_obj, task_id)
        )
        con.commit()
        cur.close()
        con.close()

    @staticmethod
    def _get_task_from_tuple(t: tuple):
        try:
            lob = t[6]
        except IndexError:
            lob = None

        if lob:
            result = json.loads(gzip.decompress(lob.read()).decode("utf-8"))
        else:
            result = None

        return {
            "id": t[0],
            "name": t[1],
            "user": t[2],
            "start_time": t[3].strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": t[4].strftime("%Y-%m-%d %H:%M:%S") if t[4] else None,
            "success": t[5] == 'Y' if t[5] is not None else None,
            "result": result
        }

    def get_tasks(self, task_id: Optional[str] = None,
                  task_name: Optional[str] = None,
                  task_prefix: Optional[str] = None,
                  seconds: int = 0, get_result: bool = True) -> List[dict]:
        columns = ["T.ID", "T.NAME AS TASK_NAME", "U.NAME AS USER_NAME",
                   "T.STARTED", "T.FINISHED", "T.STATUS"]
        if get_result:
            columns.append("T.RESULT")

        if task_id:
            cond = "T.ID = :1"
            params = [task_id]
        elif task_name:
            cond = "T.NAME = :1"
            params = [task_name]
        elif task_prefix:
            cond = "T.NAME LIKE :1"
            params = [task_prefix + "%"]
        else:
            cond = "T.FINISHED IS NULL"
            params = []
            if seconds > 0:
                cond += (f" OR T.STARTED >= SYSDATE - INTERVAL '{seconds}' "
                         f"SECOND")

        con = connect_oracle()
        cur = con.cursor()

        cur.execute(
            f"""
            SELECT {', '.join(columns)}
            FROM INTERPRO.PRONTO_TASK T
              INNER JOIN INTERPRO.PRONTO_USER U
              ON T.USERNAME = U.DB_USER
            WHERE {cond}
            ORDER BY T.STARTED
            """, params
        )
        tasks = [self._get_task_from_tuple(row) for row in cur.fetchall()]
        cur.close()
        con.close()
        return tasks

    def submit(self, url: str, name: str,
               fn: Callable, *args, **kwargs) -> dict:
        """

        :param url: Oracle connection string/URL
        :param name: task name
        :param fn: function to execute
        :param args: positional arguments for `fn`
        :param kwargs: keywords arguments for `fn`
        :return: task
        """

        tasks = self.get_tasks(task_name=name, get_result=False)
        if tasks and tasks[-1]["end_time"] is None:
            # Running task: we do not submit an other one
            return tasks[-1]

        task_id = uuid.uuid1().hex

        # Insert task in database
        con = cx_Oracle.connect(url)
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO INTERPRO.PRONTO_TASK (ID, NAME, USERNAME, STARTED)
            VALUES (:1, :2, USER, SYSDATE)
            """, (task_id, name)
        )
        con.commit()
        cur.close()
        con.close()

        # Get new task
        tasks = self.get_tasks(task_name=name, get_result=False)

        # Submit task to thread pool
        self._submit(self._run_task, url, task_id, fn, *args, **kwargs)

        return tasks[-1]


executor = Executor()


def connect_oracle() -> cx_Oracle.Connection:
    return cx_Oracle.connect(current_app.config["ORACLE_IP"])


def connect_oracle_auth(user: dict) -> cx_Oracle.Connection:
    # input format:  app_user/app_passwd@[host:port]/service
    dsn = current_app.config["ORACLE_IP"].rsplit('@', 1)[-1]
    return cx_Oracle.connect(user["dbuser"], user["password"], dsn)


def get_oracle_url(user: dict) -> str:
    dsn = current_app.config["ORACLE_IP"].rsplit('@', 1)[-1]
    return f"{user['dbuser']}/{user['password']}@{dsn}"


def get_oracle_dsn():
    return current_app.config["ORACLE_IP"].rsplit('@', 1)[-1]


def get_oracle_goa_url() -> str:
    return current_app.config["ORACLE_GOA"]


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


class DefaultDatabase:
    home = None
    color = "#7F8C8D"

    def gen_link(self, *args):
        return None


class CathGene3D:
    home = 'http://www.cathdb.info'
    color = '#d9417c'

    def gen_link(self, acc: str):
        m = re.match(r'G3DSA:(.+)', acc)
        return f"{self.home}/superfamily/{m.group(1)}"


class Cdd:
    base = "//www.ncbi.nlm.nih.gov/Structure/cdd"
    home = f"{base}/cdd.shtml"
    color = '#c6554b'

    def gen_link(self, acc: str):
        return f"{self.base}/cddsrv.cgi?uid={acc}"


class FunFam:
    home = '//www.cathdb.info'
    color = '#d9417c'

    def gen_link(self, acc: str):
        # G3DSA:3.40.640.10:FF:000006
        m = re.match(r"G3DSA:([0-9.]+):FF:(\d+)", acc)
        fam_acc, funfam_acc = m.groups()
        return f"{self.home}/superfamily/{fam_acc}/funfam/{int(funfam_acc)}"


class Hamap:
    home = 'http://hamap.expasy.org'
    color = '#ce672d'

    def gen_link(self, acc: str):
        return f"{self.home}/profile/{acc}"


class MobiDbLite:
    home = '//mobidb.bio.unipd.it'
    color = '#cca14a'

    def gen_link(self, acc: str):
        return f"{self.home}/{acc}"


class Panther:
    home = 'http://www.pantherdb.org'
    color = '#777934'

    def gen_link(self, acc: str):
        return f"{self.home}/panther/family.do?clsAccession={acc}"


class Pfam:
    home = 'https://www.ebi.ac.uk/interpro'
    color = '#77b341'

    def gen_link(self, acc: str):
        return f"{self.home}/entry/pfam/{acc}"


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
    home = 'http://sfld.rbvi.ucsf.edu/archive/django'
    color = '#9958cb'

    def gen_link(self, acc: str):
        if acc.startswith('SFLDF'):
            return f"{self.home}/family/{int(acc[5:])}"
        elif acc.startswith('SFLDS'):
            return f"{self.home}/superfamily/{int(acc[5:])}"
        else:
            return f"{self.home}/subgroup/{int(acc[5:])}"


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
    home = "https://www.ncbi.nlm.nih.gov/genome/annotation_prok/tigrfams/"
    color = '#a04867'

    def gen_link(self, acc: str):
        return f"https://www.ncbi.nlm.nih.gov/genome/annotation_prok/evidence/{acc}/"


def get_database_obj(key: str):
    databases = {
        "cathgene3d": CathGene3D,
        "cath-gene3d": CathGene3D,
        "cdd": Cdd,
        "funfam": FunFam,
        "hamap": Hamap,
        "mobidblt": MobiDbLite,
        "mobidb lite": MobiDbLite,
        "panther": Panther,
        "pfam": Pfam,
        "pirsf": Pirsf,
        "prints": Prints,
        "profile": PrositeProfiles,
        "prosite profiles": PrositeProfiles,
        "prosite": PrositePatterms,
        "prosite patterns": PrositePatterms,
        "sfld": Sfld,
        "smart": Smart,
        "ssf": Superfamily,
        "superfamily": Superfamily,
        "tigrfams": Tigrfams,
    }

    try:
        return databases[key.lower()]()
    except KeyError:
        return DefaultDatabase()


@dataclass
class Prediction:
    a: int  # sample A
    b: int  # sample B
    i: int  # intersection A & B
    similarity: float = field(init=False)
    containment_a: float = field(init=False)
    containment_b: float = field(init=False)
    relationship: Optional[str] = field(init=False)

    def __post_init__(self):
        try:
            self.similarity = self.i / (self.a + self.b - self.i)
        except ZeroDivisionError:
            self.similarity = 1

        try:
            self.containment_a = self.i / self.a
        except ZeroDivisionError:
            self.containment_a = 0

        try:
            self.containment_b = self.i / self.b
        except ZeroDivisionError:
            self.containment_b = 0

        if self.similarity >= 0.75:
            self.relationship = "similar"
        elif self.containment_a >= 0.75:
            if self.containment_b >= 0.75:
                self.relationship = "related"
            else:
                self.relationship = "child"  # A child of B
        elif self.containment_b >= 0.75:
            self.relationship = "parent"  # A parent of B
        else:
            self.relationship = None

    @property
    def containment(self) -> float:
        if self.similarity == "related":
            return min(self.containment_a, self.containment_b)
        elif self.similarity == "child":
            return self.containment_a
        elif self.similarity == "parent":
            return self.containment_b
        return 0


def predict_relationship(a: int, b: int, intersection: int) -> tuple:
    similarity = intersection / (a + b - intersection)

    if similarity >= 0.75:
        return similarity, "similar"

    containment_a = intersection / a
    containment_b = intersection / b
    if containment_a >= 0.75:
        if containment_b >= 0.75:
            return min(containment_a, containment_b), "related"
        return containment_a, "child"  # A child of B
    elif containment_b >= 0.75:
        return containment_b, "parent"  # A parent of B
    return 0, "none"

