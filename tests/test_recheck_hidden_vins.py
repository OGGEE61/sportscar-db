"""scripts/maintenance/recheck_hidden_vins.py flags pending otomoto ads saved without a VIN whose
page now says the VIN is behind "Wyświetl VIN", so the reveal job picks them up."""
import os
import sys
import unittest
from unittest import mock

sys.path[:0] = [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_recheck_hidden_vins.db")

import db
from scripts.maintenance import recheck_hidden_vins as job


class TestRecheckHiddenVins(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db.init_db()
        conn = db.get_db()
        for sid, source, status, conf in (("1", "otomoto", "pending", "none"),      # flag on the page
                                          ("2", "otomoto", "pending", "none"),      # no flag
                                          ("3", "otomoto", "rejected", "none"),     # not in the queue
                                          ("4", "olx", "pending", "none"),          # not otomoto
                                          ("5", "otomoto", "pending", "not_shown")):  # Otomoto said no VIN
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, source_url, status, vin_confidence) "
                         "VALUES (?, ?, ?, ?, ?)", (source, sid, f"https://www.otomoto.pl/x-ID{sid}.html", status, conf))
        conn.commit()
        conn.close()
        patches = [mock.patch.object(job.time, "sleep"), mock.patch("builtins.print"),
                   mock.patch.object(job, "fetch_detail", side_effect=self.page)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.opened = []

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def page(self, url):
        self.opened.append(url)
        return {"vin": None, "vin_confidence": "found_in_schema" if "ID1." in url else "none"}

    def flags(self):
        conn = db.get_db()
        out = {r["source_listing_id"]: r["vin_confidence"] for r in conn.execute("SELECT * FROM pending_listings")}
        conn.close()
        return out

    def test_without_yes_nothing_changes(self):
        before = self.flags()
        with mock.patch.object(sys, "argv", ["recheck_hidden_vins.py"]):
            job.main()
        self.assertEqual(self.flags(), before)

    def test_only_pending_otomoto_ads_are_opened_and_only_flagged_ones_change(self):
        with mock.patch.object(sys, "argv", ["recheck_hidden_vins.py", "--yes"]):
            job.main()
        self.assertEqual(len(self.opened), 2)
        self.assertEqual(self.flags(), {"1": "found_in_schema", "2": "none", "3": "none", "4": "none",
                                        "5": "not_shown"})


if __name__ == "__main__":
    unittest.main()
