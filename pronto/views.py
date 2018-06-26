#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import jsonify, redirect, render_template, request, url_for

from pronto import app, api


@app.route('/api/feed/')
def get_feed():
    try:
        n = int(request.args['n'])
    except (KeyError, ValueError):
        n = 20

    return jsonify(api.get_feed(n))


@app.route('/api/protein/<protein_ac>/')
def get_protein(protein_ac):
    r = {
        'status': False,
        'result': None,
        'error': None
    }

    protein = api.get_protein(protein_ac)

    if protein:
        r.update({
            'status': True,
            'result': protein
        })
    else:
        r['error'] = 'The protein <strong>{}</strong> does not exist.'.format(protein_ac)

    return jsonify(r)


@app.route('/api/entry/<entry_ac>/')
def get_entry(entry_ac):
    r = {
        'status': False,
        'result': None,
        'error': None
    }

    try:
        entry = api.get_entry(entry_ac)
    except:
        r['error'] = 'An error occurred while searching for <strong>{}</strong>.'.format(entry_ac)
        status = 500
    else:
        if entry:
            r.update({
                'status': True,
                'result': entry
            })
            status = 200
        else:
            r['error'] = 'The entry <strong>{}</strong> does not exist.'.format(entry_ac)
            status = 404
    finally:
        return jsonify(r), status


@app.route('/api/entry/<entry_ac>/check/', strict_slashes=False, methods=['POST'])
def check_entry(entry_ac):
    try:
        is_checked = bool(int(request.form['checked']))
    except (KeyError, ValueError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.check_entry(entry_ac, is_checked)

    return jsonify(response), status


@app.route('/api/entry/<entry_ac>/comments/')
def get_entry_comments(entry_ac):
    try:
        n = int(request.args['size'])
    except (KeyError, ValueError):
        n = 0

    return jsonify(api.get_entry_comments(entry_ac, n)), 200


@app.route('/api/entry/<entry_ac>/comment/', strict_slashes=False, methods=['POST'])
def comment_entry(entry_ac):
    try:
        comment = request.form['comment'].strip()
    except (AttributeError, KeyError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.comment_entry(entry_ac, comment)
    return jsonify(response), status


@app.route('/api/entry/<entry_ac>/comment/<comment_id>/', strict_slashes=False, methods=['DELETE'])
def delete_entry_comment(entry_ac, comment_id):
    try:
        comment_id = int(comment_id)
    except ValueError:
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.delete_comment(entry_ac, comment_id, 'entry')
    return jsonify(response), status


@app.route('/api/entry/<entry_ac>/go/', strict_slashes=False, methods=['POST', 'DELETE'])
def entry_go(entry_ac):
    terms = set(request.form.get('ids', '').strip().split(','))
    if not terms:
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    if request.method == 'POST':
        response, status = api.add_go_mapping(entry_ac.upper(), map(str.upper, set(terms)))
    else:
        response, status = api.delete_go_mapping(entry_ac.upper(), map(str.upper, set(terms)))

    return jsonify(response), status


@app.route('/api/method/<method_ac>/proteins/')
def get_method_proteins(method_ac):
    try:
        taxon = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon = None

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 25

    try:
        desc_id = int(request.args['description'])
    except (KeyError, ValueError):
        desc_id = None

    try:
        topic_id = int(request.args['topic'])
        comment_id = int(request.args['comment'])
    except (KeyError, ValueError):
        topic_id = None
        comment_id = None

    dbcode = request.args.get('db', '').upper()
    if dbcode not in ('S', 'T'):
        dbcode = None

    return jsonify(
        api.get_method_matches(
            method_ac=method_ac,
            taxon=taxon,
            dbcode=dbcode,
            desc=desc_id,
            topic=topic_id,
            comment=comment_id,
            go=request.args.get('term'),
            ecno=request.args.get('ec'),
            rank=request.args.get('rank'),
            query=request.args.get('search', '').strip(),
            page=page,
            page_size=page_size
        )
    ), 200


@app.route('/api/method/<method_ac>/prediction/')
def get_method_predictions(method_ac):
    """
    Returns the overlapping entries for a given signature.
    Example:
    ---
    /api/method/PF00051/prediction/
    """

    try:
        overlap = float(request.args['overlap'])
    except (KeyError, ValueError):
        overlap = 0.3
    finally:
        return jsonify(api.get_method_predictions(method_ac, overlap)), 200


@app.route('/api/method/<method_ac>/comment/', strict_slashes=False, methods=['POST'])
def comment_method(method_ac):
    try:
        comment = request.form['comment'].strip()
    except (AttributeError, KeyError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.comment_method(method_ac, comment)
    return jsonify(response), status


@app.route('/api/method/<method_ac>/comment/<comment_id>/',  strict_slashes=False, methods=['DELETE'])
def delete_method_comment(method_ac, comment_id):
    try:
        comment_id = int(comment_id)
    except ValueError:
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.delete_comment(method_ac, comment_id, 'method')
    return jsonify(response), status


@app.route('/api/method/<method_ac>/comments/')
def get_method_comments(method_ac):
    try:
        n = int(request.args['size'])
    except (KeyError, ValueError):
        n = 0

    return jsonify(api.get_method_comments(method_ac, n)), 200


@app.route('/api/method/<method_ac>/references/<go_id>')
def get_method_references(method_ac, go_id):
    return jsonify(api.get_method_references(method_ac, go_id)), 200


@app.route('/api/method/<method_ac>/proteins/all/')
def get_method_all_proteins(method_ac):
    return jsonify(api.get_method_proteins(method_ac, dbcode=request.args.get('db'))), 200


@app.route('/api/methods/<path:methods>/matches/')
def api_methods_matches(methods):
    try:
        taxon = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon = None

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 5

    try:
        desc_id = int(request.args['description'])
    except (KeyError, ValueError):
        desc_id = None

    try:
        topic_id = int(request.args['topic'])
        comment_id = int(request.args['comment'])
    except (KeyError, ValueError):
        topic_id = None
        comment_id = None

    dbcode = request.args.get('db', '').upper()
    if dbcode not in ('S', 'T'):
        dbcode = None

    api.get_methods_matches(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        dbcode=dbcode,
        desc=desc_id,
        topic=topic_id,
        comment=comment_id,
        go=request.args.get('term'),
        ecno=request.args.get('ec'),
        rank=request.args.get('rank'),
        query=request.args.get('search', '').strip(),
        force=request.args.get('force', '').split(','),
        exclude=request.args.get('exclude', '').split(','),
        code=request.args.get('code'),
        page=page,
        page_size=page_size
    )


@app.route('/api/methods/<path:methods>/enzymes/')
def get_methods_enzymes(methods):
    return jsonify(
        api.get_methods_enzymes(
            methods=[m.strip() for m in methods.split('/') if m.strip()],
            dbcode=request.args.get('db')
        )
    ), 200


@app.route('/api/methods/<path:methods>/taxonomy/')
def get_methods_taxonomy(methods):
    try:
        taxon = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon = None

    return jsonify(api.get_methods_taxonomy(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        taxon=taxon,
        rank=request.args.get('rank')
    )), 200


@app.route('/api/methods/<path:methods>/descriptions/')
def get_methods_descriptions(methods):
    return jsonify(api.get_methods_descriptions(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        dbcode=request.args.get('db')
    )), 200


@app.route('/api/methods/<path:methods>/go/')
def get_methods_go(methods):
    return jsonify(api.get_methods_go(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        aspects=request.args.get('aspect', '').upper().split(',')
    )), 200


@app.route('/api/methods/<path:methods>/comments/')
def get_methods_swissprot_comments(methods):
    try:
        topic = int(request.args['topic'])
    except (KeyError, ValueError):
        topic = 34

    return jsonify(api.get_methods_swissprot_comments(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        topic=topic
    )), 200


@app.route('/api/methods/<path:methods>/matrices/')
def get_methods_matrixx(methods):
    return jsonify(
        api.get_methods_matrix(
            methods=[m.strip() for m in methods.split('/') if m.strip()]
        )
    ), 200


@app.route('/api/database/')
def get_databases():
    return jsonify(api.get_databases()), 200


@app.route('/api/database/<dbshort>/')
def get_database_methods(dbshort):
    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 100

    try:
        integrated = bool(int(request.args['integrated']))
    except (KeyError, ValueError):
        integrated = None

    try:
        checked = bool(int(request.args['checked']))
    except (KeyError, ValueError):
        checked = None

    try:
        commented = bool(int(request.args['commented']))
    except (KeyError, ValueError):
        commented = None

    query = request.args.get('search', '').strip()

    response, status = api.get_database_methods(
        dbshort,
        query=query,
        integrated=integrated,
        checked=checked,
        commented=commented,
        page=page,
        page_size=page_size
    )

    return jsonify(response), status


@app.route('/api/database/<dbshort>/unintegrated/')
def get_database_unintegrated_methods(dbshort):
    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 100

    response, status = api.get_database_unintegrated_methods(
        dbshort,
        query=request.args.get('search', '').strip(),
        filter=request.args.get('filter', 'exist'),
        page=page,
        page_size=page_size
    )

    return jsonify(response), status


@app.route('/')
def index():
    return render_template('index.html', databases=api.get_databases(),
                           user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/search/')
def search():
    query = request.args.get('q', '').strip()

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    page_size = 20

    entries, methods, proteins, hits, hit_count = api.search(query=query, page=page, page_size=page_size)

    if len(entries) == 1 and not methods and not proteins:
        return redirect(url_for('entry', accession=entries[0]))
    elif not entries and len(methods) == 1 and not proteins:
        return redirect(url_for('method', accession=entries[0]))
    elif not entries and not methods and len(proteins) == 1:
        return redirect(url_for('protein', accession=entries[0]))

    suggestions = []
    if entries:
        suggestions.append('<li>Entries: {}</li>'.format(
            ', '.join(['<a href="/entry/{0}/">{0}</a>'.format(accession) for accession in entries])
        ))

    if methods:
        suggestions.append('<li>Signatures: {}</li>'.format(
            ', '.join(['<a href="/method/{0}/">{0}</a>'.format(accession) for accession in methods])
        ))

    if proteins:
        suggestions.append('<li>Proteins: {}</li>'.format(
            ', '.join(['<a href="/protein/{0}/">{0}</a>'.format(accession) for accession in proteins])
        ))

    return render_template('search.html',
                           query=query,
                           entries=entries,
                           methods=methods,
                           proteins=proteins,
                           hits=hits,
                           hit_count=hit_count,
                           page=page,
                           page_size=page_size,
                           user=api.get_user(),
                           schema=app.config['DB_SCHEMA'])


@app.route('/database/<dbcode>/')
def database(dbcode):
    return render_template('database.html', user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/database/<dbcode>/unintegrated/')
def database_unint(dbcode):
    return render_template('database2.html', user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/protein/<accession>/')
def protein(accession):
    return accession


@app.route('/method/<accession>/')
def method(accession):
    return accession


@app.route('/entry/<accession>/')
def entry(accession):
    return accession
