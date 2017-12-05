# Pronto!

*InterPro curation system*

Pronto is a web application aiming to assist InterPro curators by displaying protein match information for member database signatures. 
 
## Getting started

Clone this repository.

```bash
cd pronto
pip install -r requirements.txt
```

Pronto requires Python>=3.3, `cx_Oracle`, and `Flask`.

## Configuration

Edit `config.cfg`, and set the following options:

* `DEBUG` - if `True`, displays debugging information.
* `DATABASE_USER` - Oracle connection credentials (`user/password`).
* `DATABASE_HOST` - Oracle database (`host:port/service`).
* `DB_SCHEMA` - Database schema (i.e. owner of tables).
* `SECRET_KEY` - key used to sign cookies to prevent forgery.

## Usage

```bash
export PRONTO_CONFIG=/path/to/config.cfg
python pronto.py
```
