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
def get_analyses():
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT NAME, VERSION, ACTIVE
        FROM INTERPRO.ISPRO_ANALYSIS
        """
    )

    results = {}
    for name, version, active in cur:
        if name.lower().startswith("signalp"):
            name = "SignalP"

        key = f"{name}{version}"
        results[key] = {
            "name": name,
            "version": version,
            "active": active == "Y"
        }

    cur.close()
    con.close()
    return jsonify(list(results.values()))


@bp.route("/<string:name>/<string:version>/")
def get_analysis(name: str, version: str):
    num_sequences = int(request.args.get("sequences", "1000000"))

    results = {
        "name": name,
        "version": version,
        "color": utils.get_database_obj(name).color,
        "runtime": 0,
        "cputime": 0,
        "reqmem": None,
        "maxmem": [],
        "sequences": 0
    }

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT MIN(UPI)
        FROM (
            SELECT P.UPI
            FROM (
                SELECT UPI
                FROM INTERPRO.ISPRO_PROTEIN
                ORDER BY UPI DESC
            ) P
            WHERE ROWNUM <= :1
        )
        """,
        [num_sequences]
    )
    upi_from, = cur.fetchone()

    if name == "SignalP":
        comp = "LIKE"
        params = ["SignalP%", version, upi_from]
    else:
        comp = "="
        params = [name, version, upi_from]

    cur.execute(
        f"""
        SELECT J.START_TIME, J.END_TIME, J.CPU_TIME, J.LIM_MEMORY, J.MAX_MEMORY,
               J.SEQUENCES
        FROM INTERPRO.ISPRO_ANALYSIS A
        INNER JOIN INTERPRO.ISPRO_ANALYSIS_JOBS J ON A.ID = J.ANALYSIS_ID
        WHERE A.NAME {comp} :1 
          AND A.VERSION = :2 
          AND J.UPI_TO >= :3 
          AND J.END_TIME IS NOT NULL
          AND J.SUCCESS = 'Y'
          AND J.SEQUENCES IS NOT NULL
          AND J.SEQUENCES > 0
        """,
        params
    )

    for start_time, end_time, cpu_time, req_mem, max_mem, num_sequences in cur:
        runtime = (end_time - start_time).total_seconds()

        results["runtime"] += math.floor(runtime)
        results["cputime"] += cpu_time
        if results["reqmem"] is None or req_mem < results["reqmem"]:
            results["reqmem"] = req_mem

        results["maxmem"].append(max_mem)
        results["sequences"] += num_sequences

    cur.close()
    con.close()

    values = sorted(results.pop("maxmem"))

    if len(values):
        results["maxmem"] = {
            "min": values[0],
            "q1": values[math.ceil(0.25 * len(values))],
            "q2": values[math.ceil(0.50 * len(values))],
            "q3": values[math.ceil(0.75 * len(values))],
            "avg": math.ceil(sum(values) / len(values)),
            "max": values[-1],
        }
    else:
        results["maxmem"] = None

    return jsonify(results)
