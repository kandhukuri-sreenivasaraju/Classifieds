"""Writes the results as a classifieds-style HTML page, plus JSON and CSV."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

from .models import Job

ENGAGEMENT_LABEL = {
    "part-time": "Part-time",
    "contract": "Contract",
    "freelance": "Freelance",
    "unknown": "Unspecified",
    "full-time": "Full-time",
}


def _age_label(job: Job, now: datetime) -> str:
    age = job.age_days(now)
    if age is None:
        return "date unknown"
    if age < 1:
        hours = int(age * 24)
        return "just now" if hours < 1 else f"{hours}h ago"
    return f"{int(age)}d ago"


def _card(job: Job, now: datetime) -> str:
    skills = "".join(f'<li>{escape(s)}</li>' for s in job.matched_skills)
    meta = [escape(job.company or "Unknown company")]
    if job.location:
        meta.append(escape(job.location[:60]))
    if job.salary:
        meta.append(escape(job.salary))
    sources = escape(" · ".join([job.source, *job.also_on]))
    new_badge = '<span class="badge new">New</span>' if job.is_new else ""
    return f"""
<article class="ad" data-eng="{job.engagement}" data-new="{int(job.is_new)}"
  data-score="{job.score}" data-posted="{job.posted.timestamp() if job.posted else 0}"
  data-text="{escape((job.title + ' ' + job.company + ' ' + ' '.join(job.matched_skills)).lower())}">
  <header>
    <span class="badge eng-{job.engagement}">{ENGAGEMENT_LABEL[job.engagement]}</span>{new_badge}
    <span class="score" title="Match score">{job.score:g}</span>
  </header>
  <h2><a href="{escape(job.url)}" target="_blank" rel="noopener noreferrer">{escape(job.title)}</a></h2>
  <p class="meta">{" · ".join(meta)}</p>
  <p class="snippet">{escape(job.snippet(260))}</p>
  <ul class="skills">{skills}</ul>
  <footer><span>{_age_label(job, now)}</span><span>{sources}</span></footer>
</article>"""


def render_html(jobs: List[Job], cfg: dict, stats: dict, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    cards = "\n".join(_card(j, now) for j in jobs) or '<p class="empty">No matching listings this run.</p>'
    links = "\n".join(
        f'<li><a href="{escape(l["url"])}" target="_blank" rel="noopener noreferrer">{escape(l["label"])}</a></li>'
        for l in cfg.get("search_links", [])
    )
    counts = {k: sum(1 for j in jobs if j.engagement == k) for k in ENGAGEMENT_LABEL}
    chips = "".join(
        f'<button class="chip" data-filter="{k}" aria-pressed="false">{v} <b>{counts[k]}</b></button>'
        for k, v in ENGAGEMENT_LABEL.items()
        if counts[k]
    )
    new_count = sum(1 for j in jobs if j.is_new)
    source_line = ", ".join(f"{escape(k)} {v}" for k, v in sorted(stats.get("per_source", {}).items()))
    owner = escape(cfg.get("owner_name") or "My")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contract Classifieds</title>
<style>
:root {{
  --bg: #f6f3ec; --paper: #fffdf8; --ink: #1d1b16; --muted: #6b665b; --rule: #d9d3c4;
  --accent: #0b5cad; --new: #b3261e; --pt: #1f7a4d; --ct: #0b5cad; --fl: #7a4bb3; --uk: #6b665b; --ft: #9a6a00;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #15140f; --paper: #1e1c17; --ink: #ece7da; --muted: #a39d8e; --rule: #38352c;
    --accent: #7ab4f5; --new: #ff8a80; --pt: #6fd3a0; --ct: #7ab4f5; --fl: #c3a2f0; --uk: #a39d8e; --ft: #e0b453;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
.wrap {{ max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }}
.masthead {{ text-align: center; border-bottom: 3px double var(--ink); padding-bottom: 12px; }}
.masthead h1 {{ font: 700 clamp(28px, 6vw, 52px)/1.05 Georgia, "Times New Roman", serif; margin: 0; letter-spacing: -0.5px; }}
.masthead p {{ margin: 6px 0 0; color: var(--muted); font-size: 13px; }}
.toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 16px 0; }}
.toolbar input[type=search] {{ flex: 1 1 220px; min-width: 0; padding: 8px 10px; border: 1px solid var(--rule);
  border-radius: 6px; background: var(--paper); color: var(--ink); font: inherit; }}
.chip, select {{ border: 1px solid var(--rule); background: var(--paper); color: var(--ink); border-radius: 999px;
  padding: 6px 12px; font: inherit; font-size: 13px; cursor: pointer; }}
.chip[aria-pressed=true] {{ background: var(--ink); color: var(--paper); }}
.grid {{ columns: 3 320px; column-gap: 16px; }}
.ad {{ break-inside: avoid; background: var(--paper); border: 1px solid var(--rule); border-radius: 4px;
  padding: 14px 16px; margin: 0 0 16px; }}
.ad header {{ display: flex; gap: 6px; align-items: center; }}
.ad h2 {{ font: 700 18px/1.25 Georgia, serif; margin: 8px 0 4px; overflow-wrap: anywhere; }}
.ad h2 a {{ color: var(--ink); text-decoration: none; }}
.ad h2 a:hover {{ color: var(--accent); text-decoration: underline; }}
.meta {{ margin: 0 0 8px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }}
.snippet {{ margin: 0 0 10px; font-size: 13.5px; }}
.badge {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px;
  border: 1px solid currentColor; border-radius: 3px; padding: 1px 6px; }}
.badge.new {{ color: var(--new); }}
.eng-part-time {{ color: var(--pt); }} .eng-contract {{ color: var(--ct); }} .eng-freelance {{ color: var(--fl); }}
.eng-unknown {{ color: var(--uk); }} .eng-full-time {{ color: var(--ft); }}
.score {{ margin-left: auto; font: 700 13px Georgia, serif; color: var(--muted); }}
.skills {{ list-style: none; padding: 0; margin: 0 0 10px; display: flex; flex-wrap: wrap; gap: 4px; }}
.skills li {{ font-size: 12px; background: var(--bg); border-radius: 3px; padding: 1px 6px; }}
.ad footer {{ display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--muted);
  border-top: 1px dotted var(--rule); padding-top: 6px; }}
aside {{ margin-top: 32px; border-top: 3px double var(--ink); padding-top: 12px; }}
aside h3 {{ font: 700 18px Georgia, serif; margin: 0 0 4px; }}
aside p {{ margin: 0 0 8px; color: var(--muted); font-size: 13px; }}
aside ul {{ display: flex; flex-wrap: wrap; gap: 8px; list-style: none; padding: 0; margin: 0; }}
aside a {{ color: var(--accent); }}
.empty {{ color: var(--muted); text-align: center; padding: 40px 0; }}
.hidden {{ display: none; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="masthead">
    <h1>{owner} Contract Classifieds</h1>
    <p>{len(jobs)} remote listings matched · <strong>{new_count} new</strong> since last check ·
      updated {now.strftime("%a %d %b %Y, %H:%M UTC")}</p>
    <p>Sources: {source_line}</p>
  </div>
  <div class="toolbar">
    <input type="search" id="q" placeholder="Filter: e.g. copado, apex, java…" aria-label="Filter listings">
    <button class="chip" id="newOnly" aria-pressed="false">New only <b>{new_count}</b></button>
    {chips}
    <select id="sort" aria-label="Sort">
      <option value="score">Best match</option>
      <option value="posted">Newest</option>
    </select>
  </div>
  <main class="grid" id="grid">
{cards}
  </main>
  <aside>
    <h3>Also check (sites without a public feed)</h3>
    <p>Pre-filled searches for remote contract / part-time roles.</p>
    <ul>{links}</ul>
  </aside>
</div>
<script>
(() => {{
  const grid = document.getElementById('grid');
  const ads = [...grid.querySelectorAll('.ad')];
  const q = document.getElementById('q');
  const newOnly = document.getElementById('newOnly');
  const chips = [...document.querySelectorAll('.chip[data-filter]')];
  const sort = document.getElementById('sort');
  const toggle = b => b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') !== 'true');
  function apply() {{
    const text = q.value.trim().toLowerCase();
    const engs = chips.filter(c => c.getAttribute('aria-pressed') === 'true').map(c => c.dataset.filter);
    const onlyNew = newOnly.getAttribute('aria-pressed') === 'true';
    for (const ad of ads) {{
      const ok = (!text || ad.dataset.text.includes(text))
        && (!engs.length || engs.includes(ad.dataset.eng))
        && (!onlyNew || ad.dataset.new === '1');
      ad.classList.toggle('hidden', !ok);
    }}
    const key = sort.value;
    ads.sort((a, b) => parseFloat(b.dataset[key]) - parseFloat(a.dataset[key])).forEach(a => grid.appendChild(a));
  }}
  q.addEventListener('input', apply);
  sort.addEventListener('change', apply);
  newOnly.addEventListener('click', () => {{ toggle(newOnly); apply(); }});
  chips.forEach(c => c.addEventListener('click', () => {{ toggle(c); apply(); }}));
}})();
</script>
</body>
</html>
"""


def write_outputs(jobs: List[Job], cfg: dict, stats: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "index.html"
    html_path.write_text(render_html(jobs, cfg, stats), encoding="utf-8")
    (out_dir / "jobs.json").write_text(
        json.dumps({"generated": datetime.now(timezone.utc).isoformat(), "stats": stats,
                    "jobs": [j.to_dict() for j in jobs]}, indent=2),
        encoding="utf-8",
    )
    with (out_dir / "jobs.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["new", "score", "engagement", "title", "company", "location", "posted",
                         "skills", "salary", "source", "url"])
        for j in jobs:
            writer.writerow([
                "NEW" if j.is_new else "", j.score, j.engagement, j.title, j.company, j.location,
                j.posted.date().isoformat() if j.posted else "", "; ".join(j.matched_skills),
                j.salary, " / ".join([j.source, *j.also_on]), j.url,
            ])
    return html_path


def default_search_links(terms: List[str]) -> List[dict]:
    q = quote_plus(" OR ".join(terms[:4]))
    return [
        {"label": "LinkedIn (remote · contract/part-time · past week)",
         "url": f"https://www.linkedin.com/jobs/search/?keywords={q}&f_WT=2&f_JT=C%2CP&f_TPR=r604800"},
        {"label": "Dice (remote contracts)",
         "url": f"https://www.dice.com/jobs?q={q}&filters.workplaceTypes=Remote&filters.employmentType=CONTRACTS%7CPARTTIME"},
        {"label": "Upwork", "url": f"https://www.upwork.com/nx/search/jobs/?q={q}&sort=recency"},
        {"label": "Indeed (remote contract)", "url": f"https://www.indeed.com/jobs?q={q}+contract&l=Remote&fromage=7"},
    ]
