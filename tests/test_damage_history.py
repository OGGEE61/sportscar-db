"""Damage history: a damage found by a VIN check is recorded on the car and shown wherever it is listed."""
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_damage_history.db")

import db
from app import app
from webapp.services import photos

VIN = "WBATS31020LF51925"


def png_bytes(size=(40, 30)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


class DamageHistoryTestCase(unittest.TestCase):
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
        for k in ("R2_ENDPOINT_URL", "R2_BUCKET_NAME", "R2_PUBLIC_URL"):
            os.environ.pop(k, None)
        self.addCleanup(patcher.stop)
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year) VALUES (?, 'BMW', 'X3', 'M40i G01', 2019)", (VIN,))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def reports(self):
        conn = db.get_db()
        rows = [dict(r) for r in conn.execute("SELECT * FROM condition_reports WHERE vin = ?", (VIN,)).fetchall()]
        conn.close()
        return rows

    def add(self, **fields):
        form = {"report_date": "2020-10-11", "accident_free": "no", "country": "Belgia",
                "mileage_km": "69156", "inspection_by": "Aukcja Autorola #ACAR_11813610",
                "notes": "Uszkodzony tył", **fields}
        return self.client.post(f"/vehicle/{VIN}/add_condition", data=form, content_type="multipart/form-data")


class TestMigration(DamageHistoryTestCase):
    def test_columns_added_once(self):
        db.init_db()
        conn = db.get_db()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(condition_reports)").fetchall()}
        conn.close()
        self.assertTrue({"country", "photo"} <= cols)


class TestAddAndShow(DamageHistoryTestCase):
    def test_damage_is_stored_and_shown(self):
        with mock.patch("webapp.blueprints.vehicles.store_photo", return_value="photos/damage/x.jpg") as store:
            res = self.add(photo=(io.BytesIO(png_bytes()), "tyl.png"))
        self.assertEqual(res.status_code, 302)
        self.assertTrue(store.call_args.args[1].startswith(f"damage/{VIN}_"))
        (r,) = self.reports()
        self.assertEqual((r["accident_free"], r["country"], r["mileage_km"], r["photo"]), (0, "Belgia", 69156, "photos/damage/x.jpg"))
        self.assertEqual(r["inspection_by"], "Aukcja Autorola #ACAR_11813610")

        page = self.client.get(f"/vehicle/{VIN}").get_data(as_text=True)
        self.assertIn("Historia szkody: Belgia", page)
        self.assertIn("Uszkodzony tył", page)
        self.assertIn("/media/photos/damage/x.jpg", page)

        listing = self.client.get("/vehicles").get_data(as_text=True)
        self.assertIn("Historia szkody: Belgia", listing)

    def test_accident_free_report_is_no_damage(self):
        self.add(accident_free="yes", notes="Oględziny bez zastrzeżeń")
        page = self.client.get(f"/vehicle/{VIN}").get_data(as_text=True)
        self.assertNotIn("Historia szkody", page)
        self.assertNotIn("Historia szkody", self.client.get("/vehicles").get_data(as_text=True))

    def test_empty_date_is_today(self):
        self.add(report_date="")
        self.assertEqual(self.reports()[0]["report_date"], datetime.today().strftime("%Y-%m-%d"))

    def test_too_big_photo_adds_nothing(self):
        with mock.patch("webapp.blueprints.vehicles.DAMAGE_PHOTO_MAX_BYTES", 10):
            self.add(photo=(io.BytesIO(png_bytes()), "tyl.png"))
        self.assertEqual(self.reports(), [])

    def test_not_an_image_adds_nothing(self):
        self.add(photo=(io.BytesIO(b"not an image"), "tyl.jpg"))
        self.assertEqual(self.reports(), [])

    def test_delete(self):
        self.add()
        rid = self.reports()[0]["id"]
        self.client.post(f"/vehicle/{VIN}/delete_condition/{rid}")
        self.assertEqual(self.reports(), [])


class TestStorePhoto(unittest.TestCase):
    def test_local_store_shrinks_to_jpeg(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(photos, "PHOTOS_DIR", tmp), \
                mock.patch.dict(os.environ, {"R2_ENDPOINT_URL": "", "R2_BUCKET_NAME": ""}):
            key = photos.store_photo(png_bytes((3000, 2000)), "damage/X_1.jpg", max_width=1600)
            self.assertEqual(key, "photos/damage/X_1.jpg")
            with Image.open(os.path.join(tmp, "damage", "X_1.jpg")) as img:
                self.assertEqual((img.format, img.size), ("JPEG", (1600, 1066)))


if __name__ == "__main__":
    unittest.main()
