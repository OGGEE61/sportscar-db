"""D1 usage from Cloudflare's analytics: parsing, the dashboard bar, and what happens without a token."""
import datetime
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_d1_usage.db")

import db
from app import app
from webapp.services import d1_usage

TODAY = str(datetime.datetime.now(datetime.timezone.utc).date())


def answer(*days):
    groups = [{"dimensions": {"date": d}, "sum": {"readQueries": 10, "rowsRead": r, "rowsWritten": 7}} for d, r in days]
    response = mock.Mock()
    response.json.return_value = {"data": {"viewer": {"accounts": [{"d1AnalyticsAdaptiveGroups": groups}]}}}
    return response


class TestD1Usage(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db.init_db()
        app.config["TESTING"] = True
        self.client = app.test_client()
        patcher = mock.patch.dict(os.environ, {"CF_ANALYTICS_TOKEN": "tok", "CF_ACCOUNT_ID": "acc", "CF_D1_DATABASE_ID": "dbid"})
        patcher.start()
        os.environ.pop("ADMIN_PASSWORD", None)
        self.addCleanup(patcher.stop)
        d1_usage._cache.update(at=0.0, value=None)

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def test_daily_usage_is_parsed(self):
        with mock.patch("webapp.services.d1_usage.requests.post", return_value=answer(("2026-11-16", 1_500_000), (TODAY, 400_000))) as post:
            usage = d1_usage.daily_usage(2)
        self.assertEqual(usage[1], {"date": TODAY, "rows_read": 400_000, "rows_written": 7, "read_queries": 10})
        self.assertEqual(post.call_args.kwargs["json"]["variables"]["d"], "dbid")

    def test_nothing_is_read_without_the_token_or_when_cloudflare_fails(self):
        with mock.patch("webapp.services.d1_usage.requests.post") as post:
            del os.environ["CF_ANALYTICS_TOKEN"]
            self.assertIsNone(d1_usage.daily_usage())
            post.assert_not_called()
        os.environ["CF_ANALYTICS_TOKEN"] = "tok"
        with mock.patch("webapp.services.d1_usage.requests.post", side_effect=OSError("down")):
            self.assertIsNone(d1_usage.daily_usage())
        with mock.patch("webapp.services.d1_usage.requests.post", return_value=mock.Mock(json=lambda: {"errors": ["x"]})):
            self.assertIsNone(d1_usage.daily_usage())

    def test_bar_shows_from_half_of_the_limit(self):
        for rows, expect in ((400_000, None), (2_600_000, "alert-warning"), (4_200_000, "alert-danger")):
            d1_usage._cache.update(at=0.0, value=None)
            with mock.patch("webapp.services.d1_usage.requests.post", return_value=answer((TODAY, rows))):
                html = self.client.get("/api/d1_usage").get_data(as_text=True)
            if expect is None:
                self.assertEqual(html.strip(), "")
            else:
                self.assertIn(expect, html)
                self.assertIn(f"{round(100 * rows / 5_000_000)}%", html)

    def test_bar_is_empty_without_a_token_and_the_answer_is_kept_for_a_while(self):
        del os.environ["CF_ANALYTICS_TOKEN"]
        self.assertEqual(self.client.get("/api/d1_usage").get_data(as_text=True).strip(), "")
        os.environ["CF_ANALYTICS_TOKEN"] = "tok"
        d1_usage._cache.update(at=0.0, value=None)
        with mock.patch("webapp.services.d1_usage.requests.post", return_value=answer((TODAY, 100))) as post:
            self.client.get("/api/d1_usage")
            self.client.get("/api/d1_usage")
        self.assertEqual(post.call_count, 1)

    def test_dashboard_loads_the_bar(self):
        self.assertIn('hx-get="/api/d1_usage"', self.client.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
