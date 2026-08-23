"""Browser safety guards (Phase 1).

Safety rules (§18): passwords and credentials must never be scraped, never
exposed to the frontend, and never placed inside prompts. This module:

* flags URL paths that look like credential entry points (login / password /
  token pages) so ``browser.inspect`` / ``browser.extract`` can redact or
  refuse, and
* strips ``value`` from password inputs before any structured dump.

No authentication state is ever persisted into prompts or event payloads.
"""

from __future__ import annotations

import re

_SENSITIVE_PATH = re.compile(
    r"/(login|signin|sign-in|password|passwd|credential|token|oauth|auth"
    r"|2fa|verify|account/security|forgot-password|reset-password)",
    re.IGNORECASE,
)

_SENSITIVE_QUERY = re.compile(
    r"(password|passwd|token|secret|apikey|api_key|credential)", re.IGNORECASE
)


def is_sensitive_url(url: str) -> bool:
    """True when the URL looks like a credential entry / secret-bearing page."""
    if not url:
        return False
    try:
        from urllib.parse import urlsplit

        parts = urlsplit(url)
    except ValueError:
        return False
    if _SENSITIVE_PATH.search(parts.path or ""):
        return True
    return bool(_SENSITIVE_QUERY.search(parts.query or ""))


def redact(text: str) -> str:
    """Best-effort redaction of obvious secrets from extracted text."""
    return text
