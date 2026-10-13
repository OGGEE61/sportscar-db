"""Moduł integracji z CEPiK (HistoriaPojazdu.gov.pl).

Pobiera oficjalne dane państwowe z rejestru CEPiK dla pojazdów posiadających
komplet danych (VIN + Tablica Rejestracyjna + Data 1. rejestracji):
- Ważność polisy OC i okresowego badania technicznego (SKP),
- Liczbę właścicieli w Polsce,
- Pełną historię odczytów licznika z badań technicznych i kontroli drogowych Policji,
- Automatyczne wykrywanie cofniętych liczników (rollback detection).
"""

import os
import re
import sys
import time
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

import requests
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cepik_fetcher")


class CepikClient:
    """Klient API HistoriaPojazdu (moj.gov.pl)."""

    INIT_URL = "https://moj.gov.pl/uslugi/engine/ng/index?xFormsAppName=HistoriaPojazdu&xFormsOrigin=EXTERNAL"
    API_BASE = "https://moj.gov.pl/nforms/api/HistoriaPojazdu/1.1.0"

    def __init__(self):
        self.session = requests.Session()
        self.wid = f"HistoriaPojazdu:{int(time.time() * 1000)}"
        self._initialized = False

    def init_session(self) -> bool:
        """Inicjalizuje sesję z portalem rządowym i pobiera tokeny XSRF oraz sesyjne."""
        self.session = requests.Session()
        self.wid = f"HistoriaPojazdu:{int(time.time() * 1000)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": self.INIT_URL,
            "Origin": "https://moj.gov.pl",
        }
        try:
            resp = self.session.post(self.INIT_URL, data={"NF_WID": self.wid}, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Inicjalizacja moj.gov.pl zwróciła status {resp.status_code}")
                return False

            xsrf = self.session.cookies.get("XSRF-TOKEN")
            self.headers = {
                "User-Agent": headers["User-Agent"],
                "Referer": self.INIT_URL,
                "Origin": "https://moj.gov.pl",
                "NF_WID": self.wid,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if xsrf:
                self.headers["X-XSRF-TOKEN"] = xsrf

            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Błąd inicjalizacji sesji CEPiK: {e}")
            return False

    @staticmethod
    def normalize_date(date_str: str) -> Optional[str]:
        """Normalizuje datę do formatu YYYY-MM-DD wymaganego przez API."""
        if not date_str:
            return None
        date_str = date_str.strip()
        # Format DD.MM.YYYY lub DD/MM/YYYY
        m1 = re.match(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})$", date_str)
        if m1:
            d, m, y = m1.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"
        # Format YYYY-MM-DD
        m2 = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", date_str)
        if m2:
            y, m, d = m2.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"
        # Format YYYY-MM (uzupełnij do 1. dnia)
        m3 = re.match(r"^(\d{4})-(\d{1,2})$", date_str)
        if m3:
            y, m, d = m3.group(1), m3.group(2), "01"
            return f"{y}-{int(m):02d}-{int(d):02d}"
        return None

    def fetch_vehicle_data(self, vin: str, plate: str, first_reg_date: str) -> Optional[Dict[str, Any]]:
        """Pobiera dane techniczne i osi czasu dla danego pojazdu."""
        if not self._initialized:
            if not self.init_session():
                return None

        norm_date = self.normalize_date(first_reg_date)
        if not norm_date:
            logger.warning(f"Niepoprawny format daty pierwszej rejestracji: '{first_reg_date}' dla VIN: {vin}")
            return None

        norm_plate = re.sub(r"[^A-Za-z0-9]", "", plate).upper()
        norm_vin = vin.strip().upper()

        payload = {
            "registrationNumber": norm_plate,
            "VINNumber": norm_vin,
            "firstRegistrationDate": norm_date,
        }

        for attempt in range(2):
            try:
                # 1. Pobierz dane techniczne i podstawowe
                v_url = f"{self.API_BASE}/data/vehicle-data"
                v_resp = self.session.post(v_url, json=payload, headers=self.headers, timeout=20)

                # Jeśli wygasła sesja lub przekroczono limit zapytań
                if v_resp.status_code in (401, 403, 406) or "HTTP_HEADER_REQUIRED" in v_resp.text:
                    self.init_session()
                    v_resp = self.session.post(v_url, json=payload, headers=self.headers, timeout=20)
                elif v_resp.status_code == 429 or "Exceeded requests/sec limit" in v_resp.text:
                    logger.warning("Limit zapytań CEPiK przekroczony — oczekiwanie 3.5s...")
                    time.sleep(3.5)
                    self.init_session()
                    v_resp = self.session.post(v_url, json=payload, headers=self.headers, timeout=20)

                if v_resp.status_code != 200:
                    logger.warning(f"Błąd vehicle-data ({v_resp.status_code}) dla {norm_plate}/{norm_vin}: {v_resp.text[:160]}")
                    return None

                try:
                    v_json = v_resp.json()
                except Exception:
                    if attempt == 0:
                        self.init_session()
                        time.sleep(1.0)
                        continue
                    return None

                basic_data = v_json.get("technicalData", {}).get("basicData", {})

                # 2. Pobierz oś czasu i historię przebiegów
                time.sleep(0.5)
                t_url = f"{self.API_BASE}/data/timeline-data"
                t_resp = self.session.post(t_url, json=payload, headers=self.headers, timeout=20)
                try:
                    t_json = t_resp.json() if t_resp.status_code == 200 else {}
                except Exception:
                    t_json = {}
                timeline_data = t_json.get("timelineData", {})

                return self._parse_cepik_response(norm_vin, norm_plate, norm_date, basic_data, timeline_data)

            except Exception as e:
                if attempt == 0:
                    self.init_session()
                    time.sleep(1.0)
                    continue
                logger.error(f"Wyjątek podczas odpytywania CEPiK dla {vin}: {e}")
                return None
        return None

    def _parse_cepik_response(
        self, vin: str, plate: str, first_reg_date: str, basic: Dict[str, Any], timeline: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parsuje i strukturyzuje dane z obu endpointów CEPiK."""
        # Polisa OC
        has_oc = basic.get("hasCurrentOCPolicy", timeline.get("validOcInsurance", False))
        oc_expiry = timeline.get("insuranceExpiryDate")

        # Badanie techniczne
        tech_status = basic.get("technicalInspectionStatus", timeline.get("technicalInspectionStatus", "brak"))

        # Kradzież
        is_stolen = 1 if (basic.get("vehicleLost") or timeline.get("vehicleLost")) else 0

        # Właściciele
        total_owners = timeline.get("totalOwners") or 1

        # Odczyty drogomierza z historii zdarzeń
        odometer_history = []
        raw_events = timeline.get("events", [])
        clean_events = []

        last_tech_until = None

        for ev in raw_events:
            ev_date = ev.get("eventDate")
            ev_name = ev.get("eventName") or ""
            details = ev.get("eventDetails", [])

            # Sprawdź datę ważności badania technicznego jeśli obecna w tytule
            if "ważne do" in ev_name.lower():
                m_valid = re.search(r"ważne do\s+(\d{2}\.\d{2}\.\d{4})", ev_name, re.IGNORECASE)
                if m_valid:
                    last_tech_until = self.normalize_date(m_valid.group(1))

            # Szukaj odczytu drogomierza w szczegółach
            odo_km = None
            odo_src = "SKP" if "badanie techniczne" in ev_name.lower() else "Inne"

            for d in details:
                d_name = d.get("name", "")
                d_val = str(d.get("value", ""))
                if "policja" in d_val.lower():
                    odo_src = "Policja"
                if "drogomierza" in d_name.lower() or "drogomierza" in d_val.lower():
                    m_km = re.search(r"(\d[\d\s]*)\s*km", d_val)
                    if m_km:
                        try:
                            odo_km = int(re.sub(r"\s+", "", m_km.group(1)))
                        except ValueError:
                            pass

            if odo_km and odo_km > 0:
                odometer_history.append({
                    "date": ev_date,
                    "km": odo_km,
                    "source": odo_src,
                    "event": ev_name
                })

            clean_events.append({
                "date": ev_date,
                "name": ev_name,
                "type": ev.get("eventType"),
                "details": details
            })

        # Posortuj historię przebiegów chronologicznie
        odometer_history.sort(key=lambda x: x["date"] or "")

        last_odometer_km = None
        last_odometer_date = None
        if odometer_history:
            latest = odometer_history[-1]
            last_odometer_km = latest["km"]
            last_odometer_date = latest["date"]
        elif timeline.get("odometerReadings"):
            first_reading = timeline["odometerReadings"][0]
            last_odometer_km = first_reading.get("value")

        return {
            "vin": vin,
            "registration_plate": plate,
            "first_registration_date": first_reg_date,
            "make": basic.get("make"),
            "model": basic.get("model"),
            "type": basic.get("type"),
            "subtype": basic.get("subtype"),
            "registration_status": basic.get("registrationStatus", "Zarejestrowany"),
            "tech_inspection_status": str(tech_status).capitalize(),
            "tech_inspection_until": last_tech_until,
            "has_current_oc": 1 if has_oc else 0,
            "insurance_expiry_date": oc_expiry,
            "is_stolen": is_stolen,
            "total_owners": total_owners,
            "last_odometer_km": last_odometer_km,
            "last_odometer_date": last_odometer_date,
            "odometer_history_json": json.dumps(odometer_history, ensure_ascii=False),
            "events_json": json.dumps(clean_events, ensure_ascii=False),
        }


def save_cepik_report(report: Dict[str, Any], conn) -> bool:
    """Zapisuje raport CEPiK do bazy oraz sprawdza ewentualny rollback licznika."""
    vin = report["vin"]

    # Porównaj z przebiegiem z ogłoszeń w bazie (wykrywanie kręconego licznika)
    listing_obs = conn.execute("""
        SELECT MIN(mileage_km) as min_mileage, MAX(mileage_km) as max_mileage
        FROM listing_observations
        WHERE vin = ? AND mileage_km > 0
    """, (vin,)).fetchone()

    listing_mileage = None
    if listing_obs:
        try:
            listing_mileage = listing_obs["max_mileage"]
        except (TypeError, IndexError):
            listing_mileage = listing_obs[1] if len(listing_obs) > 1 else None

    if not listing_mileage:
        pending_obs = conn.execute("SELECT mileage_km FROM pending_listings WHERE vin = ? AND mileage_km > 0 LIMIT 1", (vin,)).fetchone()
        if pending_obs:
            try:
                listing_mileage = pending_obs["mileage_km"]
            except (TypeError, IndexError):
                listing_mileage = pending_obs[0] if len(pending_obs) > 0 else None

    odometer_rollback = 0
    rollback_diff_km = 0
    last_cepik_km = report.get("last_odometer_km")

    if last_cepik_km and listing_mileage:
        # Jeśli na przeglądzie SKP było WIĘCEJ niż sprzedawca podaje w ogłoszeniu (z tolerancją 1500 km)
        if last_cepik_km - listing_mileage > 1500:
            odometer_rollback = 1
            rollback_diff_km = last_cepik_km - listing_mileage
            print(f"  🚨 WYKRYTO COFNIĘTY LICZNIK dla {vin}!")
            print(f"     Ostatni odczyt SKP: {last_cepik_km:,} km vs Ogłoszenie: {listing_mileage:,} km (różnica: -{rollback_diff_km:,} km)")

            # Wstaw tag ostrzegawczy do tabeli tags
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO tags (vin, tag, source_method)
                    VALUES (?, ?, 'cepik')
                """, (vin, f"Cofnięty licznik (SKP: {last_cepik_km} km / Ad: {listing_mileage} km)"))
            except Exception:
                pass

    conn.execute("""
        INSERT OR REPLACE INTO cepik_reports (
            vin, registration_plate, first_registration_date,
            make, model, type, subtype, registration_status,
            tech_inspection_status, tech_inspection_until,
            has_current_oc, insurance_expiry_date,
            is_stolen, total_owners,
            last_odometer_km, last_odometer_date,
            odometer_history_json, events_json,
            odometer_rollback, rollback_diff_km, fetched_at
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, datetime('now')
        )
    """, (
        report["vin"], report["registration_plate"], report["first_registration_date"],
        report["make"], report["model"], report["type"], report["subtype"], report["registration_status"],
        report["tech_inspection_status"], report["tech_inspection_until"],
        report["has_current_oc"], report["insurance_expiry_date"],
        report["is_stolen"], report["total_owners"],
        report["last_odometer_km"], report["last_odometer_date"],
        report["odometer_history_json"], report["events_json"],
        odometer_rollback, rollback_diff_km
    ))

    # Opcjonalnie dodaj tag o ważnym OC i SKP jeśli bez uwag
    if report["has_current_oc"] and report["tech_inspection_status"].lower() == "aktualne" and not odometer_rollback and not report["is_stolen"]:
        try:
            conn.execute("INSERT OR IGNORE INTO tags (vin, tag, source_method) VALUES (?, 'CEPiK: Ważne OC i SKP', 'cepik')", (vin,))
        except Exception:
            pass

    conn.commit()
    return True


def run_cepik_sync(limit: int = 50, single_vin: Optional[str] = None, retry_failed: bool = False):
    """Główna funkcja synchronizacji raportów CEPiK."""
    conn = db.get_db()
    client = CepikClient()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cepik_sync_log (
            vin TEXT PRIMARY KEY,
            status TEXT,
            message TEXT,
            attempted_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    if single_vin:
        rows = conn.execute("""
            SELECT vin, registration_plate, first_registration_date, make, model
            FROM pending_listings
            WHERE vin = ? AND registration_plate IS NOT NULL AND first_registration_date IS NOT NULL
            LIMIT 1
        """, (single_vin,)).fetchall()
        if not rows:
            rows = conn.execute("""
                SELECT v.vin, v.registration_plate, p.first_registration_date, v.make, v.model
                FROM vehicles v
                LEFT JOIN pending_listings p ON p.vin = v.vin
                WHERE v.vin = ? AND v.registration_plate IS NOT NULL AND p.first_registration_date IS NOT NULL
                LIMIT 1
            """, (single_vin,)).fetchall()
    else:
        log_filter = "" if retry_failed else "AND (l.vin IS NULL OR l.status != 'not_found')"
        # Pobierz auta, które mają komplet danych i nie były jeszcze sprawdzone
        rows = conn.execute(f"""
            SELECT DISTINCT 
                v.vin, 
                v.registration_plate, 
                COALESCE(v.first_registration_date, p.first_registration_date) as first_registration_date, 
                v.make, 
                v.model
            FROM vehicles v
            LEFT JOIN pending_listings p ON p.vin = v.vin
            LEFT JOIN cepik_reports c ON c.vin = v.vin
            LEFT JOIN cepik_sync_log l ON l.vin = v.vin
            WHERE v.vin IS NOT NULL
              AND v.vin != ''
              AND v.vin NOT LIKE 'PLH%'
              AND v.registration_plate IS NOT NULL
              AND v.registration_plate != ''
              AND COALESCE(v.first_registration_date, p.first_registration_date) IS NOT NULL
              AND COALESCE(v.first_registration_date, p.first_registration_date) != ''
              AND c.vin IS NULL
              {log_filter}
            ORDER BY v.vin
            LIMIT ?
        """, (limit,)).fetchall()

        # Jeśli brak w vehicles, sprawdź dodatkowo pending_listings
        if not rows:
            rows = conn.execute(f"""
                SELECT DISTINCT p.vin, p.registration_plate, p.first_registration_date, p.make, p.model
                FROM pending_listings p
                LEFT JOIN cepik_reports c ON c.vin = p.vin
                LEFT JOIN cepik_sync_log l ON l.vin = p.vin
                WHERE p.vin IS NOT NULL
                  AND p.vin != ''
                  AND p.vin NOT LIKE 'PLH%'
                  AND p.registration_plate IS NOT NULL
                  AND p.registration_plate != ''
                  AND p.first_registration_date IS NOT NULL
                  AND p.first_registration_date != ''
                  AND c.vin IS NULL
                  {log_filter}
                ORDER BY p.id DESC
                LIMIT ?
            """, (limit,)).fetchall()

    print(f"\n=== CEPiK Sync: Znaleziono {len(rows)} aut do weryfikacji w rejestrze państwowym ===")

    success_count = 0
    for idx, r in enumerate(rows, 1):
        vin = r["vin"]
        plate = r["registration_plate"]
        date_str = r["first_registration_date"]
        make = r["make"] or "Samochód"
        model = r["model"] or ""

        print(f"\n[{idx}/{len(rows)}] Sprawdzam: {make} {model} | Tablica: {plate} | Data: {date_str} (VIN: {vin})")

        data = client.fetch_vehicle_data(vin, plate, date_str)
        if data:
            save_cepik_report(data, conn)
            try:
                conn.execute("INSERT OR REPLACE INTO cepik_sync_log (vin, status, message, attempted_at) VALUES (?, 'success', 'OK', datetime('now'))", (vin,))
                conn.commit()
            except Exception:
                pass
            success_count += 1
            oc_txt = "✓ Aktualna" if data["has_current_oc"] else "✗ Brak"
            skp_txt = data["tech_inspection_status"]
            odo_txt = f"{data['last_odometer_km']:,} km" if data['last_odometer_km'] else "Brak danych"
            print(f"  ✓ Zapisano dane CEPiK! OC: {oc_txt} | Badanie SKP: {skp_txt} | Ostatni licznik: {odo_txt} | Właściciele: {data['total_owners']}")
        else:
            try:
                conn.execute("INSERT OR REPLACE INTO cepik_sync_log (vin, status, message, attempted_at) VALUES (?, 'not_found', 'Pojazd nie odnaleziony w CEPiK', datetime('now'))", (vin,))
                conn.commit()
            except Exception:
                pass
            print("  ⚠️ Nie udało się pobrać raportu z CEPiK (sprawdź poprawność tablicy lub daty rejestracji).")

        time.sleep(2.0)

    print(f"\n=== Zakończono synchronizację CEPiK! Pomyślnie zapisano: {success_count}/{len(rows)} raportów. ===")
    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Synchronizacja danych pojazdów z państwowym rejestrem CEPiK")
    parser.add_argument("--limit", type=int, default=50, help="Liczba pojazdów do sprawdzenia")
    parser.add_argument("--vin", type=str, default=None, help="Sprawdź pojedynczy numer VIN")
    parser.add_argument("--retry-failed", action="store_true", help="Ponów próbę dla wcześniej nieodnalezionych w CEPiK")
    args = parser.parse_args()

    run_cepik_sync(limit=args.limit, single_vin=args.vin, retry_failed=args.retry_failed)
