# Canary Rollout Plan (Phase 2)

## Stages
1. **Stage 1 (10% traffic, ≥4h)**
   - Deploy orchestrator v2 to a single instance or subset via feature flag.
   - Run `python scripts/deploy/canary_logger.py --stage 1 --status start --notes "Starting 10%"`.
   - Monitor dashboards (`Orchestrator SLO`, `Model Health`) and alerts.
   - If stable, log decision:
     ```bash
     python scripts/deploy/canary_logger.py --stage 1 --status ok --notes "Latency stable, errors <2%" --metrics monitoring/slo_history/slo_snapshot_YYYYMMDD.json
     ```

2. **Stage 2 (30% traffic, ≥24h)**
   - Repeat logging commands with `--stage 2`.
   - Capture Grafana snapshots at start, midpoint, and end.
   - Roll back with `--status rollback` if latency/error breaches occur.

3. **Stage 3 (100% traffic)**
   - Promote to full traffic once stage 2 stable for ≥24h.
   - Log start/end decisions with supporting metrics.

## Alert Checklist
- Prometheus alerts (`monitoring/alert_rules.yml`):
  - `HighOrchestratorLatency`
  - `OrchestratorErrorRate`
  - `EvidenceCoverageLow`
  - `CommandCostExceeded`
  - `MissingOrchestratorMetrics`
- Ensure Alertmanager routes to on-call during each stage.

## Rollback Guidance
- Roll back immediately if any of the following happen:
  - p95 latency > 12s for 10 minutes.
  - Error rate > 2% for 5 minutes.
  - Evidence coverage < 95% for 10 minutes.
  - Command cost p95 > $0.50 for 10 minutes.
- Record the rollback via `--status rollback` including root cause notes.

## Finalisation
- After Stage 3 success, update `monitoring/canary_rollout_log.json` stage entry with `status ok` and attach final SLO snapshot.
- Mark `deployment.stage` metadata to `"complete"` in service configuration.
