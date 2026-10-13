#!/usr/bin/env bash
# =============================================================================
# SportsCar DB — Pełne scrapowanie portali (Otomoto + OLX)
# Uruchomienie w tle: nohup ./run_full_scrape.sh > /dev/null 2>&1 &
# Chroni Maca przed uśpieniem (caffeinate). Wyniki w: scraper_full.log
# =============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

LOG_FILE="$DIR/scraper_full.log"
PYTHON_BIN="$DIR/.venv/bin/python"

if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

echo "=================================================================" | tee -a "$LOG_FILE"
echo "  SPORTSCAR DB — PEŁNE SCRAPOWANIE (OTOMOTO + OLX)" | tee -a "$LOG_FILE"
echo "  Rozpoczęto: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "  Log zapisuje się w: $LOG_FILE" | tee -a "$LOG_FILE"
echo "=================================================================" | tee -a "$LOG_FILE"

START_SECONDS=$SECONDS

# 1. Otomoto - Wszystkie modele (35 scraperów)
echo "" | tee -a "$LOG_FILE"
echo ">>> [$(date '+%H:%M:%S')] 1/2: Scrapowanie Otomoto (wszystkie 35 modeli)..." | tee -a "$LOG_FILE"
caffeinate -i -s "$PYTHON_BIN" scrapers/run_all.py all 2>&1 | tee -a "$LOG_FILE"

# 2. OLX - Wszystkie modele
echo "" | tee -a "$LOG_FILE"
echo ">>> [$(date '+%H:%M:%S')] 2/2: Scrapowanie OLX..." | tee -a "$LOG_FILE"
caffeinate -i -s "$PYTHON_BIN" scrapers/run_olx.py all 2>&1 | tee -a "$LOG_FILE"

ELAPSED_TOTAL=$(( SECONDS - START_SECONDS ))
MINUTES=$(( ELAPSED_TOTAL / 60 ))
SECS=$(( ELAPSED_TOTAL % 60 ))

echo "" | tee -a "$LOG_FILE"
echo "=================================================================" | tee -a "$LOG_FILE"
echo "  ✓ SCRAPOWANIE ZAKOŃCZONE POMYŚLNIE!" | tee -a "$LOG_FILE"
echo "  Czas trwania: ${MINUTES}m ${SECS}s" | tee -a "$LOG_FILE"
echo "  Zakończono: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "=================================================================" | tee -a "$LOG_FILE"

# Powiadomienie dźwiękowe i systemowe na Macu
if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"Wszystkie ogłoszenia zapisane w bazie! Czas: ${MINUTES}m ${SECS}s.\" with title \"SportsCar DB — Scrapowanie zakończone!\" sound name \"Glass\"" 2>/dev/null || true
fi
