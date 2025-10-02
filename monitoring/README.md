# Monitoring Stack

## Components
- monitoring/metrics.py — Prometheus exporter helpers (enable via ENABLE_METRICS=true).
- monitoring/alert_rules.yml — Alertmanager rules for latency, error rate, evidence coverage, and cost caps.
- monitoring/grafana/dashboards/ — Grafana dashboards for orchestrator SLOs and model health.
- scripts/monitoring/slo_capture.py — Daily SLO snapshot collector.
- monitoring/slo_history/ — Repository for snapshot JSON files and daily notes.
- monitoring/canary_rollout_log.json — Populated by scripts/deploy/canary_logger.py during staged rollout.

## Quick Start
1. Import dashboards in Grafana (Configuration -> Dashboards -> Import).
2. Add Prometheus datasource pointing to your server.
3. Load alert rules into Prometheus (--rule.files monitoring/alert_rules.yml).
4. Run python scripts/monitoring/slo_capture.py daily and store Grafana snapshots in docs/slo_evidence/.
