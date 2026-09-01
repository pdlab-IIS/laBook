from logger_config import setup_logger

logger = setup_logger("labook-sub")


def main():
    """Run the Slack notification scheduler in the foreground."""
    import slack_notify

    logger.info("Slack notification scheduler activated.")
    slack_notify.loop()

if __name__ == "__main__":
    main()
