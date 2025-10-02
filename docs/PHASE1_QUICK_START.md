# Phase 1 Quick Start Guide

## 🚀 Quick Usage

### 1. Execute Trends Command

```python
import asyncio
from services.orchestrator import execute_trends

async def main():
    result = await execute_trends(
        window="24h",      # Time window
        lang="auto",       # Language filter
        k_final=5          # Number of docs
    )

    print(result["text"])  # Formatted Telegram message

asyncio.run(main())
```

### 2. Execute Analyze Commands

```python
from services.orchestrator import execute_analyze

# Keywords analysis
result = await execute_analyze(
    mode="keywords",
    query="artificial intelligence regulation",
    window="24h"
)

# Sentiment analysis
result = await execute_analyze(
    mode="sentiment",
    query="economic recovery",
    window="1w"
)

# Topics analysis
result = await execute_analyze(
    mode="topics",
    query=None,  # All recent articles
    window="3d"
)
```

---

## 📦 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram Bot Handler                      │
│  /trends [window] | /analyze <mode> [query]                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               services/orchestrator.py                       │
│        (Integration Service - Async Interface)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│           core/orchestrator/orchestrator.py                  │
│              (Phase 1 Main Coordinator)                      │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                  │
        ▼                                  ▼
┌──────────────┐                 ┌──────────────────┐
│ /trends      │                 │ /analyze         │
│              │                 │  keywords        │
│ topic_modeler│                 │  sentiment       │
│      +       │                 │  topics          │
│ sentiment    │                 │                  │
└──────┬───────┘                 └────────┬─────────┘
       │                                  │
       └──────────────┬───────────────────┘
                      │
     ┌────────────────┴─────────────────┐
     │   Pipeline (4 nodes)             │
     │                                  │
     │  1. retrieval_node               │
     │     ↓                            │
     │  2. agents_node (parallel)       │
     │     ↓                            │
     │  3. format_node                  │
     │     ↓                            │
     │  4. validate_node (Policy)       │
     └────────────────┬─────────────────┘
                      │
                      ▼
          ┌───────────────────────┐
          │  BaseAnalysisResponse │
          │  (Pydantic validated) │
          └───────────┬───────────┘
                      │
                      ▼
          ┌───────────────────────┐
          │  core/ux/formatter.py │
          │  (Telegram formatting)│
          └───────────┬───────────┘
                      │
                      ▼
              ┌───────────────┐
              │  Telegram     │
              │  Message      │
              │  + Buttons    │
              └───────────────┘
```

---

## 🔧 Key Components

### 1. Retrieval Pipeline (RRF)

```
ranking_api.retrieve_for_analysis()
    │
    ├─> Pre-filter (date/lang/sources)
    │
    ├─> Parallel execution:
    │   ├─> FTS search (BM25-like)
    │   └─> Semantic search (pgvector)
    │
    ├─> RRF Fusion (k=60)
    │   score(d) = Σ 1/(k + rank_i(d))
    │
    ├─> Top-30 candidates
    │
    ├─> [Optional] Reranking (Cohere v3)
    │
    ├─> Deduplication
    │
    └─> Return k_final (5-10 docs)
```

### 2. Agent Execution (Parallel)

```
agents_node
    │
    ├─> Determine agents based on command
    │   • /trends → [topic_modeler, sentiment_emotion]
    │   • /analyze keywords → [keyphrase_mining, query_expansion?]
    │   • /analyze sentiment → [sentiment_emotion]
    │   • /analyze topics → [topic_modeler]
    │
    ├─> Run agents in parallel (asyncio.gather)
    │   │
    │   ├─> Each agent:
    │   │   ├─> Build context from docs
    │   │   ├─> Call Model Manager
    │   │   │   ├─> Try primary model (timeout 8-15s)
    │   │   │   ├─> On failure: try fallback
    │   │   │   └─> Track budget/telemetry
    │   │   └─> Parse JSON output
    │   │
    │   └─> Collect all results
    │
    └─> Return agent_results dict
```

### 3. Model Routing

```
Model Manager
    │
    ├─> Task: "keyphrase_mining"
    │   ├─> Primary: gemini-2.5-pro (timeout 10s)
    │   └─> Fallback: claude-4.5 → gpt-5
    │
    ├─> Task: "sentiment_emotion"
    │   ├─> Primary: gpt-5 (timeout 12s)
    │   └─> Fallback: claude-4.5
    │
    ├─> Task: "topic_modeler"
    │   ├─> Primary: claude-4.5 (timeout 15s)
    │   └─> Fallback: gpt-5 → gemini-2.5-pro
    │
    └─> Budget checks:
        ├─> Per-command: 8000 tokens, $0.50
        └─> Per-user (daily): 100 commands, $5.00
```

### 4. Validation (Policy Layer v1)

```
validate_node
    │
    ├─> Length checks:
    │   ├─> header ≤ 100
    │   ├─> tldr ≤ 220
    │   ├─> insight.text ≤ 180
    │   └─> snippet ≤ 240
    │
    ├─> Evidence-required:
    │   └─> Every insight MUST have ≥1 evidence_ref
    │
    ├─> PII detection:
    │   ├─> Block: SSN, credit cards, emails, phones
    │   └─> Patterns: regex-based
    │
    ├─> Domain safety:
    │   └─> Reject blacklisted domains
    │
    ├─> Schema compliance:
    │   └─> Pydantic validation (strict)
    │
    └─> Date format:
        └─> All dates in YYYY-MM-DD
```

---

## 📊 Example Output

### Trends Command
```
📈 **Trends for 24h**

📊 **Краткий обзор:**
Identified 5 main topics. Overall sentiment: positive (+0.35).
Top trend: AI regulation gaining momentum.

💡 **Ключевые выводы:**
✅ AI regulation: 12 articles, rising trend
✅ Overall sentiment is positive (+0.35)
🤔 Emerging trend: Ethical AI frameworks
⚠️ Conflict: Diverging views on implementation timeline

📰 **Источники (5):**
1. [EU proposes comprehensive AI regulations](https://...)
   📅 2025-09-30
2. [Tech giants push back on new rules](https://...)
   📅 2025-09-29
...

🟢 Уверенность: 88% | Model: claude-4.5

[📖 Объяснить] [📰 Все источники]
[🔗 Похожие] [🔔 Следить]
```

### Keywords Analysis
```
🔑 **Keyphrase Analysis**

📊 **Краткий обзор:**
Extracted 12 key phrases from 5 articles. Top: artificial intelligence,
regulation framework, ethical guidelines.

💡 **Ключевые выводы:**
✅ Key phrase: 'artificial intelligence' (score: 0.95)
✅ Key phrase: 'regulation framework' (score: 0.89)
✅ Key phrase: 'ethical guidelines' (score: 0.82)

📰 **Источники (5):**
...

🟢 Уверенность: 85% | Model: gemini-2.5-pro
```

---

## ⚙️ Configuration Examples

### Change Model Routing

```python
from infra.config.phase1_config import get_config

config = get_config()

# Change primary model for sentiment
config.models.sentiment_emotion.primary = "claude-4.5"
config.models.sentiment_emotion.fallback = ["gpt-5"]
config.models.sentiment_emotion.timeout_seconds = 10
```

### Adjust Budgets

```python
# Per-command limits
config.budget.max_tokens_per_command = 10000
config.budget.max_cost_cents_per_command = 75  # $0.75

# Per-user daily limits
config.budget.max_commands_per_user_daily = 150
```

### Toggle Features

```python
# Enable/disable commands
config.features.enable_trends_enhanced = True
config.features.enable_analyze_keywords = True
config.features.enable_query_expansion = False  # Disable expansion

# Retrieval settings
config.retrieval.enable_rrf = True
config.retrieval.enable_rerank = True  # Enable Cohere rerank
config.retrieval.default_k_final = 7   # Increase to 7 docs
```

---

## 🧪 Testing Checklist

### Unit Tests (To Implement)

```python
# Test agents
test_keyphrase_mining_valid_output()
test_sentiment_analysis_score_range()
test_topic_modeler_min_topics()

# Test validators
test_policy_evidence_required()
test_policy_length_limits()
test_policy_pii_detection()

# Test model manager
test_fallback_on_primary_failure()
test_budget_enforcement()
test_timeout_handling()
```

### Integration Tests

```python
# Test pipeline
test_trends_pipeline_end_to_end()
test_analyze_keywords_pipeline()
test_validation_failure_handling()

# Test retrieval
test_rrf_fusion()
test_deduplication()
test_cache_hit()
```

---

## 🚨 Error Handling

All errors return structured `ErrorResponse`:

```json
{
  "error": {
    "code": "NO_DATA",
    "user_message": "No articles found for the specified criteria",
    "tech_message": "Retrieval returned 0 documents",
    "retryable": true
  },
  "meta": {
    "confidence": 0.0,
    "model": "unknown",
    "version": "phase1-v1.0",
    "correlation_id": "abc-123-uuid"
  }
}
```

**Error Codes:**
- `VALIDATION_FAILED` — Response failed policy checks
- `NO_DATA` — No articles found
- `BUDGET_EXCEEDED` — Budget limit reached
- `MODEL_UNAVAILABLE` — All models failed
- `INTERNAL` — Unexpected error

---

## 📈 Monitoring

**New in Phase 1 audit update**
- Metrics exporter starts automatically when `ENABLE_METRICS=true` (`.env.example` now includes METRICS_HOST/METRICS_PORT).
- Prometheus alert rules: import `monitoring/alert_rules.yml` to track latency, error rate, evidence coverage, and cost thresholds.
- Grafana dashboards: import JSON from `monitoring/grafana/dashboards/` (`orchestrator_dashboard.json`, `model_health.json`).
- Validate alerts in staging before go-live; ensure Alertmanager targets are reachable.

Track these metrics:

Track these metrics:

```python
# Latency
P50_latency_ms
P95_latency_ms
P99_latency_ms

# Cost
cost_per_command_cents
cost_per_user_daily_cents
token_usage_per_command

# Quality
validation_pass_rate
evidence_coverage_rate
cache_hit_rate

# Reliability
fallback_usage_rate
error_rate_by_code
model_failure_rate
```

---

## 🔗 Related Files

- **Main Report:** [PHASE1_IMPLEMENTATION_REPORT.md](PHASE1_IMPLEMENTATION_REPORT.md)
- **System Prompt:** [phase1_prompt.md](phase1_prompt.md)
- **Integration Service:** [../services/orchestrator.py](../services/orchestrator.py)
- **Config:** [../infra/config/phase1_config.py](../infra/config/phase1_config.py)

---

**Version:** phase1-v1.0
**Last Updated:** 2025-09-30
