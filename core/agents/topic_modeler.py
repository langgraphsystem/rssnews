"""
Topic Modeling Agent — Identify topics and clusters using Claude 4.5
Primary: claude-4.5, Fallback: gpt-5, gemini-2.5-pro
"""

import logging
import json
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


TOPIC_MODELING_PROMPT = """You are a topic modeling expert. Analyze the provided news articles to identify key topics, clusters, emerging trends, and content gaps.

TASK: Identify 3-8 main topics/themes across the articles.

OUTPUT FORMAT (strict JSON):
{
  "topics": [
    {
      "label": "Economic Recovery",
      "terms": ["gdp", "growth", "recovery", "inflation"],
      "size": 8,
      "trend": "rising"
    }
  ],
  "clusters": [
    {
      "id": "cluster_1",
      "doc_ids": ["art_1", "art_3", "art_7"]
    }
  ],
  "emerging": ["new trend 1", "new trend 2"],
  "gaps": ["underreported topic 1"]
}

RULES:
1. topics: 3-8 main topics with descriptive labels
2. terms: 3-10 key terms per topic (lowercase)
3. size: number of articles related to this topic
4. trend: "rising", "falling", or "stable" based on temporal signals
5. clusters: group document IDs by similarity (optional)
6. emerging: 1-3 emerging trends not yet mainstream
7. gaps: 0-2 important topics that are underreported
8. Order topics by size (largest first)
9. Return ONLY valid JSON, no additional text"""


async def run_topic_modeler(
    docs: List[Dict[str, Any]],
    correlation_id: str
) -> Dict[str, Any]:
    """
    Run topic modeling agent

    Args:
        docs: Retrieved documents
        correlation_id: Tracking ID

    Returns:
        Result dict with topics
    """
    try:
        from core.ai_models.model_manager import ModelManager

        logger.info(f"Topic modeling: processing {len(docs)} docs")

        # Build context
        context = _build_topic_context(docs)

        # Build prompt
        prompt = f"{TOPIC_MODELING_PROMPT}\n\nDOCUMENTS:\n{context}\n\nIdentify topics now:"

        # Call model via ModelManager
        model_manager = ModelManager(correlation_id=correlation_id)

        output, warnings = await model_manager.invoke_model(
            task="topic_modeler",
            prompt=prompt,
            max_tokens=1800
        )

        # Parse JSON output
        try:
            result = json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON output: {e}")
            result = _extract_json(output)

        # Validate result structure
        if "topics" not in result:
            raise ValueError("Missing 'topics' field in output")

        if not result["topics"]:
            raise ValueError("No topics identified")

        # Add metadata
        result["success"] = True
        result["warnings"] = warnings
        result["model_used"] = model_manager.budget_tracker.invocations[-1].model if model_manager.budget_tracker.invocations else "unknown"

        # Ensure optional fields exist
        if "clusters" not in result:
            result["clusters"] = []
        if "emerging" not in result:
            result["emerging"] = []
        if "gaps" not in result:
            result["gaps"] = []

        logger.info(f"Topic modeling completed: {len(result['topics'])} topics")

        return result

    except Exception as e:
        logger.error(f"Topic modeling failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "topics": [],
            "clusters": [],
            "emerging": [],
            "gaps": []
        }


def _build_topic_context(docs: List[Dict[str, Any]], max_chars: int = 4000) -> str:
    """Build context for topic modeling"""
    context_parts = []
    total_chars = 0

    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "")
        snippet = doc.get("snippet", "")
        date = doc.get("date", "")
        article_id = doc.get("article_id", f"doc_{i}")

        doc_text = f"[{i}] ID: {article_id}\nTitle: {title}\nDate: {date}\nText: {snippet}\n"

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
        "topics": [],
        "clusters": [],
        "emerging": [],
        "gaps": [],
        "error": "Failed to parse output"
    }