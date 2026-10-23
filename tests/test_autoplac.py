"""Offline tests for the autoplac.pl parser and run loop (pages built from ng-state)."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrapers"))

os.environ["API_TOKEN"] = "test-token"

import base_scraper

API = base_scraper.AUTOPLAC_API
SEARCH = "https://autoplac.pl/oferty/samochody-osobowe?fullTextQuery=bmw%20x3%20m40&p={page}"
HASH = "g01-3-0-2019r-m40i-polski-salon-7490-2353-BE"
URL = f"https://autoplac.pl/oferta/bmw/x3/{HASH}"


def page(state: dict) -> str:
    return f'<html><script id="ng-state" type="application/json">{json.dumps(state)}</script></html>'


def offer(**over):
    ad = {
        "id": 4788919, "brand": "BMW", "productionYear": 2019, "mileage": 94000,
        "enginePowerKW": 265, "engineCapacity": 2998, "bodyType": "SUV", "bodyTypeText": "SUV",
        "fuelType": "GASOLINE", "transmissionType": "AUTOMATIC", "driveType": "FOUR_WHEEL",
        "colorText": "Srebrny", "doors": 5, "licensePlateNumber": "WB0570Y",
        "vin": "WBATS31020LP72826", "description": "Na sprzedaż BMW X3 M40i.",
        "priceInfo": {"primary": {"value": "155 000 zł", "price": 155000}},
        "locationInfo": {"city": "Warszawa", "voivodeshipName": "Mazowieckie"},
        "equipmentGroups": {
            "autoplac": {"groups": [{"name": "Komfort", "elements": ["Klimatyzacja automatyczna"]}]},
            "ie": {"groupName": "Wyposażenie producenta", "elements": []},
            "manual": {"groupName": "Pozostałe wyposażenie", "elements": ["BMW Live Cockpit"]},
        },
        "title": "BMW X3 G01 3.0 M40i", "webUrl": f"/oferta/bmw/x3/{HASH}", "city": "Warszawa",
    }
    ad.update(over)
    return ad


def detail_page(**over):
    photos = [{"sortNumber": 1, "webpUrl": "https://cdn/2"}, {"sortNumber": 0, "webpUrl": "https://cdn/1"}]
    return page({
        f"{API}offer/form?vehicleType=PASSENGER": {"body": {"unrelated": True}, "status": 200},
        f"{API}offer/{HASH}": {"body": {"offer": offer(**over), "photoList": photos}, "status": 200},
    })


def search_page(ids, total):
    items = [{"offer": offer(id=i, webUrl=f"/oferta/bmw/x3/x-{i}"), "photoList": []} for i in ids]
    return page({f"{API}offers/search?fullTextQuery=bmw%20x3%20m40": {
        "body": {"offerList": items, "offerCount": total}, "status": 200}})


class TestAutoplacDetail(unittest.TestCase):
    def test_reads_vin_plate_and_specs(self):
        d = base_scraper._fetch_autoplac_detail(detail_page(), URL)
        self.assertEqual(d["vin"], "WBATS31020LP72826")
        self.assertEqual(d["vin_confidence"], "found_in_schema")
        self.assertEqual(d["registration_plate"], "WB0570Y")
        self.assertEqual((d["year"], d["mileage_km"], d["power_hp"], d["engine_cc"]), (2019, 94000, 360, 2998))
        self.assertEqual((d["fuel_type"], d["transmission"], d["drivetrain"], d["body_type"]),
                         ("petrol", "automatic", "AWD", "SUV"))
        self.assertEqual(d["price_from_detail"], 155000)
        self.assertEqual(d["location_from_detail"], "Warszawa, Mazowieckie")
        self.assertEqual(d["photo_urls"], ["https://cdn/1", "https://cdn/2"])

    def test_equipment_has_otomoto_shape(self):
        eq = json.loads(base_scraper._fetch_autoplac_detail(detail_page(), URL)["equipment"])
        self.assertEqual(eq, [
            {"label": "Komfort", "values": [{"label": "Klimatyzacja automatyczna"}]},
            {"label": "Pozostałe wyposażenie", "values": [{"label": "BMW Live Cockpit"}]},
        ])

    def test_fake_vin_is_not_used(self):
        d = base_scraper._fetch_autoplac_detail(detail_page(vin="WBA0000000000000X"), URL)
        self.assertIsNone(d["vin"])
        self.assertEqual(d["vin_confidence"], "invalid_vin")
        self.assertEqual(d["invalid_vin"], "WBA0000000000000X")

    def test_vin_from_description_when_field_empty(self):
        d = base_scraper._fetch_autoplac_detail(
            detail_page(vin=None, description="VIN: WBATS31020LP72826, bezwypadkowy"), URL)
        self.assertEqual(d["vin"], "WBATS31020LP72826")
        self.assertEqual(d["vin_confidence"], "found_in_description")

    def test_bad_plate_is_dropped(self):
        self.assertIsNone(base_scraper._fetch_autoplac_detail(
            detail_page(licensePlateNumber="BMWm40i"), URL)["registration_plate"])

    def test_page_of_another_offer_gives_nothing(self):
        self.assertEqual(base_scraper._fetch_autoplac_detail(detail_page(), URL + "-other"), {})
        self.assertEqual(base_scraper._fetch_autoplac_detail("<html></html>", URL), {})


class TestAutoplacCards(unittest.TestCase):
    def test_cards_and_total(self):
        cards, total = base_scraper._parse_autoplac_cards(search_page([1, 2], 25))
        self.assertEqual(total, 25)
        self.assertEqual([c["listing_id"] for c in cards], ["1", "2"])
        self.assertEqual(cards[0]["source_url"], "https://autoplac.pl/oferta/bmw/x3/x-1")
        self.assertEqual(cards[0]["price_raw"], "155 000 zł")
        self.assertEqual(cards[0]["location_city"], "Warszawa")

    def test_page_without_search_state(self):
        self.assertEqual(base_scraper._parse_autoplac_cards("<html>blocked</html>"), ([], None))


class FakeResp:
    def __init__(self, text="", status=200, data=None):
        self.status_code = status
        self.text = text
        self.headers = {}
        self._data = data or {}

    def json(self):
        return self._data


class TestAutoplacRun(unittest.TestCase):
    CFG = base_scraper.ScraperConfig(make="BMW", model="X3", variant="M40i G01", source="autoplac",
                                     list_url=SEARCH, detail_delay=0)

    def run_scraper(self, pages):
        pages = iter(pages)
        api = mock.MagicMock()
        api.post.side_effect = lambda url, **kw: FakeResp(data={"known": {}} if "known_listings" in url
                                                          else {"tag": "pending", "marked": 0})
        with mock.patch.object(base_scraper, "load_cookies") as cookies, \
             mock.patch.object(base_scraper.requests, "get", side_effect=lambda *a, **k: FakeResp(next(pages))) as get, \
             mock.patch.object(base_scraper, "fetch_detail", return_value={}), \
             mock.patch.object(base_scraper, "_API_SESSION", api), \
             mock.patch.object(base_scraper.time, "sleep"):
            base_scraper.run(self.CFG)
        return api, get, cookies

    def test_stops_at_offer_count_and_marks_sold(self):
        # A page past the last one would wrap to page 1, so p=3 must never be requested
        api, get, cookies = self.run_scraper([search_page([1, 2], 3), search_page([3], 3)])
        self.assertEqual(get.call_count, 2)
        cookies.assert_not_called()  # the otomoto session is never sent to autoplac
        call = next(c for c in api.post.call_args_list if "mark_removed" in c.args[0])
        self.assertEqual(call.kwargs["json"]["source"], "autoplac")
        self.assertEqual(set(call.kwargs["json"]["seen_ids"]), {"1", "2", "3"})
        ingested = [c.kwargs["json"] for c in api.post.call_args_list if c.args[0].endswith("/api/ingest_pending")]
        self.assertEqual({p["source"] for p in ingested}, {"autoplac"})

    def test_block_page_is_partial_and_marks_nothing(self):
        api, _, _ = self.run_scraper([search_page([1, 2], 30), "<html>captcha</html>"])
        self.assertFalse(any("mark_removed" in c.args[0] for c in api.post.call_args_list))
        log = next(c for c in api.post.call_args_list if c.args[0].endswith("/api/log_run"))
        self.assertEqual(log.kwargs["json"]["status"], "partial")


class TestX3G01Reassign(unittest.TestCase):
    """An M40i filed as X3 M (and the other way around) is saved under the right model."""

    def classify(self, vin, **detail):
        from x3_g01 import classify_x3_g01
        return classify_x3_g01({"vin": vin, "fuel_type": "petrol", "engine_cc": 2998, **detail})

    def test_vin_maker_code_decides(self):
        self.assertEqual(self.classify("WBS11EC0009W81579", power_hp=510), "X3 M")
        self.assertEqual(self.classify("5YMTS0C02LLT10845", power_hp=510), "X3 M")
        self.assertEqual(self.classify("WBATS31020LP72826", power_hp=360), "M40i")
        self.assertEqual(self.classify("5UX83DP0XN9L06777", power_hp=480), "M40i")  # X3 M power typed in

    def test_not_settled_by_vin(self):
        self.assertIsNone(self.classify(None, power_hp=360))
        self.assertIsNone(self.classify("WBATS31020LP72826", fuel_type="diesel"))           # M40d
        self.assertIsNone(self.classify("5UXTS3C57J0Z00282", engine_cc=1998, power_hp=252))  # 30i
        self.assertIsNone(self.classify("WAPXXXXXXXXXXXX12"))                                # Alpina XD3

    def test_every_market_reassigns_to_its_own_sibling(self):
        import importlib
        from x3_g01 import reassign_x3_g01
        for market in ("autoplac", "olx", "otomoto"):
            with self.subTest(market=market):
                m40i = importlib.import_module(f"{market}.bmw_x3_m40i_g01").CONFIG
                x3m = importlib.import_module(f"{market}.bmw_x3_m_f97").CONFIG
                self.assertEqual((m40i.source, x3m.source), (market, market))
                self.assertIs(m40i.list_url, x3m.list_url)      # shared searches
                for cfg in (m40i, x3m):
                    self.assertEqual(cfg.reassign({"vin": "WBATS31020LP72826", "engine_cc": 2998}).variant, "M40i G01")
                    self.assertEqual(cfg.reassign({"vin": "WBS11EC0009W81579", "engine_cc": 2993}).variant, "F97")
                    self.assertIsNone(cfg.reassign({"power_hp": 360}))
                self.assertIs(reassign_x3_g01(market)({"vin": "WBS11EC0009W81579"}), x3m)

    def test_otomoto_searches_cover_both_models_without_a_power_ceiling(self):
        from otomoto.bmw_x3_m40i_g01 import CONFIG
        self.assertEqual([u.split("?")[0].rsplit("/", 1)[1] for u in CONFIG.list_url], ["x3", "x3-m"])
        self.assertFalse(any("engine_power%3Ato" in u for u in CONFIG.list_url))

    def test_fallback_power_check_when_the_vin_does_not_settle_it(self):
        from x3_g01 import x3_g01_power_validator
        m40i, x3m = x3_g01_power_validator("M40i"), x3_g01_power_validator("X3 M")
        self.assertTrue(m40i({"power_hp": 360}) and m40i({}))
        self.assertFalse(m40i({"power_hp": 510}))
        self.assertTrue(x3m({"power_hp": 510}) and x3m({}))
        self.assertFalse(x3m({"power_hp": 360}))

    def run_cfg(self, cfg, detail):
        api = mock.MagicMock()
        api.post.side_effect = lambda url, **kw: FakeResp(data={"known": {}} if "known_listings" in url
                                                          else {"tag": "pending", "marked": 0})
        pages = {cfg.list_url[0].format(page=1): search_page([1], 1),
                 cfg.list_url[1].format(page=1): search_page([1, 2], 2)}
        with mock.patch.object(base_scraper.requests, "get", side_effect=lambda url, **k: FakeResp(pages[url])), \
             mock.patch.object(base_scraper, "fetch_detail", return_value=detail) as fetch, \
             mock.patch.object(base_scraper, "_API_SESSION", api), \
             mock.patch.dict(base_scraper._DETAIL_CACHE, clear=True), \
             mock.patch.object(base_scraper.time, "sleep"):
            base_scraper.run(cfg)
        ingested = [c.kwargs["json"] for c in api.post.call_args_list if c.args[0].endswith("/api/ingest_pending")]
        return ingested, fetch, api

    def test_x3m_listed_under_m40i_is_saved_as_x3m(self):
        from autoplac.bmw_x3_m40i_g01 import CONFIG as M40I
        detail = {"vin": "WBS11EC0009W81579", "fuel_type": "petrol", "engine_cc": 2993, "power_hp": 510,
                  "year": 2024, "title": "BMW X3 M40i"}
        ingested, _, _ = self.run_cfg(M40I, detail)
        self.assertEqual({(p["model"], p["variant"]) for p in ingested}, {("X3 M", "F97")})

    def test_m40i_badged_as_x3m_is_not_rejected(self):
        # The X3 M validator alone would reject this title
        from autoplac.bmw_x3_m_f97 import CONFIG as X3_M
        detail = {"vin": "WBATS31020LP72826", "fuel_type": "petrol", "engine_cc": 2998, "power_hp": 360,
                  "year": 2018, "title": "BMW X3 M40i OEM X3M Competition"}
        ingested, _, _ = self.run_cfg(X3_M, detail)
        self.assertEqual({(p["model"], p["variant"], p["power_hp"]) for p in ingested}, {("X3", "M40i G01", 360)})

    def test_shared_searches_fetch_each_ad_once_and_cover_both_urls(self):
        from autoplac.bmw_x3_m_f97 import CONFIG as X3_M
        ingested, fetch, api = self.run_cfg(X3_M, {"vin": "WBS11EC0009W81579", "fuel_type": "petrol", "year": 2024})
        self.assertEqual(fetch.call_count, 2)   # ad 1 is in both searches, fetched once
        sold = next(c for c in api.post.call_args_list if "mark_removed" in c.args[0])
        self.assertEqual(set(sold.kwargs["json"]["seen_ids"]), {"1", "2"})

    def test_second_scraper_reuses_the_detail_pages_of_the_first(self):
        from autoplac.bmw_x3_m40i_g01 import CONFIG as M40I
        from autoplac.bmw_x3_m_f97 import CONFIG as X3_M
        api = mock.MagicMock()
        api.post.side_effect = lambda url, **kw: FakeResp(data={"known": {}} if "known_listings" in url
                                                          else {"tag": "pending", "marked": 0})
        pages = {M40I.list_url[0].format(page=1): search_page([1], 1),
                 M40I.list_url[1].format(page=1): search_page([1, 2], 2)}
        detail = {"vin": "WBS11EC0009W81579", "fuel_type": "petrol", "engine_cc": 2993, "year": 2024}
        with mock.patch.object(base_scraper.requests, "get", side_effect=lambda url, **k: FakeResp(pages[url])), \
             mock.patch.object(base_scraper, "fetch_detail", return_value=detail) as fetch, \
             mock.patch.object(base_scraper, "_API_SESSION", api), \
             mock.patch.dict(base_scraper._DETAIL_CACHE, clear=True), \
             mock.patch.object(base_scraper.time, "sleep"):
            base_scraper.run(M40I)
            base_scraper.run(X3_M)
        self.assertEqual(fetch.call_count, 2)   # not 4: the X3 M run found both pages cached


class TestAutoplacConfigs(unittest.TestCase):
    def test_url_helper(self):
        from autoplac._common import autoplac_url
        self.assertEqual(autoplac_url("bmw", "m-3", year_from=2014, year_to=2020, power_from=420),
                         "https://autoplac.pl/oferty/samochody-osobowe/bmw/m-3"
                         "?yearFrom=2014&yearTo=2020&enginePowerFrom=420&p={page}")
        self.assertEqual(autoplac_url("mercedes-benz", "klasa-s", year_to=2005, cc_from=5300, cc_to=5500),
                         "https://autoplac.pl/oferty/samochody-osobowe/mercedes-benz/klasa-s"
                         "?yearTo=2005&engineCapacityFrom=5300&engineCapacityTo=5500&p={page}")
        self.assertEqual(autoplac_url(query="bmw x3 m40"),
                         "https://autoplac.pl/oferty/samochody-osobowe?fullTextQuery=bmw%20x3%20m40&p={page}")

    def test_every_fleet_config_is_autoplac(self):
        import run_autoplac
        self.assertEqual(len({id(c) for c in run_autoplac.ALL_AUTOPLAC_FLEET}), len(run_autoplac.ALL_AUTOPLAC_FLEET))
        for cfg in run_autoplac.ALL_AUTOPLAC_FLEET:
            urls = [cfg.list_url] if isinstance(cfg.list_url, str) else cfg.list_url
            with self.subTest(variant=cfg.variant):
                self.assertEqual(cfg.source, "autoplac")
                for u in urls:
                    self.assertTrue(u.startswith("https://autoplac.pl/oferty/") and u.endswith("p={page}"), u)

    def test_autoplac_covers_the_whole_olx_fleet_under_the_same_model_names(self):
        # Same make / model / variant, so finds from every market land on the same model
        import run_autoplac
        import run_olx
        key = lambda c: (c.make, c.model, c.variant)  # noqa: E731
        self.assertEqual({key(c) for c in run_autoplac.ALL_AUTOPLAC_FLEET}, {key(c) for c in run_olx.ALL_OLX_FLEET})
        self.assertEqual(len(run_autoplac.ALL_AUTOPLAC_FLEET), len({key(c) for c in run_autoplac.ALL_AUTOPLAC_FLEET}))

    def test_make_targets_partition_the_fleet(self):
        import run_autoplac as R
        parts = R.BMW_FLEET + R.MERCEDES_FLEET + R.AUDI_FLEET + R.PORSCHE_FLEET + [R.GR_YARIS_AUTOPLAC, R.S2000_AUTOPLAC]
        self.assertEqual([id(c) for c in parts], [id(c) for c in R.ALL_AUTOPLAC_FLEET])
        self.assertEqual(len(R.ALL_AUTOPLAC_FLEET), 35)

    def test_overlapping_models_are_told_apart_by_the_url(self):
        # Models sharing a path must not return the same cars: split by year or engine size
        import run_autoplac as R
        for a, b in ((R.R8_V8_AUTOPLAC, R.R8_V10_AUTOPLAC), (R.CAYMAN_981_AUTOPLAC, R.CAYMAN_GT4_AUTOPLAC)):
            urls_a, urls_b = (set([c.list_url] if isinstance(c.list_url, str) else c.list_url) for c in (a, b))
            self.assertFalse(urls_a & urls_b, (a.variant, b.variant))
        self.assertIn("engineCapacityTo=4500", R.R8_V8_AUTOPLAC.list_url)
        self.assertIn("engineCapacityFrom=4500", R.R8_V10_AUTOPLAC.list_url)
        # Mercedes sellers use both 'Klasa X' and 'X' for the same car
        for cfg, slugs in ((R.C63_W204_AUTOPLAC, {"klasa-c", "c"}), (R.S55_W220_AUTOPLAC, {"klasa-s", "s"}),
                           (R.E55_W211_AUTOPLAC, {"klasa-e", "e"})):
            self.assertEqual({u.split("?")[0].rsplit("/", 1)[1] for u in cfg.list_url}, slugs, cfg.variant)

    def test_verify_script_knows_every_model(self):
        # scripts/verify_autoplac.py holds the expected power / engine size per model
        import run_autoplac as R
        from scripts.verify_autoplac import EXPECT, MAKE_WMI
        for cfg in R.ALL_AUTOPLAC_FLEET:
            with self.subTest(variant=cfg.variant):
                self.assertIn((cfg.model, cfg.variant), EXPECT)
                self.assertIn(cfg.make, MAKE_WMI)


class TestPreflight(unittest.TestCase):
    """A blocked network must stop the fleet with one clear error, not 35 empty runs."""

    def fake_get(self, resp):
        return mock.patch.object(base_scraper.requests, "get", return_value=resp)

    def test_blocked_with_cloudflare_headers(self):
        import run_autoplac
        resp = FakeResp(status=403)
        resp.headers = {"server": "cloudflare", "cf-ray": "abc-WAW", "cf-mitigated": "challenge"}
        with self.fake_get(resp):
            problem = run_autoplac.preflight(run_autoplac.X3_M40I_AUTOPLAC)
        self.assertIn("HTTP 403", problem)
        self.assertIn("cf-mitigated=challenge", problem)

    def test_reachable_and_no_data(self):
        import run_autoplac
        with self.fake_get(FakeResp(text=search_page([1], 1))):
            self.assertIsNone(run_autoplac.preflight(run_autoplac.C63_W204_AUTOPLAC))
        with self.fake_get(FakeResp(text="<html>just a moment</html>")):
            self.assertIn("no search data", run_autoplac.preflight(run_autoplac.C63_W204_AUTOPLAC))

    def test_runner_exits_1_and_logs_an_error_without_scraping(self):
        import runpy
        resp = FakeResp(status=403)
        resp.headers = {}
        with self.fake_get(resp), \
             mock.patch.object(base_scraper, "_log_run") as log, \
             mock.patch.object(base_scraper, "run") as scrape, \
             mock.patch.object(sys, "argv", ["run_autoplac.py", "bmw"]), \
             self.assertRaises(SystemExit) as exit_:
            runpy.run_path(os.path.join(os.path.dirname(base_scraper.__file__), "run_autoplac.py"), run_name="__main__")
        self.assertEqual(exit_.exception.code, 1)
        scrape.assert_not_called()
        self.assertEqual(log.call_args.args[0], "error")
        self.assertEqual(log.call_args.kwargs["source"], "autoplac")


if __name__ == "__main__":
    unittest.main()
