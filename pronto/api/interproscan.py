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
    upi_from = request.args.get("from")
    upi_to = request.args.get("to")
    num_sequences = int(request.args.get("sequences", "1000000"))

    con = utils.connect_oracle()
    cur = con.cursor()

    if not upi_from:
        if upi_to:
            cond = "WHERE UPI <= :upito"
            params = dict(upito=upi_to, nseqs=num_sequences)
        else:
            cond = ""
            params = dict(nseqs=num_sequences)

        cur.execute(
            f"""
            SELECT MIN(UPI)
            FROM (
                SELECT P.UPI
                FROM (
                    SELECT UPI
                    FROM INTERPRO.ISPRO_PROTEIN
                    {cond}
                    ORDER BY UPI DESC
                ) P
                WHERE ROWNUM <= :nseqs
            )
            """,
            params
        )
        upi_from, = cur.fetchone()

    if name == "SignalP":
        name_cond = "LIKE"
        params = ["signalp%", version]
    else:
        name_cond = "="
        params = [name.lower(), version]

    if upi_to:
        upi_cond = "BETWEEN :3 AND :4"
        params += [upi_from, upi_to]
    else:
        upi_cond = ">= :3"
        params.append(upi_from)

    cur.execute(
        f"""
        SELECT J.START_TIME, J.END_TIME, J.CPU_TIME, J.LIM_MEMORY, J.MAX_MEMORY,
               J.SEQUENCES
        FROM INTERPRO.ISPRO_ANALYSIS A
        INNER JOIN INTERPRO.ISPRO_ANALYSIS_JOBS J ON A.ID = J.ANALYSIS_ID
        WHERE LOWER(A.NAME) {name_cond} :1 
          AND A.VERSION = :2 
          AND J.UPI_TO {upi_cond} 
          AND J.END_TIME IS NOT NULL
          AND J.SUCCESS = 'Y'
          AND J.SEQUENCES IS NOT NULL
          AND J.SEQUENCES > 0
        """,
        params
    )

    results = {
        "name": name,
        "version": version,
        "color": utils.get_database_obj(name).color,
        "runtime": 0,
        "cputime": 0,
        "reqmem": None,
        "maxmem": [],
        "proteins": {
            "from": upi_from,
            "to": upi_to,
            "count": 0
        }
    }

    for start_time, end_time, cpu_time, req_mem, max_mem, num_sequences in cur:
        runtime = (end_time - start_time).total_seconds()

        results["runtime"] += math.floor(runtime)
        results["cputime"] += cpu_time
        if results["reqmem"] is None or req_mem < results["reqmem"]:
            results["reqmem"] = req_mem

        results["maxmem"].append(max_mem)
        results["proteins"]["count"] += num_sequences

    cur.close()
    con.close()

    values = sorted(results.pop("maxmem"))

    if len(values):
        q1 = values[math.ceil(0.25 * len(values))]
        med = values[math.ceil(0.50 * len(values))]
        q3 = values[math.ceil(0.75 * len(values))]
        iqr = q3 - q1  # Interquartile range

        low = high = None
        for val in values:
            if low is None and val >= (q1 - 1.5 * iqr):
                # `and` is NOT and error: we want the smallest value
                # that verifies the condition
                low = val

            if high is None or high < val <= (q3 + 1.5 * iqr):
                high = val

        results["maxmem"] = {
            "min": values[0],
            "low": low,
            "q1": q1,
            "q2": med,
            "q3": q3,
            "avg": math.ceil(sum(values) / len(values)),
            "high": high,
            "max": values[-1],
        }
    else:
        results["maxmem"] = None

    return jsonify(results)
