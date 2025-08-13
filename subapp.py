import os
import time
from logger_config import setup_logger
from db import dbname

logger = setup_logger("labook-sub","labook-sub.log")

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