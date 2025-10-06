# /ask Command Deployment Guide

## Overview

This guide covers deployment of the enhanced `/ask` command with intent routing, advanced filtering, and metrics.

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Environment Setup](#environment-setup)
3. [Testing](#testing)
4. [Gradual Rollout](#gradual-rollout)
5. [Monitoring](#monitoring)
6. [Rollback Plan](#rollback-plan)
7. [Post-Deployment](#post-deployment)

---

## Pre-Deployment Checklist

### Code Review

- [ ] All Sprint 1-5 commits merged to main
- [ ] No failing tests in CI/CD
- [ ] Code review approved by 2+ engineers
- [ ] Documentation updated (README, CHANGELOG)

### Dependencies

- [ ] Python 3.9+ installed
- [ ] Required packages: `pytest`, `pytest-benchmark`
- [ ] Database migrations applied (if any)
- [ ] GPT5Service initialized correctly

### Configuration

- [ ] `.env.ask.example` reviewed
- [ ] Production `.env` file created
- [ ] Environment variables validated
- [ ] Secrets manager configured (API keys)

---

## Environment Setup

### Step 1: Copy Environment Template

```bash
cp .env.ask.example .env
```

### Step 2: Configure Production Values

```bash
# Edit .env file
nano .env
```

**Required Variables:**
```bash
# Time windows
ASK_DEFAULT_TIME_WINDOW=7d
ASK_MAX_TIME_WINDOW=1y

# Retrieval
ASK_K_FINAL=10
ASK_USE_CACHE=false  # Important: fresh results for /ask

# Filtering (production defaults)
ASK_FILTER_OFFTOPIC_ENABLED=true
ASK_MIN_COSINE_THRESHOLD=0.28
ASK_CATEGORY_PENALTIES_ENABLED=true
ASK_DATE_PENALTIES_ENABLED=true

# Domain diversity
ASK_DOMAIN_DIVERSITY_ENABLED=true
ASK_MAX_PER_DOMAIN=2

# Auto-recovery
ASK_AUTO_EXPAND_WINDOW=true
ASK_MAX_EXPANSION_ATTEMPTS=5

# Scoring weights (must sum to 1.0)
ASK_SEMANTIC_WEIGHT=0.45
ASK_FTS_WEIGHT=0.30
ASK_FRESHNESS_WEIGHT=0.20
ASK_SOURCE_WEIGHT=0.05

# Metrics
ASK_METRICS_ENABLED=true
ASK_LOG_METRICS_INTERVAL=300  # 5 minutes

# Feature flags
ASK_EXPERIMENTAL_FEATURES=false
ASK_DEBUG_MODE=false  # Set to true for staging only
```

### Step 3: Validate Configuration

```bash
python -c "from core.config import get_ask_config; config = get_ask_config(); assert config.validate(), 'Invalid config'"
```

**Expected Output:**
```
INFO: AskCommandConfig loaded from environment: window=7d, k_final=10, intent_router=True
```

**If Errors:**
- Check weights sum to 1.0
- Verify thresholds are 0-1
- Ensure k_final is 1-50

---

## Testing

### Step 1: Unit Tests

```bash
pytest tests/test_ask_integration.py -v
```

**Expected:**
```
tests/test_ask_integration.py::TestIntentRouterIntegration::test_router_records_metrics_for_all_paths PASSED
tests/test_ask_integration.py::TestQueryParserIntegration::test_parser_records_operator_metrics PASSED
...
==================== 15 passed in 2.34s ====================
```

### Step 2: Acceptance Tests

```bash
pytest tests/test_ask_acceptance.py -v
```

**Expected:**
```
tests/test_ask_acceptance.py::TestS1_IntentRouting::test_general_qa_patterns PASSED
tests/test_ask_acceptance.py::TestS2_QueryParsing::test_site_operator_extraction PASSED
tests/test_ask_acceptance.py::TestS3_TimeWindowDefaults::test_news_query_default_window PASSED
...
==================== 30 passed in 5.67s ====================
```

### Step 3: Manual Smoke Tests

```bash
# Test 1: General-QA
/ask what is the difference between AI and ML?
# ✅ Expected: Direct answer in 2-3s, no evidence list

# Test 2: News query
/ask Israel ceasefire talks
# ✅ Expected: 7d retrieval, 5-10 articles with dates

# Test 3: Search operators
/ask AI regulation site:europa.eu after:2025-01-01
# ✅ Expected: Only europa.eu articles from 2025

# Test 4: Auto-recovery
/ask obscure topic that has no recent news
# ✅ Expected: Window expansion to 14d/30d, or "no results" after 5 attempts

# Test 5: Metrics
python -c "from core.metrics import get_metrics_collector; print(get_metrics_collector().get_summary())"
# ✅ Expected: JSON with intent_routing, retrieval, performance metrics
```

---

## Gradual Rollout

### Phase 1: Staging (Day 1-3)

**Deployment:**
```bash
# Deploy to staging environment
git checkout main
git pull origin main

# Set staging flag
export ASK_DEBUG_MODE=true
export ASK_EXPERIMENTAL_FEATURES=true

# Start service
python launcher.py
```

**Validation:**
- Run 50-100 test queries
- Monitor metrics every hour
- Check error rates (<1%)
- Verify response times (p95 < 8s)

**Success Criteria:**
- [ ] 0 critical errors
- [ ] Response time p95 < 8s
- [ ] Empty result rate < 5%
- [ ] User feedback positive

---

### Phase 2: Production (10% Traffic) — Day 4-7

**Feature Flag Setup:**
```python
# In bot handler, add rollout logic
import random

def should_use_enhanced_ask(user_id: str) -> bool:
    """10% gradual rollout based on user_id hash"""
    return (hash(user_id) % 100) < 10  # 10% of users
```

**Monitor:**
- Metrics dashboard (Grafana/DataDog)
- Error logs (Sentry/CloudWatch)
- User feedback channels

**Rollback Trigger:**
- Error rate >2%
- Response time p95 >12s
- Multiple user complaints

---

### Phase 3: Production (50% Traffic) — Day 8-10

**Update Feature Flag:**
```python
def should_use_enhanced_ask(user_id: str) -> bool:
    return (hash(user_id) % 100) < 50  # 50% of users
```

**A/B Test Results:**
Compare old vs new implementation:
- Response time distribution
- User satisfaction (thumbs up/down)
- Query success rate
- Unique sources per response

**Decision Point:**
- If metrics better → proceed to 100%
- If metrics worse → investigate and fix
- If neutral → extend testing period

---

### Phase 4: Production (100% Traffic) — Day 11+

**Full Rollout:**
```python
def should_use_enhanced_ask(user_id: str) -> bool:
    return True  # All users
```

**Remove Feature Flag:**
After 7 days of stable 100% traffic, remove feature flag code.

---

## Monitoring

### Dashboard Metrics

**Intent Routing:**
```
- General-QA queries/hour
- News queries/hour
- Average confidence score
```

**Retrieval:**
```
- Bypassed (general-QA) count
- Executed (news) count
- Empty results rate (target: <5%)
- Window expansion frequency
```

**Performance:**
```
- Response time p50/p95/p99
- LLM calls per hour
- Database query time
```

**Quality:**
```
- Top-10 unique domains (target: >6)
- Dated articles % (target: >90%)
- Off-topic filter drops
```

### Alerting Rules

**Critical (PagerDuty):**
```yaml
- name: ask_error_rate_high
  condition: error_rate > 5%
  duration: 5 minutes
  action: page_on_call_engineer

- name: ask_response_time_high
  condition: p95_response_time > 15s
  duration: 10 minutes
  action: page_on_call_engineer
```

**Warning (Slack):**
```yaml
- name: ask_empty_results_high
  condition: empty_result_rate > 10%
  duration: 15 minutes
  action: notify_team_channel

- name: ask_diversity_low
  condition: avg_unique_domains < 4
  duration: 30 minutes
  action: notify_team_channel
```

### Log Queries

**Track Intent Distribution:**
```sql
SELECT
  DATE_TRUNC('hour', timestamp) as hour,
  intent,
  COUNT(*) as queries,
  AVG(confidence) as avg_confidence
FROM ask_intent_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hour, intent
ORDER BY hour DESC;
```

**Track Empty Results:**
```sql
SELECT
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(*) FILTER (WHERE results_count = 0) as empty,
  COUNT(*) as total,
  ROUND(100.0 * COUNT(*) FILTER (WHERE results_count = 0) / COUNT(*), 2) as empty_rate
FROM ask_retrieval_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

---

## Rollback Plan

### Scenario 1: Critical Bug

**Symptoms:**
- Error rate >10%
- Service crashes
- Data corruption

**Action (Immediate):**
```bash
# 1. Revert to previous commit
git revert HEAD~5..HEAD  # Revert last 5 commits (Sprint 1-5)
git push origin main

# 2. Redeploy
git pull origin main
systemctl restart rssnews-bot

# 3. Verify rollback
curl http://localhost:8000/health
```

**Timeline:** 5-10 minutes

---

### Scenario 2: Performance Degradation

**Symptoms:**
- Response time p95 >15s
- Database CPU >80%
- Memory leak

**Action (Tuning):**
```bash
# 1. Increase thresholds (reduce retrieval load)
export ASK_MIN_COSINE_THRESHOLD=0.35  # Was 0.28
export ASK_K_FINAL=5  # Was 10

# 2. Disable expensive features temporarily
export ASK_DOMAIN_DIVERSITY_ENABLED=false
export ASK_CATEGORY_PENALTIES_ENABLED=false

# 3. Enable caching (if necessary)
export ASK_USE_CACHE=true

# 4. Restart service
systemctl restart rssnews-bot
```

**Timeline:** 2-5 minutes

---

### Scenario 3: Quality Issues

**Symptoms:**
- High off-topic rate
- Low user satisfaction
- Empty results >15%

**Action (Parameter Adjustment):**
```bash
# 1. Relax filters
export ASK_MIN_COSINE_THRESHOLD=0.20  # Was 0.28
export ASK_DATE_PENALTY_FACTOR=0.5  # Was 0.3

# 2. Increase diversity
export ASK_MAX_PER_DOMAIN=3  # Was 2

# 3. Restart
systemctl restart rssnews-bot
```

**Timeline:** 2 minutes

---

## Post-Deployment

### Week 1: Daily Reviews

**Daily Tasks:**
- Review metrics dashboard (10 min)
- Check error logs for new patterns
- Read user feedback (Telegram/Discord)
- Adjust thresholds if needed

**Metrics to Track:**
- Error rate trend
- Response time trend
- User satisfaction (thumbs up/down ratio)
- Feature adoption (operators usage)

---

### Week 2-4: Weekly Reviews

**Weekly Tasks:**
- Analyze A/B test results
- Review top queries (what users ask most)
- Identify edge cases
- Plan improvements

**Questions to Answer:**
- Are users using search operators? (site:, after:, before:)
- What's the general-QA vs news distribution?
- Which domains are most popular?
- What time windows are most common?

---

### Month 1: Optimization

**Data-Driven Tuning:**

1. **Analyze intent confidence distribution:**
   - If many queries have confidence 0.5-0.6 → improve patterns
   - If many false positives → adjust decision thresholds

2. **Analyze retrieval results:**
   - If empty results >5% → increase default window to 14d
   - If too many results → increase cosine threshold

3. **Analyze performance:**
   - If p95 >8s consistently → optimize database queries
   - If LLM calls excessive → cache general-QA answers

4. **Analyze quality:**
   - If off-topic high → increase cosine threshold
   - If diversity low → decrease max_per_domain

---

## Troubleshooting

### Issue: High Memory Usage

**Symptoms:** RSS memory >2GB

**Solutions:**
```bash
# 1. Check metrics collector (histogram size)
from core.metrics import get_metrics_collector
metrics = get_metrics_collector()
summary = metrics.get_summary()
print(f"Response time samples: {len(metrics.response_time_histogram.values)}")

# 2. Reset metrics periodically (add cron job)
0 */6 * * * python -c "from core.metrics import reset_metrics; reset_metrics()"

# 3. Limit histogram size
# In ask_metrics.py, add max_samples parameter
```

---

### Issue: Database Connection Pool Exhausted

**Symptoms:** "No available connections"

**Solutions:**
```python
# Increase pool size in pg_client_new.py
self.pool = await asyncpg.create_pool(
    dsn=dsn,
    min_size=10,  # Was 5
    max_size=50,  # Was 20
    command_timeout=60
)
```

---

### Issue: GPT5Service Timeout

**Symptoms:** "Request timeout after 15s"

**Solutions:**
```bash
# Increase timeout for general-QA
export ASK_GENERAL_QA_TIMEOUT=30  # Was 15

# Or use fallback to ModelRouter
# In phase3_orchestrator_new.py, improve error handling
```

---

## Checklist Summary

### Pre-Deployment
- [ ] Code merged and reviewed
- [ ] Tests passing (unit + acceptance)
- [ ] Configuration validated
- [ ] Documentation complete

### Deployment
- [ ] Staging deployed and tested
- [ ] 10% rollout successful (3 days)
- [ ] 50% rollout successful (3 days)
- [ ] 100% rollout successful (7+ days)

### Post-Deployment
- [ ] Metrics dashboard created
- [ ] Alerts configured
- [ ] Daily reviews (Week 1)
- [ ] Weekly reviews (Week 2-4)
- [ ] Optimization completed (Month 1)

---

## Support Contacts

- **Engineering Lead:** [Name]
- **On-Call Engineer:** PagerDuty rotation
- **Slack Channel:** #ask-command-rollout
- **Documentation:** `/docs/ASK_COMMAND_GUIDE.md`

---

## Appendix: Configuration Profiles

### Conservative (High Precision)
```bash
ASK_MIN_COSINE_THRESHOLD=0.35
ASK_DATE_PENALTY_FACTOR=0.1
ASK_MAX_PER_DOMAIN=1
ASK_CATEGORY_PENALTIES_ENABLED=true
```

### Balanced (Default)
```bash
ASK_MIN_COSINE_THRESHOLD=0.28
ASK_DATE_PENALTY_FACTOR=0.3
ASK_MAX_PER_DOMAIN=2
ASK_CATEGORY_PENALTIES_ENABLED=true
```

### Permissive (High Recall)
```bash
ASK_MIN_COSINE_THRESHOLD=0.20
ASK_DATE_PENALTY_FACTOR=0.5
ASK_MAX_PER_DOMAIN=3
ASK_CATEGORY_PENALTIES_ENABLED=false
```

---

**End of Deployment Guide**
