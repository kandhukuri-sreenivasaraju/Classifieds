import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from classifieds.models import Job, parse_date, strip_html
from classifieds.render import render_html
from classifieds.scoring import classify_engagement, dedupe, keyword_regex, score_and_filter
from unittest import mock

from classifieds import sources
from classifieds.sources import parse_feed
from classifieds.store import mark_new

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)


def job(title, description="", job_type="", days_old=1, company="Acme", **kw):
    return Job(source="Test", title=title, company=company, url=f"https://x.test/{title}",
               description=description, job_type=job_type, posted=NOW - timedelta(days=days_old),
               remote=True, **kw)


class KeywordTests(unittest.TestCase):
    def test_java_does_not_match_javascript(self):
        self.assertIsNone(keyword_regex("java").search("Senior JavaScript engineer"))
        self.assertIsNotNone(keyword_regex("java").search("Java/Spring developer"))

    def test_symbols_in_keywords(self):
        self.assertIsNotNone(keyword_regex("ci/cd").search("own our CI/CD pipelines"))
        self.assertIsNotNone(keyword_regex("force.com").search("Force.com sites"))


class EngagementTests(unittest.TestCase):
    def test_labels_and_text(self):
        self.assertEqual(classify_engagement(job("Salesforce Dev", job_type="part_time")), "part-time")
        self.assertEqual(classify_engagement(job("Salesforce Dev", job_type="Contractor")), "contract")
        self.assertEqual(classify_engagement(job("Part-Time Salesforce Admin")), "part-time")
        self.assertEqual(classify_engagement(job("Salesforce Dev", "20-30 hours per week")), "part-time")
        self.assertEqual(classify_engagement(job("Salesforce Dev", "Full-time, benefits")), "full-time")
        self.assertEqual(classify_engagement(job("Salesforce Dev", "Great team")), "unknown")

    def test_full_time_label_overridden_by_strong_contract_wording(self):
        j = job("Copado Engineer", "This is a 6 month contract with possible extension.", job_type="full_time")
        self.assertEqual(classify_engagement(j), "contract")
        j = job("Copado Engineer", "We sign contracts with customers.", job_type="full_time")
        self.assertEqual(classify_engagement(j), "full-time")


class ScoringTests(unittest.TestCase):
    def test_filters_and_ranks(self):
        jobs = [
            job("Copado Release Engineer (Contract)", "Salesforce DevOps with Copado and Flosum"),
            job("Salesforce Admin", "Part-time, flows and permission sets", days_old=3),
            job("React Developer", "JavaScript contract role"),  # no core skill
            job("Java Engineer", "Full-time permanent role, Salesforce integration"),  # full-time
            job("Old Salesforce contract", "contract", days_old=90),  # too old
            job("Salesforce Intern", "contract"),                 # excluded keyword
        ]
        out = score_and_filter(jobs, CFG, now=NOW)
        titles = [j.title for j in out]
        self.assertEqual(titles, ["Copado Release Engineer (Contract)", "Salesforce Admin"])
        self.assertIn("Copado", out[0].matched_skills)
        self.assertIn("Flosum", out[0].matched_skills)

        with_ft = score_and_filter(jobs, CFG, now=NOW, include_full_time=True)
        self.assertIn("Java Engineer", [j.title for j in with_ft])

    def test_dedupe_merges_sources(self):
        a = job("Salesforce Developer", "short")
        b = job("Salesforce Developer", "a much longer description", job_type="contract")
        b.source = "Other"
        merged = dedupe([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].source, "Other")
        self.assertEqual(merged[0].also_on, ["Test"])


class HelperTests(unittest.TestCase):
    def test_parse_date_formats(self):
        for value in ("2026-09-27T10:00:00", "2026-09-27T10:00:00Z", "2026-09-27 10:00:00",
                      "Sun, 27 Sep 2026 10:00:00 +0000", 1790503200, "1790503200"):
            self.assertIsNotNone(parse_date(value), value)
        self.assertIsNone(parse_date("not a date"))

    def test_strip_html(self):
        self.assertEqual(strip_html("<p>Hello&nbsp;<b>world</b></p><p>Line 2</p>"), "Hello\xa0world\nLine 2")
        self.assertEqual(strip_html("&lt;p&gt;Escaped &amp;amp; ok&lt;/p&gt;"), "Escaped & ok")

    def test_parse_rss(self):
        raw = b"""<?xml version="1.0"?><rss><channel><item>
          <title>Acme: Salesforce Contractor</title><link>https://wwr.test/1</link>
          <pubDate>Sun, 27 Sep 2026 10:00:00 +0000</pubDate><region>Anywhere</region>
          <type>Contract</type><description>&lt;p&gt;Apex work&lt;/p&gt;</description>
        </item></channel></rss>"""
        (j,) = parse_feed(raw, "We Work Remotely", remote=True)
        self.assertEqual((j.company, j.title, j.job_type, j.description), ("Acme", "Salesforce Contractor", "Contract", "Apex work"))

    def test_hackernews_skips_seeking_work_and_strips_prefix(self):
        hits = {"hits": [
            {"objectID": "1", "story_title": "Ask HN: Freelancer? Seeking freelancer?", "created_at_i": 1790503200,
             "comment_text": "SEEKING FREELANCER | Umbrella | Salesforce Apex dev | REMOTE<p>Hourly contract"},
            {"objectID": "2", "story_title": "Ask HN: Freelancer? Seeking freelancer?", "created_at_i": 1790503200,
             "comment_text": "SEEKING WORK | Remote | Salesforce consultant"},
            {"objectID": "3", "story_title": "Show HN: something else", "created_at_i": 1790503200,
             "comment_text": "Salesforce"},
        ]}
        with mock.patch.object(sources, "fetch_json", return_value=hits):
            (j,) = sources.fetch_hackernews(["salesforce"])
        self.assertEqual((j.company, j.title), ("Umbrella", "Salesforce Apex dev | REMOTE"))
        self.assertTrue(j.remote)

    def test_mark_new_and_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "seen.json"
            jobs = score_and_filter([job("Salesforce Contract Dev", "apex")], CFG, now=NOW)
            self.assertEqual(mark_new(jobs, state), 1)
            again = score_and_filter([job("Salesforce Contract Dev", "apex")], CFG, now=NOW)
            self.assertEqual(mark_new(again, state), 0)
            page = render_html(jobs, CFG, {"per_source": {"test": 1}}, now=NOW)
            self.assertIn("Salesforce Contract Dev", page)
            self.assertIn('class="badge new"', page)


if __name__ == "__main__":
    unittest.main()
