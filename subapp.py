import os
import time
import threading
import logging
from db import dbname

log_handler = logging.FileHandler("labook.log", encoding="utf-8")
log_handler.setLevel(logging.INFO)
log_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
)
logging.basicConfig(level=logging.INFO, handlers=[log_handler, logging.StreamHandler()])
logger = logging.getLogger(__name__)

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

def periodic_backup():
    logger.info("periodic backup activated")
    try:
        do_backup()
        logger.info("Initial backup executed.")
    except Exception as e:
        logger.error(f"Initial backup failed: {e}")
    while True:
        time.sleep(86400)
        try:
            do_backup()
            logger.info("Periodic backup executed.")
        except Exception as e:
            logger.error(f"Periodic backup failed: {e}")

if __name__ == "__main__":
    import slack_notify
    slack_notify.initiate()
    periodic_backup()