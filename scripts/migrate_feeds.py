#!/usr/bin/env python3
"""
Migrate only the `feeds` table from an old Postgres to the new one.

Usage:
  - Set env vars and run:
      OLD_PG_DSN=postgresql://... NEW_PG_DSN=postgresql://... python scripts/migrate_feeds.py

  - Or pass CLI args:
      python scripts/migrate_feeds.py --from "postgresql://..." --to "postgresql://..."

Notes:
  - Requires that the target DB already has schema created (run: python main.py ensure).
  - Upserts by feed_url (unique key). Only a safe subset of columns is migrated.
"""

import os
import sys
import argparse
import psycopg2
from psycopg2.extras import execute_values


SAFE_COLS = [
    # Common fields we try to preserve if present in source
    "feed_url",
    "feed_url_canon",
    "lang",
    "status",
    "last_entry_date",
    "last_crawled",
    "no_updates_days",
    "etag",
    "last_modified",
    "health_score",
    "notes",
    "checked_at",
    "category",
]


def get_cols(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'feeds'
            """
        )
        return {r[0] for r in cur.fetchall()}


def fetch_source_rows(src_conn, cols: list[str]) -> list[tuple]:
    with src_conn.cursor() as cur:
        sel = ", ".join(cols)
        cur.execute(f"SELECT {sel} FROM public.feeds ORDER BY id")
        return cur.fetchall()


def upsert_target_rows(dst_conn, cols: list[str], rows: list[tuple]) -> tuple[int, int]:
    if not rows:
        return 0, 0

    placeholders = ",".join(["%s"] * len(cols))
    col_list = ", ".join(cols)

    # Build ON CONFLICT update clause excluding key and very volatile fields
    updatable = [
        c
        for c in cols
        if c not in {"feed_url"}
    ]
    if updatable:
        update_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in updatable])
        on_conflict = f"ON CONFLICT (feed_url) DO UPDATE SET {update_clause}"
    else:
        on_conflict = "ON CONFLICT (feed_url) DO NOTHING"

    sql = f"""
        INSERT INTO public.feeds ({col_list})
        VALUES %s
        {on_conflict}
    """

    with dst_conn.cursor() as cur:
        execute_values(cur, sql, rows)
        # rowcount can be unreliable with execute_values; return (inserted_or_updated, 0)
        return cur.rowcount or 0, 0


def main():
    ap = argparse.ArgumentParser("Migrate feeds table")
    ap.add_argument("--from", dest="src", default=os.environ.get("OLD_PG_DSN"), help="Source DSN (OLD_PG_DSN)")
    ap.add_argument("--to", dest="dst", default=os.environ.get("NEW_PG_DSN") or os.environ.get("PG_DSN"), help="Target DSN (NEW_PG_DSN or PG_DSN)")
    args = ap.parse_args()

    if not args.src or not args.dst:
        print("ERROR: Provide source and target DSNs via --from/--to or env OLD_PG_DSN / NEW_PG_DSN (or PG_DSN)")
        return 2

    print("Connecting source...")
    src = psycopg2.connect(args.src)
    src.autocommit = True
    print("Connecting target...")
    dst = psycopg2.connect(args.dst)
    dst.autocommit = True

    try:
        # Discover column intersections
        src_cols = get_cols(src)
        dst_cols = get_cols(dst)
        cols = [c for c in SAFE_COLS if c in src_cols and c in dst_cols]
        if "feed_url" not in cols:
            print("ERROR: feeds table must have 'feed_url' column in both source and target.")
            return 3

        print(f"Columns to migrate: {cols}")
        rows = fetch_source_rows(src, cols)
        print(f"Fetched from source: {len(rows)} feeds")

        inserted, _ = upsert_target_rows(dst, cols, rows)
        print(f"Upserted into target: ~{inserted} rows (inserted/updated)")
        print("Done. You can now run: python main.py poll")
        return 0
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())

