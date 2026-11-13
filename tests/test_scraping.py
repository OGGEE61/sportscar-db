"""Regression tests for sold-marking scope, partial scrapes, detail skipping and paging."""
import json
import os
import re
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrapers"))

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_scraping.db")
if "REVEAL_STATE_FILE" not in os.environ:   # tests/conftest.py sets it under pytest
    import tempfile
    os.environ["REVEAL_STATE_FILE"] = os.path.join(tempfile.mkdtemp(prefix="reveal-state-"), "reveal_state.json")

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

    def test_pending_with_vin_lists_the_listings_reject_novin_would_keep(self):
        self.add("m1", "otomoto", vin="WBS8M9C59J5K12345")
        self.add("m2", "otomoto")
        self.add("m3", "otomoto", vin="UNVERIFIED-OTOMOTO-m3")
        self.add("o1", "olx", vin="WBS8M9C59J5K54321")
        self.add("m4", "otomoto", status="rejected", vin="WBS8M9C59J5K11111")

        def listed(query=""):
            ids = self.client.get("/review/pending_with_vin" + query).get_json()["ids"]
            conn = db.get_db()
            sids = {r["source_listing_id"] for r in conn.execute(
                f"SELECT source_listing_id FROM pending_listings WHERE id IN ({','.join('?' * len(ids))})", ids)}
            conn.close()
            return sids

        self.assertEqual(listed(), {"m1", "o1"})
        self.assertEqual(listed("?source=otomoto"), {"m1"})
        self.client.post("/review/bulk_reject_novin?source=otomoto")
        self.assertEqual(self.status("m1"), "pending")
        self.assertEqual({self.status("m2"), self.status("m3")}, {"rejected"})

    def test_review_page_has_approve_all_with_vin_button(self):
        self.add("m1", "otomoto", vin="WBS8M9C59J5K12345")
        page = self.client.get("/review?source=otomoto").get_data(as_text=True)
        self.assertIn('id="approve-all-vin-btn"', page)
        self.assertIn("/review/pending_with_vin?source=otomoto", page)

    def test_review_row_shows_the_registration_plate(self):
        self.add("a1", "autoplac", vin="WBS8M9C59J5K12345")
        conn = db.get_db()
        conn.execute("UPDATE pending_listings SET registration_plate='SD3097N' WHERE source_listing_id='a1'")
        conn.commit()
        conn.close()
        self.assertIn("SD3097N", self.client.get("/review?source=autoplac").get_data(as_text=True))


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

    def test_models_page_draws_a_trend_line(self):
        self.add_vehicle("WBS8M9C50J5K99001", "BMW", "X3", "M40i", 2022, model_id="x3_m40i_g01")
        conn = db.get_db()
        conn.execute("""INSERT INTO listing_observations (vin, source, source_listing_id, price_pln, mileage_km)
                        VALUES ('WBS8M9C50J5K99001', 'otomoto', '1', 200000, 50000)""")
        conn.commit()
        conn.close()
        page = self.client.get("/models?model=x3_m40i_g01")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"label: 'Trend'", page.data)

    def _ad(self, vin, sid, price, km, damaged=False):
        conn = db.get_db()
        conn.execute("""INSERT INTO listing_observations (vin, source, source_listing_id, price_pln, mileage_km)
                        VALUES (?, 'otomoto', ?, ?, ?)""", (vin, sid, price, km))
        if damaged:
            conn.execute("INSERT INTO damaged_listings (source, source_listing_id) VALUES ('otomoto', ?)", (sid,))
        conn.commit()
        conn.close()

    def test_damaged_car_stays_listed_but_leaves_the_price_chart(self):
        self.add_vehicle("WBS8M9C50J5K99001", "BMW", "X3", "M40i", 2022, model_id="x3_m40i_g01")
        self.add_vehicle("WBS8M9C50J5K99002", "BMW", "X3", "M40i", 2021, model_id="x3_m40i_g01")
        self._ad("WBS8M9C50J5K99001", "1", 200000, 50000)
        self._ad("WBS8M9C50J5K99002", "2", 91234, 60000, damaged=True)
        page = self.client.get("/models?model=x3_m40i_g01").data.decode()
        self.assertIn("WBS8M9C50J5K99002", page)            # still listed in the table
        self.assertIn(">Uszkodzony<", page)
        chart = page.split("const scatterData =")[1].split(";")[0]
        self.assertIn("WBS8M9C50J5K99001", chart)
        self.assertNotIn("WBS8M9C50J5K99002", chart)

    def test_vehicle_pages_say_sold_as_damaged(self):
        self.add_vehicle("WBS8M9C50J5K99002", "BMW", "X3", "M40i", 2021, model_id="x3_m40i_g01")
        self._ad("WBS8M9C50J5K99002", "2", 91234, 60000, damaged=True)
        self.assertIn("Uszkodzony</span>", self.client.get("/vehicle/WBS8M9C50J5K99002").get_data(as_text=True))
        self.assertIn("Uszkodzony</span>", self.client.get("/vehicles").get_data(as_text=True))

    def test_ingest_records_a_damaged_ad(self):
        with mock.patch("webapp.blueprints.api.check_api_token", return_value=None):
            self.client.post("/api/ingest_pending", json={
                "source": "otomoto", "source_listing_id": "77", "source_url": "https://x", "raw_title": "BMW",
                "make": "BMW", "model": "M3", "damaged": True})
            self.client.post("/api/ingest_pending", json={
                "source": "otomoto", "source_listing_id": "78", "source_url": "https://y", "raw_title": "BMW",
                "make": "BMW", "model": "M3", "damaged": False})
        conn = db.get_db()
        got = [r[0] for r in conn.execute("SELECT source_listing_id FROM damaged_listings").fetchall()]
        conn.close()
        self.assertEqual(got, ["77"])

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

    def test_autoplac_is_complete_without_first_registration(self):
        # autoplac never shows the date, so VIN + plate is all a detail fetch can give
        conn = db.get_db()
        for source, sid, plate in (("autoplac", "ap-full", "WX12345"), ("autoplac", "ap-noplate", None),
                                   ("otomoto", "oto-nodate", "WX12345")):
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, make, model, vin, status, "
                         "registration_plate) VALUES (?, ?, 'BMW', 'X3', 'WBATS31020LP72826', 'approved', ?)",
                         (source, sid, plate))
        conn.commit()
        conn.close()
        known = self.client.post("/api/known_listings", headers=TOKEN, json={"items": [
            ["autoplac", "ap-full"], ["autoplac", "ap-noplate"], ["otomoto", "oto-nodate"]]}).get_json()["known"]
        self.assertTrue(known["autoplac:ap-full"]["complete"])
        self.assertFalse(known["autoplac:ap-noplate"]["complete"])
        self.assertFalse(known["otomoto:oto-nodate"]["complete"])

    def test_requires_token(self):
        res = self.client.post("/api/known_listings", json={"items": []})
        self.assertEqual(res.status_code, 401)


def _card(i):
    return {"listing_id": f"id{i}", "title": "BMW M3 F80", "price_raw": "300 000 PLN",
            "source_url": f"https://www.otomoto.pl/oferta/{i}", "thumbnail": None, "location_city": "Warszawa"}


class TestVehiclePriceChart(ScrapingTestCase):
    """The vehicle page plots one price line per platform the car was seen on."""

    VIN = "WBS8M9C50J5K99001"

    def seed(self):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year) VALUES (?, 'BMW', 'M3', 'F80', 2018)", (self.VIN,))
        rows = [("otomoto", "o1", "2026-10-20 08:00:00", 160000), ("otomoto", "o1", "2026-10-20 20:00:00", 158000),
                ("olx", "x1", "2026-10-21 09:00:00", 155000), ("autoplac", "a1", "2026-10-22 10:00:00", 150000),
                ("autoplac", "a1", "2026-10-25 10:00:00", 147000)]
        for source, sid, at, price in rows:
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, price_pln, observed_at, last_seen_at) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (self.VIN, source, sid, price, at, at))
        conn.commit()
        conn.close()

    def test_page_carries_every_platform_and_draws_a_line_each(self):
        self.seed()
        res = self.client.get(f"/vehicle/{self.VIN}")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Price History by platform", html)
        for source in ("otomoto", "olx", "autoplac"):
            self.assertRegex(html, rf'"source":\s*"{source}"')
        # the chart script builds one dataset per platform, coloured like the badges
        for color in ("#c2410c", "#0f766e", "#1d4ed8"):
            self.assertIn(color, html)

    def test_no_chart_without_prices(self):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year) VALUES (?, 'BMW', 'M3', 'F80', 2018)", (self.VIN,))
        conn.commit()
        conn.close()
        self.assertNotIn("chartPrice", self.client.get(f"/vehicle/{self.VIN}").get_data(as_text=True))

class TestModelTableSorting(ScrapingTestCase):
    """/models lists tracked cars newest observation first, with sortable column headers."""

    def seed(self):
        conn = db.get_db()
        cars = [("WBS8M9C50J5K99001", "2026-10-20 10:00:00", 150000), ("WBS8M9C50J5K99002", "2026-10-24 10:00:00", 120000),
                ("WBS8M9C50J5K99003", "2026-10-22 10:00:00", 135000)]
        for vin, at, price in cars:
            conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, model_id) VALUES (?, 'BMW', 'M3', 'F80', 2016, 'm3_f80')", (vin,))
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, price_pln, observed_at) VALUES (?, 'otomoto', ?, ?, ?)",
                         (vin, vin[-3:], price, at))
        conn.commit()
        conn.close()

    def test_default_order_is_newest_observation_first(self):
        self.seed()
        html = self.client.get("/models?model=m3_f80").get_data(as_text=True)
        order = [html.index(f"WBS8M9C50J5K99{n}") for n in ("002", "003", "001")]
        self.assertEqual(order, sorted(order))

    def test_headers_are_sortable_and_rows_carry_sort_values(self):
        self.seed()
        html = self.client.get("/models?model=m3_f80").get_data(as_text=True)
        for key in ("vehicle", "year", "hp", "mileage", "price", "location", "observed"):
            self.assertIn(f'data-key="{key}"', html)
            self.assertIn(f"data-s-{key}=", html)
        self.assertIn('aria-sort="descending">Widziane', html)
        # The whole row opens the car; no separate "Details" button
        self.assertIn('class="model-vehicle-row row-link" data-href="/vehicle/', html)
        self.assertNotIn("Details →", html)
        self.assertIn('data-s-price="120000', html)


class TestDashboardStatCards(ScrapingTestCase):
    """The dashboard summary shows five stat cards; the placeholder-VIN card is gone."""

    def test_summary_has_no_placeholders_card(self):
        html = self.client.get("/api/dashboard/summary").get_data(as_text=True)
        self.assertNotIn("Placeholders", html)
        for label in ("Total VINs", "Observations", "Active Listings", "Unique Ads", "Avg Price"):
            self.assertIn(label, html)
        self.assertEqual(html.count('class="card stat-card'), 5)

    def test_loading_skeleton_matches_the_five_cards(self):
        html = self.client.get("/").get_data(as_text=True)
        shell = html.split('id="dash-summary"')[1].split("hx-swap")[1]
        self.assertEqual(shell.split("</div>\n</div>")[0].count('class="card stat-card'), 5)


class TestPager(ScrapingTestCase):
    """Pagination shows first / last / current +-2 with gaps marked, not just three pages."""

    def pager(self, page, pages, **kw):
        tpl = app.jinja_env.get_template("_pagination.html")
        return str(tpl.module.pager(page, pages, "/x?a=1&page=", "Test pages", **kw))

    def labels(self, html):
        return re.findall(r'<li class="page-item[^"]*">\s*<(?:a|span) class="page-link"[^>]*>([^<]+)</', html)

    def test_shapes(self):
        L = self.labels
        self.assertEqual(L(self.pager(1, 3)), ["‹ Prev", "1", "2", "3", "Next ›"])
        self.assertEqual(L(self.pager(10, 20)), ["‹ Prev", "1", "…", "8", "9", "10", "11", "12", "…", "20", "Next ›"])
        self.assertEqual(L(self.pager(1, 20)), ["‹ Prev", "1", "2", "3", "…", "20", "Next ›"])
        self.assertEqual(L(self.pager(20, 20)), ["‹ Prev", "1", "…", "18", "19", "20", "Next ›"])
        self.assertEqual(L(self.pager(4, 20)), ["‹ Prev", "1", "2", "3", "4", "5", "6", "…", "20", "Next ›"])
        # a gap of one page is shown as that page, not as "…"
        self.assertEqual(L(self.pager(5, 20)), ["‹ Prev", "1", "2", "3", "4", "5", "6", "7", "…", "20", "Next ›"])
        self.assertEqual(L(self.pager(17, 20)), ["‹ Prev", "1", "…", "15", "16", "17", "18", "19", "20", "Next ›"])

    def test_single_page_has_no_pager(self):
        self.assertEqual(self.pager(1, 1).strip(), "")

    def test_links_and_state(self):
        html = self.pager(10, 20, ids=True)
        self.assertIn('href="/x?a=1&amp;page=9"', html)     # prev
        self.assertIn('href="/x?a=1&amp;page=11"', html)    # next
        self.assertIn('href="/x?a=1&amp;page=20"', html)    # last page is reachable
        self.assertIn('id="page-prev"', html)
        self.assertIn("Page 10 of 20", html)
        self.assertRegex(html, r'page-item active">\s*<a class="page-link" href="[^"]*page=10"')
        first = self.pager(1, 20)
        self.assertRegex(first, r'page-item disabled"><a class="page-link" href="[^"]*page=0"')   # Prev disabled
        self.assertNotIn('id="page-prev"', first)

    def test_logs_page_uses_it(self):
        for i in range(250):
            self.client.post("/api/log_run", headers=TOKEN, json={"status": "success", "message": f"m{i}", "source": "olx"})
        html = self.client.get("/logs?page=2").get_data(as_text=True)
        self.assertIn("Page 2 of 3", html)
        self.assertIn("page=3", html)
        self.assertIn("page=1", html)


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


class CepikCarMixin:
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


class TestCepikNotFoundRequeue(CepikCarMixin, ScrapingTestCase):

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


class TestPlateInput(CepikCarMixin, ScrapingTestCase):
    """Polish plates are only A-Z and 0-9, wherever they get saved."""

    def stored(self, table="vehicles", where="vin=?", params=None):
        conn = db.get_db()
        row = conn.execute(f"SELECT registration_plate FROM {table} WHERE {where}", params or (self.VIN,)).fetchone()
        conn.close()
        return row[0] if row else None

    def review(self, plate, **extra):
        self.car(approved_from_photo=False)
        self.fail(404)
        qid = self.queue()[0][0]["id"]
        return self.client.post("/api/plates/review", json={"id": qid, "action": "approve", "plate": plate, **extra})

    def test_review_strips_spaces_and_separators_everywhere(self):
        resp = self.review(" kr 7vg-2.2 ")
        self.assertEqual(resp.get_json()["plate"], "KR7VG22")
        self.assertEqual(self.queue()[0][0]["reviewed_plate"], "KR7VG22")
        self.assertEqual(self.stored(), "KR7VG22")
        self.assertEqual(self.stored("pending_listings"), "KR7VG22")
        self.assertEqual(self.stored("listing_observations"), "KR7VG22")

    def test_review_rejects_symbols_instead_of_changing_the_plate(self):
        self.car(approved_from_photo=False)
        self.fail(404)
        qid = self.queue()[0][0]["id"]
        for bad in ("KR7VG2Ż", "KR7VG2!", "KR/7VG22"):
            resp = self.client.post("/api/plates/review", json={"id": qid, "action": "approve", "plate": bad})
            self.assertEqual(resp.status_code, 400, bad)
            self.assertEqual(self.stored(), "AB12345")

    def test_review_cleans_a_stored_proposal_when_no_plate_is_typed(self):
        self.car(approved_from_photo=False)
        self.fail(404)
        conn = db.get_db()
        conn.execute("UPDATE plate_review_queue SET detected_plate='KN 4300F'")
        conn.commit()
        conn.close()
        qid = self.queue()[0][0]["id"]
        self.client.post("/api/plates/review", json={"id": qid, "action": "approve"})
        self.assertEqual(self.stored(), "KN4300F")

    def test_requeued_listing_plate_is_proposed_clean(self):
        self.car(plate="AB 12345", approved_from_photo=False)
        from scripts.fetch_cepik import record_cepik_failure
        conn = db.get_db()
        record_cepik_failure(conn, mock.Mock(last_status=404), self.VIN, "AB 12345")
        conn.close()
        self.assertEqual(self.queue()[0][0]["detected_plate"], "AB12345")

    def test_vehicle_edit_form_stores_a_clean_plate(self):
        self.car()
        self.client.post(f"/vehicle/{self.VIN}/update_details", data={"registration_plate": "ab 123-45"})
        self.assertEqual(self.stored(), "AB12345")

    def test_scraped_plate_is_stored_clean(self):
        res = self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": "autoplac", "source_listing_id": "spaced", "source_url": "https://x/spaced",
            "raw_title": "BMW M2", "make": "BMW", "model": "M2", "price_pln": 100000,
            "registration_plate": "wx 12345", "photos": [],
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.stored("pending_listings", "source_listing_id=?", ("spaced",)), "WX12345")

    def test_plate_fields_are_filtered_in_the_browser(self):
        self.car(approved_from_photo=False)
        self.fail(404)
        page = self.client.get("/plates").get_data(as_text=True)
        self.assertIn("plate-field", page)
        self.assertIn("function cleanPlate", page)


class TestNextScrapers(ScrapingTestCase):
    SCRAPERS = [{"key": k, "list_url": f"https://x/{k}"} for k in ("a", "b", "c", "d")]

    def pick(self, count=2, source="otomoto"):
        res = self.client.post("/api/next_scrapers", headers=TOKEN, json={"source": source, "count": count, "scrapers": self.SCRAPERS})
        self.assertEqual(res.status_code, 200)
        return res.get_json()["keys"]

    def log(self, key, date, source="otomoto"):
        conn = db.get_db()
        conn.execute("INSERT INTO scraper_logs (run_date, status, message, list_url, source) VALUES (?, 'success', '', ?, ?)",
                     (date, f"https://x/{key}", source))
        conn.commit()
        conn.close()

    def test_needs_the_api_token(self):
        res = self.client.post("/api/next_scrapers", json={"source": "otomoto", "scrapers": self.SCRAPERS})
        self.assertEqual(res.status_code, 401)

    def test_longest_waiting_go_first(self):
        self.log("a", "2026-11-05 10:00:00")
        self.log("b", "2026-10-29 10:00:00")
        self.log("c", "2026-11-01 10:00:00")
        self.log("d", "2026-11-03 10:00:00")
        self.assertEqual(self.pick(), ["b", "c"])

    def test_every_scraper_gets_a_turn_before_any_repeats(self):
        got = self.pick() + self.pick()
        self.assertEqual(sorted(got), ["a", "b", "c", "d"])

    def test_a_run_that_dies_before_logging_does_not_block_the_others(self):
        first = self.pick(count=1)  # no log written
        self.assertNotEqual(self.pick(count=1), first)

    def test_a_manual_run_counts_as_a_turn(self):
        for key, when in (("a", "2026-11-05 10:00:00"), ("b", "2026-11-05 10:00:00"), ("c", "2026-11-05 10:00:00")):
            self.log(key, when)
        self.assertEqual(self.pick(count=1), ["d"])

    def test_sources_are_separate(self):
        self.log("a", "2026-11-05 10:00:00", source="olx")
        self.assertEqual(self.pick(count=1, source="otomoto"), ["a"])

    def test_bad_request(self):
        res = self.client.post("/api/next_scrapers", headers=TOKEN, json={"source": "otomoto"})
        self.assertEqual(res.status_code, 400)


class TestRotationPick(unittest.TestCase):
    def test_fleets_have_unique_keys(self):
        import run_all
        import run_olx
        for fleet in (run_all.ALL_FLEET, run_olx.ALL_OLX_FLEET):
            keys = [f"{c.make} {c.model} {c.variant or ''}".strip() for c in fleet]
            self.assertEqual(len(keys), len(set(keys)))

    def test_api_failure_falls_back_to_the_clock(self):
        import run_all
        with mock.patch.object(base_scraper._API_SESSION, "post", side_effect=RuntimeError("down")):
            self.assertEqual(base_scraper.pick_longest_waiting("otomoto", run_all.ALL_FLEET, 3), [])
            self.assertEqual(len(run_all.get_scheduled_models(count=3)), 3)

    def test_api_answer_is_used(self):
        import run_all
        cfg = run_all.ALL_FLEET[7]
        key = f"{cfg.make} {cfg.model} {cfg.variant or ''}".strip()
        answer = mock.Mock(status_code=200, json=lambda: {"keys": [key]})
        with mock.patch.object(base_scraper._API_SESSION, "post", return_value=answer):
            self.assertEqual([c for c, _, _ in run_all.get_scheduled_models(count=1)], [cfg])


class TestAlpinaValidator(unittest.TestCase):
    def validators(self):
        from otomoto.bmw_alpina import validate_genuine_alpina as otomoto
        from olx.bmw_alpina import validate_genuine_alpina as olx
        return otomoto, olx

    def check(self, expected, **detail):
        for validate in self.validators():
            self.assertEqual(validate(detail), expected, detail)

    def test_wap_vin_is_kept(self):
        self.check(True, vin="WAPB350009HE12345", title="BMW-ALPINA B5", power_hp=500)

    def test_powerful_bmw_vin_goes_to_review(self):
        self.check(True, vin="WBA6D6C58JG745657", title="BMW-ALPINA B6", power_hp=600)
        self.check(True, vin="WBAGX0C17PCK98406", title="Alpina B8", power_hp=621)

    def test_ordinary_bmw_vin_is_rejected(self):
        self.check(False, vin="WBA6B4C57FD986132", title="BMW Alpina 650i", power_hp=445)
        self.check(False, vin="WBA3K91090F913330", title="BMW Seria 3 Alpina", power_hp=190)
        self.check(False, vin="WBA6D6C58JG745657", title="BMW-ALPINA B6")

    def test_other_makers_at_any_power_are_rejected(self):
        self.check(False, vin="5UX43EM06S9W63847", title="Alpina XB", power_hp=631)

    def test_no_vin_is_still_rejected(self):
        self.check(False, vin=None, title="BMW-ALPINA B5", power_hp=500)

    def test_large_models_are_still_rejected(self):
        self.check(False, vin="WBA7F2C5XJG856240", title="BMW Seria 7 Alpina", power_hp=600)


class TestPlateReject(CepikCarMixin, ScrapingTestCase):
    """Rejecting a plate (missing or wrong) removes it from the car, with undo."""

    def card(self):
        self.car(approved_from_photo=False)
        self.fail(404)
        return self.queue()[0][0]["id"]

    def post(self, qid, action):
        return self.client.post("/api/plates/review", json={"id": qid, "action": action})

    def listing_plate(self):
        conn = db.get_db()
        plate = conn.execute("SELECT registration_plate FROM pending_listings WHERE vin=?", (self.VIN,)).fetchone()[0]
        conn.close()
        return plate

    def test_reject_removes_it_from_car_and_listing(self):
        qid = self.card()
        self.assertEqual(self.post(qid, "reject").get_json()["removed"], "AB12345")
        rows, plate = self.queue()
        self.assertEqual((rows[0]["status"], rows[0]["reviewed_plate"]), ("rejected", "AB12345"))
        self.assertIsNone(plate)
        self.assertIsNone(self.listing_plate())
        conn = db.get_db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tags WHERE vin=? AND tag='missing plates'", (self.VIN,)).fetchone()[0], 1)
        conn.close()

    def test_reject_matches_however_the_plate_was_stored(self):
        self.car(plate="ab 123-45", approved_from_photo=False)
        from scripts.fetch_cepik import record_cepik_failure
        conn = db.get_db()
        record_cepik_failure(conn, mock.Mock(last_status=404), self.VIN, "ab 123-45")
        conn.close()
        self.post(self.queue()[0][0]["id"], "reject")
        self.assertIsNone(self.queue()[1])

    def test_undo_puts_the_plate_back(self):
        qid = self.card()
        self.post(qid, "reject")
        self.assertEqual(self.post(qid, "revert").status_code, 200)
        rows, plate = self.queue()
        self.assertEqual((rows[0]["status"], rows[0]["reviewed_plate"]), ("pending", None))
        self.assertEqual(plate, "AB12345")
        self.assertEqual(self.listing_plate(), "AB12345")

    def test_next_scrape_does_not_bring_a_rejected_plate_back(self):
        qid = self.card()
        self.post(qid, "reject")
        res = self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": "otomoto", "source_listing_id": "L1", "raw_title": "BMW M2", "make": "BMW", "model": "M2",
            "price_pln": 100000, "vin": self.VIN, "registration_plate": "AB 12345", "photos": [],
        })
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(self.queue()[1])
        self.assertIsNone(self.listing_plate())

    def test_card_shows_date_photos_and_one_reject_button(self):
        import json
        qid = self.card()
        conn = db.get_db()
        conn.execute("UPDATE pending_listings SET photos=? WHERE vin=?", (json.dumps(["https://img/1.jpg", "https://img/2.jpg"]), self.VIN))
        conn.commit()
        conn.close()
        page = self.client.get("/plates").get_data(as_text=True)
        self.assertIn(f'id="date-{qid}"', page)
        self.assertIn('value="2023-07-06"', page)
        self.assertIn("https://img/2.jpg", page)
        self.assertIn(f"reviewPlate({qid}, 'reject')", page)
        self.assertNotIn("Nie widać tablicy", page)

    def test_rejecting_when_the_car_has_no_plate_just_closes_the_card(self):
        qid = self.card()
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET registration_plate=NULL WHERE vin=?", (self.VIN,))
        conn.commit()
        conn.close()
        self.assertIsNone(self.post(qid, "reject").get_json()["removed"])
        rows, plate = self.queue()
        self.assertEqual((rows[0]["status"], rows[0]["reviewed_plate"]), ("rejected", None))
        self.assertIsNone(plate)

    def test_rejecting_an_approved_plate_still_removes_it(self):
        self.car()
        qid = self.queue()[0][0]["id"]
        self.post(qid, "reject")
        self.assertEqual(self.queue()[0][0]["status"], "rejected")
        self.assertIsNone(self.queue()[1])


class TestConfirmQueueWithCepik(CepikCarMixin, ScrapingTestCase):
    """A number CEPiK confirms for this exact car skips human review."""

    def report(self, vin=None, make="BMW", year=2023, plate="AB12345"):
        report = dict.fromkeys(['events_json', 'first_registration_date', 'has_current_oc', 'insurance_expiry_date', 'is_stolen', 'last_odometer_date', 'last_odometer_km', 'make', 'model', 'odometer_history_json', 'registration_plate', 'registration_status', 'subtype', 'tech_inspection_status', 'tech_inspection_until', 'total_owners', 'type', 'vin'])
        report.update({"vin": self.VIN, "registration_plate": plate, "first_registration_date": "2023-07-06",
                       "identifying_feature": vin or self.VIN, "make": make, "model": "M2", "year_of_manufacture": year,
                       "has_current_oc": 1, "is_stolen": 0, "total_owners": 1, "tech_inspection_status": "Aktualne",
                       "odometer_history_json": "[]", "events_json": "[]"})
        return report

    def run_confirm(self, answer):
        """answer maps plate -> report; everything else is a 404."""
        from scripts import fetch_cepik
        client = mock.Mock(last_status=404)
        client.fetch_vehicle_data.side_effect = lambda vin, plate, date: answer.get(plate)
        with mock.patch.object(fetch_cepik, "CepikClient", return_value=client), mock.patch.object(fetch_cepik.time, "sleep"):
            return fetch_cepik.confirm_queue_with_cepik(), client

    def card(self, proposal=None):
        self.car(approved_from_photo=False)
        self.fail(404)
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET make='BMW', year=2023, first_registration_date='2023-07-06' WHERE vin=?", (self.VIN,))
        if proposal:
            conn.execute("UPDATE plate_review_queue SET detected_plate=?, confidence=0.8", (proposal,))
        conn.commit()
        conn.close()

    def test_confirmed_ocr_reading_is_approved_and_replaces_the_listing_number(self):
        self.card(proposal="CD99999")
        stats, _ = self.run_confirm({"CD99999": self.report(plate="CD99999")})
        self.assertEqual(stats["confirmed"], 1)
        rows, plate = self.queue()
        self.assertEqual((rows[0]["status"], rows[0]["reviewed_plate"]), ("approved", "CD99999"))
        self.assertEqual(plate, "CD99999")
        conn = db.get_db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM cepik_reports WHERE vin=?", (self.VIN,)).fetchone()[0], 1)
        conn.close()

    def test_miss_leaves_the_card_for_a_human_and_is_not_asked_twice(self):
        self.card(proposal="CD99999")
        _, client = self.run_confirm({})
        self.assertEqual(client.fetch_vehicle_data.call_count, 2)  # the proposal and the listing number
        rows, plate = self.queue()
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(plate, "AB12345")
        _, client = self.run_confirm({})
        self.assertEqual(client.fetch_vehicle_data.call_count, 0)

    def test_a_different_vin_in_the_answer_is_not_approved(self):
        self.card()
        stats, _ = self.run_confirm({"AB12345": self.report(vin="WBS00000000000000")})
        self.assertEqual((stats["confirmed"], stats["not_same_car"]), (0, 1))
        self.assertEqual(self.queue()[0][0]["status"], "pending")

    def test_a_different_make_or_year_is_not_approved(self):
        from scripts.fetch_cepik import is_same_car
        self.assertFalse(is_same_car(self.report(make="AUDI"), self.VIN, "BMW", 2023))
        self.assertFalse(is_same_car(self.report(year=2015), self.VIN, "BMW", 2023))
        self.assertFalse(is_same_car({"make": "BMW"}, self.VIN, "BMW", 2023))
        self.assertTrue(is_same_car(self.report(make="MERCEDES-BENZ"), self.VIN, "Mercedes-Benz", 2023))
        self.assertTrue(is_same_car(self.report(year=2022), self.VIN, "BMW", 2023))
        self.assertTrue(is_same_car(self.report(make="BMW"), self.VIN, "Alpina", 2023))
        self.assertFalse(is_same_car(self.report(make="AUDI"), self.VIN, "Alpina", 2023))

    def test_transient_error_is_asked_again(self):
        self.card()
        from scripts import fetch_cepik
        client = mock.Mock(last_status=500)
        client.fetch_vehicle_data.return_value = None
        with mock.patch.object(fetch_cepik, "CepikClient", return_value=client), mock.patch.object(fetch_cepik.time, "sleep"):
            self.assertEqual(fetch_cepik.confirm_queue_with_cepik()["errors"], 1)
        _, client = self.run_confirm({})
        self.assertEqual(client.fetch_vehicle_data.call_count, 1)

    def test_card_without_a_date_is_skipped(self):
        self.card()
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET first_registration_date=NULL WHERE vin=?", (self.VIN,))
        conn.execute("UPDATE pending_listings SET first_registration_date=NULL WHERE vin=?", (self.VIN,))
        conn.commit()
        conn.close()
        stats, client = self.run_confirm({})
        self.assertEqual((stats["no_date"], client.fetch_vehicle_data.call_count), (1, 0))

    def test_card_shows_where_the_number_comes_from(self):
        self.card()
        self.assertIn("Z ogłoszenia (otomoto)", self.client.get("/plates").get_data(as_text=True))
        conn = db.get_db()
        conn.execute("UPDATE plate_review_queue SET confidence=0.8")
        conn.commit()
        conn.close()
        self.assertIn("Odczyt ze zdjęcia", self.client.get("/plates").get_data(as_text=True))
        conn = db.get_db()
        conn.execute("UPDATE plate_review_queue SET detected_plate=''")
        conn.commit()
        conn.close()
        self.assertIn("Nieczytelna", self.client.get("/plates").get_data(as_text=True))


class TestFillMissingCrops(CepikCarMixin, ScrapingTestCase):
    """A listing plate re-queued after a CEPiK miss gets a crop and a photo reading from the scanner."""

    def scan(self, shot):
        import json
        with mock.patch.dict(sys.modules, {"numpy": mock.MagicMock()}):
            from scripts import detect_plates
        conn = db.get_db()
        conn.execute("UPDATE pending_listings SET photos=? WHERE vin=?", (json.dumps(["https://img/1.jpg"]), self.VIN))
        conn.commit()
        with mock.patch.object(detect_plates, "find_best_plate_shot", return_value=shot):
            out = detect_plates.fill_missing_crops(conn)
        conn.close()
        return out

    def test_photo_reading_becomes_the_suggestion_and_listing_plate_stays(self):
        self.car(approved_from_photo=False)
        self.fail(404)
        out = self.scan({"detected_plate": "WI 666NM", "confidence": 0.86,
                         "crop_path": "data:image/jpeg;base64,xx", "photo_url": "https://img/1.jpg"})
        self.assertEqual(out["crops_filled"], 1)
        rows, plate = self.queue()
        self.assertEqual([(r["detected_plate"], r["crop_path"]) for r in rows], [("WI 666NM", "data:image/jpeg;base64,xx")])
        self.assertIsNotNone(rows[0]["listing_id"])
        self.assertEqual(plate, "AB12345")

    def test_unreadable_crop_is_kept_without_changing_the_proposal(self):
        self.car(approved_from_photo=False)
        self.fail(404)
        out = self.scan({"detected_plate": "", "confidence": 0.5,
                         "crop_path": "data:image/jpeg;base64,xx", "photo_url": "https://img/1.jpg"})
        self.assertEqual(out["crops_filled"], 1)
        rows, plate = self.queue()
        self.assertEqual([(r["detected_plate"], r["crop_path"]) for r in rows], [("AB12345", "data:image/jpeg;base64,xx")])
        self.assertEqual(plate, "AB12345")

    def test_nothing_found_is_not_rescanned(self):
        self.car(approved_from_photo=False)
        self.fail(404)
        self.scan(None)
        rows, _ = self.queue()
        self.assertEqual([(r["detected_plate"], r["crop_path"]) for r in rows], [("AB12345", "")])
        self.assertEqual(self.scan(None)["queued_without_crop"], 0)


class DealerStockExclusionTest(ScrapingTestCase):
    """Dealer-stock sightings (any model) are flagged, kept (VIN stays known) and left out of the dashboard."""

    def _car(self, conn, vin, model, year, first_reg=None):
        conn.execute("INSERT INTO vehicles(vin,make,model,variant,year,first_registration_date) VALUES(?,?,?,?,?,?)",
                     (vin, "BMW", model, "G87", year, first_reg))

    def _obs(self, conn, vin, sid, km, seen, price=400000):
        conn.execute("INSERT INTO listing_observations(vin,source,source_listing_id,mileage_km,price_pln,first_seen_at,observed_at) "
                     "VALUES(?,?,?,?,?,?,?)", (vin, "otomoto", sid, km, price, seen, seen))

    def _flags(self, conn):
        return {r["source_listing_id"]: r["excluded_reason"]
                for r in conn.execute("SELECT source_listing_id, excluded_reason FROM listing_observations")}

    CASES = [  # id, model, year, first_reg, km, seen
        ("1", "M2", 2026, None,         3000,  "2026-09-01"),
        ("2", "M2", 2025, None,         3000,  "2026-09-01"),
        ("3", "M2", 2025, "2025-10-27", 3000,  "2026-10-26"),
        ("4", "M2", 2025, "2025-10-25", 3000,  "2026-10-26"),
        ("5", "M2", 2026, None,         20000, "2026-09-01"),
        ("6", "M2", 2026, None,         None,  "2026-09-01"),
        ("7", "M3", 2026, None,         100,   "2026-09-01"),   # any model
        ("8", "M2", 2026, "2027-01-01", 3000,  "2026-09-01"),   # future date: fall back to year
        ("9", "M2", 2025, None,         5,     "2026-11-11"),   # last model year, delivery km
        ("10", "M2", 2025, "2025-01-10", 999,  "2026-11-11"),   # registered long ago, still delivery km
        ("11", "M2", 2024, None,        5,     "2026-11-11"),   # two model years back: kept
        ("12", "Z3", 2000, None,        800,   "2026-11-11"),   # garaged classic: kept
        ("13", "M2", 2025, None,        1000,  "2026-11-11"),
    ]

    def _store(self, conn):
        for sid, model, year, reg, km, seen in self.CASES:
            vin = f"VIN{sid}".ljust(17, "X")
            self._car(conn, vin, model, year, reg)
            self._obs(conn, vin, sid, km, seen)
        conn.commit()

    def _want(self):
        from validation import is_dealer_new
        from datetime import date
        return {sid: is_dealer_new(year, km, reg, on=date.fromisoformat(seen))
                for sid, model, year, reg, km, seen in self.CASES}

    def test_trigger_matches_python_rule(self):
        conn = db.get_db()
        self._store(conn)
        flags = self._flags(conn)
        conn.close()
        want = self._want()
        self.assertEqual({sid: f is not None for sid, f in flags.items()}, want)
        self.assertEqual([sid for sid, w in want.items() if w], ["1", "3", "7", "8", "9", "10"])

    def test_migration_21_matches_python_rule(self):
        conn = db.get_db()
        conn.execute("DROP TRIGGER trg_obs_dealer_new")
        self._store(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version = 21")
        conn.execute("UPDATE listing_observations SET excluded_reason = 'not_m2' WHERE source_listing_id = '13'")
        conn.commit()
        self.assertTrue(all(f is None for sid, f in self._flags(conn).items() if sid != "13"))
        conn.close()
        db.init_db()
        conn = db.get_db()
        flags = self._flags(conn)
        conn.close()
        want = self._want()
        for sid, w in want.items():
            if sid != "13":
                self.assertEqual(flags[sid] == "dealer_new", w, sid)
        self.assertEqual(flags["13"], "not_m2")   # another reason is left as it is

    def test_dashboard_skips_excluded_but_vin_stays_known(self):
        conn = db.get_db()
        self._car(conn, "A" * 17, "M2", 2026)
        self._obs(conn, "A" * 17, "1", 5, "2026-09-01")
        self._car(conn, "B" * 17, "M2", 2020)
        self._obs(conn, "B" * 17, "2", 40000, "2026-09-01", price=300000)
        conn.commit()
        conn.close()
        summary = self.client.get("/api/dashboard/summary").get_data(as_text=True)
        self.assertNotIn("400", summary)  # no crash; stats rendered
        import webapp.blueprints.dashboard as dash
        stats = dash._load_summary()["stats"]
        self.assertEqual(stats["total_vins"], 1)
        self.assertEqual(stats["total_obs"], 1)
        self.assertEqual(stats["avg_price"], 300000)
        conn = db.get_db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM vehicles WHERE vin = ?", ("A" * 17,)).fetchone()[0], 1)
        conn.close()

    def test_vehicles_list_skips_dealer_stock_but_keeps_resold_car(self):
        conn = db.get_db()
        self._car(conn, "A" * 17, "M2", 2026)
        self._obs(conn, "A" * 17, "1", 5, "2026-09-01")           # dealer only: hidden
        self._car(conn, "B" * 17, "M2", 2025, "2025-06-01")
        self._obs(conn, "B" * 17, "2", 8000, "2025-09-01")        # dealer ad ...
        self._obs(conn, "B" * 17, "3", 30000, "2026-10-01")       # ... then resale: car stays
        conn.commit()
        conn.close()
        html = self.client.get("/vehicles").get_data(as_text=True)
        self.assertNotIn("A" * 17, html)
        self.assertIn("B" * 17, html)
        self.assertIn("B" * 17, self.client.get("/vehicles?source=otomoto").get_data(as_text=True))
        self.assertNotIn("A" * 17, self.client.get("/vehicles?source=otomoto").get_data(as_text=True))


class TestTrendLine(unittest.TestCase):
    def line(self, points):
        from webapp.helpers import trend_line
        return trend_line(points)

    def test_falling_prices_give_a_falling_line(self):
        self.assertEqual(self.line([(0, 300), (100, 200), (200, 100)]), [{"x": 0, "y": 300}, {"x": 200, "y": 100}])

    def test_too_few_points_or_one_mileage_draw_nothing(self):
        self.assertEqual(self.line([(0, 300), (100, 200)]), [])
        self.assertEqual(self.line([(100, 300), (100, 200), (100, 100)]), [])

    def test_line_never_goes_below_zero(self):
        self.assertEqual(self.line([(0, 200), (100, 100), (400, 0)])[1]["y"], 0)


class TestNewModelRules(unittest.TestCase):
    def test_catalog_keeps_new_generations_apart_from_old_rules(self):
        import sqlite3
        from webapp.model_catalog import STANDARD_MODELS, resolve_model_ids
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE vehicles (vin TEXT, make TEXT, model TEXT, variant TEXT, power_hp INT, engine_cc INT, year INT, body_type TEXT, notes TEXT)")
        cars = [("A", "Mercedes-Benz", "Klasa E", "W211 E63 AMG", 514, 6208, "e63_w211"),
                ("B", "Mercedes-Benz", "Klasa E", "W212 E63 AMG", 557, 5461, "e63_w212"),
                ("C", "Mercedes-Benz", "Klasa E", "W211 E55 AMG", 476, 5439, "e55_w211"),
                ("D", "Mercedes-Benz", "Klasa G", "W460 / W461 / W463", 544, 5461, "g_w463"),
                ("E", "Mercedes-Benz", "Klasa G", "G55 AMG W463", 507, 5439, "g55_w463"),
                ("F", "Mercedes-Benz", "Klasa S", "W140", 394, 5987, "s_w140"),
                ("G", "Audi", "RS Q3", "RS Q3 8U", 340, 2480, "rsq3_8u"),
                ("H", "Audi", "RS Q3", "RS Q3 F3", 400, 2480, "rsq3_f3")]
        conn.executemany("INSERT INTO vehicles VALUES (?,?,?,?,?,?,NULL,NULL,NULL)", [c[:6] for c in cars])
        out = resolve_model_ids(conn)
        for car in cars:
            self.assertEqual(out[car[0]], car[6], car[3])
        # Only the single rule matches: /models and CEPiK use the rule directly
        for car in cars:
            hits = [m["id"] for m in STANDARD_MODELS
                    if conn.execute(f"SELECT 1 FROM vehicles v WHERE v.vin = ? AND ({m['where']})", (car[0],)).fetchone()]
            self.assertEqual(hits, [car[6]], car[3])
        conn.close()

    def test_m5_generations_are_told_apart(self):
        from otomoto.bmw_m5_f10 import CONFIG as F10
        from otomoto.bmw_m5_f90 import CONFIG as F90
        self.assertFalse(F10.validator({"vin": "WBSJF0106HB000001"}))
        self.assertFalse(F10.validator({"vin": "WBSGV0C08LB000001"}))
        self.assertTrue(F10.validator({"vin": "WBSFV9C56ED000001"}))
        self.assertTrue(F90.validator({"year": 2021}))
        self.assertTrue(F90.validator({"year": 2017, "vin": "WBSJF0106HB000001"}))
        self.assertFalse(F90.validator({"year": 2017}))
        self.assertFalse(F90.validator({"year": 2018, "vin": "WBSFV9C56ED000001"}))

    def test_m8_listed_as_m5_is_not_an_m5(self):
        # Five M8 Gran Coupés listed on autoplac as "BMW M 5 4.4" got in as M5 F90 (VIN WBSGV...)
        from otomoto.bmw_m5_f90 import CONFIG as F90
        from autoplac.bmw_m5_f90 import CONFIG as F90_AUTOPLAC
        for vin in ("WBSGV01030CP94224", "WBSGV0C06MCF28124", "WBSAE0C08LBM00001", "WBSDZ0C08LBM00001"):
            self.assertFalse(F90.validator({"year": 2022, "vin": vin}), vin)
            self.assertFalse(F90_AUTOPLAC.validator({"year": 2022, "vin": vin}), vin)
        # Real M5s, the M5 CS included
        for vin in ("WBSJF0C55KB000001", "WBS83CH0X0CK00001", "WBS81CH000CF00001",
                    "WBS71CH080CJ40158", "WBS73CH06NCK25713"):
            self.assertTrue(F90.validator({"year": 2021, "vin": vin}), vin)
        self.assertTrue(F90.validator({"year": 2017, "vin": "WBS73CH06NCK25713"}))
        for title in ("BMW M 5 4.4 Gran Coupe 2021", "BMW M8 Competition"):
            haystack = title.lower().replace(" ", "")
            self.assertTrue(any(w.lower().replace(" ", "") in haystack for w in F90_AUTOPLAC.title_must_not_contain), title)
        self.assertFalse(any(w.lower().replace(" ", "") in "bmwm54.4competition" for w in F90.title_must_not_contain))

    def test_m340i_skips_diesel(self):
        from otomoto.bmw_m340i_g20 import CONFIG
        self.assertTrue(CONFIG.validator({"year": 2021, "mileage_km": 60000, "fuel_type": "petrol"}))
        self.assertFalse(CONFIG.validator({"year": 2021, "mileage_km": 60000, "fuel_type": "diesel"}))

    def test_dealer_stock_is_skipped_for_every_model(self):
        year = date.today().year
        self.assertTrue(base_scraper._dealer_stock({"year": year, "mileage_km": 50}))
        self.assertTrue(base_scraper._dealer_stock({"year": year - 1, "mileage_km": 5}))
        self.assertFalse(base_scraper._dealer_stock({"year": 2021, "mileage_km": 50}))
        self.assertFalse(base_scraper._dealer_stock({"year": year, "mileage_km": None}))

    def test_rsq3_f3_skips_8u_vin(self):
        from otomoto.audi_rsq3_f3 import CONFIG
        self.assertTrue(CONFIG.validator({"year": 2021, "mileage_km": 50}))
        self.assertFalse(CONFIG.validator({"year": 2021, "mileage_km": 90000, "vin": "WUAZZZ8U0FD123456"}))

    def test_g_class_title_filter_skips_g55_but_not_g550(self):
        from otomoto.mercedes_g_w463 import CONFIG
        skip = lambda title: any(w in title.lower() for w in CONFIG.title_must_not_contain)
        self.assertTrue(skip("Mercedes W463 G55 AMG Brabus"))
        self.assertTrue(skip("Mercedes G-klasa 55amg"))
        self.assertTrue(skip("Mercedes-Benz Klasa G 55 AMG"))
        self.assertFalse(skip("Mercedes-Benz Klasa G 550"))
        self.assertFalse(skip("Mercedes-Benz Klasa G AMG 63"))
        self.assertTrue(CONFIG.validator({"vin": "WDB4632481X123456"}))
        self.assertFalse(CONFIG.validator({"vin": "WDB2200751A123456"}))


class TestUrlYearRange(unittest.TestCase):
    def test_reads_the_years_of_every_market(self):
        from base_scraper import _url_year_range as years
        self.assertEqual(years("https://www.otomoto.pl/osobowe/bmw/m5?search%5Bfilter_float_year%3Afrom%5D=1998"
                               "&search%5Bfilter_float_year%3Ato%5D=2003&page={page}"), (1998, 2003))
        self.assertEqual(years("https://www.olx.pl/x/?search[filter_float_year:from]=2011"
                               "&search[filter_float_year:to]=2017&page={page}"), (2011, 2017))
        self.assertEqual(years("https://autoplac.pl/oferty/bmw/m-5?yearFrom=2017&yearTo=2024&p={page}"), (2017, 2024))
        self.assertEqual(years("https://www.otomoto.pl/osobowe/mercedes-benz/c-klasa/od-2008?page={page}"), (2008, None))

    def test_no_year_filter_means_no_limit(self):
        from base_scraper import _url_year_range as years
        self.assertEqual(years("https://www.otomoto.pl/osobowe/bmw/alpina?page={page}"), (None, None))

    def test_fleet_stays_in_the_years_it_searches_for(self):
        from base_scraper import _url_year_range as years
        import run_all
        lo, hi = years(run_all.M5_E39.list_url)
        self.assertEqual((lo, hi), (1998, 2003))
        self.assertEqual(years(run_all.M5_F90.list_url)[1], 2024)


class RevealStateMixin:
    """A fresh shared reveal budget (its own state file) and fresh per-process counts."""

    def fresh_reveal_state(self):
        import shutil, tempfile
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.state_file = os.path.join(tmp, "reveal_state.json")
        patcher = mock.patch.object(base_scraper, "REVEAL_STATE_FILE", self.state_file)
        patcher.start()
        self.addCleanup(patcher.stop)
        base_scraper.reset_reveals()
        self.addCleanup(base_scraper.reset_reveals)


class TestRevealVin(RevealStateMixin, unittest.TestCase):
    def setUp(self):
        self.fresh_reveal_state()
        sleep = mock.patch.object(base_scraper.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def reply(self, body, status=200):
        resp = mock.Mock(status_code=status, text=str(body))
        resp.json.return_value = body
        return mock.patch.object(base_scraper.requests, "post", return_value=resp)

    def test_reads_the_vin_from_the_viewer_query(self):
        body = {"data": {"viewer": {"adVin": {"__typename": "AdVin", "vin": {"value": " wdb4632481x123456 "}}}}}
        with self.reply(body) as post:
            self.assertEqual(base_scraper.reveal_vin("6151216780", {}), "WDB4632481X123456")
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["operationName"], "AdvertDetails_ViewerAdVin")
        self.assertEqual(sent["variables"], {"adId": "6151216780"})

    def test_error_code_or_bad_status_gives_none(self):
        with self.reply({"data": {"viewer": {"adVin": {"__typename": "AdVinError", "code": "NOT_FOUND"}}}}):
            self.assertIsNone(base_scraper.reveal_vin("1", {}))
        with self.reply({}, status=403):
            self.assertIsNone(base_scraper.reveal_vin("2", {}))


class TestRunLogOrigin(unittest.TestCase):
    def sent(self, env):
        import importlib
        with mock.patch.dict(os.environ, env, clear=False):
            for name in ("GITHUB_ACTIONS", "RUN_ORIGIN"):
                if name not in env:
                    os.environ.pop(name, None)
            mod = importlib.reload(base_scraper)
            with mock.patch.object(mod._API_SESSION, "post") as post:
                mod._log_run("success", "Processed 'F10 M5'", source="otomoto")
        importlib.reload(base_scraper)
        return post.call_args.kwargs["json"]["message"]

    def test_local_and_github_runs_are_told_apart(self):
        self.assertEqual(self.sent({"GITHUB_ACTIONS": "true"}), "[GitHub] Processed 'F10 M5'")
        self.assertEqual(self.sent({}), "[lokalnie] Processed 'F10 M5'")

    def test_the_vps_names_itself(self):
        self.assertEqual(self.sent({"RUN_ORIGIN": "VPS"}), "[VPS] Processed 'F10 M5'")

    def test_firewall_block_is_not_reported_as_expired_cookies(self):
        cookies = {"refresh_token": "r", "client_id": "c",
                   "id_token": "x.eyJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLmV1LXdlc3QtMS5hbWF6b25hd3MuY29tL3AifQ.y"}
        resp = mock.Mock(status_code=403, text='{"message":"Request not allowed due to WAF challenge."}')
        base_scraper._token_error_logged = False
        with mock.patch.object(base_scraper.requests, "post", return_value=resp), \
             mock.patch.object(base_scraper, "_log_run") as log:
            base_scraper.refresh_session(cookies)
        self.assertIn("WAF", log.call_args.args[1])
        self.assertNotIn("update GitHub Secrets", log.call_args.args[1])



class TestRevealVinPacing(TestRevealVin):
    @staticmethod
    def vin_body(value):
        return {"data": {"viewer": {"adVin": {"__typename": "AdVin", "vin": {"value": value}}}}}

    def test_403_stops_reveals_for_the_rest_of_the_run(self):
        with self.reply({}, status=403) as post:
            self.assertIsNone(base_scraper.reveal_vin("1", {}))
            self.assertIsNone(base_scraper.reveal_vin("2", {}))
        self.assertEqual(post.call_count, 1)
        self.assertFalse(base_scraper.vin_reveal_allowed())

    def test_reveals_are_spaced_and_capped(self):
        with self.reply(self.vin_body("WDB4632481X123456")) as post:
            for i in range(base_scraper.VIN_REVEALS_PER_RUN + 5):
                base_scraper.reveal_vin(str(i), {})
        self.assertEqual(post.call_count, base_scraper.VIN_REVEALS_PER_RUN)
        self.assertEqual(self.sleep.call_count, base_scraper.VIN_REVEALS_PER_RUN - 1)

    def test_masked_vins_do_not_stop_reveals(self):
        # "XXX" at the end is the seller hiding it, not a limit
        with self.reply(self.vin_body("WDD2040771F123XXX")) as post:
            for i in range(5):
                self.assertIsNone(base_scraper.reveal_vin(str(i), {}))
        self.assertEqual(post.call_count, 5)
        self.assertTrue(base_scraper.vin_reveal_allowed())
        with self.reply(self.vin_body("WDB4632481X123456")):
            self.assertEqual(base_scraper.reveal_vin("9", {}), "WDB4632481X123456")


class TestRevealBudget(TestRevealVin):
    """The budget is shared by every process (scrapes, the reveal job) through REVEAL_STATE_FILE."""

    vin_body = staticmethod(TestRevealVinPacing.vin_body)

    def new_process(self):
        base_scraper.reset_reveals()

    def test_a_403_pauses_every_process_for_a_day(self):
        with self.reply({}, status=403):
            base_scraper.reveal_vin("1", {})
        self.new_process()
        with self.reply(self.vin_body("WDB4632481X123456")) as post:
            self.assertIsNone(base_scraper.reveal_vin("2", {}))
        post.assert_not_called()
        self.assertIn("HTTP 403", base_scraper.reveal_skip_reason("plate"))
        later = base_scraper.time.time() + base_scraper.BLOCK_PAUSE_S + 1
        with mock.patch.object(base_scraper.time, "time", return_value=later):
            self.assertIsNone(base_scraper.reveal_skip_reason("vin"))

    def test_the_daily_limit_counts_every_process(self):
        sent = 0
        with self.reply(self.vin_body("WDB4632481X123456")) as post:
            for run in range(5):
                self.new_process()
                for i in range(base_scraper.VIN_REVEALS_PER_RUN):
                    base_scraper.reveal_vin(f"{run}-{i}", {})
            sent = post.call_count
        self.assertEqual(sent, base_scraper.REVEALS_PER_DAY)
        self.assertIn("per day", base_scraper.reveal_skip_reason("vin"))
        self.assertIsNone(base_scraper.reveal_skip_reason("plate"))   # each kind has its own

    def test_counts_start_again_the_next_day(self):
        with open(self.state_file, "w") as f:
            json.dump({"day": "2026-11-09", "vins_today": 999, "plates_today": 999}, f)
        self.assertIsNone(base_scraper.reveal_skip_reason("vin"))
        self.assertIsNone(base_scraper.reveal_skip_reason("plate"))

    def test_an_ad_without_a_vin_is_not_asked_again_for_a_day(self):
        with self.reply({"data": {"viewer": {"adVin": {"__typename": "AdVinError", "code": "NOT_FOUND"}}}}):
            base_scraper.reveal_vin("1", {})
        self.new_process()
        self.assertTrue(base_scraper.recently_asked("vin", "1"))
        self.assertFalse(base_scraper.recently_asked("plate", "1"))
        with self.reply(self.vin_body("WDB4632481X123456")) as post:
            self.assertIsNone(base_scraper.reveal_vin("1", {}))
        post.assert_not_called()
        later = base_scraper.time.time() + base_scraper.VIN_RETRY_AFTER_S + 1
        with mock.patch.object(base_scraper.time, "time", return_value=later):
            self.assertFalse(base_scraper.recently_asked("vin", "1"))

    def test_a_graphql_error_is_not_taken_for_no_vin(self):
        with self.reply({"errors": [{"message": "Unauthorized"}]}):
            base_scraper.reveal_vin("1", {})
        self.assertFalse(base_scraper.recently_asked("vin", "1"))

    def test_a_broken_state_file_counts_as_empty(self):
        with open(self.state_file, "w") as f:
            f.write('{"vin": {"1": "x"}, "blocked_until": "soon", "vins_today": [')
        self.assertIsNone(base_scraper.reveal_skip_reason("vin", "1"))
        base_scraper.mark_none("vin", "2")
        self.assertTrue(base_scraper.recently_asked("vin", "2"))


class TestRevealPlate(TestRevealVin):
    """Since early November 2026 the plate comes from a GraphQL query, like the VIN."""

    def get(self, body, status=200):
        resp = mock.Mock(status_code=status, text=str(body))
        resp.json.return_value = body
        return mock.patch.object(base_scraper.requests, "get", return_value=resp)

    @staticmethod
    def plate_body(value):
        return {"data": {"viewer": {"adRegistration": {
            "__typename": "AdRegistration",
            "registration": {"value": value, "__typename": "AdAttribute"}}, "__typename": "Viewer"}}}

    def test_reads_the_plate_as_the_ad_page_asks_for_it(self):
        with self.get(self.plate_body(" wpr6606t ")) as get:
            self.assertEqual(base_scraper.reveal_plate("6151103542", {}), "WPR6606T")
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["operationName"], "AdvertDetails_ViewerAdRegistration")
        self.assertEqual(json.loads(params["variables"]), {"adId": "6151103542"})
        self.assertEqual(json.loads(params["extensions"])["persistedQuery"]["sha256Hash"],
                         base_scraper._PLATE_QUERY[1])

    def test_an_answer_without_a_valid_plate_is_empty(self):
        for i, body in enumerate((self.plate_body(""), self.plate_body("BRAK123"),
                                  {"data": {"viewer": {"adRegistration": None}}})):
            with self.get(body):
                self.assertEqual(base_scraper.reveal_plate(str(i), {}), "", body)
            self.assertTrue(base_scraper.recently_asked("plate", str(i)))

    def test_a_failed_request_is_none(self):
        with self.get({"errors": [{"message": "PersistedQueryNotFound"}]}):
            self.assertIsNone(base_scraper.reveal_plate("1", {}))
        with self.get({}, status=500):
            self.assertIsNone(base_scraper.reveal_plate("1", {}))

    def test_403_stops_plates_and_vins(self):
        with self.get({}, status=403) as get:
            self.assertIsNone(base_scraper.reveal_plate("1", {}))
            self.assertIsNone(base_scraper.reveal_plate("2", {}))
        self.assertEqual(get.call_count, 1)
        self.assertFalse(base_scraper.vin_reveal_allowed())

    def test_masked_vins_do_not_stop_plates(self):
        with self.reply(TestRevealVinPacing.vin_body("XXXXXXXXXXXXXXXXX")):
            for i in range(5):
                base_scraper.reveal_vin(str(i), {})
        self.assertTrue(base_scraper.plate_reveal_allowed())

    def test_plates_are_capped_and_paced_with_the_vins(self):
        with self.reply(TestRevealVinPacing.vin_body("WDB4632481X123456")):
            base_scraper.reveal_vin("0", {})
        with self.get(self.plate_body("WA12345")) as get:
            for i in range(base_scraper.VIN_REVEALS_PER_RUN + 5):
                base_scraper.reveal_plate(str(i), {})
        self.assertEqual(get.call_count, base_scraper.VIN_REVEALS_PER_RUN)
        self.assertEqual(self.sleep.call_count, base_scraper.VIN_REVEALS_PER_RUN)   # after the VIN too
        self.assertTrue(base_scraper.vin_reveal_allowed())


class TestOtomotoDetailPlate(unittest.TestCase):
    def detail(self, params_dict, details=()):
        nd = {"props": {"pageProps": {"advert": {
            "id": "6151103542", "details": list(details), "parametersDict": params_dict}}}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script>'
        with mock.patch.object(base_scraper.requests, "get", return_value=mock.Mock(status_code=200, text=html)):
            return base_scraper.fetch_detail("https://www.otomoto.pl/osobowe/oferta/x-ID1.html")

    def test_an_ad_with_a_plate_behind_the_button_is_flagged(self):
        d = self.detail({"has_registration": {"values": [{"value": "1"}]}},
                        details=[{"key": "registration", "value": ""}])
        self.assertIsNone(d["registration_plate"])
        self.assertTrue(d["plate_behind_reveal"])

    def test_an_ad_without_a_plate_is_not_flagged(self):
        self.assertFalse(self.detail({})["plate_behind_reveal"])


class TestOtomotoVinIsValidated(unittest.TestCase):
    """A VIN from the description or from "Show VIN" must pass is_plausible_vin, like the page's own."""

    def detail(self, description):
        nd = {"props": {"pageProps": {"advert": {
            "id": "1", "details": [], "parametersDict": {}, "description": description}}}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script>'
        with mock.patch.object(base_scraper.requests, "get", return_value=mock.Mock(status_code=200, text=html)):
            return base_scraper.fetch_detail("https://www.otomoto.pl/osobowe/oferta/x-ID1.html")

    def test_description_vin_of_a_known_maker_is_taken(self):
        d = self.detail("Auto bezwypadkowe, VIN: WBS11DM0108E8AG77, serwis ASO.")
        self.assertEqual((d["vin"], d["vin_confidence"]), ("WBS11DM0108E8AG77", "found_in_description"))

    def test_description_vin_of_an_unknown_maker_is_not(self):
        d = self.detail("Kod ZZZ11DM0108E8AG77 z opisu")
        self.assertIsNone(d["vin"])

    def test_revealed_vin_is_used_only_when_plausible(self):
        good = {"vin": None, "vin_confidence": "found_in_schema"}
        self.assertTrue(base_scraper._use_revealed_vin(good, "WDD2040771F408260"))
        self.assertEqual((good["vin"], good["vin_confidence"]), ("WDD2040771F408260", "found_in_schema"))

        bad = {"vin": None, "vin_confidence": "found_in_schema"}
        self.assertFalse(base_scraper._use_revealed_vin(bad, "ZZZ11DM0108E8AG77"))
        self.assertIsNone(bad["vin"])
        self.assertEqual((bad["invalid_vin"], bad["vin_confidence"]), ("ZZZ11DM0108E8AG77", "invalid_vin"))

        none = {"vin": None, "vin_confidence": "found_in_schema"}
        self.assertFalse(base_scraper._use_revealed_vin(none, None))
        self.assertEqual(none, {"vin": None, "vin_confidence": "found_in_schema"})


class TestWorthRevealing(unittest.TestCase):
    def test_no_reveal_for_a_listing_the_validator_rejects(self):
        from otomoto.bmw_m340i_g20 import CONFIG
        self.assertFalse(base_scraper._worth_revealing(CONFIG, {"year": 2021, "mileage_km": 1, "fuel_type": "diesel"}))
        self.assertTrue(base_scraper._worth_revealing(CONFIG, {"year": 2021, "mileage_km": 60000, "fuel_type": "petrol"}))

    def test_a_2017_m5_waits_for_its_vin(self):
        from otomoto.bmw_m5_f90 import CONFIG
        self.assertTrue(base_scraper._worth_revealing(CONFIG, {"year": 2017}))
        self.assertFalse(CONFIG.validator({"year": 2017}))

    def test_no_reveal_for_dealer_stock_of_any_model(self):
        from otomoto.bmw_x3_m_f97 import CONFIG as X3M          # picks its model by VIN
        from otomoto.toyota_gr_yaris import CONFIG as YARIS     # no validator
        year = date.today().year
        for cfg in (X3M, YARIS):
            self.assertFalse(base_scraper._worth_revealing(cfg, {"year": year, "mileage_km": 15}))
            self.assertTrue(base_scraper._worth_revealing(cfg, {"year": year - 3, "mileage_km": 45000}))

    def test_m2_g87_needs_an_m_vin(self):
        from otomoto.bmw_m2_g87 import CONFIG
        from olx.bmw_m2_g87 import CONFIG as OLX
        from autoplac.bmw_m2_g87 import CONFIG as AUTOPLAC
        for cfg in (CONFIG, OLX, AUTOPLAC):
            self.assertTrue(cfg.validator({"vin": "WBS21DM0608G23935"}))
            self.assertTrue(cfg.validator({"vin": "3MF23DM02S8E99894"}))
            self.assertFalse(cfg.validator({"vin": "WBA13AL02P7M17423"}))   # 2 Series sold as an M2
            self.assertTrue(cfg.validator({"vin": None, "before_reveal": True}))

    def test_scrapers_that_pick_the_model_by_vin_always_reveal(self):
        from otomoto.bmw_x3_m_f97 import CONFIG
        self.assertTrue(base_scraper._worth_revealing(CONFIG, {"year": 2021, "power_hp": 360}))



class TestSessionCheckKeepsAccountPrivate(unittest.TestCase):
    def test_session_check_never_prints_the_account_email_or_name(self):
        import io, contextlib
        resp = mock.Mock()
        resp.json.return_value = {"user": {"name": "Jan Kowalski", "email": "someone@example.com"}}
        out = io.StringIO()
        with mock.patch.object(base_scraper.requests, "get", return_value=resp), contextlib.redirect_stdout(out):
            self.assertTrue(base_scraper.check_session({}))
        self.assertNotIn("someone@example.com", out.getvalue())
        self.assertNotIn("Kowalski", out.getvalue())


class TestRevealEndpoints(ScrapingTestCase):
    """/api/reveal_queue and /api/reveal_result, used by the reveal job on the VPS."""

    def add(self, sid, status="pending", vin=None, vc="found_in_schema", plate=None, scraped="2026-11-08 10:00:00"):
        conn = db.get_db()
        cur = conn.execute("""INSERT INTO pending_listings (source, source_listing_id, make, model, variant, status,
                              vin, vin_confidence, registration_plate, scraped_at)
                              VALUES ('otomoto', ?, 'BMW', 'Seria 3', 'M340i', ?, ?, ?, ?, ?)""",
                           (sid, status, vin, vc, plate, scraped))
        conn.commit()
        conn.close()
        return cur.lastrowid

    def row(self, listing_id):
        conn = db.get_db()
        r = conn.execute("SELECT vin, registration_plate FROM pending_listings WHERE id=?", (listing_id,)).fetchone()
        conn.close()
        return r

    def test_queue(self):
        self.add("novin")
        self.add("hasvin", vin="WBA5U91010FK21968")
        self.add("novin-in-ad", vc="none")
        self.add("rejected", status="rejected")
        self.add("old", plate=None, scraped="2026-10-01 10:00:00")
        self.add("approved-noplate", status="approved", vin="WBA5U91010FK21968")
        q = self.client.post("/api/reveal_queue", headers=TOKEN, json={"plates_since": "2026-11-05"}).get_json()
        self.assertEqual([it["source_listing_id"] for it in q["vins"]], ["old", "novin"])
        self.assertEqual([it["source_listing_id"] for it in q["plates"]],
                         ["novin-in-ad", "hasvin", "novin", "approved-noplate"])

    def test_vin_is_stored_only_if_plausible_and_missing(self):
        good, bad = self.add("good"), self.add("bad")
        res = self.client.post("/api/reveal_result", headers=TOKEN, json={"id": good, "vin": "wba5u91010fk21968"})
        self.assertEqual(res.get_json(), {"vin": True, "plate": False})
        self.assertEqual(self.row(good)["vin"], "WBA5U91010FK21968")
        res = self.client.post("/api/reveal_result", headers=TOKEN, json={"id": bad, "vin": "WDD15666600000000"})
        self.assertFalse(res.get_json()["vin"])
        self.assertIsNone(self.row(bad)["vin"])

    def test_plate_goes_to_the_approved_car_too(self):
        self.add_active_listing("ap", "WBS8M9C50J5K99001", "F80")
        conn = db.get_db()
        listing_id = conn.execute("SELECT id FROM pending_listings WHERE source_listing_id='ap'").fetchone()["id"]
        conn.close()
        res = self.client.post("/api/reveal_result", headers=TOKEN, json={"id": listing_id, "plate": "dw 12345"})
        self.assertTrue(res.get_json()["plate"])
        self.assertEqual(self.row(listing_id)["registration_plate"], "DW12345")
        conn = db.get_db()
        self.assertEqual(conn.execute("SELECT registration_plate FROM vehicles WHERE vin='WBS8M9C50J5K99001'")
                         .fetchone()[0], "DW12345")
        conn.close()

    def test_invalid_or_rejected_plate_is_not_stored(self):
        bad = self.add("bad")
        self.assertFalse(self.client.post("/api/reveal_result", headers=TOKEN,
                                          json={"id": bad, "plate": "BMWm40i"}).get_json()["plate"])
        rejected = self.add("rej", vin="WBA5U91010FK21968")
        conn = db.get_db()
        conn.execute("INSERT INTO plate_review_queue (vin, status, reviewed_plate) "
                     "VALUES ('WBA5U91010FK21968', 'rejected', 'DW12345')")
        conn.commit()
        conn.close()
        self.assertFalse(self.client.post("/api/reveal_result", headers=TOKEN,
                                          json={"id": rejected, "plate": "DW 12345"}).get_json()["plate"])
        self.assertIsNone(self.row(rejected)["registration_plate"])

    def test_token_and_unknown_id(self):
        self.assertEqual(self.client.post("/api/reveal_queue", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/reveal_result", json={"id": 1}).status_code, 401)
        self.assertEqual(self.client.post("/api/reveal_result", headers=TOKEN, json={"id": 999}).status_code, 404)


class TestRevealJob(RevealStateMixin, unittest.TestCase):
    """scripts/maintenance/reveal_pending_vins.py: a few per run, within the scrapes' shared budget."""

    def setUp(self):
        from scripts.maintenance import reveal_pending_vins as job
        self.job = job
        self.fresh_reveal_state()
        self.session = mock.Mock(get=mock.Mock(return_value={}))

    def items(self, n):
        return [{"id": i, "source_listing_id": str(1000 + i), "variant": "M340i"} for i in range(n)]

    def test_due_skips_ads_that_recently_had_none(self):
        base_scraper.mark_none("vin", "1000")
        self.assertEqual([it["source_listing_id"] for it in self.job.due("vin", self.items(3))], ["1001", "1002"])
        self.assertEqual(len(self.job.due("plate", self.items(3))), 3)

    def test_vins_are_stored_and_an_invalid_one_is_remembered(self):
        with mock.patch.object(self.job, "reveal_vin", side_effect=["WBA5U91010FK21968", None, "WDD15666600000000"]), \
             mock.patch.object(self.job, "send_result", side_effect=[{"vin": True}, {"vin": False}]) as send:
            self.assertEqual(self.job.fill_vins(self.items(3), self.session), (1, None))
        self.assertEqual(send.call_args_list[0], mock.call(0, vin="WBA5U91010FK21968"))
        self.assertTrue(base_scraper.recently_asked("vin", "1002"))

    def test_a_block_stops_the_batch(self):
        def blocked(*a):
            base_scraper._mark_blocked()
        with mock.patch.object(self.job, "reveal_vin", side_effect=blocked) as reveal:
            found, why = self.job.fill_vins(self.items(3), self.session)
        self.assertEqual((found, reveal.call_count), (0, 1))
        self.assertIn("HTTP 403", why)

    def test_plates_stop_at_the_per_run_limit(self):
        def reveal(sid, cookies):
            base_scraper._vin_reveals["plates"] += 1
            return "" if sid == "1001" else "DW12345"
        with mock.patch.object(base_scraper, "VIN_REVEALS_PER_RUN", 3), \
             mock.patch.object(self.job, "reveal_plate", side_effect=reveal), \
             mock.patch.object(self.job, "send_result", return_value={"plate": True}) as send:
            found, why = self.job.fill_plates(self.items(5), self.session)
        self.assertEqual((found, send.call_count), (2, 2))
        self.assertIn("per run", why)

    def test_no_request_at_all_while_blocked(self):
        base_scraper._mark_blocked()
        base_scraper.reset_reveals()    # a new process: only the state file knows
        with mock.patch.object(self.job, "fetch_queue") as queue, \
             mock.patch.object(self.job, "_Session") as session, \
             mock.patch.object(sys, "argv", ["reveal_pending_vins.py"]):
            self.job.main()
        queue.assert_not_called()
        session.assert_not_called()

    def test_main_reveals_what_is_due_and_logs_one_line(self):
        base_scraper.mark_none("vin", "1000")
        with mock.patch.object(self.job, "fetch_queue", return_value={"vins": self.items(2), "plates": []}), \
             mock.patch.object(self.job, "_Session", return_value=mock.Mock(cookies={}, get=lambda: {})), \
             mock.patch.object(self.job, "check_session", return_value=True), \
             mock.patch.object(self.job, "reveal_vin", return_value="WBA5U91010FK21968") as reveal, \
             mock.patch.object(self.job, "send_result", return_value={"vin": True}), \
             mock.patch.object(self.job, "_log_run") as log, \
             mock.patch.object(sys, "argv", ["reveal_pending_vins.py"]):
            self.job.main()
        reveal.assert_called_once_with("1001", {})
        self.assertEqual(log.call_args.args[0], "success")
        self.assertIn("1 of 1 pending", log.call_args.args[1])


class TestUseStored(unittest.TestCase):
    """A listing we already store keeps its VIN and plate without asking otomoto again."""

    def test_stored_vin_and_plate_fill_the_gaps(self):
        detail = {"vin": None, "vin_confidence": "found_in_schema", "plate_behind_reveal": True}
        self.assertTrue(base_scraper._use_stored(detail, {"vin": "WBS8M9C50J5K99001", "plate": "WX12345"}))
        self.assertEqual((detail["vin"], detail["registration_plate"], detail["plate_behind_reveal"]),
                         ("WBS8M9C50J5K99001", "WX12345", False))

    def test_placeholder_or_implausible_vin_is_not_used(self):
        for vin in ("UNVERIFIED-otomoto-123", "XXXXXXXXXXXXXXXXX", None):
            detail = {"vin": None}
            self.assertFalse(base_scraper._use_stored(detail, {"vin": vin, "plate": None}))
            self.assertIsNone(detail["vin"])

    def test_the_ad_page_wins_over_the_stored_values(self):
        detail = {"vin": "WDD2040771F408260", "registration_plate": "KR1ABC"}
        self.assertFalse(base_scraper._use_stored(detail, {"vin": "WBS8M9C50J5K99001", "plate": "WX12345"}))
        self.assertEqual((detail["vin"], detail["registration_plate"]), ("WDD2040771F408260", "KR1ABC"))
        self.assertFalse(base_scraper._use_stored(detail, None))


class TestKnownListingsGiveStoredValues(ScrapingTestCase):
    def test_vin_and_plate_are_returned(self):
        self.add_active_listing("full", "WBS8M9C50J5K99001", "F80", plate="WX12345")
        self.add_active_listing("noplate", "WBS8M9C50J5K99003", "F80", status="pending")
        known = self.client.post("/api/known_listings", headers=TOKEN, json={"items": [
            ["otomoto", "full"], ["otomoto", "noplate"]]}).get_json()["known"]
        self.assertEqual((known["otomoto:full"]["vin"], known["otomoto:full"]["plate"]),
                         ("WBS8M9C50J5K99001", "WX12345"))
        self.assertEqual((known["otomoto:noplate"]["status"], known["otomoto:noplate"]["plate"]), ("pending", None))


class TestScraperRevealsOnlyWhatIsMissing(RevealStateMixin, unittest.TestCase):
    """The scrape reveals nothing for an approved listing and takes stored values over a reveal."""

    CFG = base_scraper.ScraperConfig(make="BMW", model="M3", variant="F80", source="otomoto",
                                     list_url="https://www.otomoto.pl/x?page={page}", detail_delay=0)

    def run_scraper(self, known):
        self.fresh_reveal_state()
        api = mock.MagicMock()
        api.post.side_effect = lambda url, **kw: FakeResp(200, {"known": known} if "known_listings" in url
                                                          else {"tag": "pending", "marked": 0})
        detail = lambda url, **kw: {"year": 2016, "vin": None, "vin_confidence": "found_in_schema",
                                    "plate_behind_reveal": True}
        with mock.patch.dict(base_scraper._DETAIL_CACHE, clear=True), \
             mock.patch.object(base_scraper, "load_cookies", return_value={"c": "1"}), \
             mock.patch.object(base_scraper, "refresh_session", side_effect=lambda c, **kw: c), \
             mock.patch.object(base_scraper, "check_session", return_value=True), \
             mock.patch.object(base_scraper.requests, "get", side_effect=lambda *a, **k: FakeResp(200)), \
             mock.patch.object(base_scraper, "_parse_otomoto_cards", side_effect=[[_card(1), _card(2)], []]), \
             mock.patch.object(base_scraper, "fetch_detail", side_effect=detail), \
             mock.patch.object(base_scraper, "reveal_vin", return_value="WBS8M9C50J5K99002") as vin, \
             mock.patch.object(base_scraper, "reveal_plate", return_value="WX99999") as plate, \
             mock.patch.object(base_scraper, "_API_SESSION", api), \
             mock.patch.object(base_scraper.time, "sleep"):
            results = base_scraper.run(self.CFG)
        return {r["source_listing_id"]: r for r in results}, vin, plate

    def test_approved_listing_is_not_revealed_and_keeps_its_values(self):
        results, vin, plate = self.run_scraper({"otomoto:id1": {
            "status": "approved", "complete": False, "vin": "WBS8M9C50J5K99001", "plate": None}})
        self.assertEqual([c.args[0] for c in vin.call_args_list], ["id2"])
        self.assertEqual([c.args[0] for c in plate.call_args_list], ["id2"])
        self.assertEqual(results["id1"]["vin"], "WBS8M9C50J5K99001")
        self.assertEqual((results["id2"]["vin"], results["id2"]["registration_plate"]),
                         ("WBS8M9C50J5K99002", "WX99999"))

    def test_pending_listing_with_a_stored_vin_reveals_only_the_plate(self):
        results, vin, plate = self.run_scraper({"otomoto:id1": {
            "status": "pending", "complete": False, "vin": "WBS8M9C50J5K99001", "plate": None}})
        self.assertEqual([c.args[0] for c in vin.call_args_list], ["id2"])
        self.assertEqual([c.args[0] for c in plate.call_args_list], ["id1", "id2"])
        self.assertEqual(results["id1"]["vin"], "WBS8M9C50J5K99001")


class TestOutsideSearch(unittest.TestCase):
    """Power and engine size must fit the model's searches (a GLA 200 is not a GLA45)."""

    def test_power_outside_the_search_is_ruled_out(self):
        from otomoto.mercedes_gla45_x156 import CONFIG
        self.assertIn("156 HP", base_scraper._outside_search(CONFIG, {"power_hp": 156}))
        self.assertIsNone(base_scraper._outside_search(CONFIG, {"power_hp": 381}))
        self.assertIsNone(base_scraper._outside_search(CONFIG, {"power_hp": 340}))   # within 10 %
        self.assertIsNone(base_scraper._outside_search(CONFIG, {}))                  # unknown fits
        self.assertFalse(base_scraper._worth_revealing(CONFIG, {"power_hp": 156}))

    def test_a_search_without_the_filter_borrows_the_otomoto_one(self):
        from autoplac.bmw_135i_e82 import CONFIG
        self.assertEqual(base_scraper._url_range(CONFIG.list_url, "cc"), (None, None))
        self.assertIn("1995 cm3", base_scraper._outside_search(CONFIG, {"engine_cc": 1995}))
        self.assertIsNone(base_scraper._outside_search(CONFIG, {"engine_cc": 2979, "power_hp": 306}))

    def test_no_filter_anywhere_lets_everything_through(self):
        cfg = base_scraper.ScraperConfig(make="X", model="Y", variant="Z", source="olx",
                                         list_url="https://www.olx.pl/x/?page={page}")
        self.assertIsNone(base_scraper._outside_search(cfg, {"power_hp": 50, "engine_cc": 900}))

    def test_one_fitting_search_is_enough(self):
        cfg = base_scraper.ScraperConfig(make="X", model="Y", variant="Z2", source="autoplac", list_url=[
            "https://autoplac.pl/oferty/x?enginePowerFrom=300&enginePowerTo=350&p={page}",
            "https://autoplac.pl/oferty/x?enginePowerFrom=450&p={page}"])
        self.assertIsNone(base_scraper._outside_search(cfg, {"power_hp": 500}))
        self.assertIsNotNone(base_scraper._outside_search(cfg, {"power_hp": 400}))

    def test_filters_of_each_site_are_read(self):
        from olx._common import olx_url
        from autoplac._common import autoplac_url
        self.assertEqual(base_scraper._url_range(olx_url("bmw", ["m3"], power_from=400, size_to=3100), "power"),
                         (400, None))
        self.assertEqual(base_scraper._url_range(olx_url("bmw", ["m3"], power_from=400, size_to=3100), "cc"),
                         (None, 3100))
        self.assertEqual(base_scraper._url_range(autoplac_url("bmw", "m-3", cc_from=2900, cc_to=3100), "cc"),
                         (2900, 3100))
        from otomoto.bmw_m340i_g20 import CONFIG
        self.assertEqual(base_scraper._url_range(CONFIG.list_url, "power"), (350, 420))

    def test_every_stored_scraper_keeps_its_own_cars(self):
        # each config's own defaults (a typical car of the model) must pass its own searches
        from scripts.maintenance.audit_listings import load_configs
        for cfgs in load_configs().values():
            for cfg in cfgs:
                self.assertIsNone(base_scraper._outside_search(cfg, cfg.defaults), cfg)


class TestBulkRejectKeepsVinsAwaitingReveal(ScrapingTestCase):
    def test_only_listings_without_any_vin_are_rejected(self):
        conn = db.get_db()
        for sid, source, vin, vc in (("behind", "otomoto", None, "found_in_schema"),
                                     ("none", "otomoto", None, "none"),
                                     ("olx", "olx", None, "found_in_schema"),
                                     ("has", "otomoto", "WBS8M9C50J5K99001", "found_in_schema")):
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, make, model, vin, vin_confidence)"
                         " VALUES (?, ?, 'BMW', 'M3', ?, ?)", (sid and source, sid, vin, vc))
        conn.commit()
        self.client.post("/review/bulk_reject_novin")
        status = {r["source_listing_id"]: r["status"] for r in
                  conn.execute("SELECT source_listing_id, status FROM pending_listings").fetchall()}
        conn.close()
        self.assertEqual(status, {"behind": "pending", "none": "rejected", "olx": "rejected", "has": "pending"})

    def seed(self):
        conn = db.get_db()
        for sid, vin, vc in (("behind", None, "found_in_schema"), ("masked", "WDB4632481X165XXX", "found_in_schema"),
                             ("none", None, "none")):
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, make, model, vin, vin_confidence)"
                         " VALUES ('otomoto', ?, 'BMW', 'M3', ?, ?)", (sid, vin, vc))
        conn.commit()
        ids = {r["source_listing_id"]: r["id"] for r in conn.execute("SELECT id, source_listing_id FROM pending_listings")}
        conn.close()
        return ids

    def statuses(self):
        conn = db.get_db()
        out = {r["source_listing_id"]: r["status"] for r in
               conn.execute("SELECT source_listing_id, status FROM pending_listings").fetchall()}
        conn.close()
        return out

    def test_reject_all_keeps_vins_awaiting_reveal(self):
        # On 2026-11-11 "reject all" took 47 listings whose VIN was still behind "Show VIN"
        self.seed()
        res = self.client.post("/review/reject_all_pending?ajax=1")
        self.assertEqual(res.get_json(), {"status": "success", "skipped": 1})
        self.assertEqual(self.statuses(), {"behind": "pending", "masked": "rejected", "none": "rejected"})

    def test_reject_selected_keeps_vins_awaiting_reveal(self):
        ids = self.seed()
        res = self.client.post("/review/bulk_reject?ajax=1", data={"ids": [ids["behind"], ids["none"]]})
        self.assertEqual(res.get_json()["skipped"], 1)
        self.assertEqual(self.statuses(), {"behind": "pending", "masked": "pending", "none": "rejected"})
        page = self.client.get("/review").get_data(as_text=True)
        self.assertIn("Pominięto 1: VIN jest w ogłoszeniu za „Pokaż VIN”", page)


class TestAuditListings(unittest.TestCase):
    def setUp(self):
        from scripts.maintenance import audit_listings
        from otomoto.mercedes_gla45_x156 import CONFIG
        self.audit = audit_listings.audit
        self.configs = {("otomoto", CONFIG.model, CONFIG.variant): [CONFIG]}

    def listing(self, **kw):
        base = {"source": "otomoto", "found_by": "otomoto", "model": "GLA", "variant": "GLA45 AMG X156",
                "raw_title": "Mercedes-Benz GLA 45 AMG", "year": 2017, "power_hp": 381, "engine_cc": 1991,
                "vin": None, "vin_confidence": "none", "raw_description": "", "status": "pending"}
        return {**base, **kw}

    def test_a_pending_gla_200_is_to_be_rejected(self):
        a = self.audit(self.listing(power_hp=156, engine_cc=1595), self.configs)
        self.assertEqual(a["verdict"], "reject")
        self.assertTrue(any("156 HP" in b for b in a["broken"]))

    def test_rejected_only_for_a_vin_behind_reveal_can_be_restored(self):
        a = self.audit(self.listing(status="rejected", vin_confidence="found_in_schema"), self.configs)
        self.assertEqual((a["verdict"], a["vin"]), ("restore", "behind_reveal"))
        a = self.audit(self.listing(status="rejected", raw_description="VIN WDD1569421J123456"), self.configs)
        self.assertEqual((a["verdict"], a["vin"]), ("restore", "in_description"))
        # The seller masked it: nothing to reveal, the rejection stands
        a = self.audit(self.listing(status="rejected", vin_confidence="found_in_schema", vin="WDB4632481X165XXX"), self.configs)
        self.assertEqual((a["verdict"], a["vin"]), ("ok", "none"))

    def test_rejected_without_any_vin_stays(self):
        self.assertEqual(self.audit(self.listing(status="rejected"), self.configs)["verdict"], "ok")
