# Phase 1 — Production Action Plan

**Status:** 🟡 Core Complete, Production Blockers Remain
**Target:** Production-ready in 5-7 days
**Version:** phase1-v1.0

---

## 📋 Executive Summary

**What's Done (85%):**
- ✅ Core architecture (orchestrator, agents, retrieval, validation)
- ✅ RRF retrieval with pre-filters
- ✅ 4 production agents (keyphrase, sentiment, topics, expansion)
- ✅ Policy Layer v1 (evidence-required, PII, lengths)
- ✅ Model Manager (fallbacks, budget, telemetry)
- ✅ Telegram UX formatter
- ✅ Integration service
- ✅ Documentation

**Critical Gaps (15%):**
- 🔴 Gemini Client (placeholder) — BLOCKS `/analyze keywords`
- 🔴 Tests (0% coverage) — BLOCKS production confidence
- 🔴 Monitoring (no dashboards/alerts) — BLOCKS SLO tracking
- 🔴 Bot handlers (not wired) — BLOCKS user access

---

## 🎯 Definition of Done

Phase 1 is **production-ready** when:

### Functionality ✓
- [ ] All 4 commands work end-to-end from bot
- [ ] Gemini client implemented with timeout/retry/quota
- [ ] Fallback chains tested and working
- [ ] Degradation logic triggered on budget/timeout

### Quality ✓
- [ ] Evidence coverage ≥ 95% (measured on e2e samples)
- [ ] Schema validation 100% pass rate
- [ ] PII detection blocks all test patterns
- [ ] Date format enforced (YYYY-MM-DD)

### Performance ✓
- [ ] P95 simple ≤ 5s, enhanced ≤ 12s
- [ ] Cost/command ≤ $0.50 (7-day average)
- [ ] Fallback rate ≤ 10%
- [ ] Cache hit-rate ≥ 30% (after warmup)

### Observability ✓
- [ ] 4 Grafana dashboards live (latency, cost, quality, reliability)
- [ ] 6 Prometheus alerts configured (3 P1, 3 P2)
- [ ] Runbook written and reviewed
- [ ] Correlation IDs tracked end-to-end

### Rollout ✓
- [ ] Canary 10% passes (4h monitoring)
- [ ] Canary 30% passes (1 day monitoring)
- [ ] Full rollout 100%
- [ ] SLO maintained 7 days

---

## 📅 Timeline (5-7 Working Days)

### Day 1-2: P0 Blockers (Critical)

**Goal:** Remove production blockers

#### Task 1.1: Gemini Client Implementation
**Owner:** Backend team
**Estimate:** 4-6 hours
**Deliverable:** `core/ai_models/clients/gemini_client.py`

```python
class GeminiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        timeout: int = 10
    ) -> str:
        """
        Generate text with Gemini 2.5 Pro
        - Implement retry logic (max 2 retries)
        - Track tokens_in, tokens_out, cost
        - Log model, latency, success/failure
        - Raise timeout after 10s
        """
        pass
```

**Acceptance Criteria:**
- [ ] Client connects to Gemini API
- [ ] Timeout enforced (10s default)
- [ ] Retry logic works (1 retry on transient errors)
- [ ] Telemetry logged (tokens, cost, latency)
- [ ] Integration test passes

---

#### Task 1.2: Unit Tests
**Owner:** QA + Backend
**Estimate:** 8 hours (1 day)
**Files:**
- `tests/unit/test_schemas.py` (10 tests)
- `tests/unit/test_validators.py` (15 tests)
- `tests/unit/test_model_manager.py` (10 tests)

**Test Coverage:**

```python
# test_schemas.py
def test_valid_base_response()
def test_tldr_length_limit()          # ≤ 220
def test_insight_length_limit()       # ≤ 180
def test_snippet_length_limit()       # ≤ 240
def test_evidence_required()          # ≥ 1 per insight
def test_date_format_validation()     # YYYY-MM-DD
def test_confidence_range()           # 0.0-1.0
def test_invalid_insight_type()       # Must be fact|hypothesis|recommendation|conflict
def test_missing_required_fields()
def test_extra_fields_rejected()

# test_validators.py
def test_pii_detection_email()
def test_pii_detection_phone()
def test_pii_detection_ssn()
def test_pii_detection_credit_card()
def test_domain_whitelist_pass()
def test_domain_blacklist_fail()
def test_url_validation_http()
def test_url_validation_https()
def test_evidence_ref_validation()
def test_insight_without_evidence_fails()
def test_snippet_truncation()
def test_tldr_truncation()
def test_header_length_validation()
def test_language_consistency()
def test_empty_response_fails()

# test_model_manager.py
def test_model_routing_keyphrase_mining()
def test_model_routing_sentiment()
def test_model_routing_topics()
def test_primary_timeout_triggers_fallback()
def test_budget_cap_enforcement()
def test_budget_degradation_reduces_context()
def test_telemetry_tracking()
def test_cost_estimation()
def test_multiple_fallbacks()
def test_all_models_fail_raises_error()
```

**Acceptance Criteria:**
- [ ] All 35 tests pass
- [ ] Coverage ≥ 80% for schemas, validators, model_manager
- [ ] CI/CD pipeline green

---

#### Task 1.3: Integration Tests
**Owner:** QA + Backend
**Estimate:** 8 hours (1 day)
**Files:**
- `tests/integration/test_retrieval.py` (6 tests)
- `tests/integration/test_command_flows.py` (8 tests)
- `tests/integration/test_error_handling.py` (4 tests)

**Test Coverage:**

```python
# test_retrieval.py
async def test_retrieve_for_analysis_with_rrf()
async def test_retrieve_time_window_24h()
async def test_retrieve_language_filter_ru()
async def test_retrieve_source_filter()
async def test_retrieve_deduplication()
async def test_retrieve_cache_hit()

# test_command_flows.py
async def test_trends_enhanced_pipeline()
async def test_analyze_keywords_pipeline()
async def test_analyze_sentiment_pipeline()
async def test_analyze_topics_pipeline()
async def test_validation_passes()
async def test_validation_fails_missing_evidence()
async def test_parallel_agents_execution()
async def test_format_node_builds_response()

# test_error_handling.py
async def test_error_model_unavailable()
async def test_error_budget_exceeded()
async def test_error_no_data()
async def test_error_validation_failed()
```

**Acceptance Criteria:**
- [ ] All 18 tests pass
- [ ] End-to-end flows verified
- [ ] Error handling tested

---

### Day 3: E2E + Bot Integration (P0/P1)

#### Task 3.1: E2E Tests
**Owner:** QA
**Estimate:** 4-6 hours
**Files:** `tests/e2e/test_bot_commands.py`

**Test Coverage:**

```python
# test_bot_commands.py
async def test_trends_command_24h()
async def test_trends_command_1w()
async def test_analyze_keywords_with_query()
async def test_analyze_sentiment_without_query()
async def test_telegram_formatting()
async def test_buttons_rendered()
async def test_evidence_cards_formatted()
async def test_localization_ru()
async def test_localization_en()
async def test_callback_explain()
async def test_callback_sources()
```

**Acceptance Criteria:**
- [ ] All 11 tests pass
- [ ] Bot commands return formatted messages
- [ ] Buttons clickable and callbacks work

---

#### Task 3.2: Bot Handlers Integration
**Owner:** Backend
**Estimate:** 2-3 hours
**File:** `bot_service/commands.py`

**Implementation:**

```python
# bot_service/commands.py
from telegram import Update
from telegram.ext import ContextTypes
from services.orchestrator import execute_trends, execute_analyze

async def trends_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /trends [window] command"""
    try:
        # Parse window
        window = context.args[0] if context.args else "24h"

        # Execute orchestrator
        result = await execute_trends(window=window, lang="auto")

        # Send formatted message
        await update.message.reply_text(
            text=result["text"],
            parse_mode=result["parse_mode"],
            reply_markup=build_inline_keyboard(result["buttons"])
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /analyze <mode> [query] command"""
    try:
        if not context.args:
            await update.message.reply_text(
                "Usage: /analyze <keywords|sentiment|topics> [query]"
            )
            return

        mode = context.args[0]
        query = " ".join(context.args[1:]) if len(context.args) > 1 else None

        # Execute orchestrator
        result = await execute_analyze(mode=mode, query=query)

        # Send formatted message
        await update.message.reply_text(
            text=result["text"],
            parse_mode=result["parse_mode"],
            reply_markup=build_inline_keyboard(result["buttons"])
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# Register handlers
application.add_handler(CommandHandler("trends", trends_handler))
application.add_handler(CommandHandler("analyze", analyze_handler))
```

**Acceptance Criteria:**
- [ ] `/trends` command works in bot
- [ ] `/analyze keywords|sentiment|topics` commands work
- [ ] Error messages user-friendly
- [ ] Buttons rendered correctly

---

### Day 4: Monitoring + Runbook (P1)

#### Task 4.1: Grafana Dashboards
**Owner:** DevOps + Backend
**Estimate:** 6 hours
**Deliverables:** 4 dashboards

**Dashboard 1: Latency**
```
Panels:
- P50/P95/P99 latency per command (trends, analyze keywords, etc.)
- P50/P95/P99 latency per agent (keyphrase_mining, sentiment, topics)
- Retrieval latency (retrieve_for_analysis)
- Format/validate node latency
```

**Dashboard 2: Cost & Budget**
```
Panels:
- Tokens used per model (line chart)
- Cost per command (avg, P95)
- Cost per user (daily/weekly)
- Budget utilization % (gauge)
- Model usage distribution (pie chart)
```

**Dashboard 3: Quality**
```
Panels:
- Schema validation pass rate (should be 100%)
- Evidence coverage % (should be ≥ 95%)
- Insight count per response (avg)
- Fallback usage rate %
```

**Dashboard 4: Reliability**
```
Panels:
- Error rate % (per error code)
- Model availability %
- Timeout rate %
- Cache hit-rate %
- Rerank enabled/disabled (boolean)
```

**Acceptance Criteria:**
- [ ] All 4 dashboards created
- [ ] Metrics flowing from orchestrator
- [ ] Panels update in real-time

---

#### Task 4.2: Prometheus Alerts
**Owner:** DevOps
**Estimate:** 2 hours
**Deliverable:** `monitoring/alerts.yml`

**P1 Alerts (Critical):**

```yaml
groups:
  - name: phase1_critical
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: rate(orchestrator_errors_total[10m]) > 0.05
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Error rate > 5% for 10 minutes"
          description: "{{ $value }}% errors detected"

      - alert: ModelUnavailable
        expr: up{job="orchestrator",model=~"gpt-5|claude-4.5|gemini-2.5-pro"} == 0
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: "Primary model unavailable"

      - alert: HighLatency
        expr: histogram_quantile(0.95, orchestrator_latency_seconds_bucket{command="trends"}) > 20
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "P95 latency > 20s for trends"
```

**P2 Alerts (Warning):**

```yaml
      - alert: LowCacheHitRate
        expr: rate(orchestrator_cache_hits_total[1h]) / rate(orchestrator_cache_requests_total[1h]) < 0.30
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Cache hit-rate < 30%"

      - alert: HighFallbackRate
        expr: rate(orchestrator_fallback_total[1h]) / rate(orchestrator_requests_total[1h]) > 0.15
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Fallback rate > 15%"

      - alert: BudgetWarning
        expr: orchestrator_budget_used_cents / orchestrator_budget_limit_cents > 0.80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Budget utilization > 80%"
```

**Acceptance Criteria:**
- [ ] All 6 alerts configured
- [ ] Test alerts trigger correctly
- [ ] Notifications sent to Slack/PagerDuty

---

#### Task 4.3: Runbook
**Owner:** Backend + DevOps
**Estimate:** 2-3 hours
**Deliverable:** `docs/RUNBOOK.md`

**Contents:**

```markdown
# Phase 1 Operations Runbook

## Emergency Contacts
- On-call: [phone/slack]
- Escalation: [manager contact]

## Common Issues

### 1. High Error Rate (> 5%)
**Symptoms:** Error rate alert firing
**Diagnosis:**
- Check Grafana "Reliability" dashboard
- Look for MODEL_UNAVAILABLE or VALIDATION_FAILED spikes
**Resolution:**
1. If MODEL_UNAVAILABLE: Force fallback model
2. If VALIDATION_FAILED: Check recent schema changes
3. If BUDGET_EXCEEDED: Increase budget or throttle

### 2. High Latency (P95 > 20s)
**Symptoms:** HighLatency alert firing
**Diagnosis:**
- Check retrieval latency (should be < 2s)
- Check agent latency (should be < 12s)
**Resolution:**
1. Disable rerank if enabled: `config.retrieval.enable_rerank = false`
2. Reduce k_final to 5: `config.retrieval.default_k_final = 5`
3. Check database connection pool

### 3. Model Unavailable
**Symptoms:** ModelUnavailable alert firing
**Diagnosis:**
- Check model API status pages
- Check API keys validity
**Resolution:**
1. Verify API key: `echo $OPENAI_API_KEY | head -c 10`
2. Force fallback: Update config to skip primary
3. Page vendor support if outage

## Degradation Procedures

### Level 1: Soft Degradation
- Disable rerank
- Reduce k_final to 5
- Disable query_expansion

### Level 2: Hard Degradation
- Switch all to fallback models
- Disable trends_enhanced (use simple trends)
- Reduce max_tokens_per_command to 5000

### Level 3: Emergency Shutdown
- Disable all /analyze commands
- Keep only /trends simple
- Page on-call + escalate

## Rollback Procedure
1. Set feature flag: `enable_trends_enhanced = false`
2. Deploy previous version via CI/CD
3. Verify old version working
4. Investigate issue offline

## Canary Rollout
1. Deploy to 10% traffic
2. Monitor for 4 hours
3. If stable: increase to 30%
4. Monitor for 1 day
5. If stable: increase to 100%

Stop criteria (auto-rollback):
- Error rate > 5%
- P95 latency > 20s
- Evidence coverage < 90%
```

**Acceptance Criteria:**
- [ ] Runbook reviewed by team
- [ ] Emergency contacts updated
- [ ] Procedures tested in staging

---

### Day 5: Testing & Validation

#### Task 5.1: Run Full Test Suite
**Owner:** QA
**Estimate:** 4 hours

```bash
# Run all tests
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v

# Check coverage
pytest --cov=core --cov=schemas --cov=services --cov-report=html
```

**Acceptance Criteria:**
- [ ] All tests pass (unit + integration + e2e)
- [ ] Coverage ≥ 70% overall
- [ ] No critical bugs found

---

#### Task 5.2: Performance Validation
**Owner:** Backend + QA
**Estimate:** 2 hours

**Load Test Script:**

```python
import asyncio
import time
from services.orchestrator import execute_trends

async def load_test():
    """Simulate 20 concurrent requests"""
    tasks = []
    start = time.time()

    for i in range(20):
        task = execute_trends(window="24h")
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start
    successes = sum(1 for r in results if not isinstance(r, Exception))

    print(f"Total time: {elapsed:.2f}s")
    print(f"Successes: {successes}/20")
    print(f"Avg latency: {elapsed/20:.2f}s")

asyncio.run(load_test())
```

**Metrics to Capture:**
- P95 latency
- Success rate
- Fallback rate
- Cost per command

**Acceptance Criteria:**
- [ ] P95 ≤ 12s (enhanced) or ≤ 5s (simple)
- [ ] Success rate ≥ 95%
- [ ] Cost/command ≤ $0.50

---

### Day 6-7: Canary Rollout

#### Stage 1: 10% Traffic (4 hours)
**Owner:** DevOps
**Actions:**
1. Deploy to canary environment
2. Route 10% traffic via load balancer
3. Monitor dashboards continuously

**Stop Criteria (auto-rollback):**
- Error rate > 5%
- P95 latency > 20s
- Evidence coverage < 90%

**Acceptance Criteria:**
- [ ] No alerts fired
- [ ] Metrics within SLO
- [ ] No user complaints

---

#### Stage 2: 30% Traffic (1 day)
**Owner:** DevOps
**Actions:**
1. Increase traffic to 30%
2. Enable rerank flag
3. Monitor cost and quality

**Acceptance Criteria:**
- [ ] P95 latency stable
- [ ] Cost per command ≤ $0.50
- [ ] Cache hit-rate ≥ 30%

---

#### Stage 3: 100% Traffic
**Owner:** DevOps + Backend
**Actions:**
1. Full rollout
2. Monitor for 7 days
3. Confirm SLO compliance

**SLO Targets:**
- P95 latency ≤ 12s
- Error rate ≤ 2%
- Evidence coverage ≥ 95%
- Cost/command ≤ $0.50

**Acceptance Criteria:**
- [ ] All SLOs met for 7 days
- [ ] No P1 incidents
- [ ] User feedback positive

---

## 🎯 Success Metrics

### Technical Metrics
- **Test Coverage:** ≥ 70%
- **P95 Latency:** ≤ 12s (enhanced), ≤ 5s (simple)
- **Error Rate:** ≤ 2%
- **Evidence Coverage:** ≥ 95%
- **Cost per Command:** ≤ $0.50
- **Fallback Rate:** ≤ 10%
- **Cache Hit-Rate:** ≥ 30%

### Business Metrics
- **User Adoption:** Track /trends and /analyze usage
- **User Satisfaction:** NPS or CSAT survey
- **Command Success Rate:** % of commands returning valid results

---

## 🚨 Risk Mitigation

### Risk 1: Gemini API Unavailable
**Probability:** Medium
**Impact:** High (blocks /analyze keywords)
**Mitigation:**
- Implement robust fallback to Claude/GPT-5
- Monitor Gemini status page
- Pre-test fallback chain

### Risk 2: Tests Uncover Critical Bugs
**Probability:** Medium
**Impact:** Medium (delays timeline)
**Mitigation:**
- Allocate buffer time (Day 5)
- Prioritize P0 bugs
- Consider phased rollout per command

### Risk 3: Performance Degradation Under Load
**Probability:** Low
**Impact:** High
**Mitigation:**
- Load test in staging
- Implement auto-scaling
- Monitor P95 closely during canary

### Risk 4: Budget Overrun
**Probability:** Low
**Impact:** Medium
**Mitigation:**
- Set hard caps in config
- Monitor cost dashboard
- Implement per-user throttling

---

## 📞 Stakeholder Communication

### Daily Standups (Days 1-5)
- Progress updates
- Blocker identification
- Risk assessment

### Pre-Rollout Review (Day 5)
- Test results presentation
- Go/no-go decision
- Rollout plan confirmation

### Post-Rollout Review (Day 14)
- Metrics review (SLO compliance)
- User feedback summary
- Lessons learned

---

## ✅ Final Checklist

**Before Canary:**
- [ ] All P0 tasks complete
- [ ] All P1 tasks complete
- [ ] Test suite passes
- [ ] Monitoring configured
- [ ] Runbook reviewed
- [ ] Rollback tested

**During Canary:**
- [ ] 10% stage passes
- [ ] 30% stage passes
- [ ] Metrics monitored

**After Full Rollout:**
- [ ] SLOs met for 7 days
- [ ] No P1 incidents
- [ ] Documentation updated
- [ ] Post-mortem completed

---

**Document Version:** 1.0
**Last Updated:** 2025-09-30
**Owner:** Backend Team
**Approver:** Engineering Manager