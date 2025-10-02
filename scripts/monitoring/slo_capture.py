"""Scheduled SLO snapshot collector.

Collects orchestrator metrics from Prometheus and stores JSON snapshots in
`monitoring/slo_history/`. Intended to run daily via cron or CI.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict, List

import requests

PROM_URL_DEFAULT = "http://localhost:9090"
OUTPUT_DIR_DEFAULT = Path("monitoring/slo_history")

QUERIES = {
    "p95_latency_s": "histogram_quantile(0.95, sum(rate(rss_orchestrator_latency_seconds_bucket[5m])) by (command, le))",
    "error_rate": "sum(rate(rss_orchestrator_errors_total[5m])) / clamp_min(sum(rate(rss_orchestrator_requests_total[5m])), 1)",
    "evidence_coverage": "avg(rss_orchestrator_evidence_coverage_ratio)",
    "cost_p95_cents": "histogram_quantile(0.95, sum(rate(rss_command_cost_cents_bucket[10m])) by (command, le))",
}


def prom_query(prom_url: str, expr: str) -> List[Dict[str, str]]:
    resp = requests.get(
        f"{prom_url}/api/v1/query",
        params={"query": expr},
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    return payload["data"]["result"]


def collect(prom_url: str) -> Dict[str, Dict[str, float]]:
    snapshot: Dict[str, Dict[str, float]] = {}
    for name, expr in QUERIES.items():
        results = prom_query(prom_url, expr)
        metrics: Dict[str, float] = {}
        for item in results:
            labels = item.get("metric", {})
            key = labels.get("command", "total")
            value = float(item["value"][1])
            metrics[key] = value
        snapshot[name] = metrics
    return snapshot


def write_snapshot(data: Dict[str, Dict[str, float]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")
    path = output_dir / f"slo_snapshot_{timestamp}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump({
            "timestamp": timestamp,
            "targets": {
                "p95_latency_s": 12.0,
                "error_rate": 0.02,
                "evidence_coverage": 0.95,
                "cost_p95_cents": 50.0,
            },
            "metrics": data,
        }, fh, indent=2)
    return path


def main() -> None:
    parser = argparse.ArgumentParser("Collect SLO metrics snapshot from Prometheus")
    parser.add_argument("--prom-url", default=os.getenv("PROMETHEUS_URL", PROM_URL_DEFAULT))
    parser.add_argument("--output", default=str(OUTPUT_DIR_DEFAULT))
    args = parser.parse_args()

    snapshot = collect(args.prom_url)
    path = write_snapshot(snapshot, Path(args.output))
    print(f"Snapshot written to {path}")


if __name__ == "__main__":  # pragma: no cover
    main()
