"""Application configuration without storing secret values in the repository."""

from __future__ import annotations

import importlib
import os
import warnings
from typing import Any


class MissingSettingError(RuntimeError):
    """Raised when a required setting is unavailable."""


def _legacy_keys_value(name: str) -> Any:
    """Read the legacy keys.py module during the migration period."""
    try:
        keys_module = importlib.import_module("keys")
    except ModuleNotFoundError as exc:
        if exc.name == "keys":
            return None
        raise
    return getattr(keys_module, name, None)


def get_setting(name: str) -> str:
    """Return a required setting, preferring the process environment.

    An explicitly defined but empty environment value is treated as missing and
    does not fall back to keys.py. This prevents an old local file from silently
    overriding an intentionally cleared deployment setting.
    """
    if name in os.environ:
        value = os.environ[name]
    else:
        value = _legacy_keys_value(name)
        if value not in (None, ""):
            warnings.warn(
                f"Loading {name} from keys.py is deprecated; use the environment instead.",
                DeprecationWarning,
                stacklevel=2,
            )

    if value in (None, ""):
        raise MissingSettingError(f"Required setting is missing: {name}")

    return str(value)
