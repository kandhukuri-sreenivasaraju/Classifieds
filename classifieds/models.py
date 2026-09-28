"""Core data model and small text/date helpers shared by every module."""

from __future__ import annotations

import email.utils
import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional

_BLOCK_TAG_RE = re.compile(r"(?i)<br\s*/?>|<p\b[^>]*>|</p>|</li>|</div>|</h\d>")
_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n\s*\n+")
_NORM_RE = re.compile(r"[^a-z0-9]+")


def strip_html(value: Optional[str]) -> str:
    """Turn an HTML fragment (possibly entity-escaped) into readable plain text."""
    if not value:
        return ""
    text = str(value)
    if "&lt;" in text:  # some feeds double-escape their HTML
        text = html.unescape(text)
    text = _BLOCK_TAG_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _INLINE_WS_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def parse_date(value: Any) -> Optional[datetime]:
    """Parse epoch seconds/millis, ISO-8601 or RFC-822 dates into aware UTC datetimes."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            ts = float(value)
            if ts > 1e12:  # milliseconds
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None

    text = str(value).strip()
    parsed: Optional[datetime] = None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(text[:19], fmt)
                    break
                except ValueError:
                    continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize(text: str) -> str:
    return _NORM_RE.sub(" ", (text or "").lower()).strip()


@dataclass
class Job:
    source: str
    title: str
    company: str
    url: str
    description: str = ""
    location: str = ""
    posted: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    job_type: str = ""  # raw employment-type label reported by the source
    salary: str = ""
    remote: bool = False  # True when the source only lists remote jobs

    # Filled in by scoring / state tracking.
    score: float = 0.0
    matched_skills: List[str] = field(default_factory=list)
    engagement: str = "unknown"  # contract | part-time | freelance | full-time | unknown
    is_new: bool = False
    first_seen: str = ""
    also_on: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable identity across sources: the same role posted on two boards dedupes."""
        raw = f"{normalize(self.title)}|{normalize(self.company)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def age_days(self, now: Optional[datetime] = None) -> Optional[float]:
        if not self.posted:
            return None
        now = now or datetime.now(timezone.utc)
        return max(0.0, (now - self.posted).total_seconds() / 86400)

    def snippet(self, length: int = 320) -> str:
        text = " ".join(self.description.split())
        return text if len(text) <= length else text[: length - 1].rsplit(" ", 1)[0] + "…"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "source": self.source,
            "also_on": self.also_on,
            "location": self.location,
            "posted": self.posted.isoformat() if self.posted else None,
            "engagement": self.engagement,
            "job_type": self.job_type,
            "salary": self.salary,
            "score": self.score,
            "matched_skills": self.matched_skills,
            "tags": self.tags,
            "is_new": self.is_new,
            "first_seen": self.first_seen,
            "snippet": self.snippet(),
            "description": self.description[:4000],
        }
