#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import re
import urllib.error
import urllib.parse
import urllib.request

import cx_Oracle
from flask import g, session

from pronto import app
from . import xref


RANKS = (
    'superkingdom',
    'kingdom',
    'phylum',
    'class',
    'order',
    'family',
    'genus',
    'species'
)


def get_user():
    """
    Get the user for the current request.
    """

    if not hasattr(g, 'user'):
        g.user = session.get('user')
    return g.user


def get_db():
    """
    Opens a new database connection if there is none yet for the current application context.
    """

    if not hasattr(g, 'oracle_db'):
        user = get_user()
        try:
            credentials = user['dbuser'] + '/' + user['password']
        except (TypeError, KeyError):
            credentials = app.config['DATABASE_USER']
        finally:
            uri = credentials + '@' + app.config['DATABASE_HOST']

        g.oracle_db = cx_Oracle.connect(uri, encoding='utf-8', nencoding='utf-8')
    return g.oracle_db


def search(query, page=1, page_size=20):
    """
    Search a given string.
    Can be an InterPro accession ("IPR" is optional), a signature accession, or a protein accession.

    Args:
        query:
        page:
        page_size:

    Returns:

    """
    # From DB
    entry_accs = []
    methods_accs = []
    proteins_accs = []

    # From EBIsearch
    hits = []
    hit_count = 0

    cur = get_db().cursor()

    if query:
        for term in query.split():
            try:
                term = int(term)
            except ValueError:
                pass
            else:
                term = 'IPR{:06d}'.format(term)

            cur.execute('SELECT ENTRY_AC FROM INTERPRO.ENTRY WHERE ENTRY_AC = :1', (term.upper(),))
            row = cur.fetchone()
            if row:
                entry_accs.append(row[0])
                continue

            cur.execute('SELECT METHOD_AC from INTERPRO.METHOD WHERE UPPER(METHOD_AC) = :1', (term.upper(),))
            row = cur.fetchone()
            if row:
                methods_accs.append(row[0])
                continue

            cur.execute(
                'SELECT PROTEIN_AC from {}.PROTEIN WHERE PROTEIN_AC = :1 OR NAME = :1'.format(app.config['DB_SCHEMA']),
                (term.upper(),)
            )
            row = cur.fetchone()
            if row:
                proteins_accs.append(row[0])
                continue

        cur.close()

        params = urllib.parse.urlencode({
            'query': query,
            'format': 'json',
            'fields': 'id,name,type',
            'size': page_size,
            'start': (page - 1) * page_size
        })

        try:
            req = urllib.request.urlopen('http://www.ebi.ac.uk/ebisearch/ws/rest/interpro?{}'.format(params))
            res = json.loads(req.read().decode())
        except (urllib.error.HTTPError, json.JSONDecodeError):
            pass
        else:
            hit_count = res['hitCount']
            for e in res['entries']:
                hits.append({
                    'id': e['id'],
                    'name': e['fields']['name'][0],  # EBI search returns an array of name/type fields
                    'type': e['fields']['type'][0][0].upper()
                    # Take the first char only (will display a label on client)
                })

    return {
        'entries': list(sorted(set(entry_accs))),
        'methods': list(sorted(set(methods_accs))),
        'proteins': proteins_accs,

        'ebiSearch': {
            'hits': hits,
            'hitCount': hit_count,
            'page': page,
            'pageSize': page_size
        }
    }


def get_feed(n=20):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT *
        FROM (
          SELECT U.NAME, EM.TIMESTAMP, EM.METHOD_AC, EM.ENTRY_AC, E.ENTRY_TYPE
          FROM INTERPRO.ENTRY2METHOD_AUDIT EM
            INNER JOIN INTERPRO.ENTRY E ON EM.ACTION = 'I' AND EM.ENTRY_AC = E.ENTRY_AC
            INNER JOIN INTERPRO.USER_PRONTO U ON EM.DBUSER = U.DB_USER
          ORDER BY EM.TIMESTAMP DESC
        ) WHERE ROWNUM <= :1
        """,
        (n,)
    )

    events = []
    for row in cur:
        events.append({
            'user': row[0].split()[0],
            'timestamp': row[1].timestamp(),
            'event': (
                'integrated <a href="/method/{0}/">{0}</a> '
                'into <a href="/entry/{1}/" class="type-{2}">{1}</a>'.format(
                    row[2], row[3], row[4]
                )
            )
        })

    cur.close()

    return {
        'count': len(events),
        'results': events
    }


def get_protein(protein_ac):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          P.NAME,
          P.LEN,
          P.DBCODE,
          P.TAX_ID,
          E.FULL_NAME,
          E.SCIENTIFIC_NAME,
          P.FRAGMENT
        FROM {0}.PROTEIN P
        LEFT OUTER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        WHERE PROTEIN_AC = :1
        """.format(app.config['DB_SCHEMA']),
        (protein_ac, )
    )

    row = cur.fetchone()

    if not row:
        return None

    protein = {
        'id': protein_ac,
        'name': row[0],
        'length': row[1],
        'isReviewed': row[2] == 'S',
        'link': ('http://sp.isb-sib.ch/uniprot/' if row[2] == 'S' else 'http://www.uniprot.org/uniprot/') + protein_ac,
        'taxon': {
            'id': row[3],
            'fullName': row[4],
            'scientificName': row[5]
        },
        'isFragment': row[6] == 'Y',
    }

    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.ENTRY_TYPE,
          CET.ABBREV,
          E2E.PARENT_AC,
          MA.METHOD_AC,
          ME.NAME,
          MA.DBCODE,
          MA.POS_FROM,
          MA.POS_TO
        FROM {}.MATCH MA
        INNER JOIN INTERPRO.METHOD ME ON MA.METHOD_AC = ME.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON MA.METHOD_AC = E2M.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E ON E2M.ENTRY_AC = E.ENTRY_AC
        LEFT OUTER JOIN INTERPRO.CV_ENTRY_TYPE CET ON CET.CODE = E.ENTRY_TYPE
        LEFT OUTER JOIN INTERPRO.ENTRY2ENTRY E2E ON E.ENTRY_AC = E2E.ENTRY_AC
        WHERE MA.PROTEIN_AC = :1
        """.format(app.config['DB_SCHEMA']),
        (protein_ac, )
    )

    entries = {}
    for row in cur:
        entry_ac = row[0]

        try:
            entries[entry_ac]
        except KeyError:
            entries[entry_ac] = {
                'id': entry_ac,
                'name': row[1],
                'typeCode': row[2],
                'type': row[3],
                'parent': row[4],
                'methods': {}
            }
        finally:
            methods = entries[entry_ac]['methods']

        method_ac = row[5]
        try:
            methods[method_ac]
        except KeyError:
            db = xref.find_ref(dbcode=row[7], ac=method_ac)

            methods[method_ac] = {
                'id': method_ac,
                'name': row[6],
                'db': {
                    'name': db.name,
                    'link': db.gen_link(),
                    'color': db.color
                },
                'matches': []
            }
        finally:
            methods[method_ac]['matches'].append({'start': row[8], 'end': row[9]})

    for entry_ac in entries:
        entries[entry_ac]['methods'] = list(entries[entry_ac]['methods'].values())

    # Structural features and predictions
    cur.execute(
        """
        SELECT
          MS.DBCODE,
          MS.DOMAIN_ID,
          SC.FAM_ID,
          MS.POS_FROM,
          MS.POS_TO
        FROM INTERPRO.MATCH_STRUCT MS
        INNER JOIN INTERPRO.STRUCT_CLASS SC ON MS.DOMAIN_ID = SC.DOMAIN_ID
        WHERE MS.PROTEIN_AC = :1
        """,
        (protein_ac, )
    )

    structs = {}
    for dbcode, domain_id, fam_id, start, end in cur:
        try:
            structs[fam_id]
        except KeyError:
            db = xref.find_ref(dbcode=dbcode, ac=fam_id)

            structs[fam_id] = {
                'id': fam_id,
                'db': {
                    'name': db.name,
                    'link': db.gen_link(),
                    'color': db.color
                },
                'matches': []
            }
        finally:
            structs[fam_id]['matches'].append({'start': start, 'end': end})

    cur.close()

    protein.update({
        'entries': list(entries.values()),
        'structures': list(structs.values())
    })

    return protein


def get_entry(entry_ac):
    cur = get_db().cursor()

    cur.execute(
        """
        SELECT
          E.NAME,
          E.SHORT_NAME,
          E.ENTRY_TYPE,
          ET.ABBREV,
          E.CHECKED,
          NVL(EM.PROTEIN_COUNT, 0),
          E.CREATED,
          E.TIMESTAMP
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.CV_ENTRY_TYPE ET ON E.ENTRY_TYPE = ET.CODE
        LEFT OUTER JOIN INTERPRO.MV_ENTRY_MATCH EM ON E.ENTRY_AC = EM.ENTRY_AC
        WHERE E.ENTRY_AC = :1
        """,
        (entry_ac,)
    )

    row = cur.fetchone()

    if not row:
        # Might be a secondary accession
        cur.execute(
            """
            SELECT
              E.NAME,
              E.SHORT_NAME,
              E.ENTRY_TYPE,
              ET.ABBREV,
              E.CHECKED,
              NVL(EM.PROTEIN_COUNT, 0),
              E.CREATED,
              E.TIMESTAMP,
              E.ENTRY_AC
            FROM INTERPRO.ENTRY E
            INNER JOIN INTERPRO.CV_ENTRY_TYPE ET ON E.ENTRY_TYPE = ET.CODE
            LEFT OUTER JOIN INTERPRO.MV_ENTRY_MATCH EM ON E.ENTRY_AC = EM.ENTRY_AC
            INNER JOIN INTERPRO.MV_SECONDARY S ON E.ENTRY_AC = S.ENTRY_AC
            WHERE S.SECONDARY_AC = :1
            """,
            (entry_ac,)
        )

        row = cur.fetchone()
        if not row:
            cur.close()
            return None

        entry_ac = row[8]

    entry = {
        'id': entry_ac,
        'name': row[0],
        'shortName': row[1],
        'typeCode': row[2],
        'type': row[3],
        'isChecked': row[4] == 'Y',
        'proteinCount': row[5],
        'created': row[6].strftime('%Y-%m-%d %H:%M:%S'),
        'modified': row[7].strftime('%Y-%m-%d %H:%M:%S'),
        'methods': [],
        'relationships': {
            'count': 0,
            'types': {
                'parents': [],
                'children': [],
                'containers': [],
                'components': []
            }
        },
        'go': [],
        'description': None,
        'references': {},
        'missingXrefs': []
    }

    # Methods
    cur.execute(
        """
        SELECT
          M.DBCODE,
          M.METHOD_AC,
          M.NAME,
          NVL(MM.PROTEIN_COUNT, 0)
        FROM INTERPRO.METHOD M
        INNER JOIN INTERPRO.ENTRY2METHOD E2M ON M.METHOD_AC = E2M.METHOD_AC
        LEFT OUTER JOIN INTERPRO.MV_METHOD_MATCH MM ON M.METHOD_AC = MM.METHOD_AC
        WHERE E2M.ENTRY_AC = :1
        ORDER BY M.METHOD_AC
        """,
        (entry_ac, )
    )

    for row in cur:
        dbcode = row[0]
        method_ac = row[1]
        name = row[2]
        count = row[3]

        dbname = None
        home = None
        link = None

        db = xref.find_ref(dbcode, method_ac)
        if db:
            dbname = db.name
            home = db.home
            link = db.gen_link()

        entry['methods'].append({
            'dbname': dbname,
            'home': home,
            'link': link,
            'id': method_ac,
            'name': name,
            'count': count
        })

    # Relationships
    # Parents
    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.CHECKED,
          E.ENTRY_TYPE
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2ENTRY EE ON EE.PARENT_AC = E.ENTRY_AC
        WHERE EE.ENTRY_AC = :1
        """,
        (entry_ac,)
    )

    for row in cur:
        entry['relationships']['types']['parents'].append({
            'id': row[0],
            'name': row[1],
            'checked': row[2] == 'Y',
            'typeCode': row[3]
        })

    # Children
    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.CHECKED,
          E.ENTRY_TYPE
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2ENTRY EE ON EE.ENTRY_AC = E.ENTRY_AC
        WHERE EE.PARENT_AC = :1
        """,
        (entry_ac,)
    )

    for row in cur:
        entry['relationships']['types']['children'].append({
            'id': row[0],
            'name': row[1],
            'checked': row[2] == 'Y',
            'typeCode': row[3]
        })

    # Containers
    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.CHECKED,
          E.ENTRY_TYPE
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2COMP EC ON EC.ENTRY1_AC = E.ENTRY_AC
        WHERE EC.ENTRY2_AC = :1
        """,
        (entry_ac,)
    )

    for row in cur:
        entry['relationships']['types']['containers'].append({
            'id': row[0],
            'name': row[1],
            'checked': row[2] == 'Y',
            'typeCode': row[3]
        })

    # Components
    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.CHECKED,
          E.ENTRY_TYPE
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2COMP EC ON EC.ENTRY2_AC = E.ENTRY_AC
        WHERE EC.ENTRY1_AC = :1
        """,
        (entry_ac,)
    )

    for row in cur:
        entry['relationships']['types']['components'].append({
            'id': row[0],
            'name': row[1],
            'checked': row[2] == 'Y',
            'typeCode': row[3]
        })

    entry['relationships']['count'] = sum([len(e) for e in entry['relationships']['types'].values()])

    # GO annotations
    cur.execute(
        """
        SELECT T.GO_ID, T.NAME, T.CATEGORY, T.DEFINITION, T.IS_OBSOLETE, T.REPLACED_BY
        FROM INTERPRO.INTERPRO2GO I
          INNER JOIN INTERPRO_ANALYSIS.TERM T ON I.GO_ID = T.GO_ID
        WHERE I.ENTRY_AC = :1
        ORDER BY T.GO_ID
        """,
        (entry_ac,)
    )

    terms = []
    for row in cur:
        terms.append({
            'id': row[0],
            'name': row[1],
            'category': row[2],
            'definition': row[3],
            'isObsolete': row[4] == 'Y',
            'replacedBy': row[5]
        })

    entry['go'] = terms

    # References
    cur.execute(
        """
        SELECT
          DISTINCT (C.PUB_ID),
          C.TITLE,
          C.YEAR,
          C.VOLUME,
          C.RAWPAGES,
          C.DOI_URL,
          C.PUBMED_ID,
          C.ISO_JOURNAL,
          C.AUTHORS
        FROM INTERPRO.CITATION C
        WHERE C.PUB_ID IN (
          SELECT PUB_ID
          FROM INTERPRO.ENTRY2PUB
          WHERE ENTRY_AC = :1
          UNION
          SELECT M.PUB_ID
          FROM INTERPRO.METHOD2PUB M
          INNER JOIN INTERPRO.ENTRY2METHOD E ON E.METHOD_AC = M.METHOD_AC
          WHERE ENTRY_AC = :1
          UNION
          SELECT PUB_ID
          FROM INTERPRO.PDB_PUB_ADDITIONAL
          WHERE ENTRY_AC = :1
          UNION
          SELECT SUPPLEMENTARY_REF.PUB_ID
          FROM INTERPRO.SUPPLEMENTARY_REF
          WHERE ENTRY_AC = :1
        )
        """,
        (entry_ac, )
    )

    columns = ('id', 'title', 'year', 'volume', 'pages', 'doi', 'pmid', 'journal', 'authors')
    references = {row[0]: dict(zip(columns, row)) for row in cur}

    # Description
    cur.execute(
        """
        SELECT A.TEXT
        FROM INTERPRO.COMMON_ANNOTATION A
        INNER JOIN INTERPRO.ENTRY2COMMON E ON A.ANN_ID = E.ANN_ID
        WHERE E.ENTRY_AC = :1
        ORDER BY E.ORDER_IN
        """,
        (entry_ac,)
    )

    missing_refs = []
    description = ''

    for row in cur:
        text = row[0]

        # # Disabled for not breaking the <pre> tags
        # text = re.sub(r'\s{2,}', ' ', text)

        # Wrap text in paragraph
        # (not that it's better, but some annotations already contain the <p> tag)
        if text[:3].lower() != '<p>':
            text = '<p>' + text
        if text[-4:].lower() != '</p>':
            text += '</p>'

        # Find references and replace <cite id="PUBXXXX"/> by #PUBXXXX
        for m in re.finditer(r'<cite\s+id="(PUB\d+)"\s*/>', text):
            ref = m.group(1)
            text = text.replace(m.group(0), '#' + ref)

            if ref not in references:
                missing_refs.append(ref)

        # Find cross-references
        for m in re.finditer(r'<dbxref\s+db\s*=\s*"(\w+)"\s+id\s*=\s*"([\w\.\-]+)"\s*\/>', text):
            match = m.group(0)
            dbcode = m.group(1).upper()
            xref_id = m.group(2)

            url = xref.find_xref(dbcode)
            if url:
                url = url.format(xref_id)
                text = text.replace(match, '<a href="{}">{}</a>'.format(url, xref_id))
            else:
                entry['missingXrefs'].append({
                    'db': dbcode,
                    'id': xref_id
                })

        for m in re.finditer(r'<taxon\s+tax_id="(\d+)">([^<]+)</taxon>', text):
            text = text.replace(
                m.group(0),
                '<a href="http://www.uniprot.org/taxonomy/{}">{}</a>'.format(m.group(1), m.group(2))
            )

        description += text

    if missing_refs:
        # For some entries, the association entry-citation is missing in the INTERPRO.ENTRY2PUB

        missing_refs = list(set(missing_refs))
        cur.execute(
            """
            SELECT
              DISTINCT (PUB_ID),
              TITLE,
              YEAR,
              VOLUME,
              RAWPAGES,
              DOI_URL,
              PUBMED_ID,
              ISO_JOURNAL,
              AUTHORS
            FROM INTERPRO.CITATION
            WHERE PUB_ID IN ({})
            """.format(','.join([':' + str(i+1) for i in range(len(missing_refs))])),
            missing_refs
        )

        columns = ('id', 'title', 'year', 'volume', 'pages', 'doi', 'pmid', 'journal', 'authors')
        references.update({row[0]: dict(zip(columns, row)) for row in cur})

    cur.close()

    for block in re.findall(r'\[\s*#PUB\d+(?:\s*,\s*#PUB\d+)*\s*\]', description):
        refs = re.findall(r'#(PUB\d+)', block)

        description = description.replace(block, '<cite id="{}"/>'.format(','.join(refs)))

    entry.update({
        'description': description,
        'references': {
            'values': references,
            'count': len(references)
        }
    })

    return entry


def check_entry(entry_ac, is_checked):
    user = get_user()

    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    con = get_db()
    cur = con.cursor()
    try:
        cur.execute(
            'UPDATE INTERPRO.ENTRY SET CHECKED = :1 WHERE ENTRY_AC = :2',
            ('Y' if is_checked else 'N', entry_ac)
        )
    except cx_Oracle.DatabaseError as e:
        cur.close()
        return {
                   'status': False,
                   'message': 'Could not {}check entry {}: {}.'.format(
                       '' if is_checked else 'un',
                       entry_ac,
                       e
                   )
               }, 400
    else:
        con.commit()
        cur.close()
        return {
                   'status': True,
                   'message': None
               }, 200


def get_entry_comments(entry_ac, n=0):
    """
    Get the curator comments associated to a given entry
    """
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.ENTRY_COMMENT C
        INNER JOIN INTERPRO.USER_PRONTO U ON C.USERNAME = U.USERNAME
        WHERE C.ENTRY_AC = :1
        ORDER BY C.CREATED_ON DESC
        """,
        (entry_ac, )
    )

    comments = []
    for row in cur:
        comments.append({
            'id': row[0],
            'text': row[1],
            'date': row[2].strftime('%Y-%m-%d %H:%M:%S'),
            'status': row[3] == 'Y',
            'author': row[4],
        })

    cur.close()

    n_comments = len(comments)

    if n:
        comments = comments[:n]

    for c in comments:
        c['text'] = re.sub(
            r'#(\d+)',
            r'<a href="https://github.com/geneontology/go-annotation/issues/\1">#\1</a>',
            c['text']
        )

    return {
        'count': n_comments,
        'results': comments
    }


def add_comment(entry_ac, author, comment, comment_type='entry'):
    if comment_type == 'entry':
        col_name = 'ENTRY_AC'
        table_name = 'ENTRY_COMMENT'
    elif comment_type == 'method':
        col_name = 'METHOD_AC'
        table_name = 'METHOD_COMMENT'
    else:
        return False

    con = get_db()
    cur = con.cursor()

    cur.execute('SELECT MAX(ID) FROM INTERPRO.{}'.format(table_name))
    max_id = cur.fetchone()[0]
    next_id = max_id + 1 if max_id else 1

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.{} (ID, {}, USERNAME, VALUE)
            VALUES (:1, :2, :3, :4)
            """.format(table_name, col_name),
            (next_id, entry_ac, author, comment)
        )
    except cx_Oracle.IntegrityError:
        status = False
    else:
        status = True
        con.commit()

    cur.close()
    return status


def comment_entry(entry_ac, comment):
    user = get_user()

    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    if len(comment) < 3:
        return {
                   'status': False,
                   'message': 'Comment too short (must be at least three characters long).'
               }, 400
    elif add_comment(entry_ac, user['username'], comment, comment_type='entry'):
        return {
                   'status': True,
                   'message': None
               }, 200
    else:
        return {
                   'status': False,
                   'message': 'Could not add comment for entry "{}".'.format(entry_ac)
               }, 400


def add_go_mapping(entry_ac, terms):
    user = get_user()
    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    con = get_db()
    cur = con.cursor()

    # Check that all passed IDs exist
    cur.execute(
        """
        SELECT GO_ID 
        FROM {}.TERM 
        WHERE GO_ID IN ({})
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':' + str(i + 1) for i in range(len(terms))])
        ),
        terms
    )
    _terms = set([row[0] for row in cur])

    status = 201

    if terms == _terms:
        # Remove terms already mapped to the entry
        cur.execute('SELECT GO_ID FROM INTERPRO.INTERPRO2GO WHERE ENTRY_AC = :1', (entry_ac,))
        _terms = set([row[0] for row in cur])
        terms -= _terms

        if terms:
            try:
                cur.executemany(
                    """
                    INSERT INTO INTERPRO.INTERPRO2GO (ENTRY_AC, GO_ID, SOURCE) 
                    VALUES (:1, :2, :3)
                    """,
                    [(entry_ac, term_id, 'MANU') for term_id in terms]
                )
            except cx_Oracle.IntegrityError:
                res = {
                    'status': False,
                    'message': 'Could not add the following GO terms: {}'.format(', '.join(sorted(terms)))
                }
                status = 400
            else:
                con.commit()
                res = {
                    'status': True,
                    'message': None
                }
        else:
            # All terms already associated: do not return an error
            res = {
                'status': True,
                'message': None
            }
            status = 200
    else:
        res = {
            'status': False,
            'message': 'Invalid GO terms: {}'.format(', '.join(sorted(terms - _terms)))
        }
        status = 400

    cur.close()
    return res, status


def delete_go_mapping(entry_ac, terms):
    user = get_user()
    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    con = get_db()
    cur = con.cursor()

    # Delete ID-entry associations
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.INTERPRO2GO
            WHERE ENTRY_AC = :1 AND GO_ID IN ({})
            """.format(','.join([':' + str(i + 2) for i in range(len(terms))])),
            (entry_ac, *terms)
        )
    except cx_Oracle.IntegrityError:
        res = {
            'status': False,
            'message': 'Could not delete the following GO terms: {}'.format(', '.join(sorted(terms)))
        }
        status = 400
    else:
        con.commit()
        res = {
            'status': True,
            'message': None
        }
        status = 200
    finally:
        cur.close()
        return res, status


def get_method_predictions(method_ac, overlap=0.3):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          MO.C_AC,
          DB.DBCODE,
          DB.DBSHORT,

          E.ENTRY_AC,
          E.CHECKED,
          E.ENTRY_TYPE,
          E.NAME,

          MO.N_PROT_OVER,
          MO.N_OVER,          

          MO.C_N_PROT,
          MO.C_N_MATCHES,
          MO.Q_N_PROT,
          MO.Q_N_MATCHES,

          MP.RELATION
        FROM (
            SELECT
                MMQ.METHOD_AC Q_AC,
                MMQ.N_PROT Q_N_PROT,
                MMQ.N_MATCHES Q_N_MATCHES,
                MMC.METHOD_AC C_AC,
                MMC.N_PROT C_N_PROT,
                MMC.N_MATCHES C_N_MATCHES,
                MO.N_PROT_OVER,
                MO.N_OVER
            FROM (
                SELECT METHOD_AC1, METHOD_AC2, N_PROT_OVER, N_OVER, AVG_FRAC1, AVG_FRAC2
                FROM {0}.METHOD_OVERLAP
                WHERE METHOD_AC1 = :method
            ) MO
            INNER JOIN {0}.METHOD_MATCH MMQ ON MO.METHOD_AC1 = MMQ.METHOD_AC
            INNER JOIN {0}.METHOD_MATCH MMC ON MO.METHOD_AC2 = MMC.METHOD_AC
            WHERE ((MO.N_PROT_OVER >= (:overlap * MMQ.N_PROT)) OR (MO.N_PROT_OVER >= (:overlap * MMC.N_PROT)))
        ) MO
        LEFT OUTER JOIN {0}.METHOD_PREDICTION MP ON MO.Q_AC = MP.METHOD_AC1 AND MO.C_AC = MP.METHOD_AC2
        LEFT OUTER JOIN {0}.METHOD M ON MO.C_AC = M.METHOD_AC
        LEFT OUTER JOIN {0}.CV_DATABASE DB ON M.DBCODE = DB.DBCODE
        LEFT OUTER JOIN {0}.ENTRY2METHOD E2M ON MO.C_AC = E2M.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY E ON E2M.ENTRY_AC = E.ENTRY_AC
        ORDER BY MO.N_PROT_OVER DESC, MO.N_OVER DESC, MO.C_AC
        """.format(app.config['DB_SCHEMA']),
        {'method': method_ac, 'overlap': overlap}
    )

    methods = []
    for row in cur:
        db = xref.find_ref(row[1], row[0])

        methods.append({
            # method and member database
            'id': row[0],
            'dbCode': row[1],  # if None, the signature is a MEROPS entry (because not in the METHOD table)
            'dbShort': row[2],
            'dbLink': db.gen_link() if db else None,

            # InterPro entry info
            'entryId': row[3],
            'entryHierarchy': [],
            'isChecked': row[4] == 'Y',
            'entryType': row[5],
            'entryName': row[6],

            'nProts': row[7],  # number of proteins where both query and candidate signatures overlap
            'nBlobs': row[8],  # number of overlapping blobs with query and candidate signature

            'nProtsCand': row[9],  # number of proteins for every candidate signature
            'nBlobsCand': row[10],
            'nProtsQuery': row[11],  # number of proteins in the query signature found
            'nBlobsQuery': row[12],

            'relation': row[13]  # predicted relationship
        })

    cur.execute(
        """
        SELECT ENTRY_AC, PARENT_AC
        FROM {}.ENTRY2ENTRY
        """.format(app.config['DB_SCHEMA'])
    )

    parent_of = dict(cur.fetchall())
    cur.close()

    for m in methods:
        entry_ac = m['entryId']

        if entry_ac:
            hierarchy = []

            while entry_ac in parent_of:
                entry_ac = parent_of[entry_ac]
                hierarchy.append(entry_ac)

            m['entryHierarchy'] = hierarchy[::-1]

    return {
        'results': methods,
        'count': len(methods)
    }


def comment_method(entry_ac, comment):
    user = get_user()

    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    if len(comment) < 3:
        return {
                   'status': False,
                   'message': 'Comment too short (must be at least three characters long).'
               }, 400
    elif add_comment(entry_ac, user['username'], comment, comment_type='method'):
        return {
                   'status': True,
                   'message': None
               }, 200
    else:
        return {
                   'status': False,
                   'message': 'Could not add comment for signature "{}".'.format(entry_ac)
               }, 400


def get_method_comments(entry_ac, n=0):
    """
    Get the curator comments associated to a given method
    """
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.ENTRY_COMMENT C
        INNER JOIN INTERPRO.USER_PRONTO U ON C.USERNAME = U.USERNAME
        WHERE C.ENTRY_AC = :1
        ORDER BY C.CREATED_ON DESC
        """,
        (entry_ac, )
    )

    comments = []
    for row in cur:
        comments.append({
            'id': row[0],
            'text': row[1],
            'date': row[2].strftime('%Y-%m-%d %H:%M:%S'),
            'status': row[3] == 'Y',
            'author': row[4],
        })

    cur.close()

    return {
        'count': comments[:n] if n else comments,
        'results': len(comments)
    }


def get_method_references(method_ac, go_id):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT ID, TITLE, FIRST_PUBLISHED_DATE
        FROM {0}.PUBLICATION
        WHERE ID IN (
          SELECT REF_DB_ID
          FROM {0}.PROTEIN2GO P
            INNER JOIN {0}.METHOD2PROTEIN M ON P.PROTEIN_AC = M.PROTEIN_AC
          WHERE M.METHOD_AC = :1
                AND P.GO_ID = :2
                AND REF_DB_CODE = 'PMID'
        )
        ORDER BY FIRST_PUBLISHED_DATE
        """.format(app.config['DB_SCHEMA']),
        (method_ac, go_id)
    )

    references = []
    for row in cur:
        references.append({
            'id': row[0],
            'title': row[1],
            'date': row[2].strftime('%d %b %Y') if row[2] else None
        })

    cur.close()

    return {
        'count': len(references),
        'results': references
    }


def get_method_proteins(method_ac, dbcode=None):
    if dbcode in ('S', 'T'):
        source_cond = 'AND DBCODE = :2'
        params = (method_ac, dbcode)
    else:
        source_cond = ''
        params = (method_ac,)

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          M2P.PROTEIN_AC,
          P.DBCODE,
          P.LEN,
          P.NAME,
          D.TEXT,
          E.TAX_ID,
          E.FULL_NAME
        FROM (
          SELECT DISTINCT PROTEIN_AC
          FROM {0}.METHOD2PROTEIN
          WHERE METHOD_AC = :1
          {1}
        ) M2P
        INNER JOIN {0}.PROTEIN P ON M2P.PROTEIN_AC = P.PROTEIN_AC
        INNER JOIN {0}.DESC_VALUE D ON M2P.DESC_ID = D.DESC_ID
        INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        ORDER BY M2P.PROTEIN_AC
        """.format(app.config['DB_SCHEMA'], source_cond),
        params
    )

    proteins = []
    for row in cur:
        protein_ac = row[0]

        if row[1] == 'S':
            is_reviewed = True
            prefix = 'http://sp.isb-sib.ch/uniprot/'
        else:
            is_reviewed = False
            prefix = 'http://www.uniprot.org/uniprot/'

        proteins.append({
            'id': protein_ac,
            'link': prefix + protein_ac,
            'isReviewed': is_reviewed,
            'length': row[2],
            'shortName': row[3],
            'name': row[4],
            'taxon': {'id': row[5], 'fullName': row[6]},
            'matches': None
        })

    cur.close()
    return {
        'list': [p['id'] for p in proteins],
        'results': proteins,
        'maxLength': 0,
        'count': len(proteins),
        'pageInfo': {
            'page': 1,
            'pageSize': len(proteins)
        }
    }


def get_methods_enzymes(methods, dbcode=None):
    params = methods

    if dbcode in ('S', 'T'):
        source_cond = 'AND M2P.DBCODE = :' + str(len(params) + 1)
    else:
        source_cond = ''

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          M2P.METHOD_AC,
          EZ.ECNO,
          COUNT(DISTINCT M2P.PROTEIN_AC)
        FROM {0}.METHOD2PROTEIN M2P
          INNER JOIN {0}.ENZYME EZ ON M2P.PROTEIN_AC = EZ.PROTEIN_AC
        WHERE M2P.METHOD_AC IN ({1})
        {2}
        GROUP BY M2P.METHOD_AC, EZ.ECNO
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':' + str(i + 1) for i in range(len(params))]),
            source_cond
        ),
        params
    )

    enzymes = {}
    max_prot = 0
    for acc, ezno, n_prot in cur:
        if ezno in enzymes:
            e = enzymes[ezno]
        else:
            e = enzymes[ezno] = {
                'id': ezno,
                'methods': {}
            }

        e['methods'][acc] = n_prot

        if n_prot > max_prot:
            max_prot = n_prot

    cur.close()

    return {
        'results': sorted(enzymes.values(), key=lambda e: -max(e['methods'].values())),
        'database': dbcode if dbcode in ('S', 'T') else 'U',
        'max': max_prot
    }


def get_taxon(taxon_id):
    """
    Returns taxonomic information (name, phylogenetic left/right number) from a taxon ID.
    """

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT TAX_ID, FULL_NAME, LEFT_NUMBER, RIGHT_NUMBER, RANK
        FROM {}.ETAXI
        WHERE TAX_ID=:1
        """.format(app.config['DB_SCHEMA']),
        (taxon_id,))
    row = cur.fetchone()
    cur.close()

    return None if not row else dict(zip(('id', 'fullName', 'leftNumber', 'rightNumber', 'rank'), row))


def get_methods_taxonomy(methods, taxon=None, rank=None):
    taxon = get_taxon(taxon) if isinstance(taxon, int) else None

    if rank not in RANKS:
        rank = RANKS[0]

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['rank'] = rank

    if taxon:
        params['ln'] = taxon['leftNumber']
        params['rn'] = taxon['rightNumber']
        tax_cond = 'AND M2P.LEFT_NUMBER BETWEEN :ln AND :rn'
    else:
        tax_cond = ''

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          L.TAX_ID,
          MIN(E.FULL_NAME),
          M2P.METHOD_AC,
          COUNT(DISTINCT M2P.PROTEIN_AC)
        FROM {0}.METHOD2PROTEIN M2P
          LEFT OUTER JOIN {0}.LINEAGE L ON M2P.LEFT_NUMBER = L.LEFT_NUMBER AND L.RANK = :rank
          LEFT OUTER JOIN {0}.ETAXI E ON L.TAX_ID = E.TAX_ID
        WHERE M2P.METHOD_AC IN ({1})
              {2}
        GROUP BY M2P.METHOD_AC, L.TAX_ID
        """.format(app.config['DB_SCHEMA'], fmt, tax_cond),
        params
    )

    taxons = {}
    max_prots = 0
    for row in cur:
        tax_id = row[0]
        n_prots = row[3]

        if tax_id in taxons:
            t = taxons[tax_id]
        else:
            t = taxons[tax_id] = {
                'id': tax_id,
                'fullName': row[1] if tax_id else 'Others',
                'methods': {}
            }

        t['methods'][row[2]] = n_prots

        if n_prots > max_prots:
            max_prots = n_prots

    cur.close()

    return {
        'taxon': taxon if taxon else get_taxon(1),
        'rank': rank,
        'results': sorted(taxons.values(), key=lambda x: (0 if x['id'] else 1, -sum(x['methods'].values()))),
        'max': max_prots
    }