# (Auto-)Create AI entries

This dir contains scripts for automating the retrieval of AI generated signatures from a PostgreSQL db (e.g. `INTPRO`), and generating a new entry for each retrieved signature (which is not already integrated) in the oracle db (e.g. `IPPRO`), using the `pronto` API.

## Automated signature integration decision process

1. Is the human-curated data complete?
  - Yes:
    - Use human data --> leave for curators
  - No:
    2. Is AI data available?
    - Yes:
      - Use AI generated data --> auto-generate signature
    - No:
      - Use human data --> leave for curators

This means that even in cases where only one piece (from name, short-name and abstract) from the human-curatored data is missing, an 
entry will be automatically generated using the AI-generated data (when available).

## Quick Start

To create entries in the oracle db for *all* AI generated signatures in the *all* InterPro member databases:

1. Set your oracle db and password as environment variables
```bash
export PRONTO_USER="example-username"
export PRONTO_PWD="dummy-password"
```

2. Run `create_ai_entries`:
```bash
python3 create_ai_entries.py
```

**Note:** this command will connect to the live `pronto` server

**To use a local run of `pronto`,** use the `--pronto` flag and provide the base url for the local run, e.g.

```bash
python3 create_ai_entries.py \
    --pronto http://127.0.0.1:5000
```

**Write out failed signature integrations to file.** By default the accession, name and short name of signatures that are not successfully integrated into IPPRO are written to STDERR. To write them to a tsv file instead (`./failed_signatures.tsv`), call the `--file` flag.

```bash
python3 create_ai_entries.py \
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

Signatures whose short-names are tool long (i.e. longer than 30 characters) are also written to STDERR or this error file.

Each unique signature-entry pair is presented on a separate row.

```
SIGNATURE:PTHR48394	Interleukin-10 family cytokines	IL-10_family_cytokines	ENTRY:IPR050011	Interleukin-10 family cytokine	IL-10_family_cytokine
```

**Select a subset of member databases.** By default `create_ai_entries.py` integrates all ai generated signatures for all member databases listed in `utilities`. To define a single or subset of member databases, using the `--databases` flag, followed by a comma separated list of database names (lower case).

```bash
python3 create_ai_entries.py \
    --databases panther
```

## Options

```bash
$ python3 create_ai_entries.py -h
usage: Import AI generated data [-h] [-b BATCH_SIZE] [-c] [--databases {panther,ncbifam,cathgene3d} [{panther,ncbifam,cathgene3d} ...]] [--pronto PRONTO] [--request_pause REQUEST_PAUSE]
                                [--timeout TIMEOUT]

Automatically integrated AI-generated signatures into the IPPRO database

options:
  -h, --help            show this help message and exit
  -b BATCH_SIZE, --batch_size BATCH_SIZE
                        Number of signatures to parse at a time. (default: 50000000)
  -c, --cache           Write out signatures with non-unique name/short name to a TSV file (default: False)
  --databases {panther,ncbifam,cathgene3d} [{panther,ncbifam,cathgene3d} ...]
                        Member databases to integrate ai generated signatures from. Default: ALL (default: ['panther', 'ncbifam', 'cathgene3d'])
  --pronto PRONTO       URL of pronto - used to connect to the pronto API. (default: http://pronto.ebi.ac.uk:5000)
  --request_pause REQUEST_PAUSE
                        Seconds to wait between payloards to the Pronto REST API (default: 1)
  --timeout TIMEOUT     Seconds timeout limit for connection to pronto (default: 10)
```
