"""Optional process-wide HTTPS host allowlist for outbound requests."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

import requests


OUTBOUND_ALLOWLIST_ENV = "LABOOK_OUTBOUND_ALLOWLIST"


class OutboundRequestBlocked(requests.RequestException):
    """Raised before an outbound request targets a host outside the allowlist."""


def parse_allowed_hosts(value: str) -> frozenset[str]:
    return frozenset(host.strip().lower() for host in value.split(",") if host.strip())


def ensure_url_allowed(url: str, allowed_hosts: Iterable[str]) -> None:
    parsed = urlsplit(str(url))
    hostname = (parsed.hostname or "").lower()
    normalized_hosts = frozenset(host.lower() for host in allowed_hosts)

    try:
        port = parsed.port
    except ValueError as exc:
        raise OutboundRequestBlocked("Outbound HTTPS URL has an invalid port") from exc

    if (
        parsed.scheme.lower() != "https"
        or hostname not in normalized_hosts
        or port not in (None, 443)
    ):
        safe_host = hostname or "<invalid>"
        raise OutboundRequestBlocked(
            f"Outbound HTTPS host is not allowed: {safe_host}"
        )


def build_allowlisted_request(
    original_request: Callable,
    allowed_hosts: Iterable[str],
) -> Callable:
    normalized_hosts = frozenset(host.lower() for host in allowed_hosts)

    def allowlisted_request(session, method, url, *args, **kwargs):
        ensure_url_allowed(url, normalized_hosts)
        return original_request(session, method, url, *args, **kwargs)

    allowlisted_request._labook_outbound_allowlist = True
    return allowlisted_request


def install_requests_allowlist() -> bool:
    """Install the allowlist when configured; leave production defaults unchanged."""
    configured_hosts = parse_allowed_hosts(os.environ.get(OUTBOUND_ALLOWLIST_ENV, ""))
    if not configured_hosts:
        return False

    current_request = requests.sessions.Session.request
    if getattr(current_request, "_labook_outbound_allowlist", False):
        return True

    requests.sessions.Session.request = build_allowlisted_request(
        current_request,
        configured_hosts,
    )
    return True
