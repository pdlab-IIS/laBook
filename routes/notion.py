import logging

import requests
from flask import Blueprint, jsonify, request

from config import MissingSettingError, get_setting
from http_config import EXTERNAL_API_TIMEOUT


bp = Blueprint("notion", __name__, url_prefix="/api/notion")
logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


def _notion_headers():
    notion_token = get_setting("NOTION_TOKEN")
    return {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _upstream_error(operation, exc):
    if isinstance(exc, requests.Timeout):
        logger.warning("Notion request timed out: operation=%s", operation)
        return jsonify({"description": "Notion API timed out"}), 504

    logger.warning(
        "Notion request failed: operation=%s error=%s",
        operation,
        type(exc).__name__,
    )
    return jsonify({"description": "Notion API is unavailable"}), 502


@bp.errorhandler(MissingSettingError)
def handle_missing_setting(_error):
    logger.error("Notion integration is not configured")
    return jsonify({"description": "Notion integration is not configured"}), 503


@bp.route("/add", methods=["POST"])
def add_to_notion():
    data = request.get_json()
    notion_database_id = get_setting("NOTION_DATABASE_ID")
    payload = {
        "parent": {"database_id": notion_database_id},
        "properties": {
            "Title": {"title": [{"text": {"content": data.get("title", "")}}]},
            "ISBN": {
                "number": int(data.get("isbn", "0")) if data.get("isbn") else None
            },
            "Review": {
                "rich_text": [{"text": {"content": data.get("review", "")}}]
            },
            "Reviewer": {"select": {"name": data.get("reviewer", "")}},
            "Lab": {"checkbox": True},
        },
    }
    payload["properties"] = {
        key: value for key, value in payload["properties"].items() if value
    }

    try:
        response = requests.post(
            NOTION_API_URL,
            headers=_notion_headers(),
            json=payload,
            timeout=EXTERNAL_API_TIMEOUT,
        )
    except requests.RequestException as exc:
        return _upstream_error("add", exc)

    if response.status_code in (200, 201):
        return jsonify({"message": "Added to Notion"}), 200

    logger.warning("Notion add failed: status=%s", response.status_code)
    return jsonify({"description": "Notion API request failed"}), response.status_code


@bp.route("/get_review_by_isbn/<isbn>", methods=["GET"])
def get_entry_by_isbn(isbn):
    notion_database_id = get_setting("NOTION_DATABASE_ID")
    filter_payload = {
        "filter": {
            "property": "ISBN",
            "number": {"equals": int(isbn)},
        }
    }
    query_url = f"https://api.notion.com/v1/databases/{notion_database_id}/query"

    try:
        response = requests.post(
            query_url,
            headers=_notion_headers(),
            json=filter_payload,
            timeout=EXTERNAL_API_TIMEOUT,
        )
    except requests.RequestException as exc:
        return _upstream_error("query", exc)

    if response.status_code == 200:
        return jsonify(response.json().get("results", []))

    logger.warning("Notion query failed: status=%s", response.status_code)
    return jsonify({"description": "Notion API request failed"}), response.status_code
