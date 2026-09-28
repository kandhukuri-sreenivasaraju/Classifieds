"""Command-line entry point: `python3 -m classifieds`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .models import Job
from .render import ENGAGEMENT_LABEL, default_search_links, write_outputs
from .scoring import score_and_filter
from .sources import SOURCES, fetch_extra_feeds, run_source
from .store import mark_new

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg.setdefault("search_links", default_search_links(cfg.get("search_terms", [])))
    return cfg


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="classifieds",
        description="Grab the latest remote contract / part-time roles that match your skills.",
    )
    p.add_argument("--config", type=Path, default=ROOT / "config.json")
    p.add_argument("--out", type=Path, default=ROOT / "output", help="where index.html/jobs.json/jobs.csv go")
    p.add_argument("--state", type=Path, default=ROOT / "data" / "seen.json", help="seen-listings file")
    p.add_argument("--days", type=int, help="only listings posted within N days (overrides config)")
    p.add_argument("--min-score", type=float, help="drop listings scoring below this (overrides config)")
    p.add_argument("--sources", help=f"comma list, any of: {', '.join(SOURCES)}")
    p.add_argument("--include-full-time", action="store_true", help="also show full-time roles")
    p.add_argument("--new-only", action="store_true", help="terminal list shows only NEW listings")
    p.add_argument("--limit", type=int, default=30, help="rows printed to the terminal (0 = none)")
    p.add_argument("--open", action="store_true", help="open the HTML report in your browser")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def gather(cfg: dict, source_names: List[str]) -> tuple[list[Job], dict]:
    terms = cfg["search_terms"]
    per_source: dict = {}
    jobs: List[Job] = []
    with ThreadPoolExecutor(max_workers=len(source_names) + 1) as pool:
        futures = {name: pool.submit(run_source, name, terms) for name in source_names}
        extra = pool.submit(fetch_extra_feeds, cfg.get("extra_feeds", [])) if cfg.get("extra_feeds") else None
        for name, fut in futures.items():
            try:
                found = fut.result()
            except Exception as exc:
                logging.warning("%s failed entirely: %s", name, exc)
                found = []
            per_source[name] = len(found)
            jobs.extend(found)
        if extra:
            found = extra.result()
            per_source["extra feeds"] = len(found)
            jobs.extend(found)
    return jobs, per_source


def print_table(jobs: List[Job], limit: int, new_only: bool) -> None:
    rows = [j for j in jobs if j.is_new or not new_only][:limit]
    if not rows:
        return
    color = sys.stdout.isatty()
    bold, red, dim, reset = ("\033[1m", "\033[31m", "\033[2m", "\033[0m") if color else ("",) * 4
    now = datetime.now(timezone.utc)
    print()
    for j in rows:
        age = j.age_days(now)
        age_s = f"{int(age)}d" if age is not None else "?"
        flag = f"{red}NEW{reset}" if j.is_new else "   "
        print(f"{flag} {bold}{j.score:>5g}{reset}  {ENGAGEMENT_LABEL[j.engagement]:<11} {age_s:>4}  "
              f"{bold}{j.title[:70]}{reset} — {j.company[:40]}")
        print(f"     {dim}{', '.join(j.matched_skills)} · {j.source} · {j.url}{reset}")
    print()


def main(argv: List[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")

    cfg = load_config(args.config)
    if args.days is not None:
        cfg["max_age_days"] = args.days
    if args.min_score is not None:
        cfg["min_score"] = args.min_score

    names = [s.strip() for s in (args.sources.split(",") if args.sources else cfg.get("sources", list(SOURCES)))]
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        print(f"Unknown source(s): {', '.join(unknown)}. Choose from: {', '.join(SOURCES)}", file=sys.stderr)
        return 2

    print(f"Searching {len(names)} boards for: {', '.join(cfg['search_terms'])} …", file=sys.stderr)
    raw, per_source = gather(cfg, names)
    jobs = score_and_filter(raw, cfg, include_full_time=args.include_full_time)
    new_count = mark_new(jobs, args.state)

    stats = {"raw": len(raw), "matched": len(jobs), "new": new_count, "per_source": per_source}
    html_path = write_outputs(jobs, cfg, stats, args.out)

    if args.limit:
        print_table(jobs, args.limit, args.new_only)
    print(f"{len(jobs)} matching listings ({new_count} new) from {len(raw)} scanned. "
          f"Report: {html_path}", file=sys.stderr)
    if not raw:
        print("No listings were fetched — check your internet connection (run with -v for details).",
              file=sys.stderr)
    if args.open:
        webbrowser.open(html_path.as_uri())
    return 0 if raw else 1
