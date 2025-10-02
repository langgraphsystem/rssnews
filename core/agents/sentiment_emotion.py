"""
Sentiment & Emotion Analysis Agent — Analyze sentiment using GPT-5
Primary: gpt-5, Fallback: claude-4.5
"""

import logging
import json
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


SENTIMENT_SYSTEM_PROMPT = """You are a sentiment and emotion analysis expert. Analyze the provided news articles to determine overall sentiment and emotional tone.

TASK: Analyze sentiment and emotions across the articles.

OUTPUT FORMAT (strict JSON):
{
  "overall": 0.3,
  "emotions": {
    "joy": 0.2,
    "fear": 0.4,
    "anger": 0.3,
    "sadness": 0.1,
    "surprise": 0.0
  },
  "aspects": [
    {
      "name": "Economy",
      "score": -0.5,
      "evidence_ref": {
        "article_id": "art_123",
        "url": "https://...",
        "date": "2025-09-30"
      }
    }
  ],
  "timeline": [
    {
      "window": "24h",
      "score": 0.2,
      "n_docs": 5
    }
  ]
}

RULES:
1. overall: sentiment score from -1 (very negative) to +1 (very positive)
2. emotions: breakdown of 5 core emotions (0-1 each, sum should be ~1.0)
3. aspects: identify 2-4 key aspects with sentiment scores and evidence
4. timeline: optional temporal sentiment trend
5. Each aspect MUST have evidence_ref with date in YYYY-MM-DD format
6. Be objective and grounded in the text
7. Return ONLY valid JSON, no additional text"""


async def run_sentiment_emotion(
    docs: List[Dict[str, Any]],
    correlation_id: str
) -> Dict[str, Any]:
    """
    Run sentiment & emotion analysis agent

    Args:
        docs: Retrieved documents
        correlation_id: Tracking ID

    Returns:
        Result dict with sentiment analysis
    """
    try:
        from core.ai_models.model_manager import ModelManager

        logger.info(f"Sentiment analysis: processing {len(docs)} docs")

        # Build context
        context = _build_sentiment_context(docs)

        # Build prompt
        prompt = f"{SENTIMENT_SYSTEM_PROMPT}\n\nDOCUMENTS:\n{context}\n\nAnalyze sentiment now:"

        # Call model via ModelManager
        model_manager = ModelManager(correlation_id=correlation_id)

        output, warnings = await model_manager.invoke_model(
            task="sentiment_emotion",
            prompt=prompt,
            max_tokens=1200
        )

        # Parse JSON output
        try:
            result = json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON output: {e}")
            result = _extract_json(output)

        # Validate result structure
        required_fields = ["overall", "emotions"]
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Missing '{field}' field in output")

        # Validate score ranges
        if not (-1.0 <= result["overall"] <= 1.0):
            logger.warning(f"Overall sentiment {result['overall']} out of range, clamping")
            result["overall"] = max(-1.0, min(1.0, result["overall"]))

        # Add metadata
        result["success"] = True
        result["warnings"] = warnings
        result["model_used"] = model_manager.budget_tracker.invocations[-1].model if model_manager.budget_tracker.invocations else "unknown"

        logger.info(f"Sentiment analysis completed: overall={result['overall']:.2f}")

        return result

    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "overall": 0.0,
            "emotions": {
                "joy": 0.0,
                "fear": 0.0,
                "anger": 0.0,
                "sadness": 0.0,
                "surprise": 0.0
            },
            "aspects": []
        }


def _build_sentiment_context(docs: List[Dict[str, Any]], max_chars: int = 3500) -> str:
    """Build context for sentiment analysis"""
    context_parts = []
    total_chars = 0

    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "")
        snippet = doc.get("snippet", "")
        date = doc.get("date", "")
        url = doc.get("url", "")
        article_id = doc.get("article_id", f"doc_{i}")

        doc_text = f"[{i}] ID: {article_id}\nTitle: {title}\nDate: {date}\nURL: {url}\nText: {snippet}\n"

        if total_chars + len(doc_text) > max_chars:
            break

        context_parts.append(doc_text)
        total_chars += len(doc_text)

    return "\n".join(context_parts)


def _extract_json(text: str) -> Dict[str, Any]:
    """Try to extract JSON from text (fallback)"""
    try:
        # Find JSON block
        start = text.find("{")
        end = text.rfind("}") + 1

        if start >= 0 and end > start:
            json_str = text[start:end]
            return json.loads(json_str)
    except Exception as e:
        logger.warning(f"Failed to extract JSON: {e}")

    # Return minimal valid structure
    return {
        "overall": 0.0,
        "emotions": {
            "joy": 0.0,
            "fear": 0.0,
            "anger": 0.0,
            "sadness": 0.0,
            "surprise": 0.0
        },
        "aspects": [],
        "error": "Failed to parse output"
    }