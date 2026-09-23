"""Isolated HTTP test application: never imports laBook or opens its database."""
import os

from flask import Flask, jsonify, redirect, request, url_for

from gateway.inbound import Settings, SignedGateway

app = Flask(__name__)


@app.route('/', defaults={'path': ''}, methods=['GET', 'HEAD', 'POST', 'PATCH', 'DELETE'])
@app.route('/<path:path>', methods=['GET', 'HEAD', 'POST', 'PATCH', 'DELETE'])
def probe(path):
    if path == 'redirect':
        return redirect(url_for('probe', path='destination', _external=True))
    return jsonify(subject=request.environ['labook.gateway_subject'], path=request.path,
                   query=request.query_string.decode('ascii'), body_hex=request.get_data().hex(),
                   cookie=request.headers.get('Cookie'), host=request.host,
                   script_root=request.script_root)


application = SignedGateway(app, Settings.load(os.environ['LABOOK_GATEWAY_CONFIG']))
