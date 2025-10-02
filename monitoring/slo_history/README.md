# SLO Validation Runbook (7 Days)

## Daily Checklist
1. Ensure Prometheus (`PROMETHEUS_URL`) and Grafana are running.
2. Execute `python scripts/monitoring/slo_capture.py --prom-url http://localhost:9090`.
   - Output stored in `monitoring/slo_history/slo_snapshot_<timestamp>.json`.
3. Capture Grafana snapshots for:
   - `Orchestrator SLO` dashboard (p95 latency, error rate, coverage, cost).
   - `Model Health` dashboard (model latency, costs, outcomes).
4. Review alerts (latency > 12s, error > 2%, coverage < 95%, cost > $0.50).
5. Append daily notes to `monitoring/slo_history/README.md` (template below).

## After 7 Days
- Collate snapshots into a ZIP for the "SLO evidence pack".
- Publish Grafana exports (JSON or PNG) into `docs/slo_evidence/`.
- Update `docs/PHASE1_AUDIT.md` with the compliance confirmation and link to evidence.

## README Template for Daily Notes
```
# SLO Daily Notes

## 2025-10-01
- p95 latency: 8.2s
- error rate: 0.4%
- coverage: 97%
- cost (p95): $0.21
- Alerts triggered: none
- Actions: n/a
```
