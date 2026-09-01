import datetime
import logging
import threading
import time

import requests

from config import get_setting
from http_config import EXTERNAL_API_TIMEOUT


logger = logging.getLogger(__name__)


def wait_until_next_friday_17():
    # Existing production schedule: Wednesday at 15:00 JST.
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    days_ahead = (2 - now.weekday()) % 7
    next_notification = now + datetime.timedelta(days=days_ahead)
    target_time = next_notification.replace(
        hour=15,
        minute=0,
        second=0,
        microsecond=0,
    )
    if target_time <= now:
        target_time += datetime.timedelta(days=7)
    wait_seconds = (target_time - now).total_seconds()
    logger.info("Next Slack notification: %s", target_time.isoformat())
    return wait_seconds


def loop():
    while True:
        time.sleep(wait_until_next_friday_17())
        send_new_notion_entries_to_slack()


def _slack_message(entry):
    props = entry.get("properties", {})
    title = ""
    if "Title" in props and props["Title"].get("title"):
        title = props["Title"]["title"][0].get("plain_text", "")

    isbn = props.get("ISBN", {}).get("number", "")
    reviewer = props.get("Reviewer", {}).get("select", {}).get("name", "")
    review = ""
    if "Review" in props and props["Review"].get("rich_text"):
        review = "".join(
            rich_text.get("plain_text", "")
            for rich_text in props["Review"]["rich_text"]
        )

    url = entry.get("url", "")
    if "Lab" in props and props["Lab"].get("checkbox"):
        isbn = (
            "<https://pdlab.iis.u-tokyo.ac.jp/labook/books/manage"
            f"?isbn={isbn}|{isbn}>"
        )

    return (
        f"<{url}|*New Book Review*>\n"
        f"Title: *{title}*\n"
        f"ISBN: {isbn}\n"
        f"Reviewer: {reviewer}\n"
        f"Review: {review}\n"
        "<https://www.notion.so/22c8cd0402be80fc8dc5e750b784f54d|"
        "Open in Notion>"
    )


def send_new_notion_entries_to_slack():
    try:
        slack_webhook_url = get_setting("SLACK_WEBHOOK_URL")
        notion_token = get_setting("NOTION_TOKEN")
        notion_database_id = get_setting("NOTION_DATABASE_ID")
        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        now = datetime.datetime.now(datetime.timezone.utc)
        week_ago_iso = (now - datetime.timedelta(days=7)).isoformat().replace(
            "+00:00", "Z"
        )
        filter_payload = {
            "filter": {
                "timestamp": "created_time",
                "created_time": {"after": week_ago_iso},
            }
        }
        query_url = f"https://api.notion.com/v1/databases/{notion_database_id}/query"
        response = requests.post(
            query_url,
            headers=headers,
            json=filter_payload,
            timeout=EXTERNAL_API_TIMEOUT,
        )
        if response.status_code != 200:
            logger.warning("Notion query failed: status=%s", response.status_code)
            return

        for entry in response.json().get("results", []):
            slack_response = requests.post(
                slack_webhook_url,
                json={"text": _slack_message(entry)},
                timeout=EXTERNAL_API_TIMEOUT,
            )
            if not slack_response.ok:
                logger.warning(
                    "Slack webhook failed: status=%s",
                    slack_response.status_code,
                )
    except requests.RequestException as exc:
        logger.error("Notion to Slack request failed: error=%s", type(exc).__name__)
    except Exception:
        logger.exception("Unexpected error in Notion to Slack notification")


def initiate():
    logger.info("Slack webhook activated.")
    threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    send_new_notion_entries_to_slack()
