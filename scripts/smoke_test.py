"""Run destructive HTTP smoke checks against a disposable laBook database."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress


class SmokeFailure(RuntimeError):
    """Raised when a smoke-test response is unexpected."""


class SmokeClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.checks = 0

    def request(self, method, path, *, payload=None, expected=(200,)):
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                status = response.status
                content = response.read()
                content_type = response.headers.get_content_type()
        except urllib.error.HTTPError as error:
            with error:
                status = error.code
                content = error.read()
            content_type = ""

        if status not in expected:
            raise SmokeFailure(f"{method} {path} returned status {status}")
        self.checks += 1
        if not content:
            return None
        if content_type == "application/json" or content.lstrip().startswith((b"{", b"[")):
            return json.loads(content)
        return content.decode("utf-8")


def validate_target(parser, base_url, confirmed):
    parsed = urllib.parse.urlparse(base_url)
    if not confirmed:
        parser.error("--confirm-disposable-database is required")
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("base URL must be an HTTP loopback address")
    if parsed.port in (None, 5000):
        parser.error("an explicit non-production port is required")


def run_smoke(base_url):
    client = SmokeClient(base_url)
    isbn = "2999999999999"
    user_id = None
    shelf_ids = []
    loan_id = None
    book_created = False

    try:
        client.request("GET", "/healthz")
        client.request("GET", "/readyz")
        client.request("GET", "/")
        client.request("GET", "/books?limit=1")
        client.request("GET", "/books/manage")
        client.request("GET", "/shelves")
        client.request("GET", "/users")
        client.request("GET", "/loans")
        client.request("GET", "/static/index.js")
        client.request("GET", "/backup", expected=(404,))
        client.request("GET", "/initdb", expected=(404,))
        client.request("GET", f"/books/{isbn}", expected=(404,))

        user = client.request(
            "POST",
            "/users",
            payload={"user_name": "phase6-smoke-user"},
            expected=(201,),
        )
        user_id = user["user_id"]

        for code in ("PHASE6-SMOKE-A", "PHASE6-SMOKE-B"):
            shelf = client.request(
                "POST",
                "/shelves",
                payload={"shelf_code": code, "location_description": "smoke"},
                expected=(201,),
            )
            shelf_ids.append(shelf["shelf_id"])

        client.request(
            "POST",
            "/books",
            payload={
                "isbn": isbn,
                "title": "Phase 6 smoke book",
                "author": "Smoke Test",
                "owner_id": user_id,
                "shelf_id": shelf_ids[0],
            },
            expected=(201,),
        )
        book_created = True
        client.request("GET", f"/books/{isbn}")
        client.request(
            "PUT",
            f"/books/{isbn}",
            payload={
                "title": "Phase 6 smoke book updated",
                "author": "Smoke Test",
                "owner_id": user_id,
                "shelf_id": shelf_ids[0],
            },
        )
        client.request(
            "PUT",
            f"/books/move/{isbn}",
            payload={"shelf_id": shelf_ids[1]},
        )

        loan = client.request(
            "POST",
            "/loans",
            payload={"isbn": isbn, "borrower_id": user_id},
            expected=(201,),
        )
        loan_id = loan["loan_id"]
        client.request(
            "POST",
            "/loans",
            payload={"isbn": isbn, "borrower_id": user_id},
            expected=(409,),
        )
        client.request("POST", f"/loans/activeLoan/{isbn}")
        client.request(
            "POST",
            f"/loans/{loan_id}",
            payload={"returner_id": user_id},
        )
        client.request(
            "POST",
            f"/loans/{loan_id}",
            payload={"returner_id": user_id},
            expected=(409,),
        )
        client.request("DELETE", f"/loans/{loan_id}")
        loan_id = None
        client.request("DELETE", f"/books/{isbn}")
        book_created = False
        for shelf_id in reversed(shelf_ids):
            client.request("DELETE", f"/shelves/{shelf_id}")
        shelf_ids.clear()
        client.request("DELETE", f"/users/{user_id}")
        user_id = None
        client.request("GET", f"/books/{isbn}", expected=(404,))
    finally:
        if loan_id is not None:
            with suppress(Exception):
                client.request("DELETE", f"/loans/{loan_id}", expected=(200, 404))
        if book_created:
            with suppress(Exception):
                client.request("DELETE", f"/books/{isbn}", expected=(200, 404))
        for shelf_id in reversed(shelf_ids):
            with suppress(Exception):
                client.request("DELETE", f"/shelves/{shelf_id}", expected=(200, 404))
        if user_id is not None:
            with suppress(Exception):
                client.request("DELETE", f"/users/{user_id}", expected=(200, 404))

    return client.checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5100")
    parser.add_argument("--confirm-disposable-database", action="store_true")
    args = parser.parse_args(argv)
    validate_target(parser, args.base_url, args.confirm_disposable_database)

    try:
        checks = run_smoke(args.base_url)
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "error": type(error).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"status": "ok", "checks": checks}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
