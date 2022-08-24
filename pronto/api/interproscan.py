import math

from flask import Blueprint, jsonify, request

from pronto import utils


bp = Blueprint("api.interproscan", __name__, url_prefix="/api/interproscan")


@bp.route("/")
def get_analyses():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT NAME, VERSION 
        FROM IPRSCAN.ANALYSIS@ISPRO
        ORDER BY ID
        """
    )

    analyses = {}
    for name, version in cur.fetchall():
        if name.startswith("SignalP"):
            name = "SignalP"

        try:
            analyses[name]["versions"].append(version)
        except KeyError:
            analyses[name] = {"name": name, "versions": [version]}

    cur.close()
    con.close()

    return jsonify(sorted(analyses.values(), key=lambda x: x["name"]))


@bp.route("/jobs/<string:name>/<string:version>/")
def get_jobs(name: str, version: str):
    if name.lower().startswith("signalp"):
        condition = "REGEXP_LIKE(NAME, '^SignalP')"
        params = {"version": version}

        """
        SignalP is made of three analyses, so for each sequences, we need
        to run three jobs so it takes three times more time
        """
        time_factor = 3
    else:
        condition = "LOWER(NAME) = LOWER(:name)"
        params = {"name": name, "version": version}
        time_factor = 1

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT UPI_FROM, UPI_TO, 
               FLOOR((END_TIME - NVL(START_TIME, SUBMIT_TIME))*24*3600), 
               CPU_TIME, LIM_MEMORY, MAX_MEMORY, SUCCESS
        FROM IPRSCAN.ANALYSIS_JOBS@ISPRO J
        WHERE END_TIME IS NOT NULL
        AND ANALYSIS_ID IN (
            SELECT ID
            FROM IPRSCAN.ANALYSIS@ISPRO
            WHERE {condition}
              AND VERSION = :version
        )
        """,
        params
    )

    data = {
        "runtime": [],
        "cputime": [],
        "reqmem": [],
        "maxmem": [],
        "failure_rate": 0
    }

    for upi_from, upi_to, run_time, cpu_time, req_mem, max_mem, success in cur:
        data["runtime"].append(run_time)
        data["cputime"].append(cpu_time)
        data["reqmem"].append(req_mem)
        data["maxmem"].append(max_mem)
        if success != "Y":
            data["failure_rate"] += 1

    cur.close()
    con.close()

    num_jobs = len(data["runtime"])
    data["failure_rate"] /= num_jobs

    for key in ["runtime", "cputime"]:
        values = sorted(data[key])
        data[key] = {
            "max": values[-1],
            "med": values[math.ceil(0.50 * num_jobs)],
            "avg": math.ceil(sum(values) / (num_jobs / time_factor)),
        }

    for key in ["reqmem", "maxmem"]:
        values = sorted(data[key])
        data[key] = {
            "max": values[-1],
            "med": values[math.ceil(0.50 * num_jobs)],
            "avg": math.ceil(sum(values) / num_jobs),
        }

    return jsonify(data)


@bp.route("/jobs/running/")
def get_running_jobs():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT A.ID, A.NAME, A.VERSION, NVL(J.CNT, 0)
        FROM IPRSCAN.ANALYSIS@ISPRO A
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
                    FROM IPRSCAN.ANALYSIS_JOBS@ISPRO
                ) A
            )
            WHERE RN = 1 AND SUCCESS != 'Y'
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
