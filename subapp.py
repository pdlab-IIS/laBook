import os
import time
from logger_config import setup_logger
from db import DATABASE
from db_backup import create_online_backup

logger = setup_logger("labook-sub","labook-sub.log")

def do_backup():
    if not os.path.exists(DATABASE):
        logger.warning("Database file does not exist.")
        return None

    backup_file = create_online_backup(DATABASE)
    logger.info("Backup created: %s", backup_file)
    return str(backup_file)

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
