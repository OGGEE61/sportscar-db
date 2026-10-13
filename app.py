"""Entry point for Vercel (`app`) and local dev (`python app.py`)."""
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import get_db, init_db, make_placeholder_vin, resolve_placeholder  # noqa: F401
from webapp import create_app

# Re-exported for scripts (enrich_with_bielik.py, scripts/maintenance/*) and tests
from webapp.helpers import is_plausible_vin, is_valid_registration_plate  # noqa: F401
from webapp.regions import CITY_TO_REGION, REGION_NAME_TO_CODE, REGION_NAMES  # noqa: F401
from webapp.services.listings import _approve_listing, _enrich_location_with_nominatim  # noqa: F401

app = create_app()

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5555)
