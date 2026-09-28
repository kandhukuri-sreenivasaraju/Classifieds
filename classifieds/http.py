"""Tiny stdlib HTTP helpers (no third-party dependencies needed)."""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Optional

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 personal-classifieds/1.0"
)


def fetch(url: str, timeout: float = 25, headers: Optional[Dict[str, str]] = None) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url: str, **kwargs: Any) -> Any:
    return json.loads(fetch(url, **kwargs).decode("utf-8", "replace"))
