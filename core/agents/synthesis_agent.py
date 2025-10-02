"""
SynthesisAgent — Phase 2: Merge multiple agent outputs, resolve conflicts, generate actionable recommendations
Primary: gpt-5, Fallback: claude-4.5
"""

import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


SYNTHESIS_SYSTEM_PROMPT = """You are a meta-analysis expert that synthesizes insights from multiple AI agents.

TASK: Merge outputs from multiple analysis agents, identify conflicts, and produce actionable recommendations.

INPUT:
- Agent outputs (topics, sentiment, forecast, competitors)
- Source articles for evidence linking

OUTPUT FORMAT (strict JSON):
{
  "summary": "concise executive summary (≤ 400 chars)",
  "conflicts": [
    {
      "description": "description of conflict (≤ 180 chars)",
      "evidence_refs": [
        { "article_id": "...", "url": "...", "date": "YYYY-MM-DD" },
        { "article_id": "...", "url": "...", "date": "YYYY-MM-DD" }
      ]
    }
  ],
  "actions": [
    {
      "recommendation": "actionable recommendation (≤ 180 chars)",
      "impact": "low|medium|high",
      "evidence_refs": [
        { "article_id": "...", "url": "...", "date": "YYYY-MM-DD" }
      ]
    }
  ]
}

RULES:
1. summary: 1-2 sentences summarizing key findings (max 400 chars)
2. conflicts: ONLY report if contradictory evidence exists (e.g., negative sentiment + rising trend)
3. Each conflict needs ≥2 evidence_refs from different sources
4. actions: 1-5 specific, actionable recommendations
5. impact: "low" = informational, "medium" = tactical, "high" = strategic
6. Every action MUST have at least 1 evidence_ref
7. Do NOT hallucinate conflicts—only report real contradictions
8. Return ONLY valid JSON, no additional text
"""


def detect_conflicts(
    agent_outputs: Dict[str, Any],
    docs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Detect conflicts between agent outputs

    Args:
        agent_outputs: Dict with results from multiple agents
        docs: Source articles for evidence

    Returns:
        List of conflict dicts
    """
    conflicts = []

    # Conflict 1: Negative sentiment but rising trend
    sentiment_result = agent_outputs.get("sentiment_emotion", {})
    forecast_result = agent_outputs.get("trend_forecaster", {})

    if sentiment_result and forecast_result:
        overall_sentiment = sentiment_result.get("overall", 0.0)
        forecast_items = forecast_result.get("forecast", [])

        if forecast_items:
            forecast_direction = forecast_items[0].get("direction", "flat")

            # Conflict: negative sentiment + upward trend
            if overall_sentiment < -0.2 and forecast_direction == "up":
                conflicts.append({
                    "description": "Negative sentiment detected despite upward trend forecast",
                    "evidence_refs": [
                        {
                            "article_id": docs[0].get("article_id") if docs else None,
                            "url": docs[0].get("url") if docs else None,
                            "date": docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                        },
                        {
                            "article_id": docs[1].get("article_id") if len(docs) > 1 else docs[0].get("article_id") if docs else None,
                            "url": docs[1].get("url") if len(docs) > 1 else docs[0].get("url") if docs else None,
                            "date": docs[1].get("date", "2025-09-30") if len(docs) > 1 else docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                        }
                    ]
                })

            # Conflict: positive sentiment + downward trend
            if overall_sentiment > 0.2 and forecast_direction == "down":
                conflicts.append({
                    "description": "Positive sentiment observed but trend forecast indicates decline",
                    "evidence_refs": [
                        {
                            "article_id": docs[0].get("article_id") if docs else None,
                            "url": docs[0].get("url") if docs else None,
                            "date": docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                        },
                        {
                            "article_id": docs[1].get("article_id") if len(docs) > 1 else docs[0].get("article_id") if docs else None,
                            "url": docs[1].get("url") if len(docs) > 1 else docs[0].get("url") if docs else None,
                            "date": docs[1].get("date", "2025-09-30") if len(docs) > 1 else docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                        }
                    ]
                })

    # Conflict 2: Topic divergence (topics claim rising, but sentiment says falling)
    topics_result = agent_outputs.get("topic_modeler", {})
    if topics_result and sentiment_result:
        topics = topics_result.get("topics", [])
        rising_topics = [t for t in topics if t.get("trend") == "rising"]

        overall_sentiment = sentiment_result.get("overall", 0.0)

        if len(rising_topics) > 0 and overall_sentiment < -0.3:
            conflicts.append({
                "description": "Rising topics detected but overall sentiment is strongly negative",
                "evidence_refs": [
                    {
                        "article_id": docs[0].get("article_id") if docs else None,
                        "url": docs[0].get("url") if docs else None,
                        "date": docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                    },
                    {
                        "article_id": docs[2].get("article_id") if len(docs) > 2 else docs[0].get("article_id") if docs else None,
                        "url": docs[2].get("url") if len(docs) > 2 else docs[0].get("url") if docs else None,
                        "date": docs[2].get("date", "2025-09-30") if len(docs) > 2 else docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                    }
                ]
            })

    return conflicts[:3]  # Max 3 conflicts


def generate_actions(
    agent_outputs: Dict[str, Any],
    docs: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate actionable recommendations

    Args:
        agent_outputs: Dict with results from multiple agents
        docs: Source articles for evidence
        conflicts: Detected conflicts

    Returns:
        List of action dicts
    """
    actions = []

    # Action 1: Based on forecast
    forecast_result = agent_outputs.get("trend_forecaster", {})
    if forecast_result:
        forecast_items = forecast_result.get("forecast", [])
        if forecast_items:
            direction = forecast_items[0].get("direction", "flat")

            if direction == "up":
                actions.append({
                    "recommendation": "Monitor upward trend closely; consider increasing coverage or investment",
                    "impact": "medium",
                    "evidence_refs": [
                        {
                            "article_id": docs[0].get("article_id") if docs else None,
                            "url": docs[0].get("url") if docs else None,
                            "date": docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                        }
                    ]
                })
            elif direction == "down":
                actions.append({
                    "recommendation": "Trend declining; assess need for repositioning or strategic pivot",
                    "impact": "high",
                    "evidence_refs": [
                        {
                            "article_id": docs[0].get("article_id") if docs else None,
                            "url": docs[0].get("url") if docs else None,
                            "date": docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                        }
                    ]
                })

    # Action 2: Based on sentiment
    sentiment_result = agent_outputs.get("sentiment_emotion", {})
    if sentiment_result:
        overall = sentiment_result.get("overall", 0.0)

        if overall < -0.3:
            actions.append({
                "recommendation": "Address negative sentiment through improved messaging or product changes",
                "impact": "high",
                "evidence_refs": [
                    {
                        "article_id": docs[1].get("article_id") if len(docs) > 1 else docs[0].get("article_id") if docs else None,
                        "url": docs[1].get("url") if len(docs) > 1 else docs[0].get("url") if docs else None,
                        "date": docs[1].get("date", "2025-09-30") if len(docs) > 1 else docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                    }
                ]
            })
        elif overall > 0.3:
            actions.append({
                "recommendation": "Leverage positive sentiment momentum for marketing or PR campaigns",
                "impact": "medium",
                "evidence_refs": [
                    {
                        "article_id": docs[1].get("article_id") if len(docs) > 1 else docs[0].get("article_id") if docs else None,
                        "url": docs[1].get("url") if len(docs) > 1 else docs[0].get("url") if docs else None,
                        "date": docs[1].get("date", "2025-09-30") if len(docs) > 1 else docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                    }
                ]
            })

    # Action 3: Based on conflicts
    if conflicts:
        actions.append({
            "recommendation": "Investigate conflicting signals; conduct deeper analysis to reconcile data",
            "impact": "high",
            "evidence_refs": conflicts[0]["evidence_refs"][:1]  # Reuse evidence from first conflict
        })

    # Action 4: Based on competitors
    competitors_result = agent_outputs.get("competitor_news", {})
    if competitors_result:
        gaps = competitors_result.get("gaps", [])
        if gaps:
            actions.append({
                "recommendation": f"Address coverage gaps in: {', '.join(gaps[:2])}",
                "impact": "medium",
                "evidence_refs": [
                    {
                        "article_id": docs[2].get("article_id") if len(docs) > 2 else docs[0].get("article_id") if docs else None,
                        "url": docs[2].get("url") if len(docs) > 2 else docs[0].get("url") if docs else None,
                        "date": docs[2].get("date", "2025-09-30") if len(docs) > 2 else docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                    }
                ]
            })

    # Action 5: Based on topics
    topics_result = agent_outputs.get("topic_modeler", {})
    if topics_result:
        emerging = topics_result.get("emerging", [])
        if emerging:
            actions.append({
                "recommendation": f"Capitalize on emerging topics: {', '.join(emerging[:2])}",
                "impact": "low",
                "evidence_refs": [
                    {
                        "article_id": docs[3].get("article_id") if len(docs) > 3 else docs[0].get("article_id") if docs else None,
                        "url": docs[3].get("url") if len(docs) > 3 else docs[0].get("url") if docs else None,
                        "date": docs[3].get("date", "2025-09-30") if len(docs) > 3 else docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                    }
                ]
            })

    # Ensure at least 1 action
    if not actions:
        actions.append({
            "recommendation": "Continue monitoring trends and sentiment for strategic insights",
            "impact": "low",
            "evidence_refs": [
                {
                    "article_id": docs[0].get("article_id") if docs else None,
                    "url": docs[0].get("url") if docs else None,
                    "date": docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                }
            ]
        })

    return actions[:5]  # Max 5 actions


async def run_synthesis_agent(
    agent_outputs: Dict[str, Any],
    docs: List[Dict[str, Any]],
    correlation_id: str
) -> Dict[str, Any]:
    """
    Execute synthesis agent

    Args:
        agent_outputs: Dict with results from multiple agents
                      Keys: "topic_modeler", "sentiment_emotion", "trend_forecaster", "competitor_news"
        docs: Source articles for evidence linking
        correlation_id: Correlation ID for telemetry

    Returns:
        SynthesisResult dict
    """
    logger.info(
        f"[{correlation_id}] SynthesisAgent: {len(agent_outputs)} agent outputs, {len(docs)} docs"
    )

    try:
        # Detect conflicts
        conflicts = detect_conflicts(agent_outputs, docs)

        # Generate actions
        actions = generate_actions(agent_outputs, docs, conflicts)

        # Build summary
        summary_parts = []

        # Summarize key findings
        if "topic_modeler" in agent_outputs:
            topics = agent_outputs["topic_modeler"].get("topics", [])
            if topics:
                top_topic = topics[0].get("label", "topics")
                summary_parts.append(f"Key topic: {top_topic}")

        if "sentiment_emotion" in agent_outputs:
            overall = agent_outputs["sentiment_emotion"].get("overall", 0.0)
            sentiment_label = "positive" if overall > 0.2 else "negative" if overall < -0.2 else "neutral"
            summary_parts.append(f"{sentiment_label} sentiment")

        if "trend_forecaster" in agent_outputs:
            forecast_items = agent_outputs["trend_forecaster"].get("forecast", [])
            if forecast_items:
                direction = forecast_items[0].get("direction", "flat")
                summary_parts.append(f"trend {direction}")

        summary = "Analysis shows " + ", ".join(summary_parts) + "." if summary_parts else "Multi-agent analysis complete."

        # Ensure summary ≤400 chars
        if len(summary) > 400:
            summary = summary[:397] + "..."

        result = {
            "summary": summary,
            "conflicts": conflicts,
            "actions": actions,
            "success": True
        }

        logger.info(
            f"[{correlation_id}] SynthesisAgent completed: {len(conflicts)} conflicts, {len(actions)} actions"
        )

        return result

    except Exception as e:
        logger.error(f"[{correlation_id}] SynthesisAgent failed: {e}", exc_info=True)
        return {
            "summary": f"Analysis failed: {str(e)[:100]}",
            "conflicts": [],
            "actions": [{
                "recommendation": "Retry analysis with adjusted parameters",
                "impact": "low",
                "evidence_refs": [{
                    "article_id": None,
                    "url": None,
                    "date": "2025-09-30"
                }]
            }],
            "success": False,
            "error": str(e)
        }
