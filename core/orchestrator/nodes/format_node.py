"""
Format Node — Fourth step: build BaseAnalysisResponse from agent results
Assembles header, TL;DR, insights, evidence, result sections
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from schemas.analysis_schemas import (
    BaseAnalysisResponse, Insight, Evidence, EvidenceRef, Meta,
    build_base_response, build_error_response
)

logger = logging.getLogger(__name__)


async def format_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute format step

    Input state:
        - command: str
        - params: Dict
        - docs: List[Dict]
        - agent_results: Dict[str, Any]
        - correlation_id: str

    Output state (adds):
        - response_draft: BaseAnalysisResponse
    """
    try:
        command = state.get("command")
        params = state.get("params", {})
        docs = state.get("docs", [])
        agent_results = state.get("agent_results", {})
        correlation_id = state.get("correlation_id", "unknown")

        logger.info(f"Format node: building response for {command}")

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

        state["response_draft"] = response

        logger.info(f"Format node completed: response built")

        return state

    except Exception as e:
        logger.error(f"Format node failed: {e}", exc_info=True)
        state["error"] = {
            "node": "format",
            "code": "INTERNAL",
            "message": f"Failed to format response: {e}"
        }
        return state


def _format_trends_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format /trends enhanced response"""

    # Extract agent results
    topics_result = agent_results.get("topic_modeler", {})
    sentiment_result = agent_results.get("sentiment_emotion", {})

    # Build header
    window = params.get("window", "24h")
    header = f"Trends for {window}"

    # Build TL;DR (max 220 chars)
    topics = topics_result.get("topics", [])
    sentiment_overall = sentiment_result.get("overall", 0.0)

    tldr = f"Identified {len(topics)} main topics. Overall sentiment: {_sentiment_label(sentiment_overall)}. "
    if topics:
        top_topic = topics[0].get("label", "General")
        tldr += f"Top trend: {top_topic}."
    tldr = tldr[:220]

    # Build insights (3-5 bullets with evidence)
    insights = _build_trends_insights(topics, sentiment_result, docs)

    # Build evidence from docs
    evidence = _build_evidence_list(docs[:5])

    # Build result section (combined topics + sentiment)
    result = {
        "topics": topics_result.get("topics", []),
        "sentiment": {
            "overall": sentiment_overall,
            "emotions": sentiment_result.get("emotions", {})
        },
        "top_sources": _extract_top_sources(docs[:10]),
        "emerging": topics_result.get("emerging", []),
        "gaps": topics_result.get("gaps", [])
    }

    # Build meta
    model_used = topics_result.get("model_used", "unknown")
    confidence = _calculate_confidence(agent_results)
    warnings = topics_result.get("warnings", []) + sentiment_result.get("warnings", [])

    meta = Meta(
        confidence=confidence,
        model=model_used,
        version="phase1-v1.0",
        correlation_id=correlation_id
    )

    # Build response
    return build_base_response(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=result,
        meta=meta,
        warnings=warnings
    )


def _format_analyze_response(
    mode: str,
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format /analyze response based on mode"""

    if mode == "keywords":
        return _format_keywords_response(docs, agent_results, correlation_id, params)
    elif mode == "sentiment":
        return _format_sentiment_response(docs, agent_results, correlation_id, params)
    elif mode == "topics":
        return _format_topics_response(docs, agent_results, correlation_id, params)
    else:
        raise ValueError(f"Unknown analyze mode: {mode}")


def _format_keywords_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format keywords analysis"""

    keyphrase_result = agent_results.get("keyphrase_mining", {})
    expansion_result = agent_results.get("query_expansion", {})

    keyphrases = keyphrase_result.get("keyphrases", [])

    # Header
    header = "Keyphrase Analysis"

    # TL;DR
    tldr = f"Extracted {len(keyphrases)} key phrases from {len(docs)} articles. "
    if keyphrases:
        top_phrases = [kp["phrase"] for kp in keyphrases[:3]]
        tldr += f"Top: {', '.join(top_phrases)}."
    tldr = tldr[:220]

    # Insights
    insights = _build_keyphrase_insights(keyphrases, docs)

    # Evidence
    evidence = _build_evidence_list(docs[:5])

    # Result
    result = {
        "keyphrases": keyphrases,
        "expansion_hint": expansion_result if expansion_result.get("success") else None
    }

    # Meta
    model_used = keyphrase_result.get("model_used", "unknown")
    meta = Meta(
        confidence=0.85,
        model=model_used,
        version="phase1-v1.0",
        correlation_id=correlation_id
    )

    return build_base_response(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=result,
        meta=meta,
        warnings=keyphrase_result.get("warnings", [])
    )


def _format_sentiment_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format sentiment analysis"""

    sentiment_result = agent_results.get("sentiment_emotion", {})
    overall = sentiment_result.get("overall", 0.0)
    emotions = sentiment_result.get("emotions", {})

    # Header
    header = "Sentiment Analysis"

    # TL;DR
    sentiment_label = _sentiment_label(overall)
    dominant_emotion = max(emotions.items(), key=lambda x: x[1])[0] if emotions else "neutral"
    tldr = f"Overall sentiment: {sentiment_label} ({overall:+.2f}). Dominant emotion: {dominant_emotion}."
    tldr = tldr[:220]

    # Insights
    insights = _build_sentiment_insights(sentiment_result, docs)

    # Evidence
    evidence = _build_evidence_list(docs[:5])

    # Result
    result = {
        "overall": overall,
        "emotions": emotions,
        "aspects": sentiment_result.get("aspects", []),
        "timeline": sentiment_result.get("timeline", [])
    }

    # Meta
    model_used = sentiment_result.get("model_used", "unknown")
    meta = Meta(
        confidence=0.82,
        model=model_used,
        version="phase1-v1.0",
        correlation_id=correlation_id
    )

    return build_base_response(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=result,
        meta=meta,
        warnings=sentiment_result.get("warnings", [])
    )


def _format_topics_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format topics analysis"""

    topics_result = agent_results.get("topic_modeler", {})
    topics = topics_result.get("topics", [])

    # Header
    header = "Topic Analysis"

    # TL;DR
    tldr = f"Identified {len(topics)} main topics across {len(docs)} articles. "
    if topics:
        top_topic = topics[0].get("label", "")
        tldr += f"Primary topic: {top_topic}."
    tldr = tldr[:220]

    # Insights
    insights = _build_topic_insights(topics, docs)

    # Evidence
    evidence = _build_evidence_list(docs[:5])

    # Result
    result = {
        "topics": topics,
        "clusters": topics_result.get("clusters", []),
        "emerging": topics_result.get("emerging", []),
        "gaps": topics_result.get("gaps", [])
    }

    # Meta
    model_used = topics_result.get("model_used", "unknown")
    meta = Meta(
        confidence=0.88,
        model=model_used,
        version="phase1-v1.0",
        correlation_id=correlation_id
    )

    return build_base_response(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=result,
        meta=meta,
        warnings=topics_result.get("warnings", [])
    )


# Helper functions

def _build_trends_insights(
    topics: List[Dict],
    sentiment_result: Dict,
    docs: List[Dict]
) -> List[Insight]:
    """Build insights for trends"""
    insights = []

    # Insight 1: Top topic
    if topics:
        top = topics[0]
        insights.append(Insight(
            type="fact",
            text=f"{top['label']}: {top['size']} articles, trend {top['trend']}",
            evidence_refs=[_doc_to_evidence_ref(docs[0])] if docs else []
        ))

    # Insight 2: Sentiment
    if sentiment_result:
        overall = sentiment_result.get("overall", 0.0)
        insights.append(Insight(
            type="fact",
            text=f"Overall sentiment is {_sentiment_label(overall)} ({overall:+.2f})",
            evidence_refs=[_doc_to_evidence_ref(docs[0])] if docs else []
        ))

    # Insight 3: Emerging topic
    emerging = [t for t in topics if t.get("trend") == "rising"]
    if emerging:
        insights.append(Insight(
            type="hypothesis",
            text=f"Emerging trend: {emerging[0]['label']}",
            evidence_refs=[_doc_to_evidence_ref(docs[1])] if len(docs) > 1 else [_doc_to_evidence_ref(docs[0])]
        ))

    # Ensure at least 1 insight
    if not insights and docs:
        insights.append(Insight(
            type="fact",
            text=f"Analyzed {len(docs)} recent articles",
            evidence_refs=[_doc_to_evidence_ref(docs[0])]
        ))

    return insights[:5]


def _build_keyphrase_insights(keyphrases: List[Dict], docs: List[Dict]) -> List[Insight]:
    """Build insights for keyphrases"""
    insights = []

    # Top 3 keyphrases as insights
    for i, kp in enumerate(keyphrases[:3]):
        phrase = kp.get("phrase", "")
        score = kp.get("score", 0.0)
        insights.append(Insight(
            type="fact",
            text=f"Key phrase: '{phrase}' (score: {score:.2f})",
            evidence_refs=[_doc_to_evidence_ref(docs[min(i, len(docs)-1)])] if docs else []
        ))

    return insights[:5]


def _build_sentiment_insights(sentiment_result: Dict, docs: List[Dict]) -> List[Insight]:
    """Build insights for sentiment"""
    insights = []

    overall = sentiment_result.get("overall", 0.0)
    emotions = sentiment_result.get("emotions", {})

    # Overall sentiment
    insights.append(Insight(
        type="fact",
        text=f"Overall sentiment: {_sentiment_label(overall)} ({overall:+.2f})",
        evidence_refs=[_doc_to_evidence_ref(docs[0])] if docs else []
    ))

    # Top emotion
    if emotions:
        top_emotion = max(emotions.items(), key=lambda x: x[1])
        insights.append(Insight(
            type="fact",
            text=f"Dominant emotion: {top_emotion[0]} ({top_emotion[1]:.2f})",
            evidence_refs=[_doc_to_evidence_ref(docs[1])] if len(docs) > 1 else [_doc_to_evidence_ref(docs[0])]
        ))

    # Aspects (if available)
    aspects = sentiment_result.get("aspects", [])
    for aspect in aspects[:2]:
        name = aspect.get("name", "")
        score = aspect.get("score", 0.0)
        insights.append(Insight(
            type="fact",
            text=f"{name}: {_sentiment_label(score)} ({score:+.2f})",
            evidence_refs=[aspect.get("evidence_ref")] if aspect.get("evidence_ref") else [_doc_to_evidence_ref(docs[0])]
        ))

    return insights[:5]


def _build_topic_insights(topics: List[Dict], docs: List[Dict]) -> List[Insight]:
    """Build insights for topics"""
    insights = []

    # Top 3 topics
    for i, topic in enumerate(topics[:3]):
        label = topic.get("label", "")
        size = topic.get("size", 0)
        trend = topic.get("trend", "stable")
        insights.append(Insight(
            type="fact",
            text=f"{label}: {size} articles, {trend} trend",
            evidence_refs=[_doc_to_evidence_ref(docs[min(i, len(docs)-1)])] if docs else []
        ))

    return insights[:5]


def _build_evidence_list(docs: List[Dict]) -> List[Evidence]:
    """Build evidence list from documents"""
    evidence_list = []

    for doc in docs[:5]:  # Max 5 evidence items
        evidence_list.append(Evidence(
            title=doc.get("title", "")[:200],
            article_id=doc.get("article_id"),
            url=doc.get("url"),
            date=doc.get("date", ""),
            snippet=doc.get("snippet", "")[:240]
        ))

    return evidence_list


def _doc_to_evidence_ref(doc: Dict) -> EvidenceRef:
    """Convert doc to evidence reference"""
    return EvidenceRef(
        article_id=doc.get("article_id"),
        url=doc.get("url"),
        date=doc.get("date", "2025-01-01")
    )


def _sentiment_label(score: float) -> str:
    """Convert sentiment score to label"""
    if score > 0.3:
        return "positive"
    elif score < -0.3:
        return "negative"
    else:
        return "neutral"


def _extract_top_sources(docs: List[Dict]) -> List[str]:
    """Extract unique source domains"""
    sources = []
    seen = set()

    for doc in docs:
        url = doc.get("url", "")
        if url:
            # Extract domain
            from urllib.parse import urlparse
            try:
                domain = urlparse(url).netloc
                if domain and domain not in seen:
                    sources.append(domain)
                    seen.add(domain)
            except:
                pass

    return sources[:10]


def _calculate_confidence(agent_results: Dict[str, Any]) -> float:
    """Calculate overall confidence from agent results"""
    # Simple heuristic: if all agents succeeded, high confidence
    successful = sum(1 for r in agent_results.values() if r.get("success", True))
    total = len(agent_results)

    if total == 0:
        return 0.5

    return 0.5 + (successful / total) * 0.4  # Range: 0.5-0.9


# ============================================================================
# Phase 2: NEW Formatters
# ============================================================================

def _format_forecast_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format /predict trends response (Phase 2)"""

    forecast_result = agent_results.get("trend_forecaster", {})
    forecast_items = forecast_result.get("forecast", [])

    if not forecast_items:
        raise ValueError("No forecast data available")

    forecast_item = forecast_items[0]
    direction = forecast_item.get("direction", "flat")
    topic = forecast_item.get("topic", "general")

    # Build header
    direction_emoji = {"up": "📈", "down": "📉", "flat": "➡️"}
    header = f"{direction_emoji.get(direction, '📊')} Trend Forecast: {topic}"[:100]

    # Build TL;DR
    ci = forecast_item.get("confidence_interval", [0.4, 0.6])
    tldr = f"Forecast indicates {direction} trend for {topic} (confidence: {ci[0]:.1f}-{ci[1]:.1f})"[:220]

    # Build insights from drivers
    insights = []
    drivers = forecast_item.get("drivers", [])
    for driver in drivers[:3]:  # Max 3 insights
        evidence_ref_data = driver.get("evidence_ref", {})
        insight = Insight(
            type="hypothesis" if direction == "flat" else "fact",
            text=driver.get("rationale", "")[:180],
            evidence_refs=[EvidenceRef(
                article_id=evidence_ref_data.get("article_id"),
                url=evidence_ref_data.get("url"),
                date=evidence_ref_data.get("date", "2025-09-30")
            )]
        )
        insights.append(insight)

    # Ensure at least 1 insight
    if not insights and docs:
        insights.append(Insight(
            type="fact",
            text=f"Forecast based on {len(docs)} articles",
            evidence_refs=[_doc_to_evidence_ref(docs[0])]
        ))

    # Build evidence
    evidence = _build_evidence_list(docs[:5])

    # Build meta
    meta = Meta(
        confidence=0.5 + (abs(ci[1] - ci[0]) / 2),
        model="gpt-5",
        version="phase2-v1.0",
        correlation_id=correlation_id
    )

    return build_base_response(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=forecast_result,
        meta=meta
    )


def _format_competitors_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format /analyze competitors response (Phase 2) with degradation support"""

    competitors_result = agent_results.get("competitor_news", {})
    positioning = competitors_result.get("positioning", [])
    gaps = competitors_result.get("gaps", [])
    overlap_matrix = competitors_result.get("overlap_matrix", [])

    # DEGRADATION: If budget constraints, simplify overlap matrix to top 5
    if len(overlap_matrix) > 5:
        competitors_result["overlap_matrix"] = overlap_matrix[:5]
        logger.warning(f"Degradation applied: limiting overlap_matrix to top 5 (was {len(overlap_matrix)})")

    # Build header
    header = f"🏆 Competitive Analysis: {len(positioning)} domains"[:100]

    # Build TL;DR
    leader_domains = [p["domain"] for p in positioning if p.get("stance") == "leader"]
    tldr = f"Analysis of {len(positioning)} competitors. Leaders: {', '.join(leader_domains[:2])}"[:220]

    # Build insights
    insights = []

    # Insight 1-2: Positioning
    for pos in positioning[:2]:
        insight = Insight(
            type="fact",
            text=f"{pos['domain']}: {pos['stance']} - {pos['notes']}"[:180],
            evidence_refs=[_doc_to_evidence_ref(docs[0])] if docs else []
        )
        insights.append(insight)

    # Insight 3: Gaps
    if gaps:
        insight = Insight(
            type="recommendation",
            text=f"Coverage gaps identified: {', '.join(gaps[:3])}"[:180],
            evidence_refs=[_doc_to_evidence_ref(docs[1])] if len(docs) > 1 else [_doc_to_evidence_ref(docs[0])] if docs else []
        )
        insights.append(insight)

    # Ensure at least 1 insight
    if not insights and docs:
        insights.append(Insight(
            type="fact",
            text=f"Analyzed {len(docs)} articles across domains",
            evidence_refs=[_doc_to_evidence_ref(docs[0])]
        ))

    # Build evidence
    evidence = _build_evidence_list(docs[:5])

    # Build meta
    meta = Meta(
        confidence=0.75,
        model="claude-4.5",
        version="phase2-v1.0",
        correlation_id=correlation_id
    )

    return build_base_response(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=competitors_result,
        meta=meta
    )


def _format_synthesis_response(
    docs: List[Dict[str, Any]],
    agent_results: Dict[str, Any],
    correlation_id: str,
    params: Dict[str, Any]
) -> BaseAnalysisResponse:
    """Format /synthesize response (Phase 2)"""

    synthesis_result = agent_results.get("synthesis_agent", {})
    summary = synthesis_result.get("summary", "")
    conflicts = synthesis_result.get("conflicts", [])
    actions = synthesis_result.get("actions", [])

    # Build header
    header = f"🔗 Synthesis: {len(actions)} Actions"[:100]

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

    # Actions as insights (max 3 more to stay within 5 total)
    remaining_slots = 5 - len(insights)
    for action in actions[:remaining_slots]:
        insight = Insight(
            type="recommendation",
            text=action.get("recommendation", "")[:180],
            evidence_refs=action.get("evidence_refs", [])
        )
        insights.append(insight)

    # Ensure at least 1 insight
    if not insights and docs:
        insights.append(Insight(
            type="fact",
            text="Synthesis complete across multiple agents",
            evidence_refs=[_doc_to_evidence_ref(docs[0])]
        ))

    # Build evidence
    evidence = _build_evidence_list(docs[:5])

    # Build meta
    meta = Meta(
        confidence=0.8,
        model="gpt-5",
        version="phase2-v1.0",
        correlation_id=correlation_id
    )

    return build_base_response(
        header=header,
        tldr=tldr,
        insights=insights,
        evidence=evidence,
        result=synthesis_result,
        meta=meta
    )