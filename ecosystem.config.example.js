// PM2 cron template for strava-kudos-bot.
//
// Copy this file to `ecosystem.config.js` and adjust paths/schedule, then:
//   pm2 start ecosystem.config.js
//   pm2 save
//
// `cron_restart` fires the script on schedule; `autorestart: false` makes
// it run-once-and-exit each fire instead of looping.

module.exports = {
  apps: [{
    name: "strava-kudos",
    script: "kudos.py",
    interpreter: "./.venv/bin/python", // or "python3" if not using a venv
    cwd: __dirname,
    cron_restart: "30 9 * * *",        // 9:30 AM daily — tune to taste
    autorestart: false,
    out_file: "logs/out.log",
    error_file: "logs/err.log",
    time: true,                        // prepend timestamp to log lines
  }]
};
