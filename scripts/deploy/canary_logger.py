"""Canary rollout logger.

Usage:
    python scripts/deploy/canary_logger.py --stage 1 --status start --notes "Initiated stage 1"
    python scripts/deploy/canary_logger.py --stage 1 --status ok --metrics metrics.json

Creates/updates `monitoring/canary_rollout_log.json` with structured entries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Optional

LOG_PATH = Path("monitoring/canary_rollout_log.json")


def load_log() -> Dict[str, Any]:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    return {"events": []}


def persist_log(data: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_event(stage: int, status: str, notes: str, metrics_path: Optional[str]) -> Dict[str, Any]:
    log = load_log()
    event: Dict[str, Any] = {
        "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        "stage": stage,
        "status": status,
        "notes": notes,
    }
    if metrics_path:
        path = Path(metrics_path)
        event["metrics_file"] = str(path)
        if path.exists():
            event["metrics_preview"] = json.loads(path.read_text(encoding="utf-8"))
    log["events"].append(event)
    persist_log(log)
    return event


def main() -> None:
    parser = argparse.ArgumentParser("Log canary rollout decisions")
    parser.add_argument("--stage", type=int, choices=[1, 2, 3], required=True)
    parser.add_argument("--status", choices=["start", "ok", "rollback"], required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--metrics", help="Optional path to metrics JSON snapshot")
    args = parser.parse_args()

    event = append_event(args.stage, args.status, args.notes, args.metrics)
    print(json.dumps(event, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
