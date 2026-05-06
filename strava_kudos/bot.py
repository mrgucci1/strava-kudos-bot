"""Core kudos automation logic. Pure functions, no entry point."""
import sys

from playwright.sync_api import BrowserContext, Error as PlaywrightError, Page

from . import config


def _log(msg: str) -> None:
    print(f"[strava-kudos] {msg}", flush=True)


_COLLECT_FEED_URLS_JS = r"""
() => {
    const out = new Set();
    for (const a of document.querySelectorAll("a[href*='/activities/']")) {
        // Match the FULL ID — anchor with a structural boundary (/, ?, #,
        // or end of string). Without the boundary, a negative lookahead like
        // (?!\/) backtracks one digit on hrefs ending /activities/ID/segments.
        const m = a.getAttribute('href').match(/\/activities\/(\d+)(?:\/|$|[?#])/);
        if (m) out.add('/activities/' + m[1]);
    }
    return [...out];
}
"""


def open_dashboard(context: BrowserContext) -> Page:
    page = context.new_page()
    # domcontentloaded over networkidle: Strava's dashboard polls analytics
    # endpoints continuously, so networkidle reliably hits its 30s timeout.
    page.goto(config.DASHBOARD_URL, wait_until="domcontentloaded")
    return page


def _collect_feed_urls(page: Page) -> tuple[list[str], int, int]:
    """Walk the dashboard feed, collecting every visible activity URL. Stops
    when KUDOED_LIMIT already-kudo'd activities are on the page, the feed is
    exhausted, or MAX_SCROLLS is hit. Returns (urls, scrolls, kudoed_seen)."""
    seen = page.locator(config.FEED_KUDOED_SELECTOR)
    urls: list[str] = []
    seen_set: set[str] = set()
    scrolls = 0
    no_growth = 0

    for _ in range(config.MAX_SCROLLS):
        for u in page.evaluate(_COLLECT_FEED_URLS_JS):
            if u not in seen_set:
                seen_set.add(u)
                urls.append(u)

        if seen.count() >= config.KUDOED_LIMIT:
            break

        prev_count = len(urls)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(config.SCROLL_DELAY_MS)
        scrolls += 1

        for u in page.evaluate(_COLLECT_FEED_URLS_JS):
            if u not in seen_set:
                seen_set.add(u)
                urls.append(u)

        if len(urls) > prev_count:
            no_growth = 0
        else:
            no_growth += 1
            if no_growth >= config.SCROLL_PATIENCE:
                break  # feed exhausted

    return urls, scrolls, seen.count()


def _kudo_one(page: Page, url: str) -> bool | None:
    """Visit an activity's detail page and click its kudos button. Returns
    True if a kudos was given, False if already kudo'd, None on nav error."""
    # wait_until="commit": fastest event, fires once response headers arrive.
    # Strava detail pages have scripts that delay 'domcontentloaded' past 30s.
    full = config.ACTIVITY_BASE_URL + url
    try:
        page.goto(full, wait_until="commit", timeout=20000)
    except PlaywrightError as e:
        print(f"[strava-kudos] navigate failed for {url}: {e}", file=sys.stderr)
        return None

    btn = page.locator(config.DETAIL_KUDOS_SELECTOR)
    try:
        btn.wait_for(state="attached", timeout=8000)
    except PlaywrightError:
        return False  # button not on page → already kudo'd (or own activity)

    try:
        btn.click(timeout=5000)
        return True
    except PlaywrightError as e:
        print(f"[strava-kudos] click failed for {url}: {e}", file=sys.stderr)
        return None


def _new_worker(context: BrowserContext) -> Page:
    """Spawn a blank worker page to drive activity-detail navigations on,
    keeping the dashboard tab undisturbed."""
    p = context.new_page()
    p.goto("about:blank")
    return p


def give_kudos(context: BrowserContext, dashboard: Page) -> tuple[int, int, int, int]:
    """Walk the feed to collect activity URLs, then visit each detail page on a
    separate worker page to click kudos. Detail-page clicks reliably commit to
    Strava's backend; feed clicks update DOM optimistically but often don't
    persist server-side. Using a separate page sidesteps nav hangs seen when
    reusing the dashboard tab. After repeated nav failures, the worker page is
    recycled — the page can wedge into a state where every goto times out.
    Returns (given, visited, scrolls, kudoed_seen_in_feed)."""
    urls, scrolls, kudoed_seen = _collect_feed_urls(dashboard)
    _log(f"collected {len(urls)} activity URLs from feed ({scrolls} scrolls)")

    worker = _new_worker(context)
    given = 0
    visited = 0
    consecutive_nav_fails = 0
    for i, url in enumerate(urls, 1):
        result = _kudo_one(worker, url)

        if result is None:
            consecutive_nav_fails += 1
            # If the worker tab wedges, recycle it and retry once.
            if consecutive_nav_fails >= 2:
                _log(f"  recycling worker page after {consecutive_nav_fails} nav fails")
                try:
                    worker.close()
                except PlaywrightError:
                    pass
                worker = _new_worker(context)
                consecutive_nav_fails = 0
                result = _kudo_one(worker, url)
                if result is None:
                    continue
            else:
                continue
        else:
            consecutive_nav_fails = 0

        visited += 1
        if result:
            given += 1
            _log(f"  [{i}/{len(urls)}] kudo'd {url}")
        worker.wait_for_timeout(config.KUDOS_DELAY_MS)

    return given, visited, scrolls, kudoed_seen
