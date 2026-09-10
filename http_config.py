"""Shared timeout policy for outbound HTTP requests."""

# (connect timeout, read timeout), in seconds.
EXTERNAL_API_TIMEOUT = (5.0, 15.0)
COVER_IMAGE_TIMEOUT = (5.0, 30.0)
