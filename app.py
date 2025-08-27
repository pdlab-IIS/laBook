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
from db import close_connection, init_db, dbname
app = Flask(__name__, static_folder=None)

register_blueprints(app)
app.register_blueprint(notion_bp)

@app.teardown_appcontext
def teardown_db(exception):
    close_connection(exception)

@app.route("/")
def hello_world():
    return render_template("index.html")

@app.route("/scan", methods=["GET", "POST", "OPTIONS"])
@app.route("/scan/", methods=["GET", "POST", "OPTIONS"])
@app.route("/scan/<location_code>", methods=["GET", "POST", "OPTIONS"])
def scan(location_code=None):    
    return render_template("scan.html", location_code=location_code)

@app.route("/L", methods=["GET", "POST", "OPTIONS"])
@app.route("/L/<location_code>", methods=["GET", "POST", "OPTIONS"])
def scan_with_location(location_code=None):
    return redirect(url_for("books.manage_book_page", isbn=0, location_code_override=location_code))

def do_backup():
    if os.path.exists(dbname):
        import datetime, shutil
        backup_file = (
            dbname + datetime.datetime.now().strftime("_%Y%m%d-%H%M%S") + ".db"
        )
        shutil.copy(dbname, backup_file)
        logger.info(f"Backup created: {backup_file}")
        return backup_file
    else:
        logger.warning("Database file does not exist.")
        return None

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
        if os.path.exists(dbname):
            os.remove(dbname)
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
