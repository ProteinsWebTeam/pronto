# Pronto!

*InterPro curation system*

Pronto is web application aiming to help InterPro curators by displaying protein match information for member database signatures.
 
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
* `SERVER_NAME` - the name and port of the web server.
* `DATABASE_URI` - Oracle connection string (`user/password@host:port/service`).
* `DB_USER_PREFIX` - prefix in database user names.
* `SECRET_KEY` - key used to sign cookies to prevent forgery.

## Usage

```bash
export PRONTO_CONFIG=config.cfg
python pronto.py
```
