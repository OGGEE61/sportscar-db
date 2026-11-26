"""The Weryfikacja tab "Szkoda w ogłoszeniu, bez wpisu": cars whose ad is marked damaged (by the portal
or its text) but whose damage history is empty, e.g. #1552 X3 with "01.2026: kolizja boczna" in its ad.
A history entry or a dismissed mark takes the car off it. The review MCP lists the tab (list_verify)."""
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT]

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(ROOT, "tests", "test_damage_marked.db")

import db
from app import app
from scripts import review_mcp
from webapp.services import verification

MARKED, CALM = "5UXTS3C57J0Z01124", "WBS8M9C53J5L01183"
QUOTE = "text: 01.2026: kolizja boczna, uszkodzony lewy przód i przód"


class TestMarkedTab(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db.init_db()
        app.config["TESTING"] = True
        self.client = app.test_client()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        os.environ.pop("ADMIN_PASSWORD", None)
        self.addCleanup(patcher.stop)
        conn = db.get_db()
        for i, vin in enumerate((MARKED, CALM), 1):
            conn.execute("INSERT INTO vehicles (vin, make, model, year) VALUES (?, 'BMW', 'X3', 2018)", (vin,))
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, source_url, status, vin) "
                         "VALUES ('otomoto', ?, ?, 'approved', ?)", (str(i), f"https://www.otomoto.pl/oferta/{i}", vin))
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, observed_at, first_seen_at) "
                         "VALUES (?, 'otomoto', ?, '2026-11-20 10:00:00', '2026-11-20')", (vin, str(i)))
        conn.execute("INSERT INTO damaged_listings (source, source_listing_id, reason) VALUES ('otomoto', '1', ?)", (QUOTE,))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def page(self):
        return self.client.get("/verify?issue=marked").get_data(as_text=True)

    def test_a_marked_car_without_history_is_listed_with_the_quote(self):
        page = self.page()
        self.assertIn(MARKED, page)
        self.assertNotIn(CALM, page)
        self.assertIn("kolizja boczna, uszkodzony lewy przód", page)
        conn = db.get_db()
        self.assertEqual(verification.verify_counts(conn)["marked"], 1)
        conn.close()

    def test_a_history_entry_or_a_dismissed_mark_ends_it(self):
        conn = db.get_db()
        conn.execute("INSERT INTO condition_reports (vin, report_date, accident_free, notes, source_method) "
                     "VALUES (?, '2026-01-01', 0, 'kolizja boczna', 'manual')", (MARKED,))
        conn.commit()
        conn.close()
        self.assertNotIn(MARKED, self.page())
        conn = db.get_db()
        conn.execute("DELETE FROM condition_reports")
        conn.commit()
        verification.set_damage_dismissed(conn, MARKED, True)
        conn.close()
        self.assertNotIn(MARKED, self.page())

    def test_the_review_mcp_lists_the_tab(self):
        listed = json.loads(review_mcp.list_verify("marked"))
        self.assertEqual(listed["total"], 1)
        car = listed["cars"][0]
        self.assertEqual((car["vin"], car["marks"], car["ad"]), (MARKED, [QUOTE], "https://www.otomoto.pl/oferta/1"))
        self.assertIn("Nieznana zakładka", review_mcp.list_verify("nope"))


if __name__ == "__main__":
    unittest.main()
