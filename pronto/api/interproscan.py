import math

from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api.interproscan", __name__, url_prefix="/api/interproscan")


"""
Relies on views IPPRO -> ISPRO

As INTERPRO:

SQL> CREATE VIEW ISPRO_ANALYSIS AS SELECT * FROM IPRSCAN.ANALYSIS@ISPRO;
SQL> GRANT SELECT ON ISPRO_ANALYSIS TO INTERPRO_SELECT;
SQL> CREATE VIEW ISPRO_ANALYSIS_JOBS AS SELECT * FROM IPRSCAN.ANALYSIS_JOBS@ISPRO;
SQL> GRANT SELECT ON ISPRO_ANALYSIS_JOBS TO INTERPRO_SELECT;
SQL> CREATE VIEW ISPRO_PROTEIN AS SELECT UPI FROM UNIPARC.PROTEIN@ISPRO;
SQL> GRANT SELECT ON ISPRO_PROTEIN TO INTERPRO_SELECT;
"""


@bp.route("/")
def get_summary():
    if request.args.get("active") is not None:
        active_condition = "AND A.ACTIVE = 'Y'"
    else:
        active_condition = ""

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT MAX(UPI)
        FROM UNIPARC.PROTEIN
        """
    )
    max_upi, = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ISPRO_PROTEIN
        WHERE UPI > :1
        """,
        [max_upi]
    )
    num_sequences, = cur.fetchone()

    cur.execute(
        F"""
        SELECT A.NAME, LOWER(D.DBSHORT), A.VERSION, 
               FLOOR((J.END_TIME - NVL(J.START_TIME, J.SUBMIT_TIME))*24*3600), 
               J.CPU_TIME, J.LIM_MEMORY, J.MAX_MEMORY
        FROM INTERPRO.ISPRO_ANALYSIS A
        INNER JOIN INTERPRO.ISPRO_ANALYSIS_JOBS J ON A.ID = J.ANALYSIS_ID
        LEFT OUTER JOIN INTERPRO.CV_DATABASE D ON A.NAME = D.DBNAME
        WHERE J.UPI_FROM > :1 AND J.END_TIME IS NOT NULL {active_condition}
        """,
        [max_upi]
    )

    analyses = {}
    for name, dbkey, version, runtime, cputime, reqmem, maxmem in cur:
        if name.lower().startswith("signalp"):
            name = "SignalP"

        key = f"{name}{version}"

        if key in analyses:
            obj = analyses[key]
        else:
            try:
                db = utils.get_database_obj(dbkey)
            except KeyError:
                color = None
            else:
                color = db.color

            obj = analyses[key] = {
                "name": name,
                "version": version,
                "color": color,
                "runtime": 0,
                "cputime": 0,
                "reqmem": None,
                "maxmem": [],
            }

        if runtime is not None:
            obj["runtime"] += runtime

        if cputime is not None:
            obj["cputime"] += cputime

        if obj["reqmem"] is None or reqmem < obj["reqmem"]:
            obj["reqmem"] = reqmem

        obj["maxmem"].append(maxmem)

    cur.close()
    con.close()

    for analysis in analyses.values():
        values = sorted(analysis["maxmem"])
        analysis["maxmem"] = {
            "q1": values[math.ceil(0.25 * len(values))],
            "q2": values[math.ceil(0.50 * len(values))],
            "q3": values[math.ceil(0.75 * len(values))],
            "avg": math.ceil(sum(values) / len(values)),
            "max": values[-1],
        }

    return jsonify({
        "databases": list(analyses.values()),
        "sequences": num_sequences
    })


@bp.route("/jobs/<string:name>/<string:version>/")
def get_jobs(name: str, version: str):
    if name.lower().startswith("signalp"):
        condition = "REGEXP_LIKE(NAME, '^SignalP')"
        params = {"version": version}
    else:
        condition = "LOWER(NAME) = LOWER(:name)"
        params = {"name": name, "version": version}

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT UPI_FROM, UPI_TO,
               FLOOR((END_TIME - NVL(START_TIME, SUBMIT_TIME))*24*3600), 
               CPU_TIME, LIM_MEMORY, MAX_MEMORY, SUCCESS
        FROM INTERPRO.ANALYSIS_JOBS J
        WHERE ANALYSIS_ID IN (
            SELECT ID
            FROM INTERPRO.ANALYSIS
            WHERE {condition}
              AND VERSION = :version
        ) 
        AND END_TIME IS NOT NULL
        """,
        params
    )

    data = {
        "failure": 0,
        "sequences": 0,
        "runtime": 0,
        "cputime": 0,
        "reqmem": [],
        "maxmem": []
    }
    total_jobs = 0
    unique_jobs = set()

    for upi_from, upi_to, run_time, cpu_time, req_mem, max_mem, success in cur:
        total_jobs += 1

        if upi_from not in unique_jobs:
            unique_jobs.add(upi_from)
            data["sequences"] += upi_to_int(upi_to) - upi_to_int(upi_from) + 1

        if success != "Y":
            data["failure"] += 1

        data["reqmem"].append(req_mem)
        data["maxmem"].append(max_mem)
        data["runtime"] += run_time
        data["cputime"] += cpu_time

    cur.close()
    con.close()

    for key in ["reqmem", "maxmem"]:
        values = sorted(data[key])
        data[key] = {
            "q1": values[math.ceil(0.25 * total_jobs)],
            "q2": values[math.ceil(0.50 * total_jobs)],
            "q3": values[math.ceil(0.75 * total_jobs)],
            "avg": math.ceil(sum(values) / total_jobs),
            "max": values[-1],
        }

    data["failure"] /= total_jobs

    return jsonify(data)


@bp.route("/jobs/running/")
def get_running_jobs():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT A.ID, A.NAME, A.VERSION, NVL(J.CNT, 0)
        FROM INTERPRO.ANALYSIS A
        LEFT OUTER JOIN (
            SELECT ANALYSIS_ID, COUNT(*) CNT
            FROM (
                SELECT A.*, 
                       ROW_NUMBER() OVER (
                           PARTITION BY ANALYSIS_ID, UPI_FROM, UPI_TO 
                           ORDER BY END_TIME DESC
                       ) RN
                FROM (
                    SELECT ANALYSIS_ID, UPI_FROM, UPI_TO, 
                           NVL(END_TIME, SYSDATE) END_TIME, SUCCESS
                    FROM INTERPRO.ANALYSIS_JOBS
                ) A
            )
            WHERE RN = 1 --AND SUCCESS != 'Y'
            GROUP BY ANALYSIS_ID
        ) J ON A.ID = J.ANALYSIS_ID
        WHERE A.ACTIVE = 'Y'
        ORDER BY A.NAME, A.ID     
        """
    )

    analyses = {}
    for _id, name, version, count in cur.fetchall():
        if name.startswith("SignalP"):
            name = "SignalP"

        if name not in analyses:
            analyses[name] = {
                version: {
                    "id": _id,
                    "name": name,
                    "version": version,
                    "count": count
                }
            }
        elif version in analyses[name]:
            analyses[name][version]["count"] += count
        else:
            analyses[name][version] = {
                "id": _id,
                "name": name,
                "version": version,
                "count": count
            }

    cur.close()
    con.close()

    results = []

    for name in sorted(analyses):
        for version in sorted(analyses[name].values(), key=lambda x: x["id"]):
            del version["id"]
            results.append(version)

    return jsonify(results)


def upi_to_int(upi):
    return int(upi[3:], 16)
