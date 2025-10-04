"""
Phase 1-3 Analysis Schemas — Production-grade JSON contracts
Enforces strict validation for Phase 3 Agentic RAG, GraphRAG, Events, Memory
"""

from __future__ import annotations
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator
import re


# ============================================================================
# Evidence & Insights (базовые блоки для всех схем)
# ============================================================================

class EvidenceRef(BaseModel):
    """Reference to source article"""
    article_id: Optional[str] = None
    url: Optional[str] = None
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")  # YYYY-MM-DD

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v


class Evidence(BaseModel):
    """Source article with snippet"""
    title: str = Field(..., max_length=200)
    article_id: Optional[str] = None
    url: Optional[str] = None
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    snippet: str = Field(..., max_length=240)

    @field_validator('snippet')
    @classmethod
    def validate_snippet_length(cls, v: str) -> str:
        if len(v) > 240:
            raise ValueError("Snippet must be ≤ 240 characters")
        return v


class Insight(BaseModel):
    """Single insight with evidence"""
    type: Literal["fact", "hypothesis", "recommendation", "conflict", "causal"]
    text: str = Field(..., max_length=180)
    evidence_refs: List[EvidenceRef] = Field(..., min_length=1)  # REQUIRED

    @field_validator('text')
    @classmethod
    def validate_text_length(cls, v: str) -> str:
        if len(v) > 180:
            raise ValueError("Insight text must be ≤ 180 characters")
        return v

    @field_validator('evidence_refs')
    @classmethod
    def validate_evidence_required(cls, v: List[EvidenceRef]) -> List[EvidenceRef]:
        if not v:
            raise ValueError("At least 1 evidence_ref is required")
        return v


# ============================================================================
# Meta & Warnings
# ============================================================================

class Meta(BaseModel):
    """Metadata for all responses"""
    confidence: float = Field(..., ge=0.0, le=1.0)
    model: str
    version: str = "phase3-v1.0"
    correlation_id: str
    experiment: Optional[str] = None  # A/B test experiment name
    arm: Optional[Literal["A", "B"]] = None  # A/B test arm
    iterations: int = Field(default=1, ge=1)


class Warnings(BaseModel):
    """Warnings array"""
    warnings: List[str] = Field(default_factory=list)


# ============================================================================
# Base Response Skeleton (обязателен для всех команд)
# ============================================================================

class BaseAnalysisResponse(BaseModel):
    """Base response structure — unified skeleton for all commands"""
    header: str = Field(..., max_length=100)
    tldr: str = Field(..., max_length=220)
    insights: List[Insight] = Field(default_factory=list, max_length=5)  # Allow empty, up to 5
    evidence: List[Evidence] = Field(default_factory=list)  # Allow empty
    result: Dict[str, Any]  # Agent-specific, validated separately
    meta: Meta
    warnings: List[str] = Field(default_factory=list)

    @field_validator('tldr')
    @classmethod
    def validate_tldr_length(cls, v: str) -> str:
        if len(v) > 220:
            raise ValueError("TL;DR must be ≤ 220 characters")
        return v


# ============================================================================
# Agent-specific Result Schemas (Phase 1 & 2)
# ============================================================================

# --- KeyphraseMining ---

class Keyphrase(BaseModel):
    """Single extracted keyphrase"""
    phrase: str
    norm: str
    score: float = Field(..., ge=0.0, le=1.0)
    ngram: int = Field(..., ge=1, le=5)
    variants: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list, max_length=3)
    lang: Literal["ru", "en"]


class ExpansionHint(BaseModel):
    """Query expansion hints"""
    intents: List[Literal["informational", "navigational", "transactional", "research"]] = Field(default_factory=list, max_length=5)
    expansions: List[str] = Field(default_factory=list, max_length=8)
    negatives: Optional[List[str]] = Field(default=None, max_length=5)


class KeyphraseResult(BaseModel):
    """Result section for /analyze keywords"""
    keyphrases: List[Keyphrase] = Field(..., min_length=1, max_length=20)
    expansion_hint: Optional[ExpansionHint] = None


# --- SentimentEmotion ---

class EmotionScores(BaseModel):
    """Emotion breakdown"""
    joy: float = Field(..., ge=0.0, le=1.0)
    fear: float = Field(..., ge=0.0, le=1.0)
    anger: float = Field(..., ge=0.0, le=1.0)
    sadness: float = Field(..., ge=0.0, le=1.0)
    surprise: float = Field(..., ge=0.0, le=1.0)


class AspectSentiment(BaseModel):
    """Sentiment for specific aspect"""
    name: str = Field(..., max_length=50)
    score: float = Field(..., ge=-1.0, le=1.0)
    evidence_ref: EvidenceRef


class TimelineSentiment(BaseModel):
    """Sentiment over time window"""
    window: Literal["6h", "12h", "24h", "1d", "3d", "1w", "2w", "1m", "3m", "6m", "1y"]
    score: float = Field(..., ge=-1.0, le=1.0)
    n_docs: int = Field(..., ge=0)


class SentimentResult(BaseModel):
    """Result section for /analyze sentiment"""
    overall: float = Field(..., ge=-1.0, le=1.0)
    emotions: EmotionScores
    aspects: List[AspectSentiment] = Field(default_factory=list, max_length=10)
    timeline: List[TimelineSentiment] = Field(default_factory=list, max_length=12)


# --- TopicModeler ---

class Topic(BaseModel):
    """Topic cluster"""
    label: str = Field(..., max_length=80)
    terms: List[str] = Field(..., min_length=1, max_length=10)
    size: int = Field(..., ge=0)
    trend: Literal["rising", "falling", "stable"]


class TopicCluster(BaseModel):
    """Cluster metadata"""
    id: str
    doc_ids: List[str] = Field(default_factory=list)


class TopicsResult(BaseModel):
    """Result section for /analyze topics"""
    topics: List[Topic] = Field(..., min_length=1, max_length=15)
    clusters: List[TopicCluster] = Field(default_factory=list, max_length=20)
    emerging: List[str] = Field(default_factory=list, max_length=10)
    gaps: List[str] = Field(default_factory=list, max_length=10)


# --- TrendsEnhanced ---

class MomentumEntry(BaseModel):
    """Momentum for topic"""
    topic: str
    score: float = Field(..., ge=0.0, le=1.0)
    direction: Literal["up", "down", "flat"]


class TrendsResult(BaseModel):
    """Result section for /trends enhanced"""
    topics: List[Topic] = Field(..., min_length=1, max_length=15)
    sentiment: Dict[str, Any]
    top_sources: List[str] = Field(..., min_length=1, max_length=20)
    momentum: List[MomentumEntry] = Field(default_factory=list, max_length=10)


# --- Forecast Result ---

class ForecastDriver(BaseModel):
    """Driver signal for forecast"""
    signal: str = Field(..., max_length=80)
    rationale: str = Field(..., max_length=180)
    evidence_ref: EvidenceRef


class ForecastEntry(BaseModel):
    """Forecast entry"""
    topic: str
    direction: Literal["up", "down", "flat"]
    confidence_interval: List[float] = Field(..., min_length=2, max_length=2)
    drivers: List[ForecastDriver] = Field(default_factory=list, max_length=5)
    horizon: Literal["6h", "12h", "1d", "3d", "1w", "2w", "1m"]

    @model_validator(mode="after")
    def validate_interval(cls, values: "ForecastEntry") -> "ForecastEntry":
        low, high = values.confidence_interval
        if not (0.0 <= low <= high <= 1.0):
            raise ValueError("confidence_interval must be within [0, 1] and non-decreasing")
        return values
class ForecastResult(BaseModel):
    """Result section for /predict trends"""
    forecast: List[ForecastEntry] = Field(..., min_length=1, max_length=10)


# --- Competitors Result ---

class OverlapMatrix(BaseModel):
    """Topic overlap per domain"""
    domain: str
    topic: str
    overlap_score: float = Field(..., ge=0.0, le=1.0)


class PositioningItem(BaseModel):
    """Competitor positioning item"""
    domain: str
    stance: Literal["leader", "fast_follower", "niche"]
    notes: str = Field(..., max_length=180)


class SentimentDelta(BaseModel):
    """Sentiment difference between domains"""
    domain: str = Field(..., max_length=100)
    delta: float = Field(..., ge=-2.0, le=2.0)


class CompetitorsResult(BaseModel):
    """Result section for /analyze competitors"""
    overlap_matrix: List[OverlapMatrix] = Field(..., max_length=20)
    gaps: List[str] = Field(default_factory=list, max_length=5)
    positioning: List[PositioningItem] = Field(..., min_length=1, max_length=10)
    sentiment_delta: List[SentimentDelta] = Field(default_factory=list, max_length=10)
    top_domains: List[str] = Field(..., min_length=1, max_length=10)


# --- SynthesisAgent (/synthesize Phase 2) ---

class Conflict(BaseModel):
    """Detected conflict between agent outputs"""
    description: str = Field(..., max_length=180)
    evidence_refs: List[EvidenceRef] = Field(..., min_length=2)


class Action(BaseModel):
    """Actionable recommendation"""
    recommendation: str = Field(..., max_length=180)
    impact: Literal["low", "medium", "high"]
    evidence_refs: List[EvidenceRef] = Field(..., min_length=1)


class SynthesisResult(BaseModel):
    """Result section for /synthesize"""
    summary: str = Field(..., max_length=400)
    conflicts: List[Conflict] = Field(default_factory=list, max_length=3)
    actions: List[Action] = Field(..., min_length=1, max_length=5)

    @field_validator('summary')
    @classmethod
    def validate_summary_length(cls, v: str) -> str:
        if len(v) > 400:
            raise ValueError("Summary must be ≤ 400 characters")
        return v


# ============================================================================
# Phase 3 Result Schemas
# ============================================================================

class AgenticStep(BaseModel):
    """Iteration step for agentic RAG"""
    iteration: int = Field(..., ge=1, le=3)
    query: str = Field(..., max_length=180)
    n_docs: int = Field(..., ge=0)
    reason: str = Field(..., max_length=200)


class AgenticResult(BaseModel):
    """Result section for /ask --depth=deep"""
    steps: List[AgenticStep] = Field(..., min_length=1, max_length=3)
    answer: str = Field(..., max_length=600)
    followups: List[str] = Field(default_factory=list, max_length=5)


class EventRecord(BaseModel):
    """Event extracted from docs"""
    id: str
    title: str = Field(..., max_length=160)
    ts_range: List[str] = Field(..., min_length=2, max_length=2)
    entities: List[str] = Field(default_factory=list, max_length=10)
    docs: List[str] = Field(default_factory=list, min_length=1)


class TimelineRelation(BaseModel):
    """Timeline relationship between events"""
    event_id: str
    position: Literal["before", "after", "overlap"]
    ref_event_id: str


class CausalLink(BaseModel):
    """Cause-effect relation between events"""
    cause_event_id: str
    effect_event_id: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_refs: List[EvidenceRef] = Field(..., min_length=1)


class EventsResult(BaseModel):
    """Result section for /events link"""
    events: List[EventRecord] = Field(..., min_length=1, max_length=20)
    timeline: List[TimelineRelation] = Field(default_factory=list, max_length=20)
    causal_links: List[CausalLink] = Field(default_factory=list, max_length=20)


class GraphNode(BaseModel):
    """Node in knowledge graph"""
    id: str
    label: str = Field(..., max_length=120)
    type: Literal["entity", "article", "topic"]


class GraphEdge(BaseModel):
    """Edge in knowledge graph"""
    src: str
    tgt: str
    type: Literal["mentions", "relates_to", "influences"]
    weight: float = Field(..., ge=0.0, le=1.0)


class GraphPath(BaseModel):
    """Path between nodes"""
    nodes: List[str] = Field(..., min_length=2, max_length=10)
    hops: int = Field(..., ge=1, le=4)
    score: float = Field(..., ge=0.0, le=1.0)


class GraphResult(BaseModel):
    """Result section for /graph query"""
    subgraph: Dict[str, List[Any]]
    paths: List[GraphPath] = Field(default_factory=list, max_length=10)
    answer: str = Field(..., max_length=600)

    @model_validator(mode="after")
    def validate_subgraph(cls, values: 'GraphResult') -> 'GraphResult':
        subgraph = values.subgraph
        if "nodes" not in subgraph or "edges" not in subgraph:
            raise ValueError("subgraph must contain 'nodes' and 'edges'")
        return values


class MemorySuggestion(BaseModel):
    """Suggestion for memory storage"""
    type: Literal["episodic", "semantic"]
    content: str = Field(..., max_length=200)
    importance: float = Field(..., ge=0.0, le=1.0)
    ttl_days: int = Field(..., ge=0, le=365)


class MemoryStoreItem(BaseModel):
    """Normalized memory item to store"""
    type: Literal["episodic", "semantic"]
    content: str = Field(..., max_length=240)
    refs: List[str] = Field(default_factory=list, max_length=10)
    ttl_days: int = Field(..., ge=0, le=365)


class MemoryRecord(BaseModel):
    """Retrieved memory record"""
    id: str
    type: Literal["episodic", "semantic"]
    content: str = Field(..., max_length=240)
    ts: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    refs: List[str] = Field(default_factory=list, max_length=10)


class MemoryResult(BaseModel):
    """Result section for /memory operations"""
    operation: Literal["suggest", "store", "recall"]
    suggestions: List[MemorySuggestion] = Field(default_factory=list, max_length=10)
    to_store: List[MemoryStoreItem] = Field(default_factory=list, max_length=10)
    records: List[MemoryRecord] = Field(default_factory=list, max_length=10)


# ============================================================================
# Error Response Schema
# ============================================================================

class ErrorDetail(BaseModel):
    """Error detail structure"""
    code: Literal["VALIDATION_FAILED", "NO_DATA", "BUDGET_EXCEEDED", "MODEL_UNAVAILABLE", "INTERNAL"]
    user_message: str = Field(..., max_length=500)  # Increased from 200 to 500
    tech_message: str = Field(..., max_length=1000)  # Increased from 500 to 1000
    retryable: bool


class ErrorResponse(BaseModel):
    """Error response for all failures"""
    error: ErrorDetail
    meta: Meta


# ============================================================================
# Input Context Schema (что передаётся в промпт)
# ============================================================================

class RetrievalContext(BaseModel):
    """Retrieval context passed to agents"""
    docs: List[Dict[str, Any]]
    window: Literal["6h", "12h", "24h", "1d", "3d", "1w", "2w", "1m", "3m", "6m", "1y"]
    lang: Literal["ru", "en", "auto"]
    sources: Optional[List[str]] = None
    k_final: int = Field(..., ge=1, le=10)


class ModelConfig(BaseModel):
    """Model configuration"""
    primary: str
    fallback: List[str] = Field(default_factory=list)


class LimitsConfig(BaseModel):
    """Budget and limits"""
    max_tokens: int = Field(..., ge=100, le=16000)
    budget_cents: int = Field(..., ge=0)
    timeout_s: int = Field(default=12, ge=1, le=60)


class TelemetryConfig(BaseModel):
    """Telemetry settings"""
    correlation_id: str
    version: str = "phase3-v1.0"


class AnalysisInputContext(BaseModel):
    """Full input context passed to orchestrator"""
    command: Literal[
        "/trends",
        "/analyze",
        "/predict",
        "/competitors",
        "/synthesize",
        "/ask",
        "/events",
        "/graph",
        "/memory"
    ]
    params: Dict[str, Any]
    retrieval: RetrievalContext
    models: ModelConfig
    limits: LimitsConfig
    telemetry: TelemetryConfig


# ============================================================================
# Validation Helpers
# ============================================================================

class PolicyValidator:
    """Static validators for policy layer"""

    PII_PATTERNS = [
        r'\b\d{3}-\d{2}-\d{4}\b',
        r'\b\d{16}\b',
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        r'\b\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b',
    ]

    DOMAIN_BLACKLIST = [
        'spam.com', 'phishing.net', 'malware.org'
    ]

    @staticmethod
    def contains_pii(text: str) -> bool:
        for pattern in PolicyValidator.PII_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def is_safe_domain(url: Optional[str]) -> bool:
        if not url:
            return True
        for domain in PolicyValidator.DOMAIN_BLACKLIST:
            if domain in url.lower():
                return False
        return True

    @staticmethod
    def validate_evidence_required(insights: List[Insight]) -> None:
        # Only validate if insights exist
        if not insights:
            return
        for insight in insights:
            if not insight.evidence_refs:
                raise ValueError(f"Insight '{insight.text}' missing required evidence_refs")

    @staticmethod
    def validate_all_evidence_safe(evidence: List[Evidence]) -> None:
        # Only validate if evidence exists
        if not evidence:
            return
        for ev in evidence:
            if not PolicyValidator.is_safe_domain(ev.url):
                raise ValueError(f"Evidence from blacklisted domain: {ev.url}")
            if PolicyValidator.contains_pii(ev.snippet):
                raise ValueError(f"Evidence snippet contains PII: {ev.title}")


# ============================================================================
# Response Builders
# ============================================================================

def build_base_response(
    header: str,
    tldr: str,
    insights: List[Insight],
    evidence: List[Evidence],
    result: Dict[str, Any],
    meta: Meta,
    warnings: Optional[List[str]] = None
) -> BaseAnalysisResponse:
    return BaseAnalysisResponse(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=result,
        meta=meta,
        warnings=warnings or []
    )


def build_error_response(
    code: Literal["VALIDATION_FAILED", "NO_DATA", "BUDGET_EXCEEDED", "MODEL_UNAVAILABLE", "INTERNAL"],
    user_message: str,
    tech_message: str,
    retryable: bool,
    meta: Meta
) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorDetail(
            code=code,
            user_message=user_message,
            tech_message=tech_message,
            retryable=retryable
        ),
        meta=meta
    )
# Backwards compatibility aliases (Phase 1/2 names)
class ForecastItem(ForecastEntry):
    """Deprecated alias maintained for Phase 2 tests."""
    pass


class KeyphraseMiningResult(KeyphraseResult):
    """Deprecated alias maintained for Phase 2 tests."""
    pass
class SentimentEmotionResult(SentimentResult):
    """Deprecated alias maintained for Phase 2 tests."""
    pass


class TopicModelResult(TopicsResult):
    """Deprecated alias maintained for Phase 2 tests."""
    pass


class TrendsEnhancedResult(TrendsResult):
    """Deprecated alias maintained for Phase 2 tests."""
    pass
class TopicModelerResult(TopicsResult):
    """Deprecated alias maintained for Phase 2 tests."""
    pass
