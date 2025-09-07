# SLO / SLA & Alerts

## Metrics (SLI)
- throughput: articles/min (pipeline in steady state)
- latency_p50/p95/p99: batch processing latency (seconds)
- error_rate: failed/total items (smoothed)
- duplicate_rate: duplicates/ingested
- LLM_share: processed_by_LLM/total (Stage 6)
- LLM_cost/day: estimated cost by provider usage

## SLO Targets
- p99 latency ≤ 5s per batch
- SLA availability: 99.9%
- error rate < 1% (excluding source‑side 4xx)

## Alerting
- Critical:
  - availability < 99.9% over 1h window
  - p99 latency > 5s for 3 consecutive windows
  - error_rate ≥ 2% over 15m
- Warning:
  - p95 latency > 3s
  - duplicate_rate spikes > baseline + 50%
  - LLM_share > configured LLM_MAX_SHARE
