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

## 6) Cron job (report)
- Create a separate Cron Job for system reports.
- Command: `python main.py report --send-telegram`.
- Schedule: `0 9,15,21 * * *` (3 times daily: 09:00, 15:00, 21:00 New York time).
- Alternative: `0 */8 * * *` (every 8 hours).
- Timezone: `America/New_York`.
- Concurrency: disable parallel runs (skip if previous is still running).

## 7) Observability
- Logs: Railway captures stdout/stderr. Note: the app also writes `logs/rssnews.log` — OK to ignore on Railway.
- Alerts: enable notifications for failed deploys or failed cron executions.

## 8) First‑run checklist
- Manually trigger the Cron Job once (Run now) to validate DB connectivity and polling.
- Verify the Worker service processes queued articles.
- Confirm the Volume mounted at `/app/storage` contains queue files after runs.
- Test the report command: manually run the report cron job to validate Telegram integration.

## 9) Useful variables
- `PG_DSN` (required): PostgreSQL DSN.
- `TZ=America/New_York`: aligns schedules/logs to New York time.
- `GEMINI_API_KEY` (optional): enables LLM features in Stage 6–8.
- `LOG_LEVEL`/`LOG_FORMAT` (optional): tune logging verbosity/format.
- `PINECONE_API_KEY` / `PINECONE_INDEX` / `PINECONE_REGION` (optional): enable Pinecone for embeddings upsert in Stage 7. If set, embeddings are stored in Pinecone instead of Postgres.
- `TELEGRAM_BOT_TOKEN` (required for reports): Telegram bot token for sending reports.
- `TELEGRAM_CHAT_ID` (required for reports): Chat ID where reports will be sent (can be user ID or channel/group ID).

## Notes on timezones
The polling schedule is enforced by Railway Cron using `America/New_York`. Some internal date logic uses a fixed TZ in `config.py`; when you allow code changes, switch it to New York for full alignment.

## Embeddings dimension (gemini-embedding-001)
If you use `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`, embeddings may be 3072‑dim. The schema here initially uses `vector(768)`. To migrate:

1) Pause the `index` service cron.
2) Open Railway → Postgres → SQL and run the statements in
   `migrations/2025-09-11_resize_embedding_to_3072.sql` step by step:
   - Drop old embedding indexes
   - (Optionally) clear old vectors
   - `ALTER TABLE ... TYPE vector(3072)`
   - Create an embedding index (HNSW for pgvector ≥ 0.5.0, IVFFLAT otherwise)
3) Set variables on the `index` service:
   - `GEMINI_API_KEY`
   - `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`
4) Resume `index` cron, Run now, and verify logs show `embeddings_updated > 0`.

## Pinecone mode (optional)
If `PINECONE_API_KEY` and `PINECONE_INDEX` are set, the Stage 7 `index` command will:
- Always update FTS in Postgres
- Generate embeddings via Gemini and upsert them to Pinecone (serverless region set by `PINECONE_REGION`, default `us-east-1-aws`)
- Skip writing embeddings into Postgres vector column

Recommended Pinecone index settings for gemini-embedding-001:
- `dimension=3072`, `metric=cosine`, serverless, a concise metadata schema (avoid large texts in metadata)
