#! /usr/bin/env python3

import sqlite3
from logger_config import setup_logger
from outbound_policy import install_requests_allowlist

logger = setup_logger()
install_requests_allowlist()

from flask import (
    Flask,
    jsonify,
    send_from_directory,
    render_template,
    request,
    url_for,
    redirect
)
from flask_cors import CORS
from routes import register_blueprints
from routes.notion import bp as notion_bp; 
from db import close_connection, get_db
app = Flask(__name__, static_folder=None)

register_blueprints(app)
app.register_blueprint(notion_bp)


@app.context_processor
def inject_runtime_environment():
    """Expose non-secret runtime flags to every rendered page."""
    return {"is_development": app.debug}


@app.route("/healthz")
def healthz():
    """Cheap liveness probe that does not touch downstream dependencies."""
    return jsonify({"status": "ok"})


@app.route("/readyz")
def readyz():
    """Report whether the application can use its required local database."""
    try:
        get_db().execute("SELECT 1").fetchone()
    except sqlite3.Error as error:
        logger.warning("Readiness database check failed: %s", type(error).__name__)
        return jsonify({"status": "not_ready", "database": "unavailable"}), 503
    return jsonify({"status": "ready", "database": "ok"})


@app.errorhandler(sqlite3.IntegrityError)
def handle_database_integrity_error(error):
    get_db().rollback()
    logger.warning(
        "Database integrity constraint rejected request: path=%s error=%s",
        request.path,
        type(error).__name__,
    )
    return jsonify({"description": "Database integrity constraint rejected request"}), 409

@app.teardown_appcontext
def teardown_db(exception):
    close_connection(exception)

@app.route("/L", methods=["GET", "POST", "OPTIONS"])
@app.route("/L/<location_code>", methods=["GET", "POST", "OPTIONS"])
def scan_with_location(location_code=None):
    if location_code:
        db = get_db()
        row = db.execute(
            "SELECT shelf_id FROM Shelves WHERE shelf_code = ?", (location_code,)
        ).fetchone()
        if row:
            return redirect(url_for("hello_world", location=location_code))
    return redirect(url_for("hello_world"))

@app.route("/")
def hello_world():
    initial_filter = request.args.get("location", "").strip()
    shelf_id = request.args.get("shelf_id", "")
    if not initial_filter and shelf_id:
        row = get_db().execute(
            "SELECT shelf_code FROM Shelves WHERE shelf_id = ?", (shelf_id,)
        ).fetchone()
        initial_filter = row[0] if row else ""
    return render_template("index.html", initial_filter=initial_filter)

@app.route("/scan", methods=["GET", "POST", "OPTIONS"])
@app.route("/scan/", methods=["GET", "POST", "OPTIONS"])
@app.route("/scan/<location_code>", methods=["GET", "POST", "OPTIONS"])
def scan(location_code=None):    
    return render_template("scan.html", location_code=location_code)

@app.route("/covers/<filename>")
def serve_cover(filename):
    covers_dir = "covers"
    response = send_from_directory(covers_dir, filename)
    response.headers["Cache-Control"] = "public, max-age=604800"
    return response

@app.route('/static/<filename>')
def static(filename):
    response = send_from_directory('static', filename)
    if filename.endswith(('.js', '.css', '.html')):
        if app.debug:
            response.headers["Cache-Control"] = "no-store, must-revalidate"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"
    elif filename.endswith(('.mp3', '.jpg', '.jpeg', '.png', '.svg')):
        response.headers["Cache-Control"] = "public, max-age=604800"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
