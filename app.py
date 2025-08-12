#! /usr/bin/env python3

import logging
from logging.handlers import RotatingFileHandler
import os, threading, time
from flask import (
    Flask,
    send_from_directory,
    render_template,
    request,
    url_for,
    redirect
)
from flask_cors import CORS
from db import close_connection, init_db, dbname
from routes import register_blueprints
from routes.notion import bp as notion_bp; 
log_handler = RotatingFileHandler(
    "labook.log", maxBytes=5 * 1024 * 1024, backupCount=500, encoding="utf-8"
)
log_handler.setLevel(logging.INFO)
log_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
)
logging.basicConfig(level=logging.INFO, handlers=[log_handler, logging.StreamHandler()])
logger = logging.getLogger(__name__)

app = Flask(__name__)

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

@app.route("/backup")
def backup():
    if os.path.exists(dbname):
        import datetime, shutil

        backup_file = (
            dbname + datetime.datetime.now().strftime("_%Y%m%d-%H%M%S") + ".db"
        )
        shutil.copy(dbname, backup_file)
        return f"Backup created: {backup_file}"
    else:
        return "Database file does not exist."


def periodic_backup():
    time.sleep(86400)
    while True:
        try:
            with app.app_context():
                backup()
                logger.info("Periodic backup executed.")
        except Exception as e:
            logger.error(f"Periodic backup failed: {e}")


@app.route("/initdb")
def initdb():
    if app.debug:
        backup()
        import shutil

        if os.path.exists(dbname):
            os.remove(dbname)
        init_db()
        return "Database initialized!"
    else:
        return "Database initialization is only allowed in debug mode."


@app.route("/covers/<filename>")
def serve_cover(filename):
    covers_dir = "covers"
    return send_from_directory(covers_dir, filename)


if __name__ == "__main__":
    t = threading.Thread(target=periodic_backup, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000, debug=True)
