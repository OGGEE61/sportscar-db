"""Save your otomoto.pl session cookies (for VIN decryption by the scrapers).

otomoto's bot protection (DataDome) blocks a Chrome that Selenium launches, so this
script starts a plain Chrome itself, with no automation attached, and you log in by
hand. Selenium only attaches AFTER you press Enter, to read the cookies.

Usage:
    pip install selenium
    python scripts/extract_otomoto_cookies.py              # writes scrapers/otomoto_cookies.json
    python scripts/extract_otomoto_cookies.py --gh-secret  # also updates the OTOMOTO_COOKIES secret

A dedicated Chrome profile (~/.otomoto_chrome_profile) is reused between runs, so
after the first login you are usually still signed in and only need to press Enter.

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
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(ROOT, "scrapers", "otomoto_cookies.json")
PROFILE_DIR = os.path.expanduser("~/.otomoto_chrome_profile")
URL = "https://www.otomoto.pl/"
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]

# Cookies the scraper needs for VIN decryption (see refresh_session in base_scraper.py)
KEY_COOKIES = ("id_token", "refresh_token", "client_id")


def start_chrome(port):
    chrome = next((p for p in CHROME_PATHS if p and os.path.exists(p)), None)
    if not chrome:
        sys.exit("Chrome not found - edit CHROME_PATHS in this script.")
    proc = subprocess.Popen(
        [chrome, f"--remote-debugging-port={port}", f"--user-data-dir={PROFILE_DIR}",
         "--no-first-run", "--no-default-browser-check", URL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            return proc
        except OSError:
            time.sleep(1)
    proc.terminate()
    sys.exit("Chrome did not open its debugging port.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT_FILE)
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--gh-secret", action="store_true",
                    help="also run `gh secret set OTOMOTO_COOKIES` with the result")
    args = ap.parse_args()

    proc = start_chrome(args.port)
    try:
        input("Log into otomoto.pl in the Chrome window that just opened "
              "(accept cookies, sign in), then press Enter here... ")
        opts = Options()
        opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{args.port}")
        driver = webdriver.Chrome(options=opts)
        cookies = driver.execute_cdp_cmd("Network.getAllCookies", {}).get("cookies", [])
    finally:
        proc.terminate()

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
          "path": c.get("path"), "expirationDate": c.get("expires")}
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
