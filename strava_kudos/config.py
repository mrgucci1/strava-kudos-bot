"""Configuration loaded from environment variables (and optional .env file)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


AUTH_FILE = os.getenv("STRAVA_AUTH_FILE", "./auth.json")
DASHBOARD_URL = os.getenv("STRAVA_DASHBOARD_URL", "https://www.strava.com/dashboard")
LOGIN_URL = os.getenv("STRAVA_LOGIN_URL", "https://www.strava.com/login")
FEED_DEPTH = int(os.getenv("STRAVA_FEED_DEPTH", "50"))
MAX_SCROLLS = int(os.getenv("STRAVA_MAX_SCROLLS", "30"))
SCROLL_DELAY_MS = int(os.getenv("STRAVA_SCROLL_DELAY_MS", "2500"))
SCROLL_PATIENCE = int(os.getenv("STRAVA_SCROLL_PATIENCE", "3"))
KUDOS_DELAY_MS = int(os.getenv("STRAVA_KUDOS_DELAY_MS", "250"))
HEADLESS = _bool(os.getenv("STRAVA_HEADLESS", "true"))
KUDOS_BUTTON_SELECTOR = os.getenv(
    "STRAVA_KUDOS_BUTTON_SELECTOR", "button[data-testid='kudos_button']"
)
ACTIVITY_BASE_URL = os.getenv("STRAVA_ACTIVITY_BASE_URL", "https://www.strava.com")
