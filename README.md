# Pronto!

*InterPro curation system*

Pronto is a web application aiming to assist InterPro curators by displaying protein match information for member database signatures. 
 
## Getting started

### Prerequisites

- Python>=3.3 with `cx_Oracle`, `Flask`, and `mysqlclient`.
- A public database link to the `LITPUB` database (literature service) must exist.

### Installation

```bash
git clone https://github.com/ProteinsWebTeam/pronto.git
cd pronto
pip install -r requirements.txt
python setup.py install
```

## Configuration

Edit `config.cfg`, and set the following options:

* `ORACLE_DB` - Oracle connection details (dictionary; keys: `dsn`, `credentials`).
* `MYSQL_DB` - InterPro7 MySQL database (dictionary; keys: `host`, `user`, `passwd`, `port`, `db`).
* `DB_SCHEMA` - Oracle database schema (i.e. owner of tables).
* `SECRET_KEY` - key used to sign cookies (prevent forgery).
* `PREFIX` - URL prefix to use for internal links and API calls.

### Generate secret key

Open a Python terminal and run:

```python
import os
os.urandom(16)
```

Copy the string and paste it into the config file.

## Usage

Pronto relies on the file the `PRONTO_CONFIG` environment variable points to. On Linux or OS X, you can set this environment variable with:
  
```bash
export PRONTO_CONFIG=/path/to/config.cfg
```

### Built-in server

*Easy to use and convenient for development, but not suitable for production.*

```bash
export FLASK_APP=pronto
flask run
```

### Gunicorn

After installing [Gunicorn](http://gunicorn.org/), run the command below to start Pronto with four worker processes:

```bash
gunicorn -w 4 -b 127.0.0.1:5000 pronto:app
```

To accept connections from all your network (i.e. not only your local machine), and detach the server from the terminal:  

```bash
gunicorn --daemon -w 4 -b 0.0.0.0:5000 pronto:app
# To kill the process:
# kill `ps aux |grep gunicorn | grep pronto | awk '{print $2}'`
```
