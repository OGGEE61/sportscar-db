"""The D1 read budget: rows read are counted per request, refused queries fail fast, the heaviest
queries use indexes, and the local copy for analysis holds the same rows."""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_d1_reads.db")

import db
from app import app

D1_ENV = {"CF_ACCOUNT_ID": "acc", "CF_D1_DATABASE_ID": "dbid", "CF_API_TOKEN": "tok"}


def d1_reply(rows_read, results=None, status=200, text=""):
    resp = mock.Mock(ok=200 <= status < 300, status_code=status, text=text)
    resp.json.return_value = {"success": True, "result": [
        {"success": True, "results": results or [], "meta": {"rows_read": rows_read, "changes": 0}}]}
    return resp


class TestD1Backend(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, D1_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        db.ROWS_READ.reset()

    def test_rows_read_are_counted(self):
        with mock.patch.object(db._D1_SESSION, "post", side_effect=[d1_reply(120), d1_reply(30)]):
            conn = db.D1Backend()
            conn.execute("SELECT 1")
            conn.execute("SELECT 2")
        self.assertEqual(db.ROWS_READ.count, 150)

    def test_refused_query_is_not_retried(self):
        limit = d1_reply(0, status=400, text="exceeded D1's free tier daily row read limit")
        with mock.patch.object(db._D1_SESSION, "post", return_value=limit) as post, \
                mock.patch.object(db.time, "sleep") as sleep:
            with self.assertRaises(db.D1ClientError):
                db.D1Backend().execute("SELECT 1")
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_server_error_is_retried(self):
        with mock.patch.object(db._D1_SESSION, "post", side_effect=[d1_reply(0, status=503), d1_reply(5)]) as post, \
                mock.patch.object(db.time, "sleep"):
            db.D1Backend().execute("SELECT 1")
        self.assertEqual(post.call_count, 2)


class LocalDbCase(unittest.TestCase):
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

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)


class TestRowsReadReported(LocalDbCase):
    def test_header_on_every_response(self):
        res = self.client.get("/api/badges")
        self.assertIn("X-D1-Rows-Read", res.headers)

    def test_heavy_request_is_logged(self):
        def heavy(*args, **kwargs):
            db.ROWS_READ.add(50000)
            return {}
        with mock.patch("webapp.blueprints.dashboard._inject_notifications", side_effect=heavy), \
                mock.patch("builtins.print") as out:
            res = self.client.get("/api/badges")
        self.assertEqual(res.headers["X-D1-Rows-Read"], "50000")
        self.assertTrue(any("[d1] 50000 rows read: GET /api/badges" in str(c) for c in out.call_args_list))


class TestHeavyQueriesUseIndexes(LocalDbCase):
    def plan(self, sql, params=()):
        conn = sqlite3.connect(TEST_DB_PATH)
        try:
            return " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall())
        finally:
            conn.close()

    def test_mark_removed_reads_one_model(self):
        from webapp.blueprints import api
        import inspect
        src = inspect.getsource(api.api_mark_removed)
        sql = src[src.index("SELECT pl.source_listing_id"):src.index('""", (source, make, model, variant)')]
        plan = self.plan(sql, ("otomoto", "BMW", "M5", "F90 M5"))
        self.assertIn("idx_pending_variant", plan)
        self.assertNotIn("SCAN", plan)

    def test_plates_queue_has_no_scan_per_entry(self):
        res = self.client.get("/plates")
        self.assertEqual(res.status_code, 200)
        from webapp.blueprints import plates
        import inspect
        src = inspect.getsource(plates)
        sql = src[src.index("SELECT q.id, q.listing_id"):src.index('""", (status_filter,)')]
        self.assertNotIn("SCAN p", self.plan(sql, ("pending",)))


class TestMarkRemovedStillWorks(LocalDbCase):
    def test_listing_gone_from_the_search_is_marked(self):
        conn = db.get_db()
        for lid in ("1", "2"):
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, make, model, variant, status) "
                         "VALUES ('otomoto', ?, 'BMW', 'M5', 'F90 M5', 'approved')", (lid,))
            conn.execute("INSERT INTO vehicles (vin, make, model, year) VALUES (?, 'BMW', 'M5', 2020)", (f"WBSJF0C55KB00000{lid}",))
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id) VALUES (?, 'otomoto', ?)",
                         (f"WBSJF0C55KB00000{lid}", lid))
        conn.commit()
        conn.close()
        res = self.client.post("/api/mark_removed", headers={"Authorization": "Bearer test-token"},
                               json={"source": "otomoto", "make": "BMW", "model": "M5", "variant": "F90 M5", "seen_ids": ["1"]})
        self.assertEqual(res.get_json(), {"marked": 1})
        conn = db.get_db()
        removed = {r["source_listing_id"]: r["removed_at"] for r in
                   conn.execute("SELECT source_listing_id, removed_at FROM listing_observations").fetchall()}
        conn.close()
        self.assertIsNone(removed["1"])
        self.assertIsNotNone(removed["2"])


class TestLocalCopy(LocalDbCase):
    def test_export_copies_every_row(self):
        from scripts.maintenance import export_d1
        conn = db.get_db()
        for i in range(1203):
            conn.execute("INSERT INTO scraper_logs (status, message) VALUES ('success', ?)", (f"run {i}",))
        conn.commit()
        conn.close()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "copy.db")
            counts = export_d1.export(out)
            self.assertEqual(counts["scraper_logs"], 1203)
            copy = sqlite3.connect(out)
            self.assertEqual(copy.execute("SELECT COUNT(*), MAX(message) FROM scraper_logs").fetchone(), (1203, "run 999"))
            indexes = {r[0] for r in copy.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
            copy.close()
        self.assertIn("idx_pending_variant", indexes)


if __name__ == "__main__":
    unittest.main()


class TestStoredCache(LocalDbCase):
    def test_value_is_kept_until_its_ttl(self):
        from webapp.services import stored_cache
        calls = []

        def compute():
            calls.append(1)
            return {"n": len(calls)}
        app.config["TESTING"] = False
        try:
            with app.app_context():
                self.assertEqual(stored_cache.stored("k", 3600, compute), {"n": 1})
                self.assertEqual(stored_cache.stored("k", 3600, compute), {"n": 1})   # one row read back
                with mock.patch.object(stored_cache.time, "time", return_value=stored_cache.time.time() + 7200):
                    self.assertEqual(stored_cache.stored("k", 3600, compute), {"n": 2})
        finally:
            app.config["TESTING"] = True
        self.assertEqual(len(calls), 2)


class TestPagesReadOnlyWhatTheyShow(LocalDbCase):
    """The model, deals and vehicles pages reach sightings through indexes, never by reading all of them."""

    def plans_of(self, path):
        import re
        plans = []
        real = db.get_conn

        def spying():
            conn = real()

            class Spy:
                def execute(_, sql, params=()):
                    if sql.strip().upper().startswith(("SELECT", "WITH")):
                        plans.append(" | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()))
                    return conn.execute(sql, params)

                def __getattr__(_, name):
                    return getattr(conn, name)
            return Spy()
        with mock.patch.object(db, "get_conn", spying):
            self.assertEqual(self.client.get(path).status_code, 200)
        return [p for p in plans if re.search(r"SCAN (listing_observations|o|x|f)\b", p)]

    def test_no_full_scan_of_sightings(self):
        for path in ("/models?model=m5_f90", "/api/deals?km=50&days=30", "/vehicles"):
            self.assertEqual(self.plans_of(path), [], path)

    def test_models_page_takes_each_cars_newest_sighting(self):
        import re
        seen = []
        real = db.get_conn

        def spying():
            conn = real()

            class Spy:
                def execute(_, sql, params=()):
                    if sql.strip().upper().startswith(("SELECT", "WITH")):
                        seen.append(" | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()))
                    return conn.execute(sql, params)

                def __getattr__(_, name):
                    return getattr(conn, name)
            return Spy()
        with mock.patch.object(db, "get_conn", spying):
            self.client.get("/models?model=m5_f90")
        main = next(p for p in seen if "idx_vehicles_model_id" in p)
        self.assertIn("idx_obs_vin_observed", main)
        self.assertFalse(re.search(r"idx_obs_price|MATERIALIZE", main), main)   # no numbering of every sighting
