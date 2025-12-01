# Universal Commercial Agent (UCA) Implementation Plan

## Phase 1: Architecture & Configuration (Completed)
- [x] Create directory structure (`uca/`, `uca/modules/`)
- [x] Define Product Categories and Emotion Matrix (`constants.py`)
- [x] Define Output JSON Schema (`schemas.py`)
- [x] Create Core Orchestrator Skeleton (`core.py`)

## Phase 2: Core Logic Modules (Completed)
- [x] **TrendAnalyzer**: Implemented with GPT-5.1 integration.
- [x] **PsychEngine**: Implemented with GPT-5.1 integration.
- [x] **ProductGenerator**: Implemented with GPT-5.1 integration.
- [ ] **MarketingGenerator**: Stub implemented. Needs full logic.
- [ ] **IPSafety**: Stub implemented. Needs full logic.

## Phase 3: Integration (Completed)
- [x] Connect UCA to `rssnews` SQLite database (`db_client.py`).
- [x] Create runner scripts (`run_simulation.py`, `run_on_db.py`).

## Phase 4: LLM Integration (Completed)
- [x] Implement `OpenAIClient` with Circuit Breaker and GPT-5.1 support.
- [x] Refactor modules to use `LLMClient`.
- [x] Verify with real DB data.

## Phase 5: Next Steps
- [x] Create Interactive Dashboard (`uca/dashboard.py`) with Word Cloud & Gauges.
- [x] Add Time Range Filter (1, 15, 30 days) to Dashboard.
- [x] Integrate Text Network Analysis (InfraNodus style) with `pyvis`.
- [x] Create Interactive Dashboard (`uca/dashboard.py`) with Word Cloud & Gauges.
- [x] Add Time Range Filter (1, 15, 30 days) to Dashboard.
- [x] Integrate Text Network Analysis (InfraNodus style) with `pyvis`.
- [x] Enhance Network Analysis with Betweenness Centrality & Structural Gaps.
- [x] **Implement AI Graph Insights (GraphRAG):** Use LLM to generate ideas bridging structural gaps.
- [x] **Add Sentiment Analysis:** Color nodes by sentiment (Positive/Negative) using `TextBlob`.
- [x] Implement `MarketingGenerator` (TikTok scripts, SEO).
- [ ] Implement `IPSafetyCheck`.
- [ ] Automate the pipeline (process new articles loop).
