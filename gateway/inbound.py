"""Fail-closed WSGI boundary for the Sakura gateway's signed requests.

Used only by gateway.wsgi, never implicitly enabled in the legacy entry point.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
from urllib.parse import unquote_to_bytes, urlsplit

from gateway.signing import RejectedRequest, verify_request


class GatewayConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    public_origin: str
    public_prefix: str
    upstream_hosts: tuple[str, ...]
    slack_team_id: str
    keys: dict[str, bytes]
    nonce_database: str
    max_body_bytes: int

    @classmethod
    def load(cls, path: str) -> 'Settings':
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            origin = data['public_origin']
            parsed = urlsplit(origin)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                    or parsed.port == 0
                    or origin != 'https://' + parsed.netloc
                    or not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]+)?', parsed.netloc)):
                raise ValueError()
            # Prefix is a fixed deployment setting, not a forwarded header.
            prefix = data['public_prefix']
            if not re.fullmatch(r'/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*(?:/index\.php)?', prefix):
                raise ValueError()
            hosts = data['upstream_hosts']
            if (not isinstance(hosts, list) or not hosts
                    or any(not isinstance(h, str) or not re.fullmatch(r'[a-z0-9.-]+(?::[0-9]+)?', h)
                           for h in hosts)):
                raise ValueError()
            team = data['slack_team_id']
            if not re.fullmatch(r'T[A-Z0-9]+', team):
                raise ValueError()
            keys = data['signing_keys']
            if not isinstance(keys, dict) or not 1 <= len(keys) <= 2:
                raise ValueError()
            decoded = {}
            for key_id, encoded in keys.items():
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', key_id):
                    raise ValueError()
                key = base64.b64decode(encoded, validate=True)
                if len(key) < 32:
                    raise ValueError()
                decoded[key_id] = key
            nonce_database = Path(data['nonce_database'])
            if (not nonce_database.is_absolute() or not nonce_database.parent.is_dir()
                    or nonce_database.is_dir()):
                raise ValueError()
            limit = data['max_body_bytes']
            if type(limit) is not int or not 1 <= limit <= 32 * 1024 * 1024:
                raise ValueError()
            return cls(origin, prefix, tuple(hosts), team, decoded, str(nonce_database), limit)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            # Never expose configuration values or keys in errors.
            raise GatewayConfigurationError('Invalid or unreadable gateway configuration') from None


def request_target(environ: dict) -> str:
    """Check raw and WSGI-decoded paths agree before Flask routing occurs."""
    raw = environ.get('RAW_URI') or environ.get('REQUEST_URI')
    if not isinstance(raw, str) or not raw.startswith('/') or raw.startswith('//'):
        raise RejectedRequest('raw target unavailable')
    if not raw.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in raw) or '#' in raw:
        raise RejectedRequest('invalid target')
    path, separator, query = raw.partition('?')
    if query != environ.get('QUERY_STRING', ''):
        raise RejectedRequest('query mismatch')
    if ('\\' in path or '//' in path or re.search(r'%(?![0-9a-fA-F]{2})', path)
            or re.search(r'%(?:2f|5c|25)', path, re.IGNORECASE)):
        raise RejectedRequest('ambiguous path')
    decoded = unquote_to_bytes(path)
    if (any(c < 32 or c == 127 for c in decoded)
            or any(segment in [b'.', b'..'] for segment in decoded.split(b'/'))):
        raise RejectedRequest('ambiguous path')
    try:
        decoded.decode('utf-8', errors='strict')
        wsgi_path = environ.get('PATH_INFO', '').encode('latin-1', errors='strict')
    except UnicodeError:
        raise RejectedRequest('invalid path encoding') from None
    if decoded != wsgi_path or environ.get('SCRIPT_NAME', ''):
        raise RejectedRequest('path mismatch')
    # Preserve an empty trailing question mark too: it is signed as transmitted.
    return path + (separator + query if separator else '')


class SignedGateway:
    def __init__(self, application, settings: Settings):
        self.application = application
        self.settings = settings

    @staticmethod
    def reject(start_response, status='403 Forbidden'):
        body = b'{"error":"gateway_request_rejected"}'
        start_response(status, [('Content-Type', 'application/json'),
                                ('Content-Length', str(len(body))),
                                ('Cache-Control', 'private, no-store')])
        return [body]

    def __call__(self, environ, start_response):
        s = self.settings
        try:
            if environ.get('HTTP_HOST', '').lower() not in s.upstream_hosts:
                raise RejectedRequest('unexpected upstream host')
            target = request_target(environ)
            key_id = environ.get('HTTP_X_LABOOK_KEY_ID', '')
            key = s.keys.get(key_id)
            if key is None:
                raise RejectedRequest('unknown key')
            subject = environ.get('HTTP_X_LABOOK_SUBJECT', '')
            if not re.fullmatch(re.escape('slack:' + s.slack_team_id + ':') + r'[A-Z][A-Z0-9]+', subject):
                raise RejectedRequest('invalid subject')
            length = environ.get('CONTENT_LENGTH', '')
            if length and not re.fullmatch(r'[0-9]{1,10}', length):
                raise RejectedRequest('invalid length')
            length = int(length or '0')
            if length > s.max_body_bytes:
                return self.reject(start_response, '413 Content Too Large')
            if environ.get('wsgi.input_terminated'):
                body = environ['wsgi.input'].read(s.max_body_bytes + 1)
                if environ.get('CONTENT_LENGTH') and len(body) != length:
                    raise RejectedRequest('body length mismatch')
            else:
                body = environ['wsgi.input'].read(length)
                if len(body) != length:
                    raise RejectedRequest('incomplete body')
            if len(body) > s.max_body_bytes:
                return self.reject(start_response, '413 Content Too Large')
            verify_request(key, environ.get('HTTP_X_LABOOK_SIGNATURE', ''), s.nonce_database,
                           key_id=key_id, method=environ.get('REQUEST_METHOD', ''), target=target,
                           content_type=environ.get('CONTENT_TYPE', ''), body=body,
                           timestamp=environ.get('HTTP_X_LABOOK_TIMESTAMP', ''),
                           nonce=environ.get('HTTP_X_LABOOK_NONCE', ''), subject=subject)
        except (RejectedRequest, OSError, ValueError):
            return self.reject(start_response)

        # Do not let browser/proxy credentials override the verified identity.
        clean = environ.copy()
        for name in list(clean):
            if (name in ['HTTP_COOKIE', 'HTTP_AUTHORIZATION', 'HTTP_FORWARDED', 'HTTP_X_REAL_IP']
                    or name.startswith(('HTTP_X_FORWARDED_', 'HTTP_X_LABOOK_'))):
                clean.pop(name)
        origin = urlsplit(s.public_origin)
        clean.update({'wsgi.input': io.BytesIO(body), 'CONTENT_LENGTH': str(len(body)),
                      'wsgi.url_scheme': 'https', 'HTTP_HOST': origin.netloc,
                      'SERVER_NAME': origin.hostname, 'SERVER_PORT': str(origin.port or 443),
                      'SCRIPT_NAME': s.public_prefix, 'labook.gateway_subject': subject,
                      'labook.gateway_authenticated': True})
        clean.pop('HTTP_TRANSFER_ENCODING', None)

        def private_response(status, headers, exc_info=None):
            headers = [(k, v) for k, v in headers if k.lower() not in ['cache-control', 'expires']]
            headers.append(('Cache-Control', 'private, no-store'))
            return start_response(status, headers, exc_info)

        return self.application(clean, private_response)
