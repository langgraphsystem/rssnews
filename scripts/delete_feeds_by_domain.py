#!/usr/bin/env python3
import os
import argparse
import psycopg2


def delete_for_domain(cur, domain: str) -> tuple[int, int, int]:
    pat = f"%{domain}%"
    where = "(feed_url ILIKE %s OR COALESCE(feed_url_canon,'') ILIKE %s)"

    cur.execute(f"SELECT COUNT(*) FROM feeds WHERE {where}", (pat, pat))
    pre = int(cur.fetchone()[0])

    cur.execute(f"DELETE FROM feeds WHERE {where}", (pat, pat))
    deleted = int(cur.rowcount or 0)

    cur.execute(f"SELECT COUNT(*) FROM feeds WHERE {where}", (pat, pat))
    post = int(cur.fetchone()[0])

    return pre, deleted, post


def main():
    ap = argparse.ArgumentParser("Delete feeds by domain substring (ILIKE)")
    ap.add_argument("--domain", "-d", action="append", required=True,
                    help="Domain substring to match (e.g. fortune.com). Repeatable.")
    args = ap.parse_args()

    dsn = os.environ.get("PG_DSN")
    if not dsn:
        print("ERROR: PG_DSN not set")
        return 2

    cn = psycopg2.connect(dsn)
    cn.autocommit = True
    cur = cn.cursor()

    total_pre = total_deleted = total_post = 0
    for dom in args.domain:
        pre, deleted, post = delete_for_domain(cur, dom)
        total_pre += pre
        total_deleted += deleted
        total_post += post
        print(f"Domain '{dom}': before={pre}, deleted={deleted}, remaining={post}")

    print(f"Total: before={total_pre}, deleted={total_deleted}, remaining={total_post}")

    cn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

