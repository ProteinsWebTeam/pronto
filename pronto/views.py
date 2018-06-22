#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import jsonify, request

from pronto import app, api


@app.route('/api/feed/')
def get_feed():
    try:
        n = int(request.args['n'])
    except (KeyError, ValueError):
        n = 20

    return jsonify(api.get_feed(n))


@app.route('/api/search/')
def search():
    query = request.args.get('query', '').strip()

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    return jsonify(api.search(query=query, page=page, page_size=20))


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


@app.route('/api/method/<method_ac>/comments/')
def get_method_comments(method_ac):
    try:
        n = int(request.args['size'])
    except (KeyError, ValueError):
        n = 0

    return jsonify(api.get_method_comments(method_ac, n)), 200


@app.route('/api/method/<method_ac>/references/<go_id>')
def get_method_references(method_ac, go_id):
    return jsonify(api.get_method_references(method_ac, go_id))


@app.route('/api/method/<method_ac>/proteins/all/')
def get_method_all_proteins(method_ac):
    return jsonify(api.get_method_proteins(method_ac, dbcode=request.args.get('db')))


@app.route('/api/methods/<path:methods>/enzymes/')
def get_methods_enzymes(methods):
    return jsonify(
        api.get_methods_enzymes(
            methods=[m.strip() for m in methods.split('/') if m.strip()],
            dbcode=request.args.get('db')
        )
    )


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
    ))
