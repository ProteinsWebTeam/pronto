# (Auto-)Create AI entries

This dir contains scripts for automating the retrieval of AI generated signatures from a PostgreSQL db (e.g. `INTPRO`), and generating a new entry for each retrieved signature (which is not already integrated) in the oracle db (e.g. `IPPRO`).

## Quick Start

To create entries in the oracle db (defined in `config.cfg`) for all AI generated signatures in the all InterPro member databases.

**Note:** this command will connect to the live `pronto` server

```bash
python3 create_ai_entries.py \
    <InterPro username> \
    <InterPro password> \
```

Note this connects to the live pronto server.

**To use a local run of `pronto`,** use the `--pronto` flag and provide the base url for the local run, e.g.

```bash
python3 create_ai_entries.py \
    <InterPro username> \
    <InterPro password> \
    --pronto http://127.0.0.1:5000
```

**Write out failed signature integrations to file.** By default the accession, name and short name of signatures that are not successfully integrated into IPPRO are written to STDERR. To write them to a tsv file instead (`./failed_signatures.tsv`), call the `--file` flag.

```bash
python3 create_ai_entries.py \
    <InterPro username> \
    <InterPro password> \
    --pronto http://127.0.0.1:5000 \
    --file
```

Example error file content:
Headers:
* Signature accession
* Signature name
* Signature short name
* Entry accession
* Entry name
* Entry short name

Each unique signature-entry pair is presented on a separate row.

```
SIGNATURE:PTHR48394	Interleukin-10 family cytokines	IL-10_family_cytokines	ENTRY:IPR050011	Interleukin-10 family cytokine	IL-10_family_cytokine
```

**Select a subset of member databases.** By default `create_ai_entries.py` integrates all ai generated signatures for all member databases listed in `utilities`. To define a single or subset of member databases, using the `--databases` flag, followed by a comma separated list of database names (lower case).

```bash
python3 create_ai_entries.py \
    <InterPro username> \
    <InterPro password> \
    --databases panther
```

## Options

```bash
$ python3 create_ai_entries.py -h
usage: Import AI generated data [-h] [-b BATCH_SIZE] [-c] [--databases {panther} [{panther} ...]] [--pronto PRONTO] [--request_pause REQUEST_PAUSE] [--timeout TIMEOUT]
                                username password

Automatically integrated AI-generated signatures into the IPPRO database

positional arguments:
  username              Oracle db username - used to login into pronto
  password              Oracle db password - used to login into pronto

options:
  -h, --help            show this help message and exit
  -b BATCH_SIZE, --batch_size BATCH_SIZE
                        Number of signatures to parse at a time. (default: 50000000)
  -c, --cache           Write out signatures with non-unique name/short name to a TSV file (default: False)
  --databases {panther} [{panther} ...]
                        Member databases to integrate ai generated signatures from. Default: ALL (default: ['panther'])
  --pronto PRONTO       URL of pronto - used to connect to the pronto API. (default: http://pronto.ebi.ac.uk:5000/)
  --request_pause REQUEST_PAUSE
                        Seconds to wait between payloards to the Pronto REST API (default: 1)
  --timeout TIMEOUT     Seconds timeout limit for connection to pronto (default: 10)
```