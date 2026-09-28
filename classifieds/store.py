"""Remembers which listings you've already seen so each run can flag what's NEW."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

from .models import Job

KEEP_DAYS = 120


def load_seen(path: Path) -> Dict[str, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def mark_new(jobs: List[Job], path: Path, now: datetime | None = None) -> int:
    """Set is_new/first_seen on each job, persist the seen-set, return the NEW count."""
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    seen = load_seen(path)
    new_count = 0
    for job in jobs:
        if job.key in seen:
            job.first_seen = seen[job.key]
        else:
            job.first_seen = seen[job.key] = stamp
            job.is_new = True
            new_count += 1

    cutoff = now - timedelta(days=KEEP_DAYS)
    seen = {k: v for k, v in seen.items() if _parse(v) >= cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seen, indent=0, sort_keys=True), encoding="utf-8")
    return new_count


def _parse(stamp: str) -> datetime:
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
