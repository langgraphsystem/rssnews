# /ask Command Implementation Plan
**Date:** 2025-10-06
**Goal:** Adapt /ask for reliable news-mode retrieval + safe general-QA
**Status:** 🚧 In Progress

---

## Architecture Analysis

### Current Flow
```
Telegram → advanced_bot.py:handle_ask_deep_command()
    ↓ window="24h" (hardcoded)
    ↓
phase3_handlers.py:execute_ask_command()
    ↓
phase3_context_builder.py:build_context()
    ↓
retrieval_client.py:retrieve()
    ↓ use_cache=True (5-min TTL)
    ↓
ranking_api.py:retrieve_for_analysis()
    ↓
ProductionScorer + DeduplicationEngine
    ↓
phase3_orchestrator_new.py:_handle_agentic()
    ↓
AgenticRAGAgent.execute() → ModelRouter → GPT-5
    ↓
formatter.py:format_for_telegram()
    ↓
Telegram User
```

### Current Issues
1. ❌ **No intent routing** — all queries go through news retrieval
2. ❌ **24h default** — too narrow for most news queries
3. ❌ **No site:/after:/before: parsing**
4. ❌ **No off-topic guard** — returns irrelevant results
5. ❌ **Weak deduplication** — doesn't use eTLD+1 or normalized paths
6. ❌ **No domain diversity** — can return 5 results from same domain
7. ❌ **No date requirements** — returns undated articles
8. ❌ **No auto-recovery** — fails on empty 24h window
9. ❌ **No metrics** — can't measure quality/performance
10. ❌ **Generic formatter** — doesn't distinguish news vs general-QA

---

## Implementation Steps

### **Phase 1: Intent Router & Time Window (Priority 1)**

#### 1.1 Create Intent Router
**File:** `core/routing/intent_router.py` (NEW)
```python
class IntentRouter:
    def classify(self, query: str) -> Literal["general_qa", "news_current_events"]:
        # Regex patterns for general_qa
        # Named entity detection for news
        # site:/after:/before: → force news
```

#### 1.2 Update Bot Handler
**File:** `bot_service/advanced_bot.py:1268-1320`
- Change default: `window="24h"` → `window="7d"`
- Parse `site:`, `after:`, `before:` from query
- Extract time indicators: "today/сегодня" → "24h", "this week" → "7d"

#### 1.3 Update Phase3 Handlers
**File:** `services/phase3_handlers.py:51-127`
- Add `intent` parameter to `execute_ask_command()`
- Route to intent_router before `_build_context()`

---

### **Phase 2: Retrieval Normalization (Priority 1)**

#### 2.1 Query Parser
**File:** `core/rag/query_parser.py` (NEW)
```python
class QueryParser:
    def parse(self, query: str) -> ParsedQuery:
        # Extract site: domains → validate against allow-list
        # Extract after:/before: dates
        # Extract time window keywords
        # Expand synonyms
        # Return: terms, time_window, domains, dates, filters
```

#### 2.2 Update Retrieval Client
**File:** `core/rag/retrieval_client.py:76-137`
- Call QueryParser before building cache key
- Pass `ensure_domain_diversity`, `require_dates`, `drop_offtopic` flags
- Change default: `use_cache=True` → `use_cache=False` for /ask

---

### **Phase 3: Ranking Pipeline (Priority 1)**

#### 3.1 Off-Topic Guard
**File:** `ranking_service/scorer.py:100+` (ADD METHOD)
```python
def filter_offtopic(self, docs: List, query: str, threshold: float = 0.28) -> List:
    # Calculate cosine(query_emb, doc_title_emb)
    # Drop if < threshold
    # Log offtopic_dropped_total
```

#### 3.2 Category Penalties
**File:** `ranking_service/scorer.py:43` (UPDATE)
- Add `category_penalties` dict: {"sports": 0.5, "crime": 0.7} when intent=news
- Apply penalty in `score_and_rank()`

#### 3.3 Update Weights
**File:** `ranking_service/scorer.py:17-22`
```python
# NEW weights
semantic: float = 0.45  # was 0.58
fts: float = 0.30       # was 0.32
freshness: float = 0.20 # was 0.06
source: float = 0.05    # was 0.04
```

#### 3.4 Date Penalties
**File:** `ranking_service/scorer.py:100+` (ADD METHOD)
```python
def apply_date_penalty(self, docs: List, require_dates: bool) -> List:
    # If no published_at → score *= 0.3
    # Sort by (score, date DESC)
```

---

### **Phase 4: Deduplication (Priority 2)**

#### 4.1 eTLD+1 Extraction
**File:** `ranking_service/deduplication.py:89+` (ADD METHOD)
```python
def extract_etld_plus_one(self, url: str) -> str:
    # Use tldextract or manual parsing
    # Return "example.com" from "news.example.com/path?utm=..."
```

#### 4.2 Normalized Path
**File:** `ranking_service/deduplication.py:89+` (ADD METHOD)
```python
def normalize_path(self, url: str) -> str:
    # Remove utm_*, fbclid, etc.
    # Lowercase
    # Return path only
```

#### 4.3 Update Dedup Key
**File:** `ranking_service/deduplication.py:140+` (UPDATE)
```python
def canonicalize_articles(self, articles: List) -> List:
    # Group by: (etld+1, norm_path, title_norm)
    # Keep: WITH date AND higher source_score
```

---

### **Phase 5: Domain Diversity (Priority 2)**

#### 5.1 MMR Domain Enforcement
**File:** `ranking_service/diversification.py:100+` (ADD METHOD)
```python
def enforce_domain_diversity(self, docs: List, max_per_domain: int = 2) -> List:
    # Track domain counts
    # Cap at max_per_domain in top-N
    # Ensure ≥3 distinct domains in top-5
```

#### 5.2 Integrate into RankingAPI
**File:** `ranking_api.py:434-445`
```python
# After dedup, before return
if ensure_domain_diversity:
    deduplicated = self.diversifier.enforce_domain_diversity(deduplicated)
```

---

### **Phase 6: Auto-Recovery (Priority 2)**

#### 6.1 Window Expansion Logic
**File:** `core/context/phase3_context_builder.py:~200+` (ADD METHOD)
```python
async def _auto_recover_with_expansion(self, ...):
    attempts = [
        {"window": "7d", "min_cosine": 0.28},
        {"window": "14d", "min_cosine": 0.25},
        {"window": "30d", "min_cosine": 0.22, "disable_diversity": True}
    ]
    for attempt in attempts:
        docs = await self._perform_retrieval_with_recovery(...)
        if len(docs) >= 3:
            return docs, warnings
    return [], ["No results after 3 expansion attempts"]
```

---

### **Phase 7: General-QA Bypass (Priority 1)**

#### 7.1 Direct LLM Call
**File:** `core/orchestrator/phase3_orchestrator_new.py:120-176`
```python
async def _handle_agentic(self, context: Dict) -> Any:
    intent = context.get("intent", "news_current_events")

    if intent == "general_qa":
        # SKIP retrieval
        return await self._handle_general_qa(context)
    else:
        # EXISTING news pipeline
        ...
```

#### 7.2 General-QA Handler
**File:** `core/orchestrator/phase3_orchestrator_new.py:~250+` (ADD METHOD)
```python
async def _handle_general_qa(self, context: Dict) -> Any:
    query = context["params"]["query"]
    # Direct LLM call via GPT5Service (NO ModelRouter)
    answer = await self.gpt5_service.generate_response(...)
    # Return with source="LLM/KB", no evidence list
```

---

### **Phase 8: Formatter Updates (Priority 2)**

#### 8.1 Detect Intent in Formatter
**File:** `core/ux/formatter.py:29-88`
```python
def _format_success_response(response: BaseAnalysisResponse) -> Dict:
    intent = response.meta.get("intent", "news_current_events")

    if intent == "general_qa":
        return _format_general_qa_response(response)
    else:
        return _format_news_response(response)
```

#### 8.2 News Formatter
**File:** `core/ux/formatter.py:~150+` (ADD)
```python
def _format_news_response(response: BaseAnalysisResponse) -> Dict:
    # Summary: 3-5 bullets with ISO dates (America/Chicago)
    # Sources: Title · Date · Domain · Link · Snippet
    # Buttons: [Show more] [24h] [7d] [30d] [Only official]
```

#### 8.3 General-QA Formatter
**File:** `core/ux/formatter.py:~200+` (ADD)
```python
def _format_general_qa_response(response: BaseAnalysisResponse) -> Dict:
    # Concise explanation
    # Label: "Source: LLM/KB"
    # NO news source list
    # NO time window buttons
```

---

### **Phase 9: Metrics & Logging (Priority 3)**

#### 9.1 Metrics Module
**File:** `infra/metrics/ask_metrics.py` (NEW)
```python
class AskMetrics:
    # Counters
    intent_general_qa_total: int
    intent_news_total: int
    retrieval_success_total: int
    retrieval_no_candidates_total: int
    duplicates_removed_total: int
    offtopic_dropped_total: int
    recovery_attempts: int
    window_expanded_total: int
    filters_relaxed_total: int
    recovery_success_total: int
    llm_calls_total: int

    # Histograms
    with_date_ratio: List[float]
    domains_diversity_index: List[float]
    db_query_ms: List[float]
    ranking_ms: List[float]
    llm_ms: List[float]
    end_to_end_ms: List[float]
    llm_tokens_total: List[int]
```

#### 9.2 Integrate Metrics
- `intent_router.py`: Log intent classification
- `retrieval_client.py`: Log retrieval success/failure
- `deduplication.py`: Count duplicates removed
- `scorer.py`: Count offtopic dropped
- `phase3_context_builder.py`: Log recovery attempts
- `phase3_orchestrator_new.py`: Log LLM calls/tokens

---

### **Phase 10: Configuration (Priority 3)**

#### 10.1 Environment Variables
**File:** `.env` (UPDATE)
```bash
# /ask configuration
ASK_DEFAULT_TIME_WINDOW_DAYS=7
ASK_MIN_COSINE=0.28
ASK_MAX_RESULTS=10
RANK_ENSURE_DOMAIN_DIVERSITY=true
RANK_REQUIRE_DATES=true
RANK_DROP_OFFTOPIC=true

# Scoring weights
W_SEMANTIC=0.45
W_FTS=0.30
W_FRESH=0.20
W_SOURCE=0.05

# Feature flags
FEATURE_FLAG_ASK_NEWS_MODE_ENABLED=true
FEATURE_FLAG_ASK_INTENT_ROUTER_ENABLED=true
```

#### 10.2 Config Loader
**File:** `infra/config/ask_config.py` (NEW)
```python
@dataclass
class AskConfig:
    default_time_window_days: int = 7
    min_cosine: float = 0.28
    max_results: int = 10
    ensure_domain_diversity: bool = True
    require_dates: bool = True
    drop_offtopic: bool = True

    @classmethod
    def from_env(cls):
        return cls(
            default_time_window_days=int(os.getenv("ASK_DEFAULT_TIME_WINDOW_DAYS", "7")),
            ...
        )
```

---

### **Phase 11: Testing (Priority 4)**

#### 11.1 Unit Tests
**File:** `tests/unit/test_intent_router.py` (NEW)
**File:** `tests/unit/test_query_parser.py` (NEW)
**File:** `tests/unit/test_offtopic_guard.py` (NEW)

#### 11.2 Integration Tests
**File:** `tests/integration/test_ask_news_mode.py` (NEW)
**File:** `tests/integration/test_ask_general_qa.py` (NEW)

#### 11.3 E2E Tests
**File:** `tests/e2e/test_ask_acceptance.py` (NEW)
- S1: General-QA (bypass retrieval)
- S2: News weekly (7d default, auto-expansion)
- S3: Site lock (domain filtering)
- S4: Off-topic guard (sports filtering)
- S5: Recovery max (30d expansion)

---

## Implementation Order

### Sprint 1 (Day 1) — Critical Path
1. ✅ Create intent router (`intent_router.py`)
2. ✅ Update bot handler (default 7d, parse site:/after:/before:)
3. ✅ Add general-QA bypass in orchestrator
4. ✅ Update formatter for news vs general-QA

### Sprint 2 (Day 2) — Ranking & Retrieval
5. ✅ Add off-topic guard in scorer
6. ✅ Implement category penalties
7. ✅ Update scoring weights
8. ✅ Add date penalties
9. ✅ Update dedup with eTLD+1

### Sprint 3 (Day 3) — Quality & Recovery
10. ✅ Add domain diversity (MMR)
11. ✅ Implement auto-recovery with window expansion
12. ✅ Add query parser (site:/after:/before:)
13. ✅ Update retrieval client normalization

### Sprint 4 (Day 4) — Metrics & Config
14. ✅ Create metrics module
15. ✅ Integrate metrics across pipeline
16. ✅ Add environment configuration
17. ✅ Create config loader

### Sprint 5 (Day 5) — Testing & Documentation
18. ✅ Write unit tests
19. ✅ Write integration tests
20. ✅ Write E2E acceptance tests
21. ✅ Create CHANGELOG
22. ✅ Update documentation

---

## Files to Touch

### Create (NEW)
- `core/routing/intent_router.py`
- `core/rag/query_parser.py`
- `infra/metrics/ask_metrics.py`
- `infra/config/ask_config.py`
- `tests/unit/test_intent_router.py`
- `tests/unit/test_query_parser.py`
- `tests/unit/test_offtopic_guard.py`
- `tests/integration/test_ask_news_mode.py`
- `tests/integration/test_ask_general_qa.py`
- `tests/e2e/test_ask_acceptance.py`

### Modify (UPDATE)
- `bot_service/advanced_bot.py` (lines 1268-1320)
- `services/phase3_handlers.py` (lines 51-127)
- `core/context/phase3_context_builder.py` (~200+ lines)
- `core/orchestrator/phase3_orchestrator_new.py` (lines 120-176, +100 lines)
- `core/rag/retrieval_client.py` (lines 76-137)
- `ranking_api.py` (lines 367-451)
- `ranking_service/scorer.py` (+150 lines)
- `ranking_service/deduplication.py` (+80 lines)
- `ranking_service/diversification.py` (+50 lines)
- `core/ux/formatter.py` (+150 lines)
- `.env` (+15 keys)

---

## Success Criteria

### Functional
- ✅ S1: General-QA bypasses retrieval, shows "Source: LLM/KB"
- ✅ S2: News query uses 7d default, expands if empty
- ✅ S3: `site:europa.eu` filters to only europa.eu results
- ✅ S4: Sports headlines dropped by off-topic guard
- ✅ S5: Empty 7d auto-expands to 14d/30d

### Quality
- ✅ `with_date_ratio` ≥ 0.7 for top-10 news results
- ✅ `domains_diversity_index` ≥ 0.5 for top-10
- ✅ `duplicates_removed_total` > 0 when corpus has dupes
- ✅ `offtopic_dropped_total` > 0 when corpus has off-topic

### Performance
- ✅ `end_to_end_ms` ≤ 5000ms (p95)
- ✅ `db_query_ms` ≤ 500ms (p95)
- ✅ `ranking_ms` ≤ 300ms (p95)
- ✅ `llm_ms` ≤ 3000ms (p95)

---

## Risk Mitigation

### Risk 1: Intent router false positives
**Mitigation:** Add confidence threshold; log all classifications; manual review sample

### Risk 2: Auto-recovery too aggressive (slow)
**Mitigation:** Limit to 3 attempts; timeout at 10s; fallback to "No results"

### Risk 3: Domain diversity breaks relevance
**Mitigation:** Only enforce in top-10; relax if <5 results; disable in recovery last attempt

### Risk 4: Off-topic guard too strict
**Mitigation:** Start with threshold=0.22; A/B test; make configurable; log dropped items

---

## Next Steps

1. Start Sprint 1: Create intent router
2. Test with sample queries
3. Iterate based on metrics
4. Deploy behind feature flag
5. Monitor production metrics
6. Gradual rollout (10% → 50% → 100%)

---

**Status:** Ready for implementation
**Owner:** Claude Code Agent
**ETA:** 5 days (20 hours total)
