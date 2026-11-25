"""Polish plate rules (webapp/services/plate_rules.py): which strings can be a Polish plate, and
how an OCR reading is fixed by the 2024 regulation's layouts and district codes."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.services.plate_rules import DISTRICTS, plate_candidates, plate_kind


class TestPlateKind(unittest.TestCase):
    def test_plates_cepik_confirmed_are_recognised(self):
        for plate, kind in (("KR7VG22", "zwyczajna"), ("WA12345", "zwyczajna"), ("PO1234A", "zwyczajna"),
                            ("DW5S123", "zwyczajna"), ("KRA12AC", "zwyczajna"), ("CB99999", "zwyczajna"),
                            ("CN27", "zmniejszona"), ("WR6P", "zmniejszona"), ("AXS4", "zmniejszona"),
                            ("E5AMG55", "indywidualna"), ("W0HT88", "indywidualna"), ("S0TWINS", "indywidualna"),
                            ("Z7M4X", "indywidualna"), ("W01234", "tymczasowa"), ("po 1234a", "zwyczajna")):
            self.assertEqual(plate_kind(plate), kind, plate)

    def test_foreign_and_junk_are_not_polish(self):
        for plate in ("7LUD212", "8ZY5033", "HHAB1234", "DW00000", "OO12345", "BMWm40i", "StanUżywany", "", None,
                      "KRA1234",     # a two-letter district never takes four digits
                      "K8A1234"):    # individual: three letters first, digits only at the end
            self.assertIsNone(plate_kind(plate), plate)

    def test_the_district_list_is_the_regulations(self):
        self.assertEqual(len(DISTRICTS), 677)
        self.assertTrue({"WA", "WX", "KR", "KRA", "PO", "PX", "CBC", "TKM"} <= DISTRICTS)
        self.assertNotIn("CD", DISTRICTS)


class TestPlateCandidates(unittest.TestCase):
    def test_a_valid_reading_comes_first(self):
        self.assertEqual(plate_candidates("KR 7VG22")[0], "KR7VG22")

    def test_letters_never_used_in_the_vehicle_part_are_digits(self):
        self.assertEqual(plate_candidates("KR7VG2Z")[0], "KR7VG22")    # no Z there: a 2
        self.assertEqual(plate_candidates("WA1234O")[0], "WA12340")    # no O there: a 0
        self.assertEqual(plate_candidates("PO12B4A")[0], "PO1284A")

    def test_a_digit_in_the_district_code_is_a_letter(self):
        self.assertEqual(plate_candidates("W012345")[0], "WO12345")
        self.assertEqual(plate_candidates("S8I12AC")[0], "SBI12AC")
        self.assertEqual(plate_candidates("P0 12345"), ["PO12345", "PO1234S"])

    def test_s5_and_g6_are_guesses_ranked_after_the_reading(self):
        self.assertEqual(plate_candidates("DW5S123"), ["DW5S123", "DW55123"])

    def test_nothing_when_no_district_fits(self):
        self.assertEqual(plate_candidates("QQ12345"), [])
        self.assertEqual(plate_candidates(""), [])

    def test_an_individual_plate_is_taken_as_read(self):
        self.assertEqual(plate_candidates("E5AMG55"), ["E5AMG55"])

    def test_an_older_individual_plate_ranks_after_every_regular_reading(self):
        self.assertEqual(plate_kind("W0HT88"), "indywidualna")
        self.assertEqual(plate_candidates("W0HT88"), ["W0HT88"])
        # SB112AC (I is never in the vehicle part: a 1) before the older individual reading S8 + I12AC
        self.assertEqual(plate_candidates("S8I12AC"), ["SBI12AC", "SB112AC", "S8I12AC"])


if __name__ == "__main__":
    unittest.main()
