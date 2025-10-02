#!/usr/bin/env python3
"""Monitor migration progress"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient


def monitor():
    client = PgClient()

    print("=== pgvector Migration Monitor ===\n")

    # Get start state
    with client._cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL')
        total = cur.fetchone()[0]

    prev_migrated = None
    start_time = time.time()

    while True:
        with client._cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL')
            migrated = cur.fetchone()[0]

        remaining = total - migrated
        percent = 100 * migrated / total if total > 0 else 0

        # Calculate speed
        if prev_migrated is not None:
            speed = (migrated - prev_migrated) / 60  # per minute
            eta_minutes = remaining / speed if speed > 0 else 0
            eta_str = f"{int(eta_minutes // 60)}h {int(eta_minutes % 60)}m"
        else:
            speed = 0
            eta_str = "calculating..."

        elapsed = time.time() - start_time
        elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"

        print(f"[{datetime.now().strftime('%H:%M:%S')}] "
              f"Progress: {migrated:,}/{total:,} ({percent:.1f}%) | "
              f"Speed: {speed:.0f}/min | "
              f"ETA: {eta_str} | "
              f"Elapsed: {elapsed_str}")

        if migrated >= total:
            print("\n✅ Migration complete!")
            break

        prev_migrated = migrated
        time.sleep(60)


if __name__ == '__main__':
    try:
        monitor()
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
