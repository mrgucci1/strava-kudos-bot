"""One-time interactive Strava login. Run on a desktop with a display.

Opens a real Chromium window pointed at Strava's login page. You sign in
manually using whatever method your account uses (email+password, magic
link, Google, Apple). When you press Enter in the terminal, the script
saves cookies + storage state to STRAVA_AUTH_FILE so kudos.py can replay
them headlessly on a schedule.
"""
import sys

from playwright.sync_api import sync_playwright

from strava_kudos import config


def main() -> int:
    print(f"Opening Strava login. Auth will be saved to: {config.AUTH_FILE}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(config.LOGIN_URL)

        print()
        print("Sign in to Strava in the browser window.")
        input("When you can see your dashboard, press Enter here: ")

        context.storage_state(path=config.AUTH_FILE)
        browser.close()

    print(f"Saved auth to {config.AUTH_FILE}. Treat this file like a password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
