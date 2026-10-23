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
        from autoplac._x3_g01 import classify_x3_g01
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

    def run_cfg(self, cfg, detail):
        api = mock.MagicMock()
        api.post.side_effect = lambda url, **kw: FakeResp(data={"known": {}} if "known_listings" in url
                                                          else {"tag": "pending", "marked": 0})
        pages = {cfg.list_url[0].format(page=1): search_page([1], 1),
                 cfg.list_url[1].format(page=1): search_page([1, 2], 2)}
        with mock.patch.object(base_scraper.requests, "get", side_effect=lambda url, **k: FakeResp(pages[url])), \
             mock.patch.object(base_scraper, "fetch_detail", return_value=detail) as fetch, \
             mock.patch.object(base_scraper, "_API_SESSION", api), \
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


class TestAutoplacConfigs(unittest.TestCase):
    def test_url_helper(self):
        from autoplac._common import autoplac_url
        self.assertEqual(autoplac_url("bmw", "m-3", year_from=2014, year_to=2020, power_from=420),
                         "https://autoplac.pl/oferty/samochody-osobowe/bmw/m-3"
                         "?yearFrom=2014&yearTo=2020&enginePowerFrom=420&p={page}")
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


if __name__ == "__main__":
    unittest.main()
