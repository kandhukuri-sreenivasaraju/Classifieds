# Personal Contract Classifieds

This tool pulls the latest **remote contract, freelance and part-time** software roles that match
your skills from several job boards. It ranks them and writes a classifieds-style web page you can
open whenever you want to check.

It is set up for these skills: **Salesforce (development, admin, integration), Java, Copado and
Flosum deployments** and related Salesforce DevOps.

Everything uses the Python standard library, so there is nothing to install and no API keys to set up.

## The web app (no commands needed)

`web/index.html` is a single-page app for browsing listings:

* **Refresh** fetches the latest listings straight from the job boards in your browser. It also
  refreshes by itself when you open it and the data is more than an hour old.
* **NEW** badges mark listings you haven't seen before.
* **Save**, **Applied** and **Hide** buttons, with a tab for each list.
* Only roles open to Canada by default (see *Location* below).
* Filters for search text, work type (part-time, contract, freelance), date range and sort order,
  plus a **CSV** export.
* **Settings** lets you edit your skills, keywords, weights, search terms, boards and exclusions.

Your settings and lists are saved in your browser only (localStorage), so they don't move between
devices.

### Put it online with GitHub Pages (one-time setup, about a minute)

1. On GitHub, open the repository's **Settings → Pages**. Under *Build and deployment → Source*,
   choose **GitHub Actions**.
2. Open **Actions → Refresh contract classifieds → Run workflow**.

When it finishes, the app is live at `https://<your-username>.github.io/<repo-name>/`. Bookmark it
or add it to your phone's home screen. After that, GitHub refreshes the data every 6 hours and on
every change to `main`. The page also shows the boards that block direct browser access (for example
We Work Remotely), because the scheduled GitHub run collects them. The page has a link to trigger a
run whenever you want.

GitHub Pages on a *private* repository requires a paid GitHub plan. The published page is
publicly readable. It contains only job listings and the skill keywords.

**Without Pages:** download `web/index.html` and open it in a browser. Refresh still works for
every board that allows direct browser access.

## Command line

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

LinkedIn, Indeed Canada, Job Bank, Eluta and Upwork have no public feed. Instead, the bottom of the
page has one-click searches on those sites, already filtered to contract or part-time roles in Canada
where the site supports it.

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
* **Location (Canada by default)**: `allow_locations` keeps only roles whose location, title or
  description mentions Canada, a Canadian city or province, or North America or the Americas.
  Roles listed as worldwide or "anywhere" are hidden unless you set `"include_worldwide": true`.
  In the web app, both settings are at the top of **Settings**. Empty `allow_locations` to show
  every location.
* **`exclude_keywords`** removes titles you never want to see. **`exclude_location_patterns`** removes
  roles restricted to regions you can't work from, e.g. `["europe only", "^EMEA$", "UK only"]`.
* **`owner_name`** personalizes the page heading.

## Scheduled runs (GitHub Actions)

`.github/workflows/refresh.yml` runs the Python fetcher every 6 hours, on changes to `main` and on
demand. Each run shows the top matches on its summary page, attaches the site (web app,
`jobs.json`, CSV, printable `report.html`) as a downloadable artifact, and publishes it to GitHub
Pages when Pages is enabled.

## Development

```bash
python3 -m unittest discover -s tests -t .
```

Each board adapter lives in `classifieds/sources.py`. To add a board, write a function that returns
`Job` objects and register it in `SOURCES`. The web app has its own copy of the board adapters and
the scoring rules (in `web/index.html`), so keep the two in step when you change them.
