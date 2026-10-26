"""Pin the behaviour of VIN/plate validation — the core of SportsCar DB.

A VIN that passes is_plausible_vin becomes the key that links a scraped listing
to a known car. If one of these tests fails, a change has altered which VINs
are matched; that must be a deliberate decision, not a refactor side effect.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date

from validation import VIN_RE, is_plausible_vin, is_valid_first_registration_date, is_valid_registration_plate


class TestVin(unittest.TestCase):
    def test_accepts_real_vins(self):
        for vin in [
            "WBS11DM0108E8AG77",   # BMW, modern serial with letters
            "3MF13DM03R8E15622",   # BMW (US-built)
            "WUAZZZ8V2LA900174",   # Audi Sport
            "WDD2040771F408260",   # Mercedes
            "WP0ZZZ98ZGK194519",   # Porsche
            "wbs11dm0108e8ag77",   # case-insensitive
        ]:
            self.assertTrue(is_plausible_vin(vin), vin)

    def test_rejects_fake_or_masked_vins(self):
        for vin in [
            None, "",
            "WBS11DM0108E8AG7",    # 16 chars
            "WBS11DM0108E8AG777",  # 18 chars
            " WBS11DM0108E8AG77",  # whitespace not stripped here
            "WBS11DM0I08E8AG77",   # I/O/Q never appear in VINs
            "WBS11DM0108E8XXXX",   # masked ending
            "JTDAF4E340A0XXXXX",   # masked ending
            "WBA81DP0109J85XXX",   # masked ending
            "12345678912345678",   # unknown manufacturer (WMI)
            "ZZZ11DM0108E8AG77",   # unknown manufacturer (WMI)
            "XXXXXXXXXXXXXXXXX",   # repeated characters
            "WBS11DM0108E8AGAA",   # must end in 2+ digits
            "WBA1111111111AB11",   # one character 7+ times
        ]:
            self.assertFalse(is_plausible_vin(vin), vin)

    def test_vin_regex_finds_candidates_in_text(self):
        text = "Auto bezwypadkowe, VIN: WBS11DM0108E8AG77, serwis ASO. Tel 600600600"
        self.assertEqual(VIN_RE.findall(text), ["WBS11DM0108E8AG77"])
        self.assertEqual(VIN_RE.findall("XWBS11DM0108E8AG77"), [])  # 18 chars: no partial match


class TestPlate(unittest.TestCase):
    def test_accepts_plates(self):
        for plate in ["WA12345", "WA 12345", "wa-123.45", "KR1AB23", "PO5555A"]:
            self.assertTrue(is_valid_registration_plate(plate), plate)

    def test_rejects_plates(self):
        for plate in [
            None, "", 123, "WA1",       # missing / too short
            "WA1234567",                # too long
            "ŁÓD1234",                  # diacritics
            "ABCDEFG", "1234567",       # needs a letter and a digit
            "SALONPL1", "BRAK123", "XXX123",  # placeholder text
        ]:
            self.assertFalse(is_valid_registration_plate(plate), plate)


class TestSingleImplementation(unittest.TestCase):
    def test_app_and_scraper_share_validation(self):
        """Scrapers and the web app must use the same functions (see validation.py)."""
        import validation
        from webapp import helpers
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrapers"))
        import base_scraper
        for mod in (helpers, base_scraper):
            self.assertIs(mod.is_plausible_vin, validation.is_plausible_vin)
            self.assertIs(mod.is_valid_registration_plate, validation.is_valid_registration_plate)
        self.assertIs(base_scraper.VIN_RE, validation.VIN_RE)


class TestFirstRegistrationDate(unittest.TestCase):
    TODAY = date(2026, 10, 14)

    def test_accepts_plausible_dates(self):
        for v in ["2016-05-01", "1980-01-01", "2026-10-14", " 2019-12-31 "]:
            self.assertTrue(is_valid_first_registration_date(v, self.TODAY), v)

    def test_rejects_future_old_and_malformed(self):
        for v in [None, "", "2026-10-15", "2031-01-01", "1979-12-31", "1900-01-01",
                  "2016-13-01", "01-05-2016", "2016/05/01", "abc", 2016]:
            self.assertFalse(is_valid_first_registration_date(v, self.TODAY), v)


class TestModelNamesAreNotPlates(unittest.TestCase):
    def test_rejects_model_names(self):
        for v in ["BMWm40i", "BMW M40i", "M40i X3", "xDrive20"]:
            self.assertFalse(is_valid_registration_plate(v), v)

    def test_real_plates_still_pass(self):
        for v in ["WX12345", "WW 488 GV", "KR-1AB23", "PZ4567K"]:
            self.assertTrue(is_valid_registration_plate(v), v)


if __name__ == "__main__":
    unittest.main()


class TestDealerNewM2(unittest.TestCase):
    TODAY = date(2026, 10, 26)

    def check(self, *a, **kw):
        from validation import is_dealer_new_m2
        return is_dealer_new_m2(*a, on=self.TODAY, **kw)

    def test_new_low_km_m2_is_dealer_stock(self):
        self.assertTrue(self.check("M2", 2026, 5000))
        self.assertTrue(self.check("M2", 2025, 19999, "2026-03-01"))

    def test_registration_date_beats_model_year(self):
        self.assertFalse(self.check("M2", 2026, 5000, "2025-10-25"))   # 366 days
        self.assertTrue(self.check("M2", 2025, 5000, "2025-10-27"))    # 364 days

    def test_year_only_older_than_current_is_kept(self):
        self.assertFalse(self.check("M2", 2025, 5000))

    def test_high_mileage_or_unknown_is_kept(self):
        self.assertFalse(self.check("M2", 2026, 20000))
        self.assertFalse(self.check("M2", 2026, None))

    def test_other_models_are_never_dealer_stock(self):
        self.assertFalse(self.check("M3", 2026, 100))
