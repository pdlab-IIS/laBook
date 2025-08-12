from flask import Blueprint, request, jsonify
import requests
import os
import keys

bp = Blueprint('notion', __name__, url_prefix='/api/notion')

NOTION_TOKEN = keys.NOTION_TOKEN
NOTION_DATABASE_ID = keys.NOTION_DATABASE_ID
NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"

@bp.route('/add', methods=['POST'])
def add_to_notion():
    data = request.get_json()
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }
    payload = {
        "parent": { "database_id": NOTION_DATABASE_ID },
        "properties": {
            "Title": { "title": [{ "text": { "content": data.get("title", "") } }] },
            "ISBN": { "number": int(data.get("isbn", "0")) if data.get("isbn") else None },
            "Review": { "rich_text": [{ "text": { "content": data.get("review") } }] },
            "Reviewer": { "select": { "name": data.get("reviewer", "") } },
            "Lab": { "checkbox": True }
        }
    }
    payload["properties"] = {k: v for k, v in payload["properties"].items() if v}

    resp = requests.post(NOTION_API_URL, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        return jsonify({"message": "Added to Notion"}), 200
    else:
        return jsonify({"description": resp.text}), resp.status_code
    
@bp.route('/get_review_by_isbn/<isbn>', methods=['GET'])
def get_entry_by_isbn(isbn):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }

    filter_payload = {
        "filter": {
            "property": "ISBN",
            "number": {
                "equals": int(isbn)
            }
        }
    }
    query_url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    resp = requests.post(query_url, headers=headers, json=filter_payload)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        return jsonify(results)
    else:
        return jsonify({"description": resp.text}), resp.status_code