# strava-kudos-bot

A small Python bot that gives kudos to every activity in your Strava following-feed on a schedule. Drives a real headless Chromium via Playwright, replays your saved login cookies — no Strava API key, no Google sign-in, no fragile credential storage.

## What it does

Once a day (or on whatever schedule you pick), the bot:

1. Launches headless Chromium with your previously-saved Strava session.
2. Loads `strava.com/dashboard` and scrolls the feed to collect activity URLs.
3. Visits each activity's detail page and clicks "Give kudos" if present.
4. Prints a one-line summary and exits.

Why visit each detail page instead of clicking in the feed? The feed's kudos
button updates the DOM optimistically but doesn't reliably commit the kudos
to Strava's backend — many feed clicks "succeed" visually but never persist.
The detail-page button works every time, at the cost of a few extra
navigations per run.

## Why this approach

Strava's public REST API does not expose a kudos endpoint and does not expose a "following feed" endpoint to third-party apps. So driving the website itself is the only path. We use Playwright with replayed cookies, which means:

- **No password lives in code or env vars** — only a session-state JSON file.
- **Works with any Strava login method** — email+password, one-time magic-link codes, Google, Apple. You sign in manually once in a real browser; the cookies do the rest.

## How it works

```
auth.py  (run once, on a desktop)         kudos.py  (run on a schedule)
   |                                          |
   |  user signs in manually in popup         |  loads auth.json
   v                                          v
  auth.json  ────────── copy to runner ────►  Chromium (headless) → kudos
```

## Prerequisites

- Python 3.10 or newer
- A Strava account
- A machine that's online when the schedule fires (laptop, Raspberry Pi, VPS, GitHub Actions runner, etc.)

## Quick start

```bash
git clone <your-fork-url> strava-kudos-bot
cd strava-kudos-bot

python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
# Linux only — installs system libs Chromium needs:
# playwright install-deps

cp .env.example .env                       # tune later if you want

python auth.py                             # opens a browser; sign in to Strava
python kudos.py                            # smoke test — should print kudos count
```

Open Strava on your phone or in another browser to verify the kudos appear on the most recent activities.

## Scheduling

Pick whichever fits your setup.

### Option A — Linux / Raspberry Pi with PM2 (recommended for always-on hosts)

If you're already running Node bots under PM2, this drops in cleanly:

```bash
cp ecosystem.config.example.js ecosystem.config.js
# edit cron_restart and interpreter path if needed

pm2 start ecosystem.config.js
pm2 save
pm2 logs strava-kudos                      # follow output
```

Notes:
- `cron_restart` triggers the run; `autorestart: false` makes it run-once-and-exit each fire.
- Logs land in `./logs/`. The bot prints exactly one summary line per run, so logs stay tiny.
- If your Pi is ARM, Playwright's bundled Chromium works fine (Playwright supports ARM Linux).

### Option B — Linux with systemd timer

`/etc/systemd/system/strava-kudos.service`:

```ini
[Unit]
Description=Strava kudos bot

[Service]
Type=oneshot
WorkingDirectory=/home/USER/strava-kudos-bot
ExecStart=/home/USER/strava-kudos-bot/.venv/bin/python kudos.py
```

`/etc/systemd/system/strava-kudos.timer`:

```ini
[Unit]
Description=Run strava-kudos daily

[Timer]
OnCalendar=*-*-* 09:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

Then `sudo systemctl enable --now strava-kudos.timer`.

### Option C — GitHub Actions (free, runs even when your machine is off)

Stash `auth.json` as a base64 secret (`STRAVA_AUTH_B64`), then add `.github/workflows/kudos.yml`:

```yaml
name: kudos
on:
  schedule:
    - cron: "30 9 * * *"
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: playwright install --with-deps chromium
      - run: echo "$STRAVA_AUTH_B64" | base64 -d > auth.json
        env: { STRAVA_AUTH_B64: ${{ secrets.STRAVA_AUTH_B64 }} }
      - run: python kudos.py
```

To produce the secret value: `base64 -w0 auth.json` on Linux, or `[Convert]::ToBase64String([IO.File]::ReadAllBytes("auth.json"))` in PowerShell.

### Option D — Windows Task Scheduler

Create a Basic Task that runs `C:\path\to\strava-kudos-bot\.venv\Scripts\python.exe` with argument `kudos.py` and "Start in" set to the project directory. Trigger: daily at your preferred time.

## Configuration

All config is environment variables, optionally loaded from a `.env` file in the project root.

| Variable | Default | Purpose |
|---|---|---|
| `STRAVA_AUTH_FILE` | `./auth.json` | Path to the saved session-state JSON |
| `STRAVA_DASHBOARD_URL` | `https://www.strava.com/dashboard` | Page to scroll for kudos |
| `STRAVA_LOGIN_URL` | `https://www.strava.com/login` | Page `auth.py` opens |
| `STRAVA_KUDOED_LIMIT` | `50` | Stop once this many already-kudo'd activities are on the page |
| `STRAVA_MAX_SCROLLS` | `30` | Safety cap on scroll iterations |
| `STRAVA_SCROLL_DELAY_MS` | `2500` | Wait after each scroll for lazy-load |
| `STRAVA_SCROLL_PATIENCE` | `3` | Consecutive no-growth scrolls before declaring feed exhausted |
| `STRAVA_KUDOS_DELAY_MS` | `400` | Wait between kudos clicks (be polite) |
| `STRAVA_HEADLESS` | `true` | Set `false` to watch the bot run |
| `STRAVA_FEED_KUDOED_SELECTOR` | `button[data-testid='kudos_button']` | Already-kudo'd marker in the feed (drives stop signal) |
| `STRAVA_DETAIL_KUDOS_SELECTOR` | `button[data-testid='give-kudos-btn']` | The button on an activity detail page |

## Refreshing auth

Strava sessions are long-lived (typically months) but not infinite. When `kudos.py` starts logging `gave kudos to 0 activities` for several days in a row, the cookie probably expired. Fix:

1. On a desktop, run `python auth.py` again, sign in.
2. Copy the new `auth.json` to wherever the bot runs (e.g. `scp auth.json pi@host:~/strava-kudos-bot/`).
3. For GitHub Actions, base64 the new file and update the `STRAVA_AUTH_B64` secret.

## Security

`auth.json` contains your authenticated Strava session. Anyone with this file can act as you on Strava until the cookie expires. Treat it like a password:

- Never commit it to git (covered by `.gitignore`).
- Don't paste its contents into chats, issues, or pastebins.
- If you suspect it's leaked, sign out from "all sessions" in Strava settings, then re-run `auth.py`.

## Disclaimer

This bot is intended for **personal use at human-scale rates** — your own feed, once a day, with delays between clicks. Don't run multiple parallel instances. Don't use it on accounts that aren't yours. Be a respectful citizen of the platform; if Strava ever signals they don't want this kind of automation, stop.

## License

MIT. See [LICENSE](LICENSE).

## Contributing

It's a small project — selector updates, new scheduler walkthroughs, and bug fixes are all welcome. Open a PR.
