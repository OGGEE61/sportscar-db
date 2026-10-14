"""Regression tests for sold-marking scope, partial scrapes, detail skipping and paging."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrapers"))

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_scraping.db")

import db
from app import app
import base_scraper

TOKEN = {"Authorization": "Bearer test-token"}


class ScrapingTestCase(unittest.TestCase):
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

    def add_active_listing(self, sid, vin, variant, make="BMW", model="M3", **pending):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year) VALUES (?,?,?,?,2016)",
                     (vin, make, model, variant))
        conn.execute("""INSERT INTO pending_listings
                        (source, source_listing_id, make, model, variant, vin, status,
                         registration_plate, first_registration_date)
                        VALUES ('otomoto', ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (sid, make, model, variant, vin, pending.get("status", "approved"),
                      pending.get("plate"), pending.get("frd")))
        conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id) VALUES (?, 'otomoto', ?)",
                     (vin, sid))
        conn.commit()
        conn.close()

    def removed(self, sid):
        conn = db.get_db()
        row = conn.execute("SELECT removed_at FROM listing_observations WHERE source_listing_id=?", (sid,)).fetchone()
        conn.close()
        return row["removed_at"] is not None


class TestMarkRemovedScope(ScrapingTestCase):
    def test_sibling_generation_is_not_marked_sold(self):
        self.add_active_listing("f80-1", "WBS8M9C50J5K99001", "F80")
        self.add_active_listing("e46-1", "WBSBL93450JR99002", "E46 M3")
        res = self.client.post("/api/mark_removed", headers=TOKEN, json={
            "source": "otomoto", "make": "BMW", "model": "M3", "variant": "F80",
            "seen_ids": ["something-else"]})
        self.assertEqual(res.get_json()["marked"], 1)
        self.assertTrue(self.removed("f80-1"))
        self.assertFalse(self.removed("e46-1"))

    def test_seen_listing_stays_active(self):
        self.add_active_listing("f80-1", "WBS8M9C50J5K99001", "F80")
        self.client.post("/api/mark_removed", headers=TOKEN, json={
            "source": "otomoto", "make": "BMW", "model": "M3", "variant": "F80", "seen_ids": ["f80-1"]})
        self.assertFalse(self.removed("f80-1"))

    def test_missing_variant_marks_nothing(self):
        self.add_active_listing("f80-1", "WBS8M9C50J5K99001", "F80")
        res = self.client.post("/api/mark_removed", headers=TOKEN, json={
            "source": "otomoto", "make": "BMW", "model": "M3", "seen_ids": ["x"]})
        self.assertEqual(res.get_json()["marked"], 0)
        self.assertFalse(self.removed("f80-1"))


class TestSeenAgainClearsRemoved(ScrapingTestCase):
    def test_reappearing_listing_is_active_again(self):
        self.add_active_listing("f80-1", "WBS8M9C50J5K99001", "F80")
        self.client.post("/api/mark_removed", headers=TOKEN, json={
            "source": "otomoto", "make": "BMW", "model": "M3", "variant": "F80", "seen_ids": ["other"]})
        self.assertTrue(self.removed("f80-1"))
        res = self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": "otomoto", "source_listing_id": "f80-1", "price_pln": 300000})
        self.assertIn(res.get_json()["tag"], ("seen_again", "price_updated"))
        conn = db.get_db()
        left = conn.execute("SELECT COUNT(*) FROM listing_observations "
                            "WHERE source_listing_id='f80-1' AND removed_at IS NOT NULL").fetchone()[0]
        conn.close()
        self.assertEqual(left, 0)


class TestModelId(ScrapingTestCase):
    def add_vehicle(self, vin, make, model, variant, year, hp=None, model_id=None):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, power_hp, model_id) VALUES (?,?,?,?,?,?,?)",
                     (vin, make, model, variant, year, hp, model_id))
        conn.commit()
        conn.close()

    def test_resolve_picks_the_single_matching_generation(self):
        from webapp.model_catalog import resolve_model_ids
        self.add_vehicle("WBS8M9C50J5K99001", "BMW", "X3", "M40i", 2022)
        self.add_vehicle("ZZZ", "Nobody", "Nothing", None, 2000)
        conn = db.get_db()
        out = resolve_model_ids(conn)
        conn.close()
        self.assertEqual(out["WBS8M9C50J5K99001"], "x3_m40i_g01")
        self.assertIsNone(out["ZZZ"])

    def test_assign_never_overwrites_and_prefers_declared_id(self):
        from webapp.model_catalog import assign_model_id
        self.add_vehicle("WBS8M9C50J5K99001", "BMW", "X3", "M40i", 2022, model_id="x3_m_f97")
        conn = db.get_db()
        assign_model_id(conn, "WBS8M9C50J5K99001", "x3_m40i_g01")
        got = conn.execute("SELECT model_id FROM vehicles WHERE vin='WBS8M9C50J5K99001'").fetchone()[0]
        conn.close()
        self.assertEqual(got, "x3_m_f97")

    def test_models_page_uses_stored_model_id(self):
        self.add_vehicle("WBS8M9C50J5K99001", "BMW", "X3", "M40i", 2022, model_id="x3_m_f97")
        page = self.client.get("/models?model=x3_m40i_g01")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"WBS8M9C50J5K99001", page.data)


class TestKnownListings(ScrapingTestCase):
    def test_complete_incomplete_and_rejected(self):
        self.add_active_listing("full", "WBS8M9C50J5K99001", "F80", plate="WX12345", frd="2016-05-01")
        self.add_active_listing("noplate", "WBS8M9C50J5K99003", "F80")
        self.add_active_listing("rej", "WBS8M9C50J5K99004", "F80", status="rejected")
        res = self.client.post("/api/known_listings", headers=TOKEN, json={"items": [
            ["otomoto", "full"], ["otomoto", "noplate"], ["otomoto", "rej"], ["otomoto", "new"]]})
        known = res.get_json()["known"]
        self.assertTrue(known["otomoto:full"]["complete"])
        self.assertFalse(known["otomoto:noplate"]["complete"])
        self.assertTrue(known["otomoto:rej"]["complete"])
        self.assertNotIn("otomoto:new", known)

    def test_requires_token(self):
        res = self.client.post("/api/known_listings", json={"items": []})
        self.assertEqual(res.status_code, 401)


def _card(i):
    return {"listing_id": f"id{i}", "title": "BMW M3 F80", "price_raw": "300 000 PLN",
            "source_url": f"https://www.otomoto.pl/oferta/{i}", "thumbnail": None, "location_city": "Warszawa"}


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self.text = "<html></html>"
        self._data = data or {}

    def json(self):
        return self._data


class TestScraperRun(unittest.TestCase):
    CFG = base_scraper.ScraperConfig(make="BMW", model="M3", variant="F80", source="otomoto",
                                     list_url="https://www.otomoto.pl/x?page={page}", detail_delay=0)

    def run_scraper(self, list_statuses, known=None):
        pages = iter(list_statuses)
        api = mock.MagicMock()
        api.post.side_effect = lambda url, **kw: FakeResp(200, {"known": known or {}} if "known_listings" in url
                                                          else {"tag": "pending", "marked": 0})
        with mock.patch.object(base_scraper, "load_cookies", return_value={}), \
             mock.patch.object(base_scraper.requests, "get", side_effect=lambda *a, **k: FakeResp(next(pages))), \
             mock.patch.object(base_scraper, "_parse_otomoto_cards", side_effect=[[_card(1), _card(2)], []]), \
             mock.patch.object(base_scraper, "fetch_detail", return_value={}) as detail, \
             mock.patch.object(base_scraper, "_API_SESSION", api), \
             mock.patch.object(base_scraper.time, "sleep"):
            base_scraper.run(self.CFG)
        urls = [c.args[0] for c in api.post.call_args_list]
        return urls, api, detail

    def test_partial_run_does_not_mark_sold(self):
        urls, api, _ = self.run_scraper([200, 403])
        self.assertFalse(any("mark_removed" in u for u in urls))
        log = next(c for c in api.post.call_args_list if c.args[0].endswith("/api/log_run"))
        self.assertEqual(log.kwargs["json"]["status"], "partial")

    def test_clean_run_marks_sold_with_variant(self):
        urls, api, _ = self.run_scraper([200, 200])
        call = next(c for c in api.post.call_args_list if "mark_removed" in c.args[0])
        self.assertEqual(call.kwargs["json"]["variant"], "F80")
        self.assertEqual(set(call.kwargs["json"]["seen_ids"]), {"id1", "id2"})

    def test_known_complete_listing_skips_detail(self):
        _, _, detail = self.run_scraper([200, 200], known={"otomoto:id1": {"status": "approved", "complete": True}})
        self.assertEqual(detail.call_count, 1)  # only id2 fetched


class TestOlxSkipsOtomotoHosted(unittest.TestCase):
    CFG = base_scraper.ScraperConfig(make="BMW", model="M4", variant="F82", source="olx",
                                     list_url="https://www.olx.pl/x/?page={page}", detail_delay=0,
                                     skip_otomoto_hosted=True)

    def test_only_olx_ads_fetched_and_otomoto_only_page_does_not_stop_paging(self):
        def card(i, host):
            c = _card(i)
            c["source_url"] = (f"https://www.otomoto.pl/oferta/{i}" if host == "oto"
                               else f"https://www.olx.pl/d/oferta/{i}")
            return c
        pages = [[card(1, "oto"), card(2, "oto")],   # page 1: only cross-posted otomoto ads
                 [card(3, "olx"), card(4, "oto")],   # page 2: one OLX ad
                 []]
        api = mock.MagicMock()
        api.post.side_effect = lambda url, **kw: FakeResp(200, {"known": {}, "tag": "pending", "marked": 0})
        with mock.patch.object(base_scraper, "load_cookies", return_value={}), \
             mock.patch.object(base_scraper.requests, "get", side_effect=lambda *a, **k: FakeResp(200)), \
             mock.patch.object(base_scraper, "_parse_olx_cards", side_effect=pages), \
             mock.patch.object(base_scraper, "fetch_detail", return_value={}) as detail, \
             mock.patch.object(base_scraper, "_API_SESSION", api), \
             mock.patch.object(base_scraper.time, "sleep"):
            results = base_scraper.run(self.CFG)
        self.assertEqual([r["source_listing_id"] for r in results], ["id3"])
        self.assertEqual(detail.call_count, 1)
        self.assertTrue(any("mark_removed" in c.args[0] for c in api.post.call_args_list))


class TestOlxRunner(unittest.TestCase):
    def test_olx_configs_are_olx_and_match_otomoto_identity(self):
        import importlib
        run_olx = importlib.import_module("run_olx")
        from otomoto.bmw_m3_f80 import CONFIG as oto_f80
        self.assertTrue(all(c.source == "olx" for c in run_olx.ALL_OLX_FLEET))
        f80 = run_olx.M3_F80_OLX
        self.assertEqual((f80.make, f80.model, f80.variant), (oto_f80.make, oto_f80.model, oto_f80.variant))
        self.assertEqual(oto_f80.source, "otomoto")  # replace() must not mutate the otomoto config


class TestSourceDisplay(ScrapingTestCase):
    def ingest(self, sid, source, found_by):
        self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": source, "source_listing_id": sid, "raw_title": f"BMW M4 {sid}",
            "make": "BMW", "model": "M4", "variant": "F82", "found_by": found_by})

    def test_ingest_stores_found_by_and_review_filters_by_source(self):
        self.ingest("o1", "otomoto", "olx")   # cross-posted otomoto ad seen by the OLX scraper
        self.ingest("x1", "olx", "olx")
        conn = db.get_db()
        row = conn.execute("SELECT source, found_by FROM pending_listings WHERE source_listing_id='o1'").fetchone()
        conn.close()
        self.assertEqual((row["source"], row["found_by"]), ("otomoto", "olx"))
        page = self.client.get("/review").get_data(as_text=True)
        self.assertIn("src-otomoto", page)
        self.assertIn("via OLX", page)
        olx_only = self.client.get("/review?source=olx").get_data(as_text=True)
        self.assertIn("BMW M4 x1", olx_only)
        self.assertNotIn("BMW M4 o1", olx_only)

    def test_logs_source_column_url_fallback_and_filter(self):
        self.client.post("/api/log_run", headers=TOKEN, json={
            "status": "success", "message": "olx run", "source": "olx"})
        # no source field, like rows written before migration v11
        self.client.post("/api/log_run", headers=TOKEN, json={
            "status": "success", "message": "old otomoto run", "list_url": "https://www.otomoto.pl/osobowe/bmw/m3"})
        page = self.client.get("/logs").get_data(as_text=True)
        self.assertIn("src-olx", page)
        self.assertIn("src-otomoto", page)
        oto = self.client.get("/logs?source=otomoto").get_data(as_text=True)
        self.assertIn("old otomoto run", oto)
        self.assertNotIn("olx run", oto)

    def test_vehicles_filter_by_source(self):
        self.add_active_listing("f80-1", "WBS8M9C50J5K99001", "F80")
        all_page = self.client.get("/vehicles").get_data(as_text=True)
        self.assertIn("WBS8M9C50J5K99001", all_page)
        self.assertIn("src-otomoto", all_page)
        self.assertNotIn("WBS8M9C50J5K99001", self.client.get("/vehicles?source=olx").get_data(as_text=True))

    def test_optional_column_write_never_raises(self):
        from webapp.blueprints.api import _set_optional_column
        conn = db.get_db()
        _set_optional_column(conn, "scraper_logs", "column_not_migrated", "olx", 1)
        conn.close()


class TestNoScriptInjection(ScrapingTestCase):
    def test_description_and_title_are_escaped(self):
        self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": "olx", "source_listing_id": "x1", "make": "BMW", "model": "M4",
            "raw_title": "M4 </script><script>alert(1)</script>",
            "raw_description": "Zadbany &amp; <img src=x onerror=alert(1)>"})
        conn = db.get_db()
        pid = conn.execute("SELECT id FROM pending_listings WHERE source_listing_id='x1'").fetchone()[0]
        conn.close()
        page = self.client.get(f"/review/{pid}").get_data(as_text=True)
        self.assertNotIn("<img src=x onerror", page)
        self.assertIn("Zadbany &amp; &lt;img", page)  # entity decoded, then escaped once
        self.assertNotIn("<script>alert(1)", self.client.get("/review").get_data(as_text=True))


class TestPages(ScrapingTestCase):
    def test_manual_vehicle_detail_without_review_or_cepik(self):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, year) VALUES ('WBS8M9C50J5K99009','BMW','M3',2016)")
        conn.commit()
        conn.close()
        self.assertEqual(self.client.get("/vehicle/WBS8M9C50J5K99009").status_code, 200)

    def test_review_is_paged(self):
        conn = db.get_db()
        for i in range(35):
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, raw_title) VALUES ('olx', ?, ?)",
                         (str(i), f"car-{i}"))
        conn.commit()
        conn.close()
        page1 = self.client.get("/review").get_data(as_text=True)
        page2 = self.client.get("/review?page=2").get_data(as_text=True)
        self.assertIn("page=2", page1)
        self.assertEqual(page1.count("list-group-item d-flex"), 30)
        self.assertEqual(page2.count("list-group-item d-flex"), 5)

    def test_logs_page_paged(self):
        self.assertEqual(self.client.get("/logs?page=3").status_code, 200)

    def test_models_defaults_to_x3_m40i(self):
        page = self.client.get("/models").get_data(as_text=True)
        self.assertIn("BMW X3 M40i (G01)", page)


if __name__ == "__main__":
    unittest.main()
