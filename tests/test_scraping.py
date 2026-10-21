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
        # "" rather than pop: importing scripts.* runs load_dotenv, which would put the real one back
        os.environ["ADMIN_PASSWORD"] = ""
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


class TestBulkActionsRespectSource(ScrapingTestCase):
    def add(self, sid, source, status="pending", vin=None):
        conn = db.get_db()
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, make, model, variant, status, vin) "
                     "VALUES (?,?,?,?,?,?,?)", (source, sid, "BMW", "M3", "F80", status, vin))
        conn.commit()
        conn.close()

    def status(self, sid):
        conn = db.get_db()
        row = conn.execute("SELECT status FROM pending_listings WHERE source_listing_id=?", (sid,)).fetchone()
        conn.close()
        return row["status"] if row else None

    def test_reject_all_only_touches_filtered_source(self):
        self.add("o1", "olx")
        self.add("m1", "otomoto")
        self.client.post("/review/reject_all_pending?ajax=1&source=olx")
        self.assertEqual(self.status("o1"), "rejected")
        self.assertEqual(self.status("m1"), "pending")

    def test_reject_all_without_filter_rejects_everything(self):
        self.add("o1", "olx")
        self.add("m1", "otomoto")
        self.client.post("/review/reject_all_pending?ajax=1")
        self.assertEqual(self.status("o1"), "rejected")
        self.assertEqual(self.status("m1"), "rejected")

    def test_reject_novin_and_clear_rejected_respect_source(self):
        self.add("o1", "olx")
        self.add("m1", "otomoto")
        self.client.post("/review/bulk_reject_novin?source=otomoto")
        self.assertEqual(self.status("o1"), "pending")
        self.assertEqual(self.status("m1"), "rejected")
        self.add("o2", "olx", status="rejected")
        self.client.post("/review/clear_rejected?ajax=1&source=olx")
        self.assertIsNone(self.status("o2"))
        self.assertEqual(self.status("m1"), "rejected")

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

class TestDashboardLoading(ScrapingTestCase):
    def test_shell_renders_without_data_and_loads_sections_async(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        for url in (b"/api/dashboard/summary", b"/api/dashboard/recent"):
            self.assertIn(url, page.data)

    def test_section_endpoints(self):
        self.assertEqual(self.client.get("/api/dashboard/summary").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard/recent?make=BMW").status_code, 200)
        charts = self.client.get("/api/dashboard/charts").get_json()
        self.assertEqual(set(charts), {"makes", "prices", "weekly", "map"})
        self.assertEqual(set(self.client.get("/api/badges").get_json()),
                         {"unread_notifications_count", "pending_plates_count"})

class TestSessionHealth(ScrapingTestCase):
    def log(self, status):
        return self.client.post("/api/log_run", headers=TOKEN, json={
            "status": "success", "message": "m", "source": "otomoto", "session_status": status})

    def test_expired_session_shows_banner(self):
        self.log("expired")
        self.assertIn("Sesja Otomoto wygasła".encode(), self.client.get("/api/dashboard/summary").data)

    def test_ok_session_has_no_banner(self):
        self.log("expired")
        self.log("ok")
        self.assertNotIn("Sesja Otomoto wygasła".encode(), self.client.get("/api/dashboard/summary").data)

    def test_unknown_value_is_ignored(self):
        self.log("garbage")
        self.assertNotIn("Sesja Otomoto wygasła".encode(), self.client.get("/api/dashboard/summary").data)

class TestPlateDateQuality(ScrapingTestCase):
    def ingest(self, sid, **extra):
        body = {"source": "otomoto", "source_listing_id": sid, "make": "BMW", "model": "X3 M",
                "variant": "M40i", "raw_title": "BMW X3"}
        body.update(extra)
        return self.client.post("/api/ingest_pending", headers=TOKEN, json=body)

    def stored(self, sid):
        conn = db.get_db()
        row = conn.execute("SELECT registration_plate, first_registration_date FROM pending_listings "
                           "WHERE source_listing_id=?", (sid,)).fetchone()
        conn.close()
        return row

    def test_invalid_dates_are_not_stored(self):
        self.ingest("future", first_registration_date="2999-01-01", registration_plate="WX12345")
        self.ingest("ancient", first_registration_date="1950-01-01")
        self.ingest("good", first_registration_date="2019-03-04")
        self.assertIsNone(self.stored("future")["first_registration_date"])
        self.assertEqual(self.stored("future")["registration_plate"], "WX12345")
        self.assertIsNone(self.stored("ancient")["first_registration_date"])
        self.assertEqual(self.stored("good")["first_registration_date"], "2019-03-04")

    def test_model_name_is_not_stored_as_plate(self):
        self.ingest("m40i", registration_plate="BMWm40i")
        self.assertIsNone(self.stored("m40i")["registration_plate"])

    def test_fix_tab_and_fix_endpoint(self):
        conn = db.get_db()
        conn.execute("CREATE TABLE IF NOT EXISTS cepik_sync_log (vin TEXT PRIMARY KEY, status TEXT, "
                     "message TEXT, attempted_at TEXT DEFAULT (datetime('now')))")
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, registration_plate, first_registration_date) "
                     "VALUES ('WBS8M9C50J5K99001','BMW','X3 M','M40i',2024,'BMWm40i','2024-01-01')")
        conn.commit()
        conn.close()
        page = self.client.get("/cepik?tab=fix")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"WBS8M9C50J5K99001", page.data)
        self.assertIn("Niepoprawna tablica".encode(), page.data)

        bad = self.client.post("/api/cepik/fix/WBS8M9C50J5K99001", json={
            "plate": "BMWm40i", "first_registration_date": "2024-01-01"})
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post("/api/cepik/fix/WBS8M9C50J5K99001", json={
            "plate": "wx 12345", "first_registration_date": "2024-02-03"})
        self.assertEqual(ok.get_json()["plate"], "WX12345")
        self.assertNotIn(b"WBS8M9C50J5K99001", self.client.get("/cepik?tab=fix").data.split(b"<tbody>")[1])


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
        self.assertEqual(page1.count("list-group-item vehicle-row"), 30)
        self.assertEqual(page2.count("list-group-item vehicle-row"), 5)

    def test_logs_page_paged(self):
        self.assertEqual(self.client.get("/logs?page=3").status_code, 200)

    def test_models_defaults_to_x3_m40i(self):
        page = self.client.get("/models").get_data(as_text=True)
        self.assertIn("BMW X3 M40i (G01)", page)


if __name__ == "__main__":
    unittest.main()


class TestCepikNotFoundRequeue(ScrapingTestCase):
    VIN = "WBS11DM0308D29565"

    def setUp(self):
        super().setUp()
        conn = db.get_db()
        conn.execute("""CREATE TABLE IF NOT EXISTS cepik_sync_log (
            vin TEXT PRIMARY KEY, status TEXT, message TEXT, attempted_at TEXT DEFAULT (datetime('now')))""")
        conn.commit()
        conn.close()

    def car(self, plate="AB12345", approved_from_photo=True):
        self.add_active_listing("L1", self.VIN, "Competition", model="M2", plate=plate, frd="2023-07-06")
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET registration_plate=? WHERE vin=?", (plate, self.VIN))
        if approved_from_photo:
            conn.execute("""INSERT INTO plate_review_queue (vin, detected_plate, reviewed_plate, confidence, status)
                            VALUES (?, ?, ?, 0.8, 'approved')""", (self.VIN, plate, plate))
        conn.commit()
        conn.close()

    def queue(self):
        conn = db.get_db()
        rows = [dict(r) for r in conn.execute("SELECT * FROM plate_review_queue WHERE vin=?", (self.VIN,)).fetchall()]
        plate = conn.execute("SELECT registration_plate FROM vehicles WHERE vin=?", (self.VIN,)).fetchone()[0]
        conn.close()
        return rows, plate

    def fail(self, status):
        from scripts.fetch_cepik import record_cepik_failure
        conn = db.get_db()
        out = record_cepik_failure(conn, mock.Mock(last_status=status), self.VIN, "AB12345")
        conn.close()
        return out

    def test_photo_plate_goes_back_to_pending_and_is_cleared(self):
        self.car()
        self.assertEqual(self.fail(404), "reverted")
        rows, plate = self.queue()
        self.assertEqual([r["status"] for r in rows], ["pending"])
        self.assertIsNone(plate)

    def test_listing_plate_gets_a_pending_entry_and_keeps_the_plate(self):
        self.car(approved_from_photo=False)
        self.assertEqual(self.fail(404), "queued")
        rows, plate = self.queue()
        self.assertEqual([(r["status"], r["detected_plate"]) for r in rows], [("pending", "AB12345")])
        self.assertEqual(plate, "AB12345")

    def test_not_queued_twice(self):
        self.car(approved_from_photo=False)
        self.fail(404)
        self.assertEqual(self.fail(404), "already_pending")
        self.assertEqual(len(self.queue()[0]), 1)

    def test_transient_error_is_not_a_plate_problem(self):
        self.car()
        self.assertEqual(self.fail(500), "error")
        rows, plate = self.queue()
        self.assertEqual([r["status"] for r in rows], ["approved"])
        self.assertEqual(plate, "AB12345")
        conn = db.get_db()
        self.assertEqual(conn.execute("SELECT status FROM cepik_sync_log").fetchone()[0], "error")
        conn.close()

    def test_new_plate_unblocks_cepik_retry_but_same_plate_does_not(self):
        from webapp.services.plates import allow_cepik_retry
        self.car()
        self.fail(404)
        conn = db.get_db()
        allow_cepik_retry(conn, self.VIN, "AB-123 45")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM cepik_sync_log").fetchone()[0], 1)
        allow_cepik_retry(conn, self.VIN, "CD99999")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM cepik_sync_log").fetchone()[0], 0)
        conn.close()

    def test_approving_a_corrected_plate_via_api_allows_retry(self):
        self.car()
        self.fail(404)
        qid = self.queue()[0][0]["id"]
        resp = self.client.post("/api/plates/review", json={"id": qid, "action": "approve", "plate": "CD99999"})
        self.assertEqual(resp.status_code, 200)
        conn = db.get_db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM cepik_sync_log").fetchone()[0], 0)
        conn.close()
        self.assertEqual(self.queue()[1], "CD99999")
