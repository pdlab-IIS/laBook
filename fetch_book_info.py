import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import requests

from config import MissingSettingError, get_setting
from http_config import COVER_IMAGE_TIMEOUT, EXTERNAL_API_TIMEOUT


logger = logging.getLogger(__name__)


def normalize_google_cover_url(url):
    """Upgrade legacy Google Books thumbnail links to the allowed HTTPS URL."""
    if not url:
        return None

    parsed = urlsplit(url)
    if parsed.scheme.lower() == "http" and parsed.hostname == "books.google.com":
        return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return url


def save_cover_image(isbn, url):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            stream=True,
            timeout=COVER_IMAGE_TIMEOUT,
        )
        response.raise_for_status()

        path = f"covers/{isbn}.jpg"
        if os.path.isfile(path):
            return path

        os.makedirs("covers", exist_ok=True)
        try:
            with open(path, "xb") as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
        except FileExistsError:
            # Another worker downloaded the same cover first.
            pass
        return path
    except (requests.RequestException, OSError) as exc:
        logger.warning("Cover download failed: error=%s", type(exc).__name__)
        return None


def get_ndl_book_info(isbn):
    url = "https://ndlsearch.ndl.go.jp/api/opensearch"
    params = {"isbn": isbn}
    response = requests.get(
        url,
        params=params,
        timeout=EXTERNAL_API_TIMEOUT,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)

    title_element = root.find(".//{http://purl.org/dc/elements/1.1/}title")
    title = title_element.text if title_element is not None else None

    author_element = root.find(".//{http://purl.org/dc/elements/1.1/}creator")
    author = author_element.text if author_element is not None else None

    publisher_element = root.find(".//{http://purl.org/dc/elements/1.1/}publisher")
    publisher = publisher_element.text if publisher_element is not None else None

    date_element = root.find(".//{http://purl.org/dc/terms/}issued")
    publication_date = date_element.text if date_element is not None else None

    return {
        "title": title,
        "author": author,
        "publisher": publisher,
        "date": publication_date,
        "cover_url": None,
    }


def get_rakuten_book_info(isbn):
    url = "https://openapi.rakuten.co.jp/services/api/BooksBook/Search/20170404"
    params = {
        "format": "json",
        "formatVersion": 2,
        "hits": 1,
        "isbn": isbn,
        "applicationId": get_setting("RAKUTEN_APP_ID"),
    }
    headers = {"accessKey": get_setting("RAKUTEN_ACCESS_KEY")}
    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=EXTERNAL_API_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    items = data.get("Items") or []
    if items:
        book = items[0]
        # formatVersion=2 returns the item directly. Keep accepting the legacy
        # wrapper so a transitional or cached response cannot break lookup.
        book = book.get("Item", book)
        author = book.get("author")
        if author:
            author = author.replace("', '", ", ").replace("['", "").replace("']", "")
        return {
            "title": book.get("title"),
            "author": author,
            "publisher": book.get("publisherName"),
            "date": book.get("salesDate"),
            "cover_url": book.get("largeImageUrl"),
        }
    return None


def get_google_book_info(isbn):
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": f"isbn:{isbn}", "key": get_setting("GOOGLE_API_KEY")}
    response = requests.get(url, params=params, timeout=EXTERNAL_API_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    if not data.get("items"):
        return None

    book_data = data["items"][0]["volumeInfo"]
    title = book_data.get("title")
    authors = book_data.get("authors")
    if authors:
        author = str(authors).replace("', '", ", ").replace("['", "").replace("']", "")
    else:
        author = book_data.get("author")

    return {
        "isbn": isbn,
        "title": title,
        "author": author,
        "publisher": book_data.get("publisher"),
        "date": book_data.get("publishedDate"),
        "cover_url": normalize_google_cover_url(
            book_data.get("imageLinks", {}).get("thumbnail")
        ),
    }


def _safe_provider_call(provider, isbn):
    try:
        return provider(isbn)
    except (
        MissingSettingError,
        requests.RequestException,
        ET.ParseError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ) as exc:
        logger.warning(
            "Book metadata provider failed: provider=%s error=%s",
            getattr(provider, "__name__", type(provider).__name__),
            type(exc).__name__,
        )
        return None


def fetch_book_info(isbn):
    numeric_isbn = int(isbn)
    uses_multiple_providers = numeric_isbn > 9780000000000 or (
        1000000000 < numeric_isbn < 10000000000
    )

    if uses_multiple_providers:
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_google = executor.submit(
                _safe_provider_call, get_google_book_info, isbn
            )
            future_rakuten = executor.submit(
                _safe_provider_call, get_rakuten_book_info, isbn
            )
            future_ndl = executor.submit(_safe_provider_call, get_ndl_book_info, isbn)

            google_info = future_google.result()
            rakuten_info = future_rakuten.result()
            ndl_info = future_ndl.result()

        sources = [google_info, rakuten_info, ndl_info]
    else:
        sources = [_safe_provider_call(get_rakuten_book_info, isbn)]

    cover_url = next(
        (source["cover_url"] for source in sources if source and source.get("cover_url")),
        None,
    )
    publication_date = next(
        (source["date"] for source in sources if source and source.get("date")),
        None,
    )

    return {
        "isbn": isbn,
        "title": next(
            (source["title"] for source in sources if source and source.get("title")),
            None,
        ),
        "author": next(
            (
                source["author"]
                for source in sources
                if source and source.get("author")
            ),
            None,
        ),
        "publisher": next(
            (
                source["publisher"]
                for source in sources
                if source and source.get("publisher")
            ),
            None,
        ),
        "publication_date": normalize_publication_date(publication_date),
        "cover_image_path": save_cover_image(isbn, cover_url),
    }


def normalize_publication_date(pub_date):
    if not pub_date:
        return None

    normalized = str(pub_date).strip()
    japanese_date = re.fullmatch(
        r"(?P<year>\d{4})年(?:(?P<month>\d{1,2})月)?(?:(?P<day>\d{1,2})日)?",
        normalized,
    )
    if japanese_date:
        year = int(japanese_date.group("year"))
        month = int(japanese_date.group("month") or 1)
        day = int(japanese_date.group("day") or 1)
        normalized = f"{year:04d}-{month:02d}-{day:02d}"

    if len(normalized) == 4 and normalized.isdigit():
        normalized += "-01-01"
    elif len(normalized) == 7 and normalized[4] == "-":
        normalized += "-01"

    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError:
        logger.warning("Invalid publication date returned by metadata provider")
        return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fetch_book_info.py <ISBN>")
        raise SystemExit(1)

    info = fetch_book_info(sys.argv[1])
    if info:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        print("No book info found for ISBN:", sys.argv[1])
