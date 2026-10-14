"""Runtime settings (from .env) and real-world reference constants.

Every rupee / CO2 figure in the product is derived from the constants below, so
keep their sources accurate. Values marked VERIFY must be checked against the
cited source before the final pitch; they can be overridden from .env.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = BACKEND_DIR / "models"
MEDIA_DIR = BACKEND_DIR / "media"
UPLOADS_DIR = BACKEND_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


# --- Reference constants -----------------------------------------------------
# VERIFY: educational-institution tariff from your state DISCOM tariff order
# (e.g. BESCOM / KERC tariff order for Karnataka), energy charge + approx. fixed share.
TARIFF_INR_PER_KWH = _f("TARIFF_INR_PER_KWH", 9.0)
TARIFF_SOURCE = os.getenv("TARIFF_SOURCE", "State DISCOM tariff order (educational institutions) - VERIFY")

# VERIFY: municipal bulk water / tanker cost per kilolitre.
WATER_INR_PER_KL = _f("WATER_INR_PER_KL", 60.0)
WATER_SOURCE = os.getenv("WATER_SOURCE", "Municipal water board non-domestic rate - VERIFY")

# VERIFY: CEA CO2 Baseline Database for the Indian Power Sector (latest version).
GRID_EF_KG_PER_KWH = _f("GRID_EF_KG_PER_KWH", 0.71)
GRID_EF_SOURCE = os.getenv("GRID_EF_SOURCE", "CEA CO2 Baseline Database (weighted average) - VERIFY")

# Typical rating-plate wattages (BEE / manufacturer plates).
FIXTURE_WATTS = {
    "tube_light": 36, "led_light": 18, "fan": 70, "ac": 1500,
    "projector": 250, "pc": 80, "exhaust": 40,
}

# Indicative capex used for payback in the what-if engine (INR).
CAPEX = {
    "occupancy_sensor_per_room": 1500,
    "led_per_tube": 300,
    "leak_fix_per_washroom": 2000,
    "extra_pickup_per_day": 300,
}

# NAAC Criterion 7.1 environment-related key indicators.
# VERIFY wording/numbering against the current NAAC manual for your institution type.
NAAC_SECTIONS = [
    ("7.1.2", "Facilities for alternate sources of energy and energy conservation measures"),
    ("7.1.3", "Facilities for management of degradable and non-degradable waste"),
    ("7.1.4", "Water conservation facilities available in the institution"),
    ("7.1.5", "Green campus initiatives"),
    ("7.1.6", "Quality audits on environment and energy"),
]

# --- Runtime settings --------------------------------------------------------
NOTIFIER = os.getenv("NOTIFIER", "console").lower()
# On Render, RENDER_EXTERNAL_URL is set automatically to the public https URL
_PUBLIC = os.getenv("RENDER_EXTERNAL_URL", "")
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or _PUBLIC or "http://localhost:8000").rstrip("/")
FRONTEND_URL = (os.getenv("FRONTEND_URL") or _PUBLIC or "http://localhost:5173").rstrip("/")

STAFF_PHONES = {
    "electrician": os.getenv("STAFF_PHONE_ELECTRICIAN", ""),
    "plumber": os.getenv("STAFF_PHONE_PLUMBER", ""),
    "housekeeping": os.getenv("STAFF_PHONE_HOUSEKEEPING", ""),
    "estate_manager": os.getenv("STAFF_PHONE_ESTATE_MANAGER", ""),
}

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_TEXT_MODELS = [m for m in [os.getenv("LLM_MODEL", ""), "openai/gpt-oss-120b", "openai/gpt-oss-20b"] if m]
GROQ_VISION_MODELS = ["qwen/qwen3.8-27b"]

META = {
    "token": os.getenv("META_WA_TOKEN", ""),
    "phone_number_id": os.getenv("META_WA_PHONE_NUMBER_ID", ""),
    "app_secret": os.getenv("META_APP_SECRET", ""),
    "verify_token": os.getenv("META_WEBHOOK_VERIFY_TOKEN", ""),
    "graph_version": os.getenv("META_GRAPH_VERSION", "") or "v21.0",
}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

TWILIO = {
    "sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
    "token": os.getenv("TWILIO_AUTH_TOKEN", ""),
    "from": os.getenv("TWILIO_WHATSAPP_FROM", ""),
    # Templates made in the console Content Template Builder (works on trial accounts)
    "content_text": os.getenv("TWILIO_CONTENT_TEXT_SID", ""),
    "content_buttons": os.getenv("TWILIO_CONTENT_BUTTONS_SID", ""),
}
