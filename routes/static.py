# routes/static.py
from flask import Blueprint, send_from_directory

bp_static = Blueprint('static', __name__, url_prefix='/static')

@bp_static.route('/<path:filename>')
def serve_static(filename):
    response = send_from_directory('static', filename)
    if filename.endswith(('.mp3', '.jpg', '.jpeg', '.png', '.svg')):
        response.headers["Cache-Control"] = "public, max-age=604800"
    elif filename.endswith(('.js', '.css', '.html')):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response