"""Retry helpers for BitGN harness control-plane calls."""

from __future__ import annotations

import re
from typing import Any

_RETRY_SECONDS_RE = re.compile(
    r"(?:retry-after|retry after|try again in|wait)\D{0,40}(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def is_resource_exhausted(exc: Any) -> bool:
    code = getattr(exc, "code", "")
    name = str(getattr(code, "name", "") or "").lower()
    value = str(getattr(code, "value", "") or "").lower()
    text = str(code).lower()
    return (
        name == "resource_exhausted"
        or value == "resource_exhausted"
        or "resource_exhausted" in text
        or "resource exhausted" in text
    )


def retry_delay_for_connect_error(exc: Any, fallback: float) -> float:
    """Choose wait time for a ConnectError retry.

    The tournament harness may return CodeResourceExhausted with a Retry-After
    value in the message. The Python ConnectError exposes code/message but not
    response headers, so parse the message and fall back to exponential backoff.
    """
    if not is_resource_exhausted(exc):
        return fallback

    message = str(getattr(exc, "message", "") or exc)
    match = _RETRY_SECONDS_RE.search(message)
    if not match:
        return fallback
    seconds = float(match.group(1))
    return max(1.0, min(seconds, 1800.0))
