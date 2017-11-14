#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
from datetime import timedelta

import cx_Oracle
from flask import Flask, g, jsonify, request, session, redirect, render_template, url_for

app = Flask(__name__)
app.config.from_envvar('PRONTO_CONFIG')
app.permanent_session_lifetime = timedelta(days=7)


def get_db_stats():
    """
    Retrieves the number of signatures (all, integrated into InterPro, and unintegrated) for each member database.
    """

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          MIN(C.DBNAME) DBNAME,
          MIN(V.VERSION),
          COUNT(M.METHOD_AC),
          SUM(CASE WHEN ENTRY_AC IS NOT NULL  AND FEATURE_ID IS NOT NULL THEN 1 ELSE 0 END),
          SUM(CASE WHEN M.CANDIDATE != 'N' AND ENTRY_AC IS NULL AND FEATURE_ID IS NOT NULL THEN 1 ELSE 0 END)
        FROM INTERPRO.METHOD M
        LEFT OUTER JOIN INTERPRO.DB_VERSION V ON M.DBCODE = V.DBCODE
        LEFT OUTER JOIN INTERPRO.CV_DATABASE C ON V.DBCODE = C.DBCODE
        LEFT OUTER JOIN INTERPRO_ANALYSIS.FEATURE_SUMMARY FS ON M.METHOD_AC = FS.FEATURE_ID
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON E2M.METHOD_AC = M.METHOD_AC
        GROUP BY M.DBCODE
        ORDER BY DBNAME
        """
    )

    databases = [dict(zip(('name', 'version', 'n_methods', 'n_integrated', 'n_unintegrated'), row)) for row in cur]

    cur.close()

    return databases


def get_topic(topic_id):
    """
    Retrieves a topic (category of comments) from its ID.
    """

    cur = get_db().cursor()
    cur.execute('SELECT TOPIC FROM INTERPRO_ANALYSIS.PROTEIN_COMMENT_TOPIC WHERE TOPIC_ID = :1', (topic_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def get_taxon(taxon_id):
    """
    Returns taxonomic information (name, phylogenetic left/right number) from a taxon ID.
    """

    cur = get_db().cursor()
    cur.execute('SELECT FULL_NAME, LEFT_NUMBER, RIGHT_NUMBER FROM INTERPRO.ETAXI WHERE TAX_ID=:1', (taxon_id,))
    row = cur.fetchone()
    cur.close()
    return None if not row else dict(zip(('full_name', 'left_number', 'right_number'), row))


def overlap_proteins(methods, taxon, page=1, page_size=10):
    """
    Returns the protein matched by one or more signatures.
    """

    cur = get_db().cursor()

    # Preparing params
    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['left_number'] = taxon['left_number']
    params['right_number'] = taxon['right_number']

    # Get proteins matched by methods
    cur.execute(
        """
        SELECT SEQ_ID, DESCRIPTION, DBCODE, LENGTH, TAX_ID, FULL_NAME FROM (
          SELECT LEFT_NUMBER, SEQ_ID, DESCRIPTION_ID, DBCODE, LENGTH, ROWNUM RN, SEQ_CT FROM (
            SELECT LEFT_NUMBER, SEQ_ID, DESCRIPTION_ID, DBCODE, LENGTH, SEQ_CT FROM (
              SELECT
                CODE,
                LEFT_NUMBER,
                SEQ_ID,
                DESCRIPTION_ID,
                DBCODE,
                LENGTH,
                COUNT(*) OVER (PARTITION BY CODE) AS SEQ_CT,
                COUNT(DISTINCT CODE) OVER (PARTITION BY CODE) AS GLOBAL_CT,
                ROW_NUMBER() OVER (PARTITION BY CODE ORDER BY LENGTH) RNP
              FROM (
                SELECT
                  MIN(LEFT_NUMBER) as LEFT_NUMBER,
                  MIN(GLOBAL) as CODE,
                  MIN(LENGTH) as LENGTH,
                  MIN(DB) as DBCODE,
                  MIN(DESCRIPTION_ID) as DESCRIPTION_ID,
                  SEQ_ID
                FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN
                WHERE FEATURE_ID IN ({})
                AND LEFT_NUMBER BETWEEN :left_number AND :right_number
                GROUP BY SEQ_ID
              )
            )
            WHERE RNP=1
            ORDER BY SEQ_CT DESC
          )
        )
        LEFT OUTER JOIN INTERPRO_ANALYSIS.PROTEIN_DESCRIPTION_VALUE USING (DESCRIPTION_ID)
        LEFT OUTER JOIN INTERPRO_ANALYSIS.ETAXI USING (LEFT_NUMBER)
        ORDER BY SEQ_CT DESC, DBCODE, SEQ_ID

        """.format(fmt),
        params
    )

    proteins = [
        dict(
            zip(('ac', 'description', 'reviewed', 'length', 'taxon_id', 'taxon_name'), row)
        ) for row in cur
    ]

    count = len(proteins)

    if not count:
        return proteins, count  # invalid method IDs, or no methods passing the taxonomic filtering

    proteins = proteins[(page-1)*page_size:page*page_size]

    # Change SwissProt/TrEMBL for boolean indicating whether the protein has been reviewed
    for p in proteins:
        p['reviewed'] = p['reviewed'] == 'S'

    # Prepare params
    fmt = ','.join([':prot' + str(i) for i in range(len(proteins))])
    params = {'prot' + str(i): p['ac'] for i, p in enumerate(proteins)}

    # Get methods for proteins found above
    cur.execute(
        """
        SELECT
          SEQ_ID,
          E2M.ENTRY_AC,
          FEATURE_ID,
          F.DBCODE,
          F.NAME,
          M.CANDIDATE
        FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN F2S
        JOIN INTERPRO_ANALYSIS.FEATURE_SUMMARY F USING (FEATURE_ID)
        JOIN (
          SELECT DISTINCT MS1.FEATURE_ID FROM INTERPRO_ANALYSIS.MATCH_SUMMARY MS1
          WHERE SEQ_ID IN ({0})
        )
        USING (FEATURE_ID)
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON (E2M.METHOD_AC=FEATURE_ID)
        LEFT OUTER JOIN INTERPRO.METHOD M ON (M.METHOD_AC=FEATURE_ID)
        WHERE F2S.SEQ_ID IN ({0})
        ORDER BY SEQ_ID, E2M.ENTRY_AC, FEATURE_ID
        """.format(fmt),
        params
    )

    all_methods = {}
    for protein_ac, entry_ac, method_ac, dbcode, name, candidate in cur:
        if protein_ac not in all_methods:
            all_methods[protein_ac] = [{
                'ac': method_ac,
                'name': name,
                'dbcode': dbcode,
                'entry': entry_ac,
                'candidate': candidate,
                'hl': method_ac in methods
            }]
        else:
            all_methods[protein_ac].append({
                'ac': method_ac,
                'name': name,
                'dbcode': dbcode,
                'entry': entry_ac,
                'candidate': candidate,
                'hl': method_ac in methods
            })

    methods2matches = {}
    cur.execute(
        """
        SELECT PROTEIN_AC, METHOD_AC, POS_FROM, POS_TO
        FROM INTERPRO.MATCH
        WHERE PROTEIN_AC IN ({})
        """.format(fmt),
        params
    )

    for protein_ac, method_ac, pos_from, pos_to in cur:
        if protein_ac not in methods2matches:
            methods2matches[protein_ac] = {
                method_ac: [{'start': pos_from, 'end': pos_to}]
            }
        elif method_ac not in methods2matches[protein_ac]:
            methods2matches[protein_ac][method_ac] = [{'start': pos_from, 'end': pos_to}]
        else:
            methods2matches[protein_ac][method_ac].append({'start': pos_from, 'end': pos_to})

    for i, p in enumerate(proteins):
        p_ac = p['ac']

        # methods associated to the current proteins
        methods = all_methods[p_ac]

        for m in methods:
            m_ac = m['ac']
            m['matches'] = methods2matches[p_ac][m_ac]

        p['methods'] = methods

    cur.close()

    return proteins, count


def get_overlapping_entries(method):
    """
     Returns the overlapping entries, and the curators' comments for a given signature.
    """
    cur = get_db().cursor()

    # Predictions
    cur.execute(
        """
        SELECT
          FSC.FEATURE_ID,
          FSC.DBCODE,
          CV.DBSHORT,
          FSC.CT_PROT,
          FSC.N_BLOB,
          EXC.EXTRA1 EXTRAC,
          EXQ.EXTRA1 EXTRAQ,
          E.ENTRY_AC,
          E.CHECKED,
          E.ENTRY_TYPE,
          E.NAME,
          OS.CT_OVER,
          OS.N_OVER,
          OS.LEN1,
          OS.LEN2,
          P.RELATION,
          R.RELATION AS CURATED_RELATION
        FROM INTERPRO_ANALYSIS.OVERLAP_SUMMARY OS
        LEFT OUTER JOIN INTERPRO_ANALYSIS.PREDICTION P ON OS.FEATURE_ID2=P.FEATURE_ID2 AND OS.FEATURE_ID1=P.FEATURE_ID1
        LEFT OUTER JOIN INTERPRO.CURATED_RELATIONS R ON OS.FEATURE_ID2=R.FEATURE_ID2 AND OS.FEATURE_ID1=R.FEATURE_ID1
        JOIN INTERPRO_ANALYSIS.FEATURE_SUMMARY FSC ON OS.FEATURE_ID1=FSC.FEATURE_ID
        LEFT JOIN INTERPRO.CV_DATABASE CV ON CV.DBCODE=FSC.DBCODE
        JOIN INTERPRO_ANALYSIS.FEATURE_SUMMARY FSQ ON OS.FEATURE_ID2=FSQ.FEATURE_ID
        LEFT JOIN INTERPRO_ANALYSIS.EXTRA_RELATIONS EXC ON EXC.FEATURE_ID1=FSC.FEATURE_ID AND EXC.FEATURE_ID2=FSQ.FEATURE_ID
        LEFT JOIN INTERPRO_ANALYSIS.EXTRA_RELATIONS EXQ ON EXQ.FEATURE_ID1=FSQ.FEATURE_ID AND EXQ.FEATURE_ID2=FSC.FEATURE_ID
        LEFT OUTER JOIN INTERPRO_ANALYSIS.ADJACENT_RELATIONS ADJC ON ADJC.FEATURE_ID2=FSC.FEATURE_ID AND ADJC.FEATURE_ID1=FSQ.FEATURE_ID
        LEFT OUTER JOIN INTERPRO_ANALYSIS.ADJACENT_RELATIONS ADJQ ON ADJQ.FEATURE_ID2=FSQ.FEATURE_ID AND ADJQ.FEATURE_ID1=FSC.FEATURE_ID
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON E2M.METHOD_AC=OS.FEATURE_ID1
        LEFT OUTER JOIN INTERPRO.ENTRY E ON E2M.ENTRY_AC=E.ENTRY_AC
        WHERE
          ((OS.CT_OVER >= (0.3 * FSC.CT_PROT)) OR (OS.CT_OVER >= (0.3 * FSQ.CT_PROT)))
          AND OS.FEATURE_ID2=:1
        ORDER BY OS.CT_OVER DESC
        """,
        (method, )
    )

    columns = (
        'method_ac', 'dbcode', 'dbshort', 'ct_prot', 'n_blob', 'extrac', 'extraq', 'entry_ac', 'is_checked', 'type',
        'name', 'ct_over', 'n_over', 'len1', 'len2', 'relation', 'curated_relation'
    )
    methods = [dict(zip(columns, row)) for row in cur]

    # Comments
    cur.execute(
        """
        SELECT VALUE, WHO, WHEN
        FROM INTERPRO.COMMENTS
        WHERE KEY=:1 AND TYPE='integration' AND VALUE IS NOT NULL
        ORDER BY WHEN
        """,
        (method, )
    )

    comments = [dict(zip(('text', 'user', 'datetime'), row)) for row in cur]
    cur.close()

    return methods, comments


def get_taxonomy(methods, taxon, rank):
    """
    Returns the taxonomic origins of one or more signatures.
    """

    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['left_number'] = taxon['left_number']
    params['right_number'] = taxon['right_number']
    params['rank'] = rank

    cur.execute(
        """
        SELECT E.TAX_ID, FULL_NAME, FEATURE_ID, SUM(CNT) CNT
        FROM (
          SELECT FEATURE_ID, LEFT_NUMBER, COUNT(SEQ_ID) CNT
          FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({}) AND LEFT_NUMBER BETWEEN :left_number AND :right_number
          GROUP BY FEATURE_ID, LEFT_NUMBER
        ) F
        INNER JOIN (
          SELECT TAX_ID, LEFT_NUMBER
          FROM INTERPRO_ANALYSIS.TAXONOMY_RANK
          WHERE LEFT_NUMBER BETWEEN :left_number AND :right_number
          AND RANK = :rank
        ) T
        ON F.LEFT_NUMBER = T.LEFT_NUMBER
        INNER JOIN INTERPRO_ANALYSIS.ETAXI E ON T.TAX_ID = E.TAX_ID
        GROUP BY FEATURE_ID, E.TAX_ID, FULL_NAME
        """.format(fmt),
        params
    )

    taxons = {}

    for tax_id, tax_name, method_ac, count in cur:
        try:
            taxons[tax_id]
        except KeyError:
            taxons[tax_id] = {
                'id': tax_id,
                'name': tax_name,
                'methods': {}
            }
        finally:
            taxons[tax_id]['methods'][method_ac] = count

    cur.close()

    return sorted(taxons.values(), key=lambda x: -sum(x['methods'].values()))


def get_descriptions(methods, db=None):
    """
    Returns the descriptions associated to one or more signatures.
    """
    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['db'] = db

    cur.execute(
        """
        SELECT F.DESCRIPTION_ID, D.DESCRIPTION, FEATURE_ID, CT, CTMAX
        FROM (
          SELECT
            FEATURE_ID,
            DESCRIPTION_ID,
            MAX(CT) CT,
            MAX(CTMAX) CTMAX
          FROM (
            SELECT
              FEATURE_ID,
              DESCRIPTION_ID,
              COUNT(*) OVER (PARTITION BY DESCRIPTION_ID, FEATURE_ID) CT ,
              COUNT(DISTINCT SEQ_ID) OVER (PARTITION BY DESCRIPTION_ID) CTMAX
            FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN
            WHERE FEATURE_ID IN ({}) AND (DB = :db OR :db IS NULL)
          )
          GROUP BY DESCRIPTION_ID, FEATURE_ID
        ) F
        INNER JOIN INTERPRO_ANALYSIS.PROTEIN_DESCRIPTION_VALUE D ON F.DESCRIPTION_ID = D.DESCRIPTION_ID
        """.format(fmt),
        params
    )

    descriptions = {}
    for desc_id, desc, method_ac, count, count_max in cur:
        try:
            descriptions[desc_id]
        except KeyError:
            descriptions[desc_id] = {
                'id': desc_id,
                'value': desc,
                'methods': {}
            }
        finally:
            descriptions[desc_id]['methods'][method_ac] = (count, count / count_max)

    cur.close()

    return sorted(descriptions.values(), key=lambda x: -sum([cnt for cnt, cnt_max in x['methods'].values()]))


def _get_descriptions(methods, db=None):
    """
    Here be dragons. Implementation of the get_descriptions() function that also returns proteins.
    """
    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['db'] = db

    cur.execute(
        """
        SELECT F.DESCRIPTION_ID, D.DESCRIPTION, FEATURE_ID, SEQ_ID, P.NAME, E.FULL_NAME
        FROM (
          SELECT
            FEATURE_ID,
            DESCRIPTION_ID,
            SEQ_ID
          FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({}) AND (DB = :db OR :db IS NULL)
        ) F
        INNER JOIN INTERPRO_ANALYSIS.PROTEIN_DESCRIPTION_VALUE D ON F.DESCRIPTION_ID = D.DESCRIPTION_ID
        INNER JOIN INTERPRO_ANALYSIS.PROTEIN P ON P.PROTEIN_AC = F.SEQ_ID
        INNER JOIN INTERPRO_ANALYSIS.ETAXI E ON E.TAX_ID = P.TAX_ID
        """.format(fmt),
        params
    )

    descriptions = {}
    for desc_id, desc, method_ac, protein_ac, prot_name, taxon in cur:
        try:
            descriptions[desc_id]
        except KeyError:
            descriptions[desc_id] = {
                'id': desc_id,
                'value': desc,
                'proteins': set(),
                'methods': {}
            }
        finally:
            d = descriptions[desc_id]
            d['proteins'].add(protein_ac)

        try:
            d['methods'][method_ac]
        except KeyError:
            d['methods'][method_ac] = 0
        finally:
            d['methods'][method_ac] += 1

    cur.close()

    for desc_id, d in descriptions.items():
        d['proteins'] = list(d['proteins'])

    return sorted(descriptions.values(), key=lambda x: -sum(x['methods'].values()))


def get_description(desc_id):
    """
    Returns proteins associated to a given description.
    """

    cur = get_db().cursor()

    cur.execute(
        """
        SELECT P.PROTEIN_AC, P.NAME, E.FULL_NAME
        FROM INTERPRO_ANALYSIS.PROTEIN_DESCRIPTION_CODE C
        INNER JOIN INTERPRO_ANALYSIS.PROTEIN P ON C.PROTEIN_AC = P.PROTEIN_AC
        INNER JOIN INTERPRO_ANALYSIS.ETAXI E ON P.TAX_ID = E.TAX_ID
        WHERE C.DESCRIPTION_ID = :desc_id AND P.DBCODE = 'S'
        """,
        (desc_id, )
    )

    proteins = [dict(zip(('ac', 'name', 'organism'), row)) for row in cur]

    cur.close()

    return proteins


def get_go_terms(methods, category=None):
    """
    Return the GO terms associated to one or more signatures.
    """

    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['category'] = category

    cur.execute(
        """
        SELECT
          F.FEATURE_ID,
          F.TERM_GROUP_ID,
          F.SEQ_ID,
          F.DB,
          T.GO_ID,
          T.NAME,
          G.CATEGORY
        FROM (
          SELECT FEATURE_ID, TERM_GROUP_ID, SEQ_ID, DB
          FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({})
        ) F
        INNER JOIN INTERPRO_ANALYSIS.TERM_GROUP2TERM G ON F.TERM_GROUP_ID = G.TERM_GROUP_ID
        INNER JOIN INTERPRO_ANALYSIS.TERMS T ON G.GO_ID = T.GO_ID
        WHERE G.CATEGORY = :category OR :category IS NULL
        """.format(fmt),
        params
    )

    methods = {}  # count the number of reviewed/unreviewed proteins for each signature
    terms = {}
    for method_ac, group_id, protein_ac, db, go_id, term, category in cur:
        try:
            terms[go_id]
        except KeyError:
            terms[go_id] = {
                'id': go_id,
                'term': term,
                'methods': {},
                'category': category
            }
        finally:
            d = terms[go_id]['methods']

        try:
            d[method_ac]
        except KeyError:
            d[method_ac] = 0
        finally:
            d[method_ac] += 1

        try:
            methods[method_ac]
        except KeyError:
            methods[method_ac] = {'S': set(), 'T': set()}
        finally:
            methods[method_ac][db.upper()].add(protein_ac)

    cur.close()

    # Remap Swiss-Prot/TrEMBL to Reviewed/Unreviewed
    for method_ac, dbs in methods.items():
        methods[method_ac] = {
            'reviewed': len(dbs['S']),
            'unreviewed': len(dbs['T'])
        }

    return (
        sorted(terms.values(), key=lambda x: -sum(x['methods'].values())),
        methods
    )


def get_comments(methods, topic_id):
    """
    Returns comments of a given topic associated to one or more signatures.
    """

    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['topic_id'] = topic_id

    cur.execute(
        """
        SELECT
          F.FEATURE_ID,
          C.COMMENT_ID,
          C.TEXT,
          COUNT(F.SEQ_ID)
        FROM (
          SELECT FEATURE_ID, SEQ_ID
          FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({})
        ) F
        INNER JOIN (
          SELECT C.PROTEIN_AC, C.COMMENT_ID, V.TEXT
          FROM INTERPRO_ANALYSIS.PROTEIN_COMMENT_CODE C
          INNER JOIN INTERPRO_ANALYSIS.PROTEIN_COMMENT_VALUE V ON C.COMMENT_ID = V.COMMENT_ID
          WHERE C.TOPIC_ID = :topic_id AND V.TOPIC_ID = :topic_id
        ) C ON F.SEQ_ID = C.PROTEIN_AC
        GROUP BY FEATURE_ID, COMMENT_ID, TEXT
        """.format(fmt),
        params
    )

    comments = {}
    for method_ac, comment_id, comment, count in cur:
        try:
            comments[comment_id]
        except KeyError:
            comments[comment_id] = {
                'id': comment_id,
                'value': comment,
                'methods': {},
                'max': 0
            }
        finally:
            comments[comment_id]['methods'][method_ac] = count

            if count > comments[comment_id]['max']:
                comments[comment_id]['max'] = count

    cur.close()

    return sorted(comments.values(), key=lambda x: -sum(x['methods'].values()))


def get_match_matrix(methods):
    """
    Returns the overlap match matrix, and the collocation match matrix for overlapping signatures.
    """

    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}

    cur.execute(
        """
        SELECT F.FEATURE_ID, F.CT_PROT, OS.FEATURE_ID2, OS.CT_COLOC, OS.AVG_OVER, OS.CT_OVER
        FROM (
          SELECT FEATURE_ID, COUNT(DISTINCT SEQ_ID) CT_PROT
          FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({0})
          GROUP BY FEATURE_ID
        ) F
        INNER JOIN (
          SELECT FEATURE_ID1, FEATURE_ID2, CT_COLOC, AVG_OVER, CT_OVER
          FROM INTERPRO_ANALYSIS.OVERLAP_SUMMARY
          WHERE FEATURE_ID1 IN ({0}) AND FEATURE_ID2 IN ({0})
        ) OS ON F.FEATURE_ID = OS.FEATURE_ID1
        """.format(fmt),
        params
    )

    matrix = {}
    for method_ac_1, n_prot, method_ac_2, n_coloc, avg_over, n_overlap in cur:
        try:
            matrix[method_ac_1]
        except KeyError:
            matrix[method_ac_1] = {
                'prot': n_prot,
                'methods': {}
            }
        finally:
            matrix[method_ac_1]['methods'][method_ac_2] = {
                'coloc': n_coloc,
                'over': n_overlap,
                'avg_over': avg_over
            }

    cur.close()

    return matrix, max([m['prot'] for m in matrix.values()])


def get_db():
    """
    Opens a new database connection if there is none yet for the current application context.
    """

    if not hasattr(g, 'oracle_db'):
        g.oracle_db = cx_Oracle.connect(app.config['DATABASE_URI'])
    return g.oracle_db


@app.teardown_appcontext
def close_db(error):
    """
    Closes the database at the end of the request.
    """

    if hasattr(g, 'oracle_db'):
        g.oracle_db.close()


def get_user():
    """
    Get the user for the current request.
    """

    if not hasattr(g, 'user'):
        g.user = session.get('user')
    return g.user


def verify_user(username, password):
    """
    Authenticates a user with the provided credentials.
    """
    # todo: create user table in Oracle
    # todo: update activity if auth is successful

    # # Check the user account exists and is active
    # cur = get_db().cursor()
    # cur.execute("SELECT name, active "
    #             "FROM user WHERE username=:1", (username,))
    # row = cur.fetchone()
    # cur.close()

    row = ('John Doe', 'Y')

    try:
        name, activity = row
    except TypeError:
        return dict(name=None, active=False, exists=False)

    try:
        con = cx_Oracle.connect(
            user=app.config['DB_USER_PREFIX'] + username,
            password=password,
            dsn=app.config['DATABASE_URI'].rsplit('@')[-1]
        )
    except cx_Oracle.DatabaseError:
        user = dict(name=name, active=(activity == 'Y'), exists=False)
    else:
        user = dict(name=name, active=(activity == 'Y'), exists=True)
        con.close()
    finally:
        return user


def login_required(f):
    """
    Decorator for endpoints that require users to be logged in
    """
    def wrap(*args, **kwargs):
        if get_user():
            return f(*args, **kwargs)
        return redirect(url_for('index', next=request.url))

    return wrap


@app.route('/')
def index():
    """Home page."""
    return render_template('index.html',
                           databases=get_db_stats(),
                           user=get_user())


@app.route('/account')
@login_required
def account():
    """Basic test for authentication."""
    return 'Account'


@app.route('/login', methods=['GET', 'POST'])
def log_in():
    """Login page. Display a form on GET, and test the credentials on POST."""
    if get_user():
        return redirect(url_for('index'))
    elif request.method == 'GET':
        return '''
            <form method="post">
                <input type="text" name=username placeholder="User name">
                <input type="password" name=password placeholder="Password">
                <input type=submit value="Log in">
            </form>
        '''
    else:
        username = request.form['username'].strip().lower()
        password = request.form['password'].strip()
        user = verify_user(username, password)

        if user['name'] and user['exists'] and user['active']:
            # Create a signed cookie
            session.permanent = True
            session['user'] = dict(username=username, name=user['name'])
            return redirect(request.args.get('next', url_for('index')))

        # Redirect to the form
        return redirect(url_for('log_in', username=request.form['username'], active=int(user['active'])))


@app.route('/logout')
def log_out():
    """Clear the cookie, which logs the user out."""
    session.clear()
    return redirect(url_for('index'))


@app.route('/api/', strict_slashes=False)
def api_root():
    """API root, display all endpoints."""
    prog = re.compile(r'/api/([^/]+)')
    endpoints = []
    for rule in app.url_map.iter_rules():
        try:
            endpoint = prog.match(rule.rule).group(1)
        except AttributeError:
            continue
        else:
            endpoints.append(endpoint)

    return jsonify({'endpoints': sorted(endpoints)})


@app.route('/api/search', strict_slashes=False, methods=['GET'])
def api_search():
    """
    Search a given string.
    Can be an InterPro accession ("IPR" is optional), a signature accession, or a protein accession.
    Example:
    ---
    /search?s=IPR000001
    """
    search = request.args.get('s', '').upper()

    try:
        search = int(search)
    except ValueError:
        pass
    else:
        search = 'IPR{:06d}'.format(search)

    cur = get_db().cursor()
    cur.execute('SELECT COUNT(*) from INTERPRO.ENTRY WHERE ENTRY_AC=:1', (search,))
    is_entry = bool(cur.fetchone()[0])

    cur.execute('SELECT COUNT(*) from INTERPRO.METHOD WHERE METHOD_AC=:1', (search,))
    is_method = bool(cur.fetchone()[0])

    cur.execute('SELECT COUNT(*) from INTERPRO.PROTEIN WHERE PROTEIN_AC=:1', (search,))
    is_protein = bool(cur.fetchone()[0])

    methods = []
    if is_entry:
        cur.execute(
            """
            SELECT METHOD_AC, DBNAME
            FROM INTERPRO.ENTRY2METHOD E2M
            INNER JOIN INTERPRO.METHOD M USING (METHOD_AC)
            INNER JOIN INTERPRO.CV_DATABASE CV USING (DBCODE)
            WHERE ENTRY_AC=:1
            ORDER BY METHOD_AC
            """,
            (search,)
        )
        _type = 'interpro'
        methods = [dict(zip(('ac', 'db'), row)) for row in cur]
    elif is_method:
        _type = 'method'
    elif is_protein:
        _type = 'protein'
    else:
        _type = None

    cur.close()

    return jsonify({
        'type': _type,
        'methods': methods
    })


# @app.route('/api/entry/', strict_slashes=False)
# def api_entry():
#     cur = get_db().cursor()
#     cur.execute(
#         """
#         SELECT DBNAME, VERSION, ENTRY_COUNT
#         FROM INTERPRO.DB_VERSION DB
#         INNER JOIN INTERPRO.CV_DATABASE CV ON DB.DBCODE = CV.DBCODE
#         WHERE DB.DBCODE IN (SELECT DBCODE FROM INTERPRO.IPRSCAN2DBCODE)
#         ORDER BY DBNAME
#         """
#     )
#     member_dbs = [dict(zip(('name', 'version', 'count'), row)) for row in cur]
#
#     cur.execute("SELECT ENTRY_COUNT FROM INTERPRO.DB_VERSION WHERE DBCODE='I'")
#     interpro, = cur.fetchone()
#     cur.close()
#
#     return jsonify({
#         'interpro': interpro,
#         'member_databases': member_dbs
#     })


@app.route('/api/matches/<path:methods>', strict_slashes=False, methods=['GET'])
def api_matches(methods):
    """
    Overlap condensed proteins
    Example:
    ---
    /matches/PF00051/PS50070/SM00130?page=0&page_size=5
    """
    try:
        taxon_id = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon_id = 1

    try:
        page = int(request.args['page'])
        page_size = int(request.args['page_size'])
    except (KeyError, ValueError):
        page = 1
        page_size = 5
    else:
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 5

    proteins, count = overlap_proteins(
        methods=methods.split('/'),
        taxon=get_taxon(taxon_id),
        page=page,
        page_size=page_size
    )

    return jsonify({
        'count': count,
        'proteins': proteins
    })


@app.route('/api/method/<method>', methods=['GET'])
def api_prediction(method):
    """
    Signature prediction
    Example:
    ---
    /method/PF00051
    """
    methods, comments = get_overlapping_entries(method)
    return jsonify({
        'methods': methods,
        'comments': comments
    })


@app.route('/api/taxonomy/<path:methods>', strict_slashes=False, methods=['GET'])
def api_taxonomy(methods):
    """
    Taxonomic origins
    Example:
    ---
    /taxonomy/MF_00011/PF00709?rank=genus
    """
    try:
        taxon_id = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon_id = 1
    finally:
        taxon = get_taxon(taxon_id)

    ranks = (
        'superkingdom', 'kingdom', 'phylum', 'class',
        'order', 'family', 'genus', 'species'
    )
    try:
        i = ranks.index(request.args['rank'].lower())
    except (KeyError, ValueError):
        i = 0
    finally:
        rank = ranks[i]

    taxons = get_taxonomy(methods=methods.split('/'), taxon=taxon, rank=rank)

    return jsonify({
        'taxon': taxon,
        'rank': rank,
        'taxons': taxons
    })


@app.route('/api/descriptions/<path:methods>', strict_slashes=False, methods=['GET'])
def api_descriptions(methods):
    """
    Protein descriptions
    Example:
    ---
    /descriptions/PF00051/SSF47852?db=S
    """
    try:
        db = request.args['db'].upper()
    except KeyError:
        db = None
    else:
        if db not in ('S', 'T'):
            db = None

    descriptions = get_descriptions(methods=methods.split('/'), db=db)

    return jsonify({
        'descriptions': descriptions,
        'db': db,
    })


@app.route('/api/descriptions-test/<path:methods>', strict_slashes=False, methods=['GET'])
def api_descriptions_test(methods):
    """
    Protein descriptions
    Example:
    ---
    /descriptions-test/PF00051/SSF47852?db=S
    """
    try:
        db = request.args['db'].upper()
    except KeyError:
        db = None
    else:
        if db not in ('S', 'T'):
            db = None

    descriptions = _get_descriptions(methods=methods.split('/'), db=db)

    return jsonify({
        'descriptions': descriptions,
        'db': db,
    })


@app.route('/api/description/<int:desc_id>', strict_slashes=False, methods=['GET'])
def api_description(desc_id):
    """
    Proteins associated to a description
    Example:
    ---
    /description/403214
    """
    return jsonify(get_description(desc_id))


@app.route('/api/go/<path:methods>', strict_slashes=False, methods=['GET'])
def api_go(methods):
    """
    GO terms
    Example:
    ---
    /go/MF_00011/PF00709?category=C
    """
    try:
        categories = ('C', 'P', 'F')
        i = categories.index(request.args['category'].upper())
    except (KeyError, ValueError):
        category = None
    else:
        category = categories[i]

    terms, methods = get_go_terms(methods.split('/'), category)

    return jsonify({
        'terms': terms,
        'methods': methods,
        'category': category,
    })


@app.route('/api/comments/<path:methods>', strict_slashes=False, methods=['GET'])
def api_comments(methods):
    """
    Protein comments (Swiss-Prot only)
    Example:
    ---
    /comments/PTHR11846:SF3/PTHR11846:SF2/TIGR00184
    """
    try:
        # todo: accept topic title
        topic_id = int(request.args['topic'])
    except (KeyError, ValueError):
        topic_id = 34

    return jsonify({
        'topic': get_topic(topic_id),
        'comments': get_comments(methods.split('/'), topic_id)
    })


@app.route('/api/matrix/<path:methods>', strict_slashes=False, methods=['GET'])
def api_matrix(methods):
    """
    Match matrix of overlapping signatures
    Example:
    ---
    /matrix/SSF57440/cd00108/PIRSF500183/PTHR19331:SF315/PTHR44106:SF1
    """
    matrix, max_prot = get_match_matrix(methods.split('/'))
    return jsonify({
        'matrix': matrix,
        'max': max_prot
    })


@app.route('/api/comment/<key>', strict_slashes=False, methods=['GET', 'POST'])
def api_comment(key):
    if request.method == 'POST':
        # add a comment
        pass
    else:
        pass
    return ''


if __name__ == '__main__':
    app.run()

