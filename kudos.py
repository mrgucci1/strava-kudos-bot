"""Headless scheduled run. Loads saved auth state, gives kudos, exits."""
import os
import sys
from datetime import datetime

from playwright.sync_api import sync_playwright

from strava_kudos import config
from strava_kudos.bot import give_kudos, open_dashboard


def main() -> int:
    if not os.path.exists(config.AUTH_FILE):
        print(
            f"[strava-kudos] auth file not found at {config.AUTH_FILE}. "
            "Run `python auth.py` first to sign in.",
            file=sys.stderr,
        )
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        context = browser.new_context(
            storage_state=config.AUTH_FILE,
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
        )
        page = open_dashboard(context)
        given, visited, scrolls, kudoed_seen = give_kudos(context, page)
        browser.close()

    print(
        f"[strava-kudos] gave kudos to {given} (of {visited} visited; "
        f"{scrolls} scrolls, {kudoed_seen} already-kudo'd in feed) "
        f"at {datetime.now().isoformat(timespec='seconds')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
