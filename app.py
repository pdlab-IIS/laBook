#! /usr/bin/env python3

import os
from logger_config import setup_logger

logger = setup_logger()

from flask import (
    Flask,
    send_from_directory,
    render_template,
    request,
    url_for,
    redirect
)
from flask_cors import CORS
from routes import register_blueprints
from routes.notion import bp as notion_bp; 
from db import DATABASE, close_connection, init_db, get_db
from db_backup import create_online_backup
app = Flask(__name__, static_folder=None)

register_blueprints(app)
app.register_blueprint(notion_bp)

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
            return redirect(url_for("hello_world", shelf_id=row[0]))
    return redirect(url_for("hello_world"))

@app.route("/")
def hello_world():
    shelf_id = request.args.get('shelf_id', '')
    initial_filter = f"shelf_id:{shelf_id}" if shelf_id else ""
    return render_template("index.html", initial_filter=initial_filter)

@app.route("/scan", methods=["GET", "POST", "OPTIONS"])
@app.route("/scan/", methods=["GET", "POST", "OPTIONS"])
@app.route("/scan/<location_code>", methods=["GET", "POST", "OPTIONS"])
def scan(location_code=None):    
    return render_template("scan.html", location_code=location_code)

def do_backup():
    if not os.path.exists(DATABASE):
        logger.warning("Database file does not exist.")
        return None

    backup_file = create_online_backup(DATABASE)
    logger.info("Backup created: %s", backup_file)
    return str(backup_file)

@app.route("/backup")
def backup():
    backup_file = do_backup()
    if backup_file:
        return f"Backup created: {backup_file}"
    else:
        return "Database file does not exist."

@app.route("/initdb")
def initdb():
    if app.debug:
        backup()
        if os.path.exists(DATABASE):
            os.remove(DATABASE)
        init_db()
        return "Database initialized!"
    else:
        return "Database initialization is only allowed in debug mode."

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
