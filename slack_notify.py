import threading
import time, datetime
import requests

import keys
SLACK_WEBHOOK_URL = keys.SLACK_WEBHOOK_URL
NOTION_TOKEN = keys.NOTION_TOKEN
NOTION_DATABASE_ID = keys.NOTION_DATABASE_ID

def wait_until_next_friday_17():
    # JST = UTC+9
    JST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(JST)
    # 0=Monday, ..., 4=Friday
    days_ahead = (4 - now.weekday()) % 7
    next_friday = now + datetime.timedelta(days=days_ahead)
    target_time = next_friday.replace(hour=17, minute=0, second=0, microsecond=0)
    if target_time <= now:
        target_time += datetime.timedelta(days=7)
    wait_seconds = (target_time - now).total_seconds()
    print("next slack notify:", target_time.isoformat())
    return wait_seconds

def send_new_notion_entries_to_slack():
    while True:
        wait_sec = wait_until_next_friday_17()
        time.sleep(wait_sec)
        try:
            headers = {
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            now = datetime.datetime.now(datetime.timezone.utc)
            week_ago = now - datetime.timedelta(days=7)
            week_ago_iso = week_ago.isoformat().replace("+00:00", "Z")
            
            filter_payload = {
                "filter": {
                    "timestamp": "created_time",
                    "created_time": {
                        "after": week_ago_iso
                    }
                }
            }
            query_url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
            resp = requests.post(query_url, headers=headers, json=filter_payload)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    for entry in results:
                        props = entry.get("properties", {})
                        title = ""
                        if "Title" in props and props["Title"].get("title"):
                            title = props["Title"]["title"][0].get("plain_text", "")
                        isbn = props.get("ISBN", {}).get("number", "")
                        reviewer = props.get("Reviewer", {}).get("select", {}).get("name", "")
                        review = ""
                        if "Review" in props and props["Review"].get("rich_text"):
                            review = "".join([rt.get("plain_text", "") for rt in props["Review"]["rich_text"]])
                        url = entry.get("url", "")
                        msg = f"*New Book Review*\nTitle: {title}\nISBN: {isbn}\nReviewer: {reviewer}\nReview: {review}\n<{url}|Open in Notion>"
                        requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
            else:
                print("Failed to fetch Notion entries:", resp.text)
        except Exception as e:
            print("Error in Notion→Slack:", e)

def initiate():
    threading.Thread(target=send_new_notion_entries_to_slack, daemon=True).start()