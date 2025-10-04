#!/usr/bin/env python3
"""
Print article processing statistics without triggering external notifications.

Outputs two sections:
- ARTICLES (index): high-level article counts from articles_index
- RAW (processing statuses): breakdown by status from raw table
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

# Ensure repository root is on sys.path so we can import root-level modules
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

load_dotenv()


async def main() -> None:
    # Lazy imports to avoid side effects on module import
    from system_stats_reporter import SystemStatsReporter

    reporter = SystemStatsReporter()
    # Collect full report but do not send to Telegram
    stats = await reporter.collect_full_report()

    print("ARTICLES (index):")
    print(json.dumps(stats.get("articles", {}), ensure_ascii=False, indent=2))

    # Also print raw table processing status breakdown
    raw_stats = reporter.db.get_stats()
    print("\nRAW (processing statuses):")
    print(json.dumps(raw_stats.get("articles", {}), ensure_ascii=False, indent=2))
    print(f"Total raw: {raw_stats.get('total_articles', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
