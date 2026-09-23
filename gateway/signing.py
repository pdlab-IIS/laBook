"""Versioned request signatures shared with the Sakura PHP gateway.

This module is not connected to the production Flask application yet.
"""

import hashlib
import hmac
from contextlib import closing
import re
import sqlite3
import time


class RejectedRequest(ValueError):
    pass


def canonical_request(key_id, method, target, content_type, body, timestamp, nonce, subject):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key_id):
        raise RejectedRequest("invalid key id")
    if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
        raise RejectedRequest("invalid method")
    # The gateway must normalize/reject ambiguous paths before signing them.
    if not target.startswith("/") or target.startswith("//") or "#" in target:
        raise RejectedRequest("invalid request target")
    if not re.fullmatch(r"[0-9]{1,12}", timestamp):
        raise RejectedRequest("invalid timestamp")
    if not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise RejectedRequest("invalid nonce")
    if not subject:
        raise RejectedRequest("missing subject")
    fields = ["labook-gateway-v1", key_id, method, target, content_type,
              hashlib.sha256(body).hexdigest(), timestamp, nonce, subject]
    if any(any(ord(c) < 32 or ord(c) == 127 for c in field) for field in fields):
        raise RejectedRequest("control character in signature field")
    return "\n".join(fields).encode("utf-8")


def sign_request(secret, **request):
    if len(secret) < 32:
        raise RejectedRequest("key must contain at least 32 bytes")
    return hmac.new(secret, canonical_request(**request), hashlib.sha256).hexdigest()


def verify_request(secret, signature, nonce_database, *, now=None, window=60, **request):
    """Verify then atomically consume a nonce across independent worker processes.

    The dedicated database must live outside the web root with private permissions.
    I/O failure rejects the request. No business data is accessed here.
    """
    expected = sign_request(secret, **request)
    if not re.fullmatch(r"[a-f0-9]{64}", signature) or not hmac.compare_digest(expected, signature):
        raise RejectedRequest("invalid signature")
    current = int(time.time()) if now is None else now
    timestamp = int(request["timestamp"])
    if abs(current - timestamp) > window:
        raise RejectedRequest("expired signature")
    try:
        with closing(sqlite3.connect(nonce_database, timeout=5)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS gateway_nonces ("
                               "key_id TEXT, nonce TEXT, expires INTEGER NOT NULL, "
                               "PRIMARY KEY(key_id, nonce))")
            connection.execute("DELETE FROM gateway_nonces WHERE expires < ?", (current,))
            connection.execute("INSERT INTO gateway_nonces VALUES (?, ?, ?)",
                               (request["key_id"], request["nonce"], timestamp + window))
    except sqlite3.Error as exc:
        raise RejectedRequest("nonce unavailable or already consumed") from exc
