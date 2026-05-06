"""Core kudos automation logic. Pure functions, no entry point."""
import collections
import sys

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
)

from . import config


def _log(msg: str) -> None:
    print(f"[strava-kudos] {msg}", flush=True)


COLLECT_FEED_IDS_JS = r"""
() => {
    const out = new Set();
    for (const a of document.querySelectorAll("a[href*='/activities/']")) {
        // Anchor with a structural boundary so backtracking can't truncate
        // the captured ID on hrefs like /activities/123/kudoers.
        const m = a.getAttribute('href').match(/\/activities\/(\d+)(?:\/|$|[?#])/);
        if (m) out.add(m[1]);
    }
    return [...out];
}
"""

# Realistic viewport + UA: Strava serves a degraded feed (much less content
# per scroll) to default headless Chromium otherwise.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
_VIEWPORT = {"width": 1920, "height": 1080}


def build_context(
    playwright: Playwright, headless: bool
) -> tuple[Browser, BrowserContext]:
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(
        storage_state=config.AUTH_FILE,
        viewport=_VIEWPORT,
        user_agent=_USER_AGENT,
    )
    return browser, context


def open_dashboard(context: BrowserContext) -> Page:
    page = context.new_page()
    # domcontentloaded over networkidle: Strava's dashboard polls analytics
    # endpoints continuously, so networkidle reliably hits its 30s timeout.
    page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")
    return page


def get_csrf_token(page: Page) -> str | None:
    return page.evaluate(
        "document.querySelector('meta[name=\"csrf-token\"]')?.content"
    )


def _merge_visible_ids(page: Page, ids: list[str], seen: set[str]) -> None:
    for x in page.evaluate(COLLECT_FEED_IDS_JS):
        if x not in seen:
            seen.add(x)
            ids.append(x)


def _collect_feed_ids(page: Page) -> tuple[list[str], int, int]:
    """Walk the dashboard feed, collecting every visible activity ID. Stops
    when FEED_DEPTH kudos buttons are on the page (≈ that many activity cards
    visible), the feed is exhausted, or MAX_SCROLLS is hit. Returns
    (ids, scrolls, buttons_seen)."""
    buttons = page.locator(config.KUDOS_BUTTON_SELECTOR)
    ids: list[str] = []
    seen: set[str] = set()
    scrolls = 0
    no_growth = 0

    _merge_visible_ids(page, ids, seen)

    for _ in range(config.MAX_SCROLLS):
        if buttons.count() >= config.FEED_DEPTH:
            break

        prev_count = len(ids)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(config.SCROLL_DELAY_MS)
        scrolls += 1

        _merge_visible_ids(page, ids, seen)

        if len(ids) > prev_count:
            no_growth = 0
        else:
            no_growth += 1
            if no_growth >= config.SCROLL_PATIENCE:
                break

    return ids, scrolls, buttons.count()


def give_kudos(context: BrowserContext, dashboard: Page) -> tuple[int, int, int, int]:
    """Walk the feed for activity IDs, then fire direct kudos POSTs to Strava's
    internal endpoint via `context.request` — same session cookies the browser
    uses, plus the CSRF token from the dashboard's <meta name='csrf-token'>.
    No detail-page navigation, no DOM clicks. Returns
    (given, tried, scrolls, buttons_seen)."""
    ids, scrolls, buttons_seen = _collect_feed_ids(dashboard)
    _log(
        f"collected {len(ids)} activity ids from feed "
        f"({scrolls} scrolls, {buttons_seen} kudos buttons in feed)"
    )

    csrf = get_csrf_token(dashboard)
    if not csrf:
        print(
            "[strava-kudos] CSRF token not found in dashboard meta — aborting",
            file=sys.stderr,
        )
        return 0, len(ids), scrolls, buttons_seen

    base_headers = {
        "x-csrf-token": csrf,
        "x-requested-with": "XMLHttpRequest",
        "accept": "application/json, text/plain, */*",
    }
    given = 0
    status_counts: collections.Counter[int] = collections.Counter()
    request = context.request
    last = len(ids) - 1
    for i, activity_id in enumerate(ids):
        endpoint = f"{config.ACTIVITY_BASE_URL}/feed/activity/{activity_id}/kudo"
        try:
            resp = request.post(
                endpoint,
                headers={
                    **base_headers,
                    "referer": f"{config.ACTIVITY_BASE_URL}/activities/{activity_id}",
                },
                timeout=10000,
            )
        except PlaywrightError as e:
            print(
                f"[strava-kudos] kudos request failed for {activity_id}: {e}",
                file=sys.stderr,
            )
            continue

        if resp.ok:
            given += 1
            _log(f"  [{i + 1}/{len(ids)}] kudo'd /activities/{activity_id}")
        else:
            status_counts[resp.status] += 1

        if i < last:
            dashboard.wait_for_timeout(config.KUDOS_DELAY_MS)

    if status_counts:
        parts = ", ".join(f"{n}x{s}" for s, n in sorted(status_counts.items()))
        _log(f"non-2xx responses: {parts} (own activity / already kudo'd / etc.)")

    return given, len(ids), scrolls, buttons_seen
