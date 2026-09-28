"""Skill matching, engagement (contract / part-time) detection, filtering and ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Pattern, Tuple

from .models import Job

PART_TIME_RE = re.compile(
    r"\bpart[\s-]?time\b|\bfractional\b|\b\d{1,2}\s*(?:-|–|to)\s*\d{1,2}\s*(?:hrs|hours)\s*(?:/|per|a)\s*(?:wk|week)\b",
    re.I,
)
CONTRACT_RE = re.compile(
    r"\b(?:contract(?:or|s)?|contract[\s-]to[\s-]hire|freelance(?:r|rs)?|1099|c2c|corp[\s-]to[\s-]corp|"
    r"hourly|per\s+hour|temporary|short[\s-]term|project[\s-]based)\b",
    re.I,
)
# Phrases strong enough to override a "full-time" label (many boards default to full-time).
STRONG_CONTRACT_RE = re.compile(
    r"\b(?:freelance(?:r)?|1099|c2c|corp[\s-]to[\s-]corp|contract[\s-]to[\s-]hire|hourly\s+rate|"
    r"contract\s+(?:role|position|basis|engagement|opportunity|assignment|work)|"
    r"(?:\d+|six|three|twelve)[\s-]+months?\s+contract)\b",
    re.I,
)
FULL_TIME_RE = re.compile(r"\bfull[\s-]?time\b|\bpermanent\b", re.I)
REMOTE_RE = re.compile(r"\bremote\b|\banywhere\b|\bwork from home\b|\bwfh\b|\bdistributed\b", re.I)
WORLDWIDE_RE = re.compile(r"\b(?:worldwide|anywhere|global(?:ly)?|international)\b", re.I)

ENGAGEMENT_BONUS = {"part-time": 5, "freelance": 4, "contract": 4, "unknown": 0, "full-time": -4}


def keyword_regex(keyword: str) -> Pattern[str]:
    """Whole-word, case-insensitive match. 'java' does not match 'javascript'."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])", re.I)


@dataclass
class Skill:
    name: str
    weight: float
    core: bool
    patterns: List[Pattern[str]]


def compile_skills(cfg_skills: List[dict]) -> List[Skill]:
    return [
        Skill(
            name=s["name"],
            weight=float(s.get("weight", 1)),
            core=bool(s.get("core", False)),
            patterns=[keyword_regex(k) for k in s.get("keywords", [])],
        )
        for s in cfg_skills
    ]


def classify_engagement(job: Job) -> str:
    label = (job.job_type or "").lower()
    title = job.title or ""
    body = f"{job.description}\n{' '.join(job.tags)}"

    if PART_TIME_RE.search(title):
        return "part-time"
    if re.search(r"\bfreelance", title, re.I):
        return "freelance"
    if CONTRACT_RE.search(title):
        return "contract"

    if "part" in label:
        return "part-time"
    if "freelance" in label:
        return "freelance"
    if any(k in label for k in ("contract", "temporary", "temp")):
        return "contract"

    if "full" in label or "permanent" in label:
        # Labelled full-time, but many boards default to that; trust strong wording in the body.
        if PART_TIME_RE.search(body):
            return "part-time"
        if STRONG_CONTRACT_RE.search(body):
            return "contract"
        return "full-time"

    if PART_TIME_RE.search(body):
        return "part-time"
    if re.search(r"\bfreelance", body, re.I):
        return "freelance"
    if CONTRACT_RE.search(body):
        return "contract"
    if FULL_TIME_RE.search(body):
        return "full-time"
    return "unknown"


def match_skills(job: Job, skills: List[Skill]) -> Tuple[float, List[str], bool]:
    """Return (skill score, matched skill names, whether any core skill matched)."""
    title = job.title or ""
    body = f"{job.description}\n{' '.join(job.tags)}"
    score, matched, core_hit = 0.0, [], False
    for skill in skills:
        in_title = any(p.search(title) for p in skill.patterns)
        if in_title or any(p.search(body) for p in skill.patterns):
            score += skill.weight * (2 if in_title else 1)
            matched.append(skill.name)
            core_hit = core_hit or skill.core
    return score, matched, core_hit


def recency_bonus(age: Optional[float]) -> float:
    if age is None:
        return 0
    if age <= 2:
        return 3
    if age <= 7:
        return 2
    if age <= 14:
        return 1
    return 0


def is_remote(job: Job) -> bool:
    return job.remote or bool(REMOTE_RE.search(f"{job.title} {job.location} {job.description}"))


def location_ok(job: Job, allow: List[Pattern[str]], include_worldwide: bool) -> bool:
    """True when the role is open to the configured locations (e.g. Canada).

    Matches the location, title or description against `allow_locations`. Roles listed as
    worldwide/anywhere (or with no location at all) count only when `include_worldwide` is on.
    """
    if not allow:
        return True
    if any(p.search(f"{job.location}\n{job.title}\n{job.description}") for p in allow):
        return True
    return include_worldwide and (not job.location.strip() or bool(WORLDWIDE_RE.search(job.location)))


def dedupe(jobs: List[Job]) -> List[Job]:
    """Merge the same role seen on several boards/search terms; keep the richest copy."""
    by_key: Dict[str, Job] = {}
    for job in jobs:
        if not job.url or not job.title:
            continue
        existing = by_key.get(job.key)
        if existing is None:
            by_key[job.key] = job
            continue
        keep, other = (job, existing) if len(job.description) > len(existing.description) else (existing, job)
        keep.also_on = sorted({*keep.also_on, *other.also_on, other.source} - {keep.source})
        keep.posted = max(filter(None, [keep.posted, other.posted]), default=None)
        keep.job_type = keep.job_type or other.job_type
        keep.salary = keep.salary or other.salary
        by_key[job.key] = keep
    return list(by_key.values())


def score_and_filter(
    jobs: List[Job],
    cfg: dict,
    now: Optional[datetime] = None,
    include_full_time: bool = False,
) -> List[Job]:
    now = now or datetime.now(timezone.utc)
    skills = compile_skills(cfg["skills"])
    allowed = set(cfg.get("engagement_allow", ["contract", "part-time", "freelance", "unknown"]))
    if include_full_time:
        allowed.add("full-time")
    max_age = cfg.get("max_age_days", 30)
    min_score = cfg.get("min_score", 0)
    exclude = [keyword_regex(k) for k in cfg.get("exclude_keywords", [])]
    exclude_loc = [re.compile(p, re.I) for p in cfg.get("exclude_location_patterns", [])]
    allow_loc = [keyword_regex(k) for k in cfg.get("allow_locations", [])]
    include_worldwide = bool(cfg.get("include_worldwide", False))

    results = []
    for job in dedupe(jobs):
        age = job.age_days(now)
        if age is not None and age > max_age:
            continue
        if cfg.get("remote_only", True) and not is_remote(job):
            continue
        if any(p.search(job.title) for p in exclude):
            continue
        if job.location and any(p.search(job.location) for p in exclude_loc):
            continue
        if not location_ok(job, allow_loc, include_worldwide):
            continue

        skill_score, matched, core_hit = match_skills(job, skills)
        if not core_hit:
            continue
        job.engagement = classify_engagement(job)
        if job.engagement not in allowed:
            continue

        job.matched_skills = matched
        job.score = round(skill_score + ENGAGEMENT_BONUS[job.engagement] + recency_bonus(age), 1)
        if job.score < min_score:
            continue
        results.append(job)

    results.sort(key=lambda j: (j.score, j.posted or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return results
