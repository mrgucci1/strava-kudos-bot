"""Headless scheduled run. Loads saved auth state, gives kudos, exits."""
import os
import sys
from datetime import datetime

from playwright.sync_api import sync_playwright

from strava_kudos import config
from strava_kudos.bot import build_context, give_kudos, open_dashboard


def main() -> int:
    if not os.path.exists(config.AUTH_FILE):
        print(
            f"[strava-kudos] auth file not found at {config.AUTH_FILE}. "
            "Run `python auth.py` first to sign in.",
            file=sys.stderr,
        )
        return 1

    with sync_playwright() as p:
        browser, context = build_context(p, headless=config.HEADLESS)
        page = open_dashboard(context)
        given, tried, scrolls, buttons_seen = give_kudos(context, page)
        browser.close()

    print(
        f"[strava-kudos] gave kudos to {given} (of {tried} tried; "
        f"{scrolls} scrolls, {buttons_seen} kudos buttons in feed) "
        f"at {datetime.now().isoformat(timespec='seconds')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
