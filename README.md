# Personal Contract Classifieds

This tool pulls the latest **remote contract, freelance and part-time** software roles that match
your skills from several job boards. It ranks them and writes a classifieds-style web page you can
open whenever you want to check.

It is set up for these skills: **Salesforce (development, admin, integration), Java, Copado and
Flosum deployments** and related Salesforce DevOps.

Everything uses the Python standard library, so there is nothing to install and no API keys to set up.

## Check for new listings

```bash
python3 -m classifieds --open
```

This fetches from every board, prints the top matches in the terminal and opens
`output/index.html` in your browser. Each run remembers what it has already shown you, so listings
that appeared since your last check get a red **NEW** badge.

Useful options:

| Option | What it does |
| --- | --- |
| `--new-only` | Terminal list shows only listings you haven't seen before |
| `--days 7` | Only listings posted in the last 7 days (default 30) |
| `--include-full-time` | Also show full-time roles |
| `--min-score 10` | Stricter matching |
| `--sources remotive,hackernews` | Only query certain boards |
| `-v` | Show how many listings each board returned |

Each run also writes `output/jobs.csv` (opens in Excel or Sheets) and `output/jobs.json`.

## Where the listings come from

| Board | How |
| --- | --- |
| Remotive, RemoteOK, Jobicy, Himalayas, Arbeitnow, Working Nomads | Public JSON APIs |
| We Work Remotely | RSS search feed |
| Hacker News | Monthly *"Who is hiring?"* and *"Freelancer? Seeking freelancer?"* threads (Algolia API) |

LinkedIn, Dice, Upwork and Indeed have no public feed. Instead, the bottom of the report has
one-click searches on those sites, already filtered to remote contract or part-time roles.

You can add more feeds, for example a Google Alert delivered as RSS, under `extra_feeds` in
`config.json`:

```json
"extra_feeds": [{"name": "Google Alert: copado contract", "url": "https://www.google.com/alerts/feeds/…", "remote": false}]
```

## How listings are ranked

`config.json` controls the matching:

* **`skills`**: each skill group has keywords and a weight. A keyword in the job title counts
  double. Keywords match whole words only, so `java` does not match `JavaScript`. A listing must hit
  at least one `"core": true` skill (Salesforce, Copado, Flosum or Java) to be shown.
* **Engagement type**: each listing is classified as part-time, contract, freelance, unspecified or
  full-time. It uses the board's own label first, then wording such as "part-time", "20–30 hrs/week",
  "1099", "C2C" or "6 month contract". Part-time and contract roles rank higher, and full-time roles
  are hidden unless you pass `--include-full-time`.
* **Recency**: listings from the last 2, 7 and 14 days get a boost.
* **`exclude_keywords`** removes titles you never want to see. **`exclude_location_patterns`** removes
  roles restricted to regions you can't work from, e.g. `["europe only", "^EMEA$", "UK only"]`.
* **`owner_name`** personalizes the page heading.

## Run it from your phone (GitHub Actions)

`.github/workflows/refresh.yml` runs the same search every 6 hours. You can also start it any time
from **Actions → Refresh contract classifieds → Run workflow**, which works in the GitHub mobile app.
Each run:

* shows the top matches in the run's summary page, and
* attaches the full report (`index.html`, CSV, JSON) as a downloadable artifact.

**Optional: a permanent URL with GitHub Pages.** Go to repository Settings → Pages → Source, choose
"GitHub Actions", then add a repository variable `ENABLE_PAGES` = `true` (Settings → Secrets and
variables → Actions → Variables). Each run then publishes the report to your Pages site.
GitHub Pages on a private repository requires a paid GitHub plan, and the page is publicly readable.

## Development

```bash
python3 -m unittest discover -s tests -t .
```

Each board adapter lives in `classifieds/sources.py`. To add a board, write a function that returns
`Job` objects and register it in `SOURCES`.
