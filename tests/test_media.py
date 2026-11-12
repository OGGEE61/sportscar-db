"""Photo links point straight at R2, so a page of cars is not one function call per photo."""
import datetime
import os
import sys
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp import media_url
from webapp.services import r2

R2_ENV = {"R2_ENDPOINT_URL": "https://abc123.r2.cloudflarestorage.com", "R2_BUCKET_NAME": "photos-bkt",
          "R2_ACCESS_KEY_ID": "AKIDEXAMPLE", "R2_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"}
NINE = datetime.datetime(2026, 11, 12, 9, 0, 0, tzinfo=datetime.timezone.utc).timestamp()


def env(**extra):
    values = {k: v for k, v in os.environ.items() if not k.startswith("R2_")}
    return mock.patch.dict(os.environ, {**values, **extra}, clear=True)


class TestPresignedUrl(unittest.TestCase):
    def test_same_url_as_boto3(self):
        try:
            import boto3
            import botocore.auth
        except ImportError:
            self.skipTest("boto3 not installed")
        when = datetime.datetime(2026, 11, 12, 9, 0, 0)

        class Frozen(datetime.datetime):
            @classmethod
            def utcnow(cls):
                return when

            @classmethod
            def now(cls, tz=None):
                return when.replace(tzinfo=tz) if tz else when

        with env(**R2_ENV):
            s3 = boto3.client("s3", endpoint_url=R2_ENV["R2_ENDPOINT_URL"], region_name="auto",
                              aws_access_key_id=R2_ENV["R2_ACCESS_KEY_ID"],
                              aws_secret_access_key=R2_ENV["R2_SECRET_ACCESS_KEY"])
            for key in ("photos/otomoto_6151609447.jpg", "photos/a b+ą&ż.jpg"):
                with mock.patch.object(botocore.auth.datetime, "datetime", Frozen):
                    expected = s3.generate_presigned_url("get_object", ExpiresIn=r2.EXPIRES_S,
                                                         Params={"Bucket": "photos-bkt", "Key": key})
                self.assertEqual(r2.presigned_url(key, now=NINE + 1234), expected, key)

    def test_url_is_stable_within_the_hour_for_the_browser_cache(self):
        with env(**R2_ENV):
            a = r2.presigned_url("photos/x.jpg", now=NINE + 1)
            b = r2.presigned_url("photos/x.jpg", now=NINE + 3599)
            c = r2.presigned_url("photos/x.jpg", now=NINE + 3600)
        self.assertEqual(a, b)
        self.assertNotEqual(b, c)

    def test_link_outlives_the_page(self):
        with env(**R2_ENV):
            url = r2.presigned_url("photos/x.jpg", now=NINE + 3599)
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q["X-Amz-Date"], ["20261112T090000Z"])
        # rendered at 09:59:59, valid until 13:00
        self.assertGreaterEqual(int(q["X-Amz-Expires"][0]) - 3599, 3 * 3600)

    def test_not_configured(self):
        with env(R2_ENDPOINT_URL="https://x"):
            self.assertIsNone(r2.presigned_url("photos/x.jpg"))


class TestMediaUrl(unittest.TestCase):
    def test_public_bucket_first(self):
        with env(**R2_ENV, R2_PUBLIC_URL="https://pub-1.r2.dev/"):
            self.assertEqual(media_url("photos/x.jpg"), "https://pub-1.r2.dev/photos/x.jpg")

    def test_presigned_link_straight_to_r2(self):
        with env(**R2_ENV):
            url = media_url("photos/x.jpg")
        self.assertTrue(url.startswith("https://abc123.r2.cloudflarestorage.com/photos-bkt/photos/x.jpg?"), url)
        self.assertIn("X-Amz-Signature=", url)

    def test_media_route_only_without_r2(self):
        with env():
            self.assertEqual(media_url("photos/x.jpg"), "/media/photos/x.jpg")
            self.assertEqual(media_url(None), "")


class TestPlatesImagesLoadLazily(unittest.TestCase):
    def test_every_photo_tag_is_lazy(self):
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "templates", "plates.html"), encoding="utf-8") as f:
            tags = re.findall(r"<img [^>]*>", f.read())
        # The two modal images get their src only when opened
        eager = [t for t in tags if 'loading="lazy"' not in t and 'src=""' not in t]
        self.assertEqual(eager, [])


if __name__ == "__main__":
    unittest.main()
