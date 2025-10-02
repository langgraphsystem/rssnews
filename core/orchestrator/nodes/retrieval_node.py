"""
Retrieval Node — First step in orchestrator pipeline
Calls retrieval client to get relevant documents
"""

import logging
from typing import Dict, Any, Optional
from core.rag.retrieval_client import get_retrieval_client

logger = logging.getLogger(__name__)


async def retrieval_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute retrieval step with degradation logic

    Input state:
        - query: Optional[str]
        - window: str
        - lang: str
        - sources: Optional[List[str]]
        - k_final: int
        - use_rerank: bool

    Output state (adds):
        - docs: List[Dict]
        - retrieval_meta: Dict
        - warnings: List[str] (if degradation applied)
    """
    try:
        # Get retrieval client
        client = get_retrieval_client()

        # Extract parameters
        query = state.get("query")
        window = state.get("window", "24h")
        lang = state.get("lang", "auto")
        sources = state.get("sources")
        k_final = state.get("k_final", 5)
        use_rerank = state.get("use_rerank", False)

        warnings = state.get("warnings", [])

        logger.info(
            f"Retrieval node: query={query or 'none'}, window={window}, k_final={k_final}, rerank={use_rerank}"
        )

        # Retrieve documents
        docs = await client.retrieve(
            query=query,
            window=window,
            lang=lang,
            sources=sources,
            k_final=k_final,
            use_rerank=use_rerank
        )

        # DEGRADATION: If no docs, try expanding window
        if not docs:
            logger.warning(f"No docs found, attempting degradation: expanding window from {window}")

            # Expand window ladder
            window_ladder = {
                "1h": "6h",
                "6h": "12h",
                "12h": "24h",
                "24h": "3d",
                "3d": "1w",
                "1w": "2w",
                "2w": "1m"
            }

            expanded_window = window_ladder.get(window, "1w")

            if expanded_window != window:
                logger.info(f"Degradation step 1: Expanding window to {expanded_window}")
                warnings.append(f"degradation_window_expanded: {window} → {expanded_window}")

                docs = await client.retrieve(
                    query=query,
                    window=expanded_window,
                    lang=lang,
                    sources=sources,
                    k_final=k_final,
                    use_rerank=use_rerank
                )

                if docs:
                    window = expanded_window  # Update for meta

        # DEGRADATION: If still no docs, disable reranking (cheaper)
        if not docs and use_rerank:
            logger.warning(f"Still no docs, degradation step 2: disabling rerank")
            warnings.append("degradation_rerank_disabled")

            docs = await client.retrieve(
                query=query,
                window=window,
                lang=lang,
                sources=sources,
                k_final=k_final,
                use_rerank=False
            )

        # DEGRADATION: If still no docs, increase k_final
        if not docs and k_final < 10:
            logger.warning(f"Still no docs, degradation step 3: increasing k_final to 10")
            warnings.append("degradation_k_final_increased")

            docs = await client.retrieve(
                query=query,
                window=window,
                lang=lang,
                sources=sources,
                k_final=10,
                use_rerank=False
            )

        # Update state
        state["docs"] = docs
        state["retrieval_meta"] = {
            "count": len(docs),
            "window": window,
            "lang": lang,
            "k_final": k_final,
            "degradation_applied": len(warnings) > 0
        }
        state["warnings"] = warnings

        logger.info(f"Retrieval node completed: {len(docs)} docs retrieved, {len(warnings)} warnings")

        return state

    except Exception as e:
        logger.error(f"Retrieval node failed: {e}", exc_info=True)
        state["error"] = {
            "node": "retrieval",
            "code": "NO_DATA",
            "message": f"Failed to retrieve documents: {e}"
        }
        return state