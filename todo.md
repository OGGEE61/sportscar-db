[x] 1. Fix region (voivodeship) assignment for towns so the map works better (Done - 100% mapped, added CITY_TO_REGION fallback)
[x] 2. Process listing data with an LLM to add equipment items to the listing (Done - enrich_with_bielik.py + a second "AI summary" box under the description on the vehicle page and in the review queue)
[x] 3. Verify the new scrapers (Done - Mercedes Kompressor, A45/GLA45 2016-2020, Porsche Cayman S/GTS/GT4 moved to scrapers/)
[x] 4. Model analytics dropdown did not list all models in our database (Done - all 34 models added, grouped by make with optgroup)
[x] 5. Model analytics for X3 M also showed X3 M40i listings (Done - strict split of X3 M F97 [18] from X3 M40i G01 [39])
[x] 6. New clean white / light theme (Done - white navbar, soft-shadow cards, Inter typography, AI and equipment pills)
[x] 7. Computer Vision module (YOLOv8 + EasyOCR) to read license plates from photos + human-in-the-loop /plates page (Done - up to 10 photos per listing, local detection/OCR in scripts/detect_plates.py, /plates with keyboard shortcuts and automatic plate assignment)
[x] 8. Remove false "sold" marks from before the PR #4 fix: clear removed_at for listings seen again after the mark, and clear it at ingest when the same listing reappears (Done - scripts/maintenance/fix_false_sold.py with --dry-run, JSON backup and D1 confirmation; run manually on production)
[x] 9. Plate and first-registration date quality for CEPiK: validate the date at ingest (not in the future, not before 1980), "Do poprawy" tab on /cepik with plate/date editing and re-check (12/29 X3 M40i have no report, e.g. plate "BMWm40i", date "2024-01-01"). Note: plate validation lives in validation.py - change only with tests (PR #9)
[x] 10. Store model_id (id from webapp/model_catalog.py) on the vehicle at approval: ScraperConfig.model_id -> pending_listings -> vehicles, migration v13 with backfill; /models filters by model_id instead of loose conditions (e.g. Cayman 981 and 718 both match 2016) (PR #11)
[x] 11. Warn about expired otomoto cookies: scraper reports session state (ok/expired), dashboard banner when VINs are not revealed; migration v12 (PR #10)
[x] 12. Maps (dashboard, /models): only pass known voivodeship codes from REGION_NAMES (PR #12)
[x] 13. Bulk buttons on /review (e.g. reject all) ignore the OLX/Otomoto filter - respect the filter or label it clearly (PR #13)

## Operational follow-ups
[ ] 14. Refresh the OTOMOTO_COOKIES GitHub secret (CI logs "Token refresh failed: Otomoto session has expired"). Use scripts/extract_otomoto_cookies.py --gh-secret. Note: locally scrapers/otomoto_cookies.json is read before .txt, so a fresh cookie placed only in .txt is ignored
[ ] 15. After merging PRs #9-#13 on production: run `python db.py` (migrations; production D1 does not have scraper_logs.source from v11 yet), then scripts/maintenance/backfill_model_id.py --dry-run and fix_false_sold.py --dry-run (both ask for confirmation before writing to D1)
[ ] 16. Check scraper freshness after the GitHub schedule delays (some otomoto scrapers had not run since 2026-10-13). If runs stay sparse: schedule target `next_3`, or an external trigger (Cloudflare Worker cron calling workflow_dispatch). Never use target=all (job timeout is 15 min); run one target at a time. "success" alone does not prove cookies work - look for `[auth] Logged in as` / `id_token refreshed` in the log
