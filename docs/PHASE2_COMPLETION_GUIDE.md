# Phase 2 Completion Guide

**For**: Completing the remaining 40% of Phase 2 implementation
**Estimated Time**: 16 hours (2 days)

---

## Quick Start

```bash
# Current status
✅ 60% Complete (7/13 major tasks done)
🟡 40% Remaining (6 tasks)

# What works now:
- All 3 agents (TrendForecaster, CompetitorNews, SynthesisAgent)
- All schemas validated
- Agent routing configured
- Phase 2 config ready

# What needs work:
- Format node (3 formatters)
- Orchestrator (3 command handlers)
- Tests (50 new tests)
- Bot integration
- Documentation
```

---

## Task 1: Complete Format Node (2 hours)

**File**: `core/orchestrator/nodes/format_node.py`

### Add Forecast Formatter

```python
def _format_forecast_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format /predict trends response"""
    from schemas.analysis_schemas import Insight, Evidence, EvidenceRef, Meta

    forecast_result = agent_results.get("trend_forecaster", {})
    forecast_items = forecast_result.get("forecast", [])

    if not forecast_items:
        raise ValueError("No forecast data available")

    forecast_item = forecast_items[0]
    direction = forecast_item.get("direction", "flat")
    topic = forecast_item.get("topic", "general")

    # Build header
    direction_emoji = {"up": "📈", "down": "📉", "flat": "➡️"}
    header = f"{direction_emoji.get(direction, '📊')} Trend Forecast: {topic}"

    # Build TL;DR
    ci = forecast_item.get("confidence_interval", [0.4, 0.6])
    tldr = f"Forecast indicates {direction} trend for {topic} (confidence: {ci[0]:.1f}-{ci[1]:.1f})"

    # Build insights from drivers
    insights = []
    drivers = forecast_item.get("drivers", [])
    for driver in drivers[:3]:  # Max 3 insights
        insight = Insight(
            type="hypothesis" if direction == "flat" else "fact",
            text=driver.get("rationale", "")[:180],
            evidence_refs=[
                EvidenceRef(
                    article_id=driver.get("evidence_ref", {}).get("article_id"),
                    url=driver.get("evidence_ref", {}).get("url"),
                    date=driver.get("evidence_ref", {}).get("date", "2025-09-30")
                )
            ]
        )
        insights.append(insight)

    # Build evidence
    evidence = []
    for i, doc in enumerate(docs[:5]):
        ev = Evidence(
            title=doc.get("title", "")[:200],
            article_id=doc.get("article_id"),
            url=doc.get("url"),
            date=doc.get("date", "2025-09-30"),
            snippet=doc.get("snippet", "")[:240]
        )
        evidence.append(ev)

    # Build meta
    meta = Meta(
        confidence=0.5 + (abs(ci[1] - ci[0]) / 2),
        model="gpt-5",
        version="phase2-v1.0",
        correlation_id=correlation_id
    )

    return BaseAnalysisResponse(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=forecast_result,
        meta=meta
    )
```

### Add Competitors Formatter

```python
def _format_competitors_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format /analyze competitors response"""
    from schemas.analysis_schemas import Insight, Evidence, EvidenceRef, Meta

    competitors_result = agent_results.get("competitor_news", {})
    positioning = competitors_result.get("positioning", [])
    gaps = competitors_result.get("gaps", [])

    # Build header
    header = f"🏆 Competitive Analysis: {len(positioning)} domains"

    # Build TL;DR
    leader_domains = [p["domain"] for p in positioning if p.get("stance") == "leader"]
    tldr = f"Analysis of {len(positioning)} competitors. Leaders: {', '.join(leader_domains[:2])}"

    # Build insights
    insights = []

    # Insight 1: Positioning
    for pos in positioning[:2]:
        insight = Insight(
            type="fact",
            text=f"{pos['domain']}: {pos['stance']} - {pos['notes']}"[:180],
            evidence_refs=[
                EvidenceRef(
                    article_id=docs[0].get("article_id") if docs else None,
                    url=docs[0].get("url") if docs else None,
                    date=docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                )
            ]
        )
        insights.append(insight)

    # Insight 2: Gaps
    if gaps:
        insight = Insight(
            type="recommendation",
            text=f"Coverage gaps identified: {', '.join(gaps[:3])}"[:180],
            evidence_refs=[
                EvidenceRef(
                    article_id=docs[1].get("article_id") if len(docs) > 1 else docs[0].get("article_id") if docs else None,
                    url=docs[1].get("url") if len(docs) > 1 else docs[0].get("url") if docs else None,
                    date=docs[1].get("date", "2025-09-30") if len(docs) > 1 else docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                )
            ]
        )
        insights.append(insight)

    # Build evidence
    evidence = []
    for doc in docs[:5]:
        ev = Evidence(
            title=doc.get("title", "")[:200],
            article_id=doc.get("article_id"),
            url=doc.get("url"),
            date=doc.get("date", "2025-09-30"),
            snippet=doc.get("snippet", "")[:240]
        )
        evidence.append(ev)

    # Build meta
    meta = Meta(
        confidence=0.75,
        model="claude-4.5",
        version="phase2-v1.0",
        correlation_id=correlation_id
    )

    return BaseAnalysisResponse(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=competitors_result,
        meta=meta
    )
```

### Add Synthesis Formatter

```python
def _format_synthesis_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any]],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format /synthesize response"""
    from schemas.analysis_schemas import Insight, Evidence, EvidenceRef, Meta

    synthesis_result = agent_results.get("synthesis_agent", {})
    summary = synthesis_result.get("summary", "")
    conflicts = synthesis_result.get("conflicts", [])
    actions = synthesis_result.get("actions", [])

    # Build header
    header = f"🔗 Synthesis: {len(actions)} Actions"

    # Build TL;DR
    tldr = summary[:220]

    # Build insights
    insights = []

    # Conflicts as insights
    for conflict in conflicts:
        insight = Insight(
            type="conflict",
            text=conflict.get("description", "")[:180],
            evidence_refs=conflict.get("evidence_refs", [])
        )
        insights.append(insight)

    # Actions as insights
    for action in actions[:3]:  # Max 3 more
        insight = Insight(
            type="recommendation",
            text=action.get("recommendation", "")[:180],
            evidence_refs=action.get("evidence_refs", [])
        )
        insights.append(insight)

    # Build evidence
    evidence = []
    for doc in docs[:5]:
        ev = Evidence(
            title=doc.get("title", "")[:200],
            article_id=doc.get("article_id"),
            url=doc.get("url"),
            date=doc.get("date", "2025-09-30"),
            snippet=doc.get("snippet", "")[:240]
        )
        evidence.append(ev)

    # Build meta
    meta = Meta(
        confidence=0.8,
        model="gpt-5",
        version="phase2-v1.0",
        correlation_id=correlation_id
    )

    return BaseAnalysisResponse(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=synthesis_result,
        meta=meta
    )
```

### Update format_node() Router

```python
async def format_node(state: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing code ...

    # Route to appropriate formatter
    if command == "/trends":
        response = _format_trends_response(docs, agent_results, correlation_id, params)
    elif command == "/analyze":
        mode = params.get("mode", "keywords")
        response = _format_analyze_response(mode, docs, agent_results, correlation_id, params)
    # Phase 2: NEW commands
    elif command == "/predict":
        response = _format_forecast_response(docs, agent_results, correlation_id, params)
    elif command == "/competitors":
        response = _format_competitors_response(docs, agent_results, correlation_id, params)
    elif command == "/synthesize":
        response = _format_synthesis_response(docs, agent_results, correlation_id, params)
    else:
        raise ValueError(f"Unknown command: {command}")
```

---

## Task 2: Update Orchestrator (3 hours)

**File**: `core/orchestrator/orchestrator.py`

Add 3 new methods (follow pattern of `execute_trends()` and `execute_analyze()`):

```python
async def execute_predict_trends(
    self,
    topic: Optional[str] = None,
    window: str = "1w",
    lang: str = "auto",
    sources: Optional[list] = None,
    k_final: int = 5,
) -> BaseAnalysisResponse | ErrorResponse:
    """Execute /predict trends command"""
    # Copy pattern from execute_trends()
    # Set command = "/predict"
    # Pass topic in params
    pass

async def execute_analyze_competitors(
    self,
    domains: Optional[List[str]] = None,
    niche: Optional[str] = None,
    window: str = "1w",
    lang: str = "auto",
    sources: Optional[list] = None,
    k_final: int = 5,
) -> BaseAnalysisResponse | ErrorResponse:
    """Execute /analyze competitors command"""
    # Copy pattern from execute_trends()
    # Set command = "/competitors"
    # Pass domains/niche in params
    pass

async def execute_synthesize(
    self,
    agent_outputs: Dict[str, Any],
    docs: List[Dict[str, Any]],
    correlation_id: Optional[str] = None,
) -> BaseAnalysisResponse | ErrorResponse:
    """Execute /synthesize command"""
    # Simpler: no retrieval needed
    # Just format agent_outputs
    pass
```

---

## Task 3: Create Tests (6 hours)

### Unit Tests (4 hours)

```python
# tests/unit/test_trend_forecaster.py
def test_compute_ewma()
def test_determine_direction()
def test_estimate_confidence_interval()
async def test_run_trend_forecaster()
async def test_insufficient_data()
# ... 5 more tests

# tests/unit/test_competitor_news.py
def test_extract_domain()
def test_compute_jaccard_similarity()
def test_classify_stance()
async def test_run_competitor_news()
# ... 6 more tests

# tests/unit/test_synthesis_agent.py
def test_detect_conflicts()
def test_generate_actions()
async def test_run_synthesis_agent()
# ... 5 more tests

# tests/unit/test_phase2_schemas.py
def test_forecast_result_validation()
def test_competitors_result_validation()
def test_synthesis_result_validation()
def test_confidence_interval_validation()
# ... 8 more tests
```

### Integration Tests (2 hours)

```python
# tests/integration/test_predict_command.py
async def test_predict_trends_flow()
async def test_predict_with_topic()
async def test_predict_insufficient_data()
async def test_predict_error_handling()

# tests/integration/test_competitors_command.py
async def test_competitors_flow()
async def test_competitors_with_domains()
async def test_competitors_auto_detect()
async def test_competitors_no_data()

# tests/integration/test_synthesis_flow.py
async def test_synthesis_merges_agents()
async def test_synthesis_detects_conflicts()
async def test_synthesis_generates_actions()
async def test_synthesis_empty_inputs()
```

---

## Task 4: Bot Integration (1 hour)

**File**: `services/orchestrator.py`

```python
async def execute_predict_trends_command(
    user_query: str,
    topic: Optional[str] = None,
    window: str = "1w",
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """Execute /predict trends command"""
    # Similar to execute_trends_command()
    pass

async def execute_analyze_competitors_command(
    domains: List[str],
    window: str = "1w",
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """Execute /analyze competitors command"""
    # Similar to execute_analyze_command()
    pass
```

---

## Task 5: Documentation (2 hours)

### PHASE2_SPEC.md

```markdown
# Phase 2 Specification

## Commands

### /predict trends [topic] [window]
Forecast trend direction using EWMA + LLM narratives
- Input: topic (optional), window (1d-1m)
- Output: ForecastResult with direction, confidence, drivers

### /analyze competitors [domains|niche]
Analyze competitive landscape
- Input: domains (list) or niche (str)
- Output: CompetitorsResult with overlap, gaps, positioning

### /synthesize
Meta-analysis of multiple agent outputs
- Input: Previous agent results
- Output: SynthesisResult with conflicts and actions
```

### PHASE2_AGENTS.md

```markdown
# Phase 2 Agents Documentation

## TrendForecaster
- Purpose: Predict trend direction
- Algorithm: EWMA + slope analysis
- Model: GPT-5 → Claude 4.5
- Inputs: docs, topic, window
- Output: ForecastResult

## CompetitorNews
- Purpose: Competitive intelligence
- Algorithm: Jaccard similarity + stance classification
- Model: Claude 4.5 → GPT-5 → Gemini 2.5 Pro
- Inputs: docs, domains/niche
- Output: CompetitorsResult

## SynthesisAgent
- Purpose: Meta-analysis
- Algorithm: Conflict detection + recommendation generation
- Model: GPT-5 → Claude 4.5
- Inputs: agent_outputs, docs
- Output: SynthesisResult
```

---

## Validation Checklist

Before marking Phase 2 complete:

- [ ] All formatters implemented
- [ ] All orchestrator methods implemented
- [ ] 40 unit tests passing
- [ ] 12 integration tests passing
- [ ] 8 E2E tests passing
- [ ] Bot integration complete
- [ ] Documentation complete
- [ ] Phase 1 tests still passing (80 tests)
- [ ] No breaking changes
- [ ] Schemas validate
- [ ] Config loads correctly

**Total Tests**: 140 (80 Phase 1 + 60 Phase 2)

---

## Estimated Timeline

| Task | Hours | Cumulative |
|------|-------|------------|
| Format Node | 2 | 2 |
| Orchestrator | 3 | 5 |
| Unit Tests | 4 | 9 |
| Integration Tests | 2 | 11 |
| E2E Tests | 2 | 13 |
| Bot Integration | 1 | 14 |
| Documentation | 2 | 16 |

**Total**: 16 hours (2 days)

---

## Quick Commands

```bash
# Run Phase 1 tests (should still pass)
pytest tests/unit/ -v

# Run Phase 2 tests (once created)
pytest tests/unit/test_trend_forecaster.py -v
pytest tests/unit/test_competitor_news.py -v
pytest tests/unit/test_synthesis_agent.py -v

# Run all tests
pytest tests/ -v

# Check schema validation
python -c "from schemas.analysis_schemas import *; print('✅ Schemas valid')"

# Check config
python -c "from infra.config.phase2_config import get_phase2_config; print(get_phase2_config())"
```

---

**Status**: Ready to complete Phase 2 implementation. Follow this guide sequentially for fastest completion.
