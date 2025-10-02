# Performance & Load Testing

## Locust Scenarios

The file `tests/perf/locustfile.py` contains parallel tasks for the Phase 2 orchestrator endpoints (`/trends`, `/analyze`, `/predict`).

### Prerequisites
- `pip install -r requirements.txt` (installs `locust`).
- Orchestrator API reachable at `ORCHESTRATOR_BASE_URL` (default `http://localhost:8080`).
- Prometheus scraping `rss_orchestrator_*` metrics for throughput/latency/error tracking.

### Running Locust (interactive UI)
```bash
export ORCHESTRATOR_BASE_URL=http://localhost:8080
locust -f tests/perf/locustfile.py
```
Open http://localhost:8089 to control the swarm size (target 100–200 commands/min).

### Headless run (CI friendly)
```bash
locust -f tests/perf/locustfile.py \
  --headless --users 50 --spawn-rate 10 \
  --run-time 15m \
  --csv monitoring/perf/locust_run
```
The CSV summary can be exported to Prometheus/Grafana for historical analysis.

## Prometheus Metrics Targets
- `sum(rate(rss_orchestrator_requests_total[1m]))` — throughput >= 100–200 commands/min.
- `histogram_quantile(0.95, sum(rate(rss_orchestrator_latency_seconds_bucket[5m])) by (command, le))` — p95 latency.
- `sum(rate(rss_orchestrator_errors_total[5m])) / sum(rate(rss_orchestrator_requests_total[5m]))` — error ratio.
- `rss_orchestrator_evidence_coverage_ratio` — evidence coverage.
- `histogram_quantile(0.95, sum(rate(rss_command_cost_cents_bucket[10m])) by (command, le)) / 100` — cost/command.

## Pytest Benchmark Shortcut
Locust is the primary tool, but quick microbenchmarks can be executed with
`pytest --benchmark-only tests/perf/test_smoke_benchmark.py` (template provided)
if you need a lightweight regression guard.
