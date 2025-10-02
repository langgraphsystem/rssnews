# Phase 2 Operational Readiness Plan

## 1. Performance & Load Testing
- Locust scenarios in `tests/perf/locustfile.py` (supports /trends, /analyze, /predict).
- Pytest benchmark smoke test in `tests/perf/test_smoke_benchmark.py`.
- Runbook: `tests/perf/README.md` (headless and UI modes, metrics to capture).

## 2. SLO Validation (7 Days)
- Automated Prometheus snapshot: `python scripts/monitoring/slo_capture.py`.
- Store outputs under `monitoring/slo_history/` and add daily notes.
- Grafana snapshots exported to `docs/slo_evidence/`.

## 3. Canary Rollout
- Logger tool `scripts/deploy/canary_logger.py` persists rollout decisions.
- Process documented in `docs/CANARY_ROLLOUT.md`.
- Alerts/metrics gating each stage (10%, 30%, 100%).

## 4. Monitoring Extensions
- Dashboards refreshed (`monitoring/grafana/dashboards/*.json`).
- Alert rules updated (`monitoring/alert_rules.yml`).
- Monitoring README summarises configuration steps.

## Next Steps
- Schedule Locust headless run in CI (e.g., nightly) with Prometheus scrape.
- Configure cron/automation to run daily SLO capture.
- Integrate canary logger with deployment pipeline (GitHub Actions / Argo / etc.).
- Review dashboards after first week and attach evidence to audit pack.
