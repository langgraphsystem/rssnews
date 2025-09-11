# Railway Deployment Guide

This project runs as two components on Railway without code changes:

- Worker service: long‑running background process (`python main.py work`).
- Cron job: hourly RSS polling (`python main.py poll`) on a New York schedule.

## 1) Connect GitHub repo
- Create a Railway project and connect `langgraphsystem/rssnews`.
- Enable auto‑deploys from branch `main`.

## 2) Database (PostgreSQL)
- Add the Railway PostgreSQL plugin to the project.
- Copy the connection string from the "Connect" tab (Postgres → Connect → `postgresql://...`).
- In Project → Variables add `PG_DSN` with that value. Ensure it includes `?sslmode=require`.

You can use `.env.example` as a reference for required variables.

## 3) Storage volume
The app writes queue/state files under `storage/`. Attach a Volume so state survives restarts:
- Create a Volume (1–2 GB is usually enough).
- Mount path: `/app/storage`.

## 4) Worker service
- Create service from the same repo.
- Type: Background/Worker (no HTTP port).
- Start command: `python main.py work`.
- Restart policy: on failure.
- Variables: ensure `PG_DSN` is present; optionally set `TZ=America/New_York` for consistent logs.

## 5) Cron job (poller)
- Create a Cron Job in the project.
- Command: `python main.py poll` (add flags as needed, e.g. `--batch-size 10 --workers 10`).
- Schedule (New York time): `0 7-22 * * *` (every hour at HH:00 from 07:00 to 22:00).
- Timezone: `America/New_York` (select in UI if available; otherwise set project var `TZ=America/New_York`).
- Concurrency: disable parallel runs (skip/start only if previous finished).

## 6) Observability
- Logs: Railway captures stdout/stderr. Note: the app also writes `logs/rssnews.log` — OK to ignore on Railway.
- Alerts: enable notifications for failed deploys or failed cron executions.

## 7) First‑run checklist
- Manually trigger the Cron Job once (Run now) to validate DB connectivity and polling.
- Verify the Worker service processes queued articles.
- Confirm the Volume mounted at `/app/storage` contains queue files after runs.

## 8) Useful variables
- `PG_DSN` (required): PostgreSQL DSN.
- `TZ=America/New_York`: aligns schedules/logs to New York time.
- `GEMINI_API_KEY` (optional): enables LLM features in Stage 6–8.
- `LOG_LEVEL`/`LOG_FORMAT` (optional): tune logging verbosity/format.

## Notes on timezones
The polling schedule is enforced by Railway Cron using `America/New_York`. Some internal date logic uses a fixed TZ in `config.py`; when you allow code changes, switch it to New York for full alignment.

