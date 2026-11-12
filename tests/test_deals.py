"""The deals page: distance from Poznań, price against the market, and the /deals routes."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_deals.db")

import db
from app import app
from webapp.regions import PLACE_COORDS, km_from_poznan, place_name
from webapp.services import deals

NOW = datetime(2026, 11, 11, 12, 0, 0)


def stamp(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def listing(vin, price, year=2015, city="Poznań", listed=1, seen=0, removed=False, damaged=False,
            variant="F80 M3", **extra):
    return dict(vin=vin, source="otomoto", source_listing_id=f"id-{vin}", source_url=f"https://x/{vin}",
                title="BMW M3", price_pln=price, mileage_km=50000, location_city=city, location_region=None,
                observed_at=stamp(seen), listed_at=stamp(listed), removed_at=stamp(seen) if removed else None,
                make="BMW", model="M3", variant=variant, year=year, power_hp=431, photo=None,
                vin_status="unverified", damaged=1 if damaged else 0, **extra)


def market_of(prices, year=2015, city="Warszawa"):
    """Cars elsewhere in Poland that set the median, listed long ago."""
    return [listing(f"M{i:016d}", p, year=year, city=city, listed=100) for i, p in enumerate(prices)]


class TestDistance(unittest.TestCase):
    def test_place_name_strips_region_and_district(self):
        self.assertEqual(place_name("Poznań, Wielkopolskie"), "Poznań")
        self.assertEqual(place_name("Poznań - Grunwald"), "Poznań")
        self.assertEqual(place_name(None), "")

    def test_distances(self):
        self.assertEqual(km_from_poznan("Poznań, Wielkopolskie"), 0)
        self.assertTrue(5 <= km_from_poznan("Luboń") <= 10)
        self.assertTrue(40 <= km_from_poznan("Gniezno") <= 55)
        self.assertTrue(135 <= km_from_poznan("Wrocław") <= 155)
        self.assertIsNone(km_from_poznan("Nigdzie"))

    def test_ambiguous_village_names_are_not_guessed(self):
        for name in ("Piotrowice", "Kościelna Wieś", "Lipka"):
            self.assertNotIn(name, PLACE_COORDS)

    def test_listing_region(self):
        self.assertEqual(deals.listing_region(None, "Wijewo, Wielkopolskie"), "PL-WP")
        self.assertEqual(deals.listing_region(None, "Swadzim"), "PL-WP")  # from the coordinates table
        self.assertEqual(deals.listing_region("PL-MZ", "Poznań"), "PL-MZ")
        self.assertEqual(deals.listing_region(None, "Gorzów Wielkopolski"), "PL-LB")


class TestCompare(unittest.TestCase):
    def test_median_of_close_years(self):
        rows = market_of([100_000, 110_000, 120_000, 130_000, 140_000]) + [listing("A" * 17, 96_000)]
        cmp = deals.compare(rows[-1], deals.market(rows))
        self.assertEqual(cmp["median"], 120_000)
        self.assertEqual(cmp["count"], 5)
        self.assertEqual(cmp["basis"], "rocznik ±1")
        self.assertAlmostEqual(cmp["diff"], -0.2)
        self.assertEqual(deals.verdict(cmp["diff"]), "deal")

    def test_widens_years_but_never_past_three(self):
        rows = market_of([100_000] * 5, year=2012) + [listing("A" * 17, 90_000, year=2015)]
        self.assertEqual(deals.compare(rows[-1], deals.market(rows))["basis"], "rocznik ±3")
        rows = market_of([100_000] * 5, year=2011) + [listing("A" * 17, 90_000, year=2015)]
        self.assertIsNone(deals.compare(rows[-1], deals.market(rows)))

    def test_too_few_cars_no_comparison(self):
        rows = market_of([100_000] * 4) + [listing("A" * 17, 50_000)]
        self.assertIsNone(deals.compare(rows[-1], deals.market(rows)))

    def test_the_listing_does_not_vote_on_itself_and_a_car_votes_once(self):
        relisted = [listing("R" * 17, 1_000_000, listed=50, seen=40) for _ in range(3)]
        rows = market_of([100_000] * 4) + relisted + [listing("A" * 17, 100_000)]
        # 4 market cars + the relisted car once = 5; the listing itself is not counted
        cmp = deals.compare(rows[-1], deals.market(rows))
        self.assertEqual(cmp["count"], 5)
        self.assertEqual(cmp["median"], 100_000)

    def test_damaged_cars_are_neither_compared_nor_the_market(self):
        rows = market_of([100_000] * 4) + [listing("D" * 17, 10_000, damaged=True), listing("A" * 17, 90_000)]
        groups = deals.market(rows)
        self.assertIsNone(deals.compare(rows[-1], groups))  # only 4 undamaged others
        self.assertIsNone(deals.compare(rows[-2], groups))

    def test_damage_history_is_like_damaged(self):
        crashed = listing("H" * 17, 10_000, damage_history=1)
        rows = market_of([100_000] * 4) + [crashed, listing("A" * 17, 90_000)]
        groups = deals.market(rows)
        self.assertIsNone(deals.compare(crashed, groups))
        self.assertIsNone(deals.compare(rows[-1], groups))  # the crashed car is not one of the 5

    def test_other_variant_is_not_the_market(self):
        rows = market_of([100_000] * 5) + [listing("A" * 17, 90_000, variant="E92 M3")]
        self.assertIsNone(deals.compare(rows[-1], deals.market(rows)))


class TestPoznanDeals(unittest.TestCase):
    def pick(self, rows, **kw):
        return deals.poznan_deals(rows, now=NOW, **kw)

    def test_radius_period_and_removed(self):
        rows = market_of([100_000] * 5) + [
            listing("A" * 17, 90_000, city="Poznań, Wielkopolskie"),
            listing("B" * 17, 90_000, city="Gniezno"),
            listing("C" * 17, 90_000, city="Konin"),
            listing("D" * 17, 90_000, city="Poznań", removed=True),
            listing("E" * 17, 90_000, city="Poznań", listed=45),
        ]
        vins = lambda r: {d["vin"][0] for d in r["items"]}  # noqa: E731
        self.assertEqual(vins(self.pick(rows, range_key="25")), {"A"})
        self.assertEqual(vins(self.pick(rows, range_key="50")), {"A", "B"})
        self.assertEqual(vins(self.pick(rows, range_key="100")), {"A", "B", "C"})
        self.assertEqual(vins(self.pick(rows, range_key="50", period_key="90")), {"A", "B", "E"})

    def test_whole_voivodeship_includes_unknown_places(self):
        rows = [listing("A" * 17, 90_000, city="Wijewo, Wielkopolskie"),
                listing("B" * 17, 90_000, city="Warszawa")]
        near = self.pick(rows, range_key="50")
        self.assertEqual((near["total"], near["unknown_place"]), (0, 1))
        self.assertEqual([d["vin"][0] for d in self.pick(rows, range_key="woj")["items"]], ["A"])

    def test_a_car_on_two_sites_shows_once_newest_first(self):
        rows = [listing("A" * 17, 90_000, listed=5), dict(listing("A" * 17, 91_000, listed=2), source="olx"),
                listing("B" * 17, 90_000, listed=1)]
        items = self.pick(rows)["items"]
        self.assertEqual([(d["vin"][0], d["source"]) for d in items], [("B", "otomoto"), ("A", "olx")])
        self.assertEqual(items[0]["age_days"], 1)

    def test_sort_by_deal_puts_uncompared_last(self):
        rows = market_of([100_000] * 5) + [
            listing("A" * 17, 95_000, listed=1),
            listing("B" * 17, 70_000, listed=3),
            listing("C" * 17, 50_000, listed=2, variant="E30 M3"),  # nothing to compare with
        ]
        self.assertEqual([d["vin"][0] for d in self.pick(rows, sort="deal")["items"]], ["B", "A", "C"])
        self.assertEqual([d["vin"][0] for d in self.pick(rows, sort="new")["items"]], ["A", "C", "B"])


class TestDealsRoutes(unittest.TestCase):
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

    def add(self, vin, price, city, listing_id, days_ago=1):
        conn = db.get_db()
        conn.execute("INSERT OR IGNORE INTO vehicles (vin, make, model, variant, year) VALUES (?, 'BMW', 'M3', 'F80 M3', 2016)",
                     (vin,))
        for seen in (days_ago, 0):
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, source_url, price_pln, "
                         "location_city, observed_at) VALUES (?, 'otomoto', ?, 'https://x', ?, ?, datetime('now', ?))",
                         (vin, listing_id, price, city, f"-{seen} days"))
        conn.commit()
        conn.close()

    def test_page_and_list(self):
        for i in range(5):
            self.add(f"WBS8M9C50G5{i:06d}", 300_000, "Warszawa", f"w{i}", days_ago=60)
        self.add("WBS8M9C50G5999999", 240_000, "Poznań, Wielkopolskie", "p1", days_ago=2)
        self.add("WBS8M9C50G5888888", 240_000, "Kraków", "k1", days_ago=2)

        page = self.client.get("/deals?km=25&sort=deal")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Okazje: Poznań i okolice", page.get_data(as_text=True))
        self.assertIn('hx-get="/api/deals?km=25&days=30&sort=deal"', page.get_data(as_text=True))

        html = self.client.get("/api/deals?km=50").get_data(as_text=True)
        self.assertIn("/vehicle/WBS8M9C50G5999999", html)
        self.assertNotIn("/vehicle/WBS8M9C50G5888888", html)  # Kraków: not shown, but part of the market
        self.assertIn("-20% od mediany", html)
        self.assertIn("Mediana 300 000 zł z 6 aut (rocznik ±1)", html)
        self.assertIn("2 dni temu", html)

    def test_damage_history_shown_on_the_card(self):
        self.add("WBATS31020LF51925", 135_000, "Opalenica", "x3")
        conn = db.get_db()
        conn.execute("INSERT INTO condition_reports (vin, report_date, accident_free, notes) "
                     "VALUES ('WBATS31020LF51925', '2020-10-11', 0, 'Belgia')")
        conn.commit()
        conn.close()
        html = self.client.get("/api/deals?km=50").get_data(as_text=True)
        self.assertIn("Historia szkody", html)
        self.assertIn("Szkoda w historii auta: bez porównania z rynkiem", html)

    def test_bad_choices_fall_back_to_defaults(self):
        html = self.client.get("/api/deals?km=9999&days=x&sort=evil").get_data(as_text=True)
        self.assertIn("w promieniu 50 km od Poznania", html)
        self.assertIn("w ostatnich 30 dniach", html)


if __name__ == "__main__":
    unittest.main()
