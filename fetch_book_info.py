import requests, os
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import keys

import logging
logger = logging.getLogger(__name__)

def save_cover_image(isbn, url):
    if not url:
        return None
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            path = f"covers/{isbn}.jpg"
            if os.path.isfile(path):                
                return path
            with open(path, "xb") as file:
                for chunk in response.iter_content(1024):
                    file.write(chunk)
            return path
    except Exception as e:
        logger.error(f"Failed to save cover image for {isbn}: {e}")
    return None

def get_ndl_book_info(isbn):
    NDL_API_URL = "https://ndlsearch.ndl.go.jp/api/opensearch"
    params = {"isbn": isbn}
    response = requests.get(NDL_API_URL, params=params)

    if response.status_code != 200:
        return None

    root = ET.fromstring(response.content)

    title_element = root.find(".//{http://purl.org/dc/elements/1.1/}title")
    title = title_element.text if title_element is not None else None

    author_element = root.find(".//{http://purl.org/dc/elements/1.1/}creator")
    author = author_element.text if author_element is not None else None

    publisher_element = root.find(".//{http://purl.org/dc/elements/1.1/}publisher")
    publisher = publisher_element.text if publisher_element is not None else None

    date_element = root.find(".//{http://purl.org/dc/terms/}issued")
    date = date_element.text if date_element is not None else None

    return {
        "title": title,
        "author": author,
        "publisher": publisher,
        "date": date,
        "cover_url": None,
    }

def get_rakuten_book_info(isbn):
    url = "https://app.rakuten.co.jp/services/api/BooksTotal/Search/20170404"
    params = {"format": "json", "isbnjan": isbn, "applicationId": keys.RAKUTEN_APP_ID}
    response = requests.get(url, params=params)
    data = response.json()

    if "Items" in data and len(data["Items"]) > 0:
        book = data["Items"][0]["Item"]
        author = book.get("author", None)
        if author:
            author = author.replace("', '", ", ").replace("['", "").replace("']", "")
        return {
            "title": book.get("title", None),
            "author": author,
            "publisher": book.get("publisherName", None),
            "date": book.get("salesDate", None),
            "cover_url": book.get("largeImageUrl", None),
        }
    return None

def get_google_book_info(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&key={keys.GOOGLE_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if "items" not in data:
        return None

    book_data = data["items"][0]["volumeInfo"]
    title = book_data.get("title", None)
    authors = book_data.get("authors", None)
    if authors:
        author = str(authors).replace("', '", ", ").replace("['", "").replace("']", "")
    else:
        author = book_data.get("author", None)
    publisher = book_data.get("publisher")
    date = book_data.get("publishedDate", None)
    cover_url = book_data.get("imageLinks", {}).get("thumbnail", None)

    return {
        "isbn": isbn,
        "title": title,
        "author": author,
        "publisher": publisher,
        "date": date,
        "cover_url": cover_url,
    }

def fetch_book_info(isbn):
    if int(isbn) > 9780000000000:
        with ThreadPoolExecutor() as executor:
            future_google = executor.submit(get_google_book_info, isbn)
            future_rakuten = executor.submit(get_rakuten_book_info, isbn)
            future_ndl = executor.submit(get_ndl_book_info, isbn)

            google_info = future_google.result()
            rakuten_info = future_rakuten.result()
            ndl_info = future_ndl.result()

        sources = [google_info, rakuten_info, ndl_info]
    else:
        sources = [get_rakuten_book_info(isbn)]

    return {
        "isbn": isbn,
        "title": next((s["title"] for s in sources if s and s.get("title")), None),
        "author": next((s["author"] for s in sources if s and s.get("author")), None),
        "publisher": next(
            (s["publisher"] for s in sources if s and s.get("publisher")), None
        ),
        "publication_date": normalize_publication_date(next((s["date"] for s in sources if s and s.get("date")), None)),
        "cover_image_path": save_cover_image(isbn, next((s["cover_url"] for s in sources if s and s.get("cover_url")), None))
        #"owner_id": None,
        #"comment": None,
        #"shelf_code": None
    }

def normalize_publication_date(pub_date):
    if not pub_date:
        return None
    if len(pub_date) == 7 and pub_date[4] == '-':
        return pub_date + '-01'
    if len(pub_date) == 4 and pub_date.isdigit():
        return pub_date + '-01-01'

if __name__ == "__main__":
    import sys, json
    if len(sys.argv) != 2:
        print("Usage: python fetch_book_info.py <ISBN>")
        exit(1)
    isbn = sys.argv[1]
    info = fetch_book_info(isbn)
    if info:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        print("No book info found for ISBN:", isbn)
