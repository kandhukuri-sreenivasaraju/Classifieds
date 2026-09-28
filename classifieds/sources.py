"""Job-board adapters. Each adapter takes the search terms and returns a list of Jobs.

Only public, key-less JSON APIs and RSS feeds are used, so the tool works out of the
box. A failing term or board is logged and skipped; it never aborts the whole run.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List
from urllib.parse import quote_plus

from .http import fetch, fetch_json
from .models import Job, parse_date, strip_html

log = logging.getLogger(__name__)

Adapter = Callable[[List[str]], List[Job]]


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_as_text(v) for v in value if v)
    if isinstance(value, dict):
        return str(value.get("name") or value.get("label") or "")
    return str(value)


def _per_term(name: str, terms: Iterable[str], fn: Callable[[str], List[Job]]) -> List[Job]:
    jobs: List[Job] = []
    for term in terms:
        try:
            jobs.extend(fn(term))
        except Exception as exc:  # network errors, bad JSON, API changes...
            log.warning("%s: search for %r failed: %s", name, term, exc)
    return jobs


# --------------------------------------------------------------------------- Remotive
def fetch_remotive(terms: List[str]) -> List[Job]:
    def one(term: str) -> List[Job]:
        data = fetch_json(f"https://remotive.com/api/remote-jobs?search={quote_plus(term)}&limit=100")
        return [
            Job(
                source="Remotive",
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                url=j.get("url", ""),
                description=strip_html(j.get("description")),
                location=j.get("candidate_required_location", ""),
                posted=parse_date(j.get("publication_date")),
                tags=list(j.get("tags") or []),
                job_type=_as_text(j.get("job_type")),
                salary=_as_text(j.get("salary")),
                remote=True,
            )
            for j in data.get("jobs", [])
        ]

    return _per_term("Remotive", terms, one)


# --------------------------------------------------------------------------- RemoteOK
def fetch_remoteok(terms: List[str]) -> List[Job]:
    def one(term: str) -> List[Job]:
        tag = term.lower().replace(" ", "-")
        data = fetch_json(f"https://remoteok.com/api?tag={quote_plus(tag)}")
        jobs = []
        for j in data if isinstance(data, list) else []:
            if not isinstance(j, dict) or not j.get("position"):
                continue  # first element is the API's legal notice
            salary = ""
            if j.get("salary_min") and j.get("salary_max"):
                salary = f"${int(j['salary_min']):,} – ${int(j['salary_max']):,}"
            jobs.append(
                Job(
                    source="RemoteOK",
                    title=j.get("position", ""),
                    company=j.get("company", ""),
                    url=j.get("url") or j.get("apply_url", ""),
                    description=strip_html(j.get("description")),
                    location=j.get("location", ""),
                    posted=parse_date(j.get("date") or j.get("epoch")),
                    tags=list(j.get("tags") or []),
                    salary=salary,
                    remote=True,
                )
            )
        return jobs

    return _per_term("RemoteOK", terms, one)


# --------------------------------------------------------------------------- Jobicy
def fetch_jobicy(terms: List[str]) -> List[Job]:
    def one(term: str) -> List[Job]:
        data = fetch_json(f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={quote_plus(term)}")
        jobs = []
        for j in data.get("jobs", []) or []:
            salary = ""
            if j.get("annualSalaryMin") and j.get("annualSalaryMax"):
                salary = f"{j.get('salaryCurrency', '')} {j['annualSalaryMin']} – {j['annualSalaryMax']}".strip()
            jobs.append(
                Job(
                    source="Jobicy",
                    title=strip_html(j.get("jobTitle")),
                    company=j.get("companyName", ""),
                    url=j.get("url", ""),
                    description=strip_html(j.get("jobDescription") or j.get("jobExcerpt")),
                    location=_as_text(j.get("jobGeo")),
                    posted=parse_date(j.get("pubDate")),
                    tags=[t for t in (j.get("jobIndustry") or []) if isinstance(t, str)],
                    job_type=_as_text(j.get("jobType")),
                    salary=salary,
                    remote=True,
                )
            )
        return jobs

    return _per_term("Jobicy", terms, one)


# --------------------------------------------------------------------------- Himalayas
def fetch_himalayas(terms: List[str]) -> List[Job]:
    def one(term: str) -> List[Job]:
        data = fetch_json(f"https://himalayas.app/jobs/api/search?q={quote_plus(term)}")
        jobs = []
        for j in data.get("jobs", []) or []:
            salary = ""
            if j.get("minSalary") and j.get("maxSalary"):
                salary = f"{j.get('currency') or ''} {j['minSalary']} – {j['maxSalary']}".strip()
            jobs.append(
                Job(
                    source="Himalayas",
                    title=j.get("title", ""),
                    company=j.get("companyName", ""),
                    url=j.get("applicationLink") or j.get("guid", ""),
                    description=strip_html(j.get("description") or j.get("excerpt")),
                    location=_as_text(j.get("locationRestrictions")) or "Anywhere",
                    posted=parse_date(j.get("pubDate")),
                    tags=[_as_text(c) for c in (j.get("categories") or [])],
                    job_type=_as_text(j.get("employmentType")),
                    salary=salary,
                    remote=True,
                )
            )
        return jobs

    return _per_term("Himalayas", terms, one)


# --------------------------------------------------------------------------- Working Nomads
def fetch_workingnomads(terms: List[str]) -> List[Job]:
    # One feed with every live job; filtered locally by the search terms.
    try:
        data = fetch_json("https://www.workingnomads.com/api/exposed_jobs/")
    except Exception as exc:
        log.warning("Working Nomads: fetch failed: %s", exc)
        return []
    needles = [t.lower() for t in terms]
    jobs = []
    for j in data if isinstance(data, list) else []:
        blob = f"{j.get('title', '')} {j.get('tags', '')} {j.get('description', '')}".lower()
        if not any(n in blob for n in needles):
            continue
        jobs.append(
            Job(
                source="Working Nomads",
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                url=j.get("url", ""),
                description=strip_html(j.get("description")),
                location=j.get("location", ""),
                posted=parse_date(j.get("pub_date")),
                tags=[t.strip() for t in str(j.get("tags") or "").split(",") if t.strip()],
                remote=True,
            )
        )
    return jobs


# --------------------------------------------------------------------------- Arbeitnow
def fetch_arbeitnow(terms: List[str], pages: int = 3) -> List[Job]:
    needles = [t.lower() for t in terms]
    jobs = []
    for page in range(1, pages + 1):
        try:
            data = fetch_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
        except Exception as exc:
            log.warning("Arbeitnow: page %d failed: %s", page, exc)
            break
        for j in data.get("data", []) or []:
            if not j.get("remote"):
                continue
            blob = f"{j.get('title', '')} {' '.join(j.get('tags') or [])} {j.get('description', '')}".lower()
            if not any(n in blob for n in needles):
                continue
            jobs.append(
                Job(
                    source="Arbeitnow",
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    url=j.get("url", ""),
                    description=strip_html(j.get("description")),
                    location=j.get("location", ""),
                    posted=parse_date(j.get("created_at")),
                    tags=list(j.get("tags") or []),
                    job_type=_as_text(j.get("job_types")),
                    remote=True,
                )
            )
        if not (data.get("links") or {}).get("next"):
            break
    return jobs


# --------------------------------------------------------------------------- Hacker News
_HN_THREAD_RE = re.compile(r"who is hiring|seeking freelancer", re.I)


def fetch_hackernews(terms: List[str], days: int = 45) -> List[Job]:
    """Comments in the monthly 'Who is hiring?' and 'Freelancer? Seeking freelancer?' threads."""
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    def one(term: str) -> List[Job]:
        url = (
            "https://hn.algolia.com/api/v1/search_by_date?tags=comment&hitsPerPage=200"
            f"&query={quote_plus(term)}&numericFilters=created_at_i>{since}"
        )
        jobs = []
        for hit in fetch_json(url).get("hits", []):
            if not _HN_THREAD_RE.search(hit.get("story_title") or ""):
                continue
            text = strip_html(hit.get("comment_text"))
            if not text:
                continue
            first_line = text.split("\n", 1)[0]
            parts = [p.strip() for p in first_line.split("|") if p.strip()]
            company = parts[0] if parts else hit.get("author", "")
            title = " | ".join(parts[1:]) if len(parts) > 1 else first_line
            jobs.append(
                Job(
                    source="Hacker News",
                    title=title[:160],
                    company=company[:80],
                    url=f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    description=text,
                    location="Remote" if re.search(r"\bremote\b", first_line, re.I) else "",
                    posted=parse_date(hit.get("created_at_i") or hit.get("created_at")),
                    tags=[hit.get("story_title", "")],
                    remote=bool(re.search(r"\bremote\b", text, re.I)),
                )
            )
        return jobs

    return _per_term("Hacker News", terms, one)


# --------------------------------------------------------------------------- RSS / Atom
_ATOM = "{http://www.w3.org/2005/Atom}"


def parse_feed(raw: bytes, source: str, remote: bool = False) -> List[Job]:
    """Parse a generic RSS 2.0 or Atom feed into Jobs."""
    root = ET.fromstring(raw)
    jobs: List[Job] = []

    def txt(el, *names) -> str:
        for name in names:
            found = el.find(name)
            if found is not None:
                if found.text:
                    return found.text.strip()
                if found.get("href"):
                    return found.get("href")
        return ""

    items = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
    for item in items:
        title = txt(item, "title", f"{_ATOM}title")
        company = ""
        if ": " in title and source == "We Work Remotely":
            company, title = title.split(": ", 1)
        jobs.append(
            Job(
                source=source,
                title=strip_html(title),
                company=company or txt(item, "company", "author", f"{_ATOM}author/{_ATOM}name"),
                url=txt(item, "link", f"{_ATOM}link", "guid"),
                description=strip_html(txt(item, "description", f"{_ATOM}content", f"{_ATOM}summary")),
                location=txt(item, "region", "location"),
                posted=parse_date(txt(item, "pubDate", f"{_ATOM}published", f"{_ATOM}updated")),
                tags=[c.text.strip() for c in item.findall("category") if c.text],
                job_type=txt(item, "type"),
                remote=remote,
            )
        )
    return jobs


def fetch_weworkremotely(terms: List[str]) -> List[Job]:
    def one(term: str) -> List[Job]:
        raw = fetch(f"https://weworkremotely.com/remote-jobs/search.rss?term={quote_plus(term)}")
        return parse_feed(raw, "We Work Remotely", remote=True)

    return _per_term("We Work Remotely", terms, one)


def fetch_extra_feeds(feeds: List[dict]) -> List[Job]:
    jobs: List[Job] = []
    for feed in feeds:
        try:
            jobs.extend(parse_feed(fetch(feed["url"]), feed.get("name", "RSS"), bool(feed.get("remote"))))
        except Exception as exc:
            log.warning("Feed %s failed: %s", feed.get("name") or feed.get("url"), exc)
    return jobs


SOURCES: Dict[str, Adapter] = {
    "remotive": fetch_remotive,
    "remoteok": fetch_remoteok,
    "jobicy": fetch_jobicy,
    "himalayas": fetch_himalayas,
    "weworkremotely": fetch_weworkremotely,
    "workingnomads": fetch_workingnomads,
    "arbeitnow": fetch_arbeitnow,
    "hackernews": fetch_hackernews,
}


def run_source(name: str, terms: List[str]) -> List[Job]:
    started = time.monotonic()
    jobs = SOURCES[name](terms)
    log.info("%-15s %4d raw listings (%.1fs)", name, len(jobs), time.monotonic() - started)
    return jobs
