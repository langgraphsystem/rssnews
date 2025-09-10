#!/usr/bin/env python3
import os
import psycopg2


def main():
    dsn = os.environ.get("PG_DSN")
    if not dsn:
        print("ERROR: PG_DSN not set")
        return 2

    cn = psycopg2.connect(dsn)
    cn.autocommit = True
    cur = cn.cursor()

    match_where = (
        "feed_url ILIKE '%feeds.washingtonpost.com%' OR "
        "COALESCE(feed_url_canon,'') ILIKE '%feeds.washingtonpost.com%'"
    )

    cur.execute(f"SELECT COUNT(*) FROM feeds WHERE {match_where}")
    pre = cur.fetchone()[0]
    print(f"Matching before: {pre}")

    cur.execute(f"DELETE FROM feeds WHERE {match_where}")
    print(f"Deleted: {cur.rowcount}")

    cur.execute(f"SELECT COUNT(*) FROM feeds WHERE {match_where}")
    post = cur.fetchone()[0]
    print(f"Remaining matching: {post}")

    cn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

