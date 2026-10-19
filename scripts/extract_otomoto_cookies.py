"""Open Chrome, let you log into otomoto.pl, and save the session cookies.

Usage:
    pip install selenium
    python scripts/extract_otomoto_cookies.py            # writes scrapers/otomoto_cookies.json
    python scripts/extract_otomoto_cookies.py --wait 300   # no Enter needed: waits for the login
    python scripts/extract_otomoto_cookies.py --gh-secret  # also updates the OTOMOTO_COOKIES secret

A dedicated Chrome profile (~/.otomoto_chrome_profile) is reused between runs,
so after the first login you are usually still signed in and only need to
press Enter.

The output is a Cookie-Editor style JSON array, which load_cookies() in
scrapers/base_scraper.py already understands. The file is git-ignored.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(ROOT, "scrapers", "otomoto_cookies.json")
PROFILE_DIR = os.path.expanduser("~/.otomoto_chrome_profile")
URL = "https://www.otomoto.pl/"

# Cookies the scraper needs for VIN decryption (see refresh_session in base_scraper.py)
KEY_COOKIES = ("id_token", "refresh_token", "client_id")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT_FILE)
    ap.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                    help="don't wait for Enter: poll until the login cookies appear "
                         "(up to SECONDS), for runs without a terminal")
    ap.add_argument("--gh-secret", action="store_true",
                    help="also run `gh secret set OTOMOTO_COOKIES` with the result")
    args = ap.parse_args()

    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--window-size=1280,900")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(URL)
        if args.wait:
            print(f"Log into otomoto.pl in the opened Chrome window (waiting up to {args.wait}s)...")
            deadline = time.time() + args.wait
            while time.time() < deadline:
                names = {c["name"] for c in driver.get_cookies()}
                if all(k in names for k in KEY_COOKIES):
                    break
                time.sleep(2)
        else:
            input("Log into otomoto.pl in the opened Chrome window (accept cookies, "
                  "sign in), then press Enter here... ")
        # Reload so cookies set by JS after login are present
        driver.get(URL)
        time.sleep(3)
        cookies = driver.get_cookies()
    finally:
        driver.quit()

    cookies = [c for c in cookies if "otomoto" in c.get("domain", "")]
    names = {c["name"] for c in cookies}
    missing = [n for n in KEY_COOKIES if n not in names]
    if not cookies:
        sys.exit("No otomoto cookies found - were you logged in?")
    if missing:
        print(f"WARNING: missing cookies {missing}; VINs may not decrypt. "
              "Make sure you are logged in.")

    if os.path.exists(args.out):
        shutil.copy2(args.out, args.out + ".bak")
    payload = json.dumps(
        [{"name": c["name"], "value": c["value"], "domain": c.get("domain"),
          "path": c.get("path"), "expirationDate": c.get("expiry")}
         for c in cookies],
        indent=2,
    )
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(payload)
    print(f"Saved {len(cookies)} cookies to {args.out}")

    if args.gh_secret:
        subprocess.run(["gh", "secret", "set", "OTOMOTO_COOKIES"],
                       input=payload, text=True, check=True)
        print("Updated GitHub secret OTOMOTO_COOKIES")


if __name__ == "__main__":
    main()
