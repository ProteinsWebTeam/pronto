# Pronto!

*InterPro curation system*

Pronto is a web application aiming to assist InterPro curators by displaying protein match information for member database signatures. 
 
## Getting started

Pronto requires Python>=3.3, `cx_Oracle`, and `Flask`.

```bash
git clone https://github.com/ProteinsWebTeam/pronto.git
cd pronto
pip install -r requirements.txt
```

## Configuration

Edit `config.cfg`, and set the following options:

* `DEBUG` - if `True`, displays debugging information, and restart the application when the code changes.
* `DATABASE_USER` - Oracle connection credentials (`user/password`).
* `DATABASE_HOST` - Oracle database (`host:port/service`).
* `DB_SCHEMA` - Database schema (i.e. owner of tables).
* `SECRET_KEY` - key used to sign cookies (prevent forgery).

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
python pronto.py
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
