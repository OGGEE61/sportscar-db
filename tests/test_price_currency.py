"""An ad priced in euro must not be stored as if the amount were zloty."""
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]
os.environ.setdefault("DB_BACKEND", "sqlite")

import base_scraper


def otomoto_html(price):
    nd = {"props": {"pageProps": {"advert": {"price": price, "description": "x", "parametersDict": {}}}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script>'


class TestPriceInPln(unittest.TestCase):
    def setUp(self):
        base_scraper._NBP_RATES.clear()

    def test_zloty_price_is_kept(self):
        self.assertEqual(base_scraper.price_in_pln(238000, "PLN"), (238000, None))
        self.assertEqual(base_scraper.price_in_pln(238000, None), (238000, None))

    def test_euro_price_is_converted_and_kept_in_euro(self):
        with mock.patch.object(base_scraper, "pln_rate", return_value=4.25):
            self.assertEqual(base_scraper.price_in_pln(57500, "EUR"), (244375, 57500))

    def test_without_a_rate_the_zloty_price_stays_empty(self):
        with mock.patch.object(base_scraper, "pln_rate", return_value=None):
            self.assertEqual(base_scraper.price_in_pln(57500, "EUR"), (None, 57500))

    def test_another_currency_is_converted_without_a_euro_price(self):
        with mock.patch.object(base_scraper, "pln_rate", return_value=5.0):
            self.assertEqual(base_scraper.price_in_pln(10000, "USD"), (50000, None))

    def test_rate_comes_from_nbp_once(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"rates": [{"mid": 4.3}]}
        with mock.patch.object(base_scraper.requests, "get", return_value=resp) as get:
            self.assertEqual(base_scraper.pln_rate("EUR"), 4.3)
            self.assertEqual(base_scraper.pln_rate("eur"), 4.3)
        self.assertEqual(get.call_count, 1)

    def test_failed_rate_lookup_is_not_repeated(self):
        with mock.patch.object(base_scraper.requests, "get", side_effect=OSError) as get:
            self.assertIsNone(base_scraper.pln_rate("EUR"))
            self.assertIsNone(base_scraper.pln_rate("EUR"))
        self.assertEqual(get.call_count, 1)


class TestOtomotoDetailCurrency(unittest.TestCase):
    def test_detail_carries_the_ad_currency(self):
        d = base_scraper.parse_detail(
            otomoto_html({"value": "57500", "currency": "EUR"}), "https://www.otomoto.pl/osobowe/oferta/x-ID1.html")
        self.assertEqual((d["price_from_detail"], d["price_currency"]), (57500, "EUR"))


class TestOlxAndAutoplacCurrency(unittest.TestCase):
    def test_olx_detail_carries_the_ad_currency(self):
        state = {"ad": {"ad": {"price": {"regularPrice": {"value": 30000, "currencyCode": "EUR"}}, "params": []}}}
        html = f'window.__PRERENDERED_STATE__ = {json.dumps(json.dumps(state))};'
        d = base_scraper.parse_detail(html, "https://www.olx.pl/d/oferta/x-CID5-ID1.html")
        self.assertEqual((d["price_from_detail"], d["price_currency"]), (30000, "EUR"))

    def test_autoplac_detail_carries_the_ad_currency(self):
        offer = {"priceInfo": {"primary": {"price": 40000}, "currency": "EUR"}}
        state = {f"{base_scraper.AUTOPLAC_API}offer/abc-NH": {"body": {"offer": offer}}}
        html = f'<script id="ng-state" type="application/json">{json.dumps(state)}</script>'
        d = base_scraper.parse_detail(html, "https://autoplac.pl/oferta/bmw/m2/abc-NH")
        self.assertEqual((d["price_from_detail"], d["price_currency"]), (40000, "EUR"))


if __name__ == "__main__":
    unittest.main()
