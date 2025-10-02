"""
Keyphrase Mining Agent — Extract key phrases using Gemini 2.5 Pro
Primary: gemini-2.5-pro, Fallback: claude-4.5, gpt-5
"""

import logging
import json
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


KEYPHRASE_SYSTEM_PROMPT = """You are a keyphrase extraction expert. Analyze the provided news articles and extract the most significant keyphrases.

TASK: Extract 5-15 keyphrases that best represent the main topics and themes.

OUTPUT FORMAT (strict JSON):
{
  "keyphrases": [
    {
      "phrase": "original phrase",
      "norm": "normalized form",
      "score": 0.95,
      "ngram": 2,
      "variants": ["variant1", "variant2"],
      "examples": ["example usage from text"],
      "lang": "en"
    }
  ]
}

RULES:
1. Extract phrases that are meaningful and specific (avoid generic terms)
2. Score based on relevance, frequency, and distinctiveness (0-1)
3. Include both unigrams and multi-word phrases (ngram: 1-3)
4. Provide normalized forms (lowercase, lemmatized if possible)
5. Include up to 2 variants and 2 example usages per phrase
6. Detect language per phrase (ru or en)
7. Order by score (highest first)
8. Return ONLY valid JSON, no additional text"""


QUERY_EXPANSION_PROMPT = """You are a query expansion expert. Based on the extracted keyphrases and document content, suggest query expansions.

TASK: Generate query expansion hints to help users refine their search.

OUTPUT FORMAT (strict JSON):
{
  "intents": ["intent1", "intent2"],
  "expansions": ["expanded query 1", "expanded query 2"],
  "negatives": ["term to exclude 1"]
}

RULES:
1. Identify 2-3 user intents based on content
2. Suggest 3-5 query expansions that broaden or refine the search
3. Optionally suggest 1-2 negative terms to exclude
4. Keep suggestions concise and actionable
5. Return ONLY valid JSON"""


async def run_keyphrase_mining(
    docs: List[Dict[str, Any]],
    correlation_id: str
) -> Dict[str, Any]:
    """
    Run keyphrase mining agent

    Args:
        docs: Retrieved documents
        correlation_id: Tracking ID

    Returns:
        Result dict with keyphrases
    """
    try:
        from core.ai_models.model_manager import ModelManager

        logger.info(f"Keyphrase mining: processing {len(docs)} docs")

        # Build context from documents
        context = _build_context(docs)

        # Build prompt
        prompt = f"{KEYPHRASE_SYSTEM_PROMPT}\n\nDOCUMENTS:\n{context}\n\nExtract keyphrases now:"

        # Call model via ModelManager
        model_manager = ModelManager(correlation_id=correlation_id)

        output, warnings = await model_manager.invoke_model(
            task="keyphrase_mining",
            prompt=prompt,
            max_tokens=1500
        )

        # Parse JSON output
        try:
            result = json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON output: {e}")
            # Try to extract JSON from output
            result = _extract_json(output)

        # Validate result structure
        if "keyphrases" not in result:
            raise ValueError("Missing 'keyphrases' field in output")

        # Add metadata
        result["success"] = True
        result["warnings"] = warnings
        result["model_used"] = model_manager.budget_tracker.invocations[-1].model if model_manager.budget_tracker.invocations else "unknown"

        logger.info(f"Keyphrase mining completed: {len(result.get('keyphrases', []))} phrases")

        return result

    except Exception as e:
        logger.error(f"Keyphrase mining failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "keyphrases": []
        }


async def run_query_expansion(
    docs: List[Dict[str, Any]],
    correlation_id: str
) -> Dict[str, Any]:
    """
    Run query expansion agent (optional enhancement)

    Args:
        docs: Retrieved documents
        correlation_id: Tracking ID

    Returns:
        Result dict with expansion hints
    """
    try:
        from core.ai_models.model_manager import ModelManager

        logger.info(f"Query expansion: processing {len(docs)} docs")

        # Build context
        context = _build_context(docs, max_chars=2000)

        # Build prompt
        prompt = f"{QUERY_EXPANSION_PROMPT}\n\nDOCUMENTS:\n{context}\n\nGenerate expansion hints now:"

        # Call model
        model_manager = ModelManager(correlation_id=correlation_id)

        output, warnings = await model_manager.invoke_model(
            task="query_expansion",
            prompt=prompt,
            max_tokens=800
        )

        # Parse JSON
        try:
            result = json.loads(output)
        except json.JSONDecodeError:
            result = _extract_json(output)

        result["success"] = True
        result["warnings"] = warnings

        logger.info(f"Query expansion completed")

        return result

    except Exception as e:
        logger.error(f"Query expansion failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "intents": [],
            "expansions": []
        }


def _build_context(docs: List[Dict[str, Any]], max_chars: int = 3000) -> str:
    """Build context string from documents"""
    context_parts = []
    total_chars = 0

    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "")
        snippet = doc.get("snippet", "")
        date = doc.get("date", "")

        doc_text = f"[{i}] {title}\nDate: {date}\n{snippet}\n"

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

    # Return empty structure
    return {"keyphrases": [], "error": "Failed to parse output"}