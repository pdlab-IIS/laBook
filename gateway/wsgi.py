"""Opt-in entry point: gunicorn gateway.wsgi:application.

Requires LABOOK_GATEWAY_CONFIG pointing to a private JSON file. The existing
app:app entry point is intentionally unchanged during parallel preparation.
"""
import os

from gateway.inbound import GatewayConfigurationError, Settings, SignedGateway

path = os.environ.get('LABOOK_GATEWAY_CONFIG')
if not path:
    raise GatewayConfigurationError('LABOOK_GATEWAY_CONFIG is required')
settings = Settings.load(path)

from app import app

application = SignedGateway(app, settings)
