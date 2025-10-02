"""
Agentic RAG Agent — Iterative retrieval with self-check and query reformulation.
Implements multi-hop reasoning for /ask --depth=deep command.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from core.models.model_router import ModelRouter, get_model_router
from core.models.budget_manager import BudgetManager
from schemas.analysis_schemas import AgenticResult, AgenticStep

logger = logging.getLogger(__name__)


class AgenticRAGAgent:
    """Agent for iterative deep-dive question answering"""

    def __init__(self, model_router: Optional[ModelRouter] = None):
        """Initialize agent with model router"""
        self.model_router = model_router or get_model_router()

    async def execute(
        self,
        query: str,
        initial_docs: List[Dict[str, Any]],
        depth: int,
        retrieval_fn,
        budget_manager: BudgetManager,
        lang: str = "en",
        window: str = "24h"
    ) -> Tuple[AgenticResult, List[Dict[str, Any]]]:
        """
        Execute agentic RAG with iterative retrieval

        Args:
            query: User question
            initial_docs: Initial retrieved documents
            depth: Number of iterations (1-3)
            retrieval_fn: Async function for re-retrieval
            budget_manager: Budget manager for tracking
            lang: Language preference
            window: Time window for retrieval

        Returns:
            Tuple of (AgenticResult, all_docs_collected)
        """
        steps: List[AgenticStep] = []
        all_docs: List[Dict[str, Any]] = list(initial_docs)
        current_query = query
        answer_parts: List[str] = []

        logger.info(f"Starting Agentic RAG: query='{query}', depth={depth}, lang={lang}")

        for iteration in range(1, depth + 1):
            # Check budget before iteration
            if not budget_manager.can_afford(estimated_tokens=500, estimated_cents=0.5):
                logger.warning(f"Budget insufficient for iteration {iteration}, stopping early")
                budget_manager.warnings.append(f"Stopped at iteration {iteration-1}/{depth} due to budget")
                break

            # Step 1: Evaluate sufficiency
            if iteration == 1:
                reason = "Initial retrieval and analysis" if lang == "en" else "Первоначальный поиск и анализ"
                docs_for_iter = initial_docs
            else:
                # Check if we need reformulation
                needs_reformulation, reformulated_query = await self._check_sufficiency(
                    query=current_query,
                    docs=all_docs,
                    answer_so_far=" ".join(answer_parts),
                    budget_manager=budget_manager,
                    lang=lang
                )

                if needs_reformulation:
                    current_query = reformulated_query
                    reason = "Query reformulated for deeper evidence" if lang == "en" else "Запрос переформулирован для углубления"

                    # Re-retrieve with new query
                    logger.info(f"Iteration {iteration}: Reformulated query: '{current_query}'")
                    new_docs = await retrieval_fn(
                        query=current_query,
                        window=window,
                        k_final=5
                    )

                    # Merge and deduplicate
                    all_docs = self._merge_docs(all_docs, new_docs)
                    docs_for_iter = new_docs
                else:
                    reason = "Self-check and refinement" if lang == "en" else "Самопроверка и уточнение"
                    docs_for_iter = all_docs[:10]  # Use accumulated docs

            # Step 2: Generate answer for this iteration
            iter_answer = await self._generate_answer(
                query=current_query,
                docs=docs_for_iter,
                iteration=iteration,
                budget_manager=budget_manager,
                lang=lang
            )

            answer_parts.append(iter_answer)

            # Record step
            steps.append(
                AgenticStep(
                    iteration=iteration,
                    query=current_query[:180],
                    n_docs=len(docs_for_iter),
                    reason=reason[:200]
                )
            )

            logger.info(
                f"Iteration {iteration} complete: query='{current_query[:50]}...', "
                f"docs={len(docs_for_iter)}, reason={reason}"
            )

        # Step 3: Final synthesis
        final_answer = await self._synthesize_answer(
            query=query,
            answer_parts=answer_parts,
            docs=all_docs,
            budget_manager=budget_manager,
            lang=lang
        )

        # Generate follow-up questions
        followups = self._generate_followups(query, final_answer, lang)

        result = AgenticResult(
            steps=steps,
            answer=final_answer[:600],
            followups=followups[:5]
        )

        return result, all_docs

    async def _check_sufficiency(
        self,
        query: str,
        docs: List[Dict[str, Any]],
        answer_so_far: str,
        budget_manager: BudgetManager,
        lang: str
    ) -> Tuple[bool, str]:
        """
        Check if current evidence is sufficient, return reformulated query if not

        Returns:
            Tuple of (needs_reformulation, reformulated_query)
        """
        if lang == "ru":
            prompt = f"""Вопрос: {query}

Текущий ответ: {answer_so_far}

Доступные источники: {len(docs)}

Достаточно ли информации для полного ответа? Если нет, переформулируй запрос для более глубокого поиска.

Ответь в формате:
SUFFICIENT: yes|no
REFORMULATED_QUERY: <новый запрос если no>"""
        else:
            prompt = f"""Question: {query}

Current answer: {answer_so_far}

Available sources: {len(docs)}

Is the information sufficient for a complete answer? If not, reformulate the query for deeper search.

Answer in format:
SUFFICIENT: yes|no
REFORMULATED_QUERY: <new query if no>"""

        try:
            response, metadata = await self.model_router.call_with_fallback(
                prompt=prompt,
                docs=docs[:3],
                primary="gpt-5",
                fallback=["claude-4.5"],
                timeout_s=10,
                max_tokens=200,
                temperature=0.3
            )

            budget_manager.record_usage(
                tokens=metadata["tokens_used"],
                cost_cents=metadata["cost_cents"],
                latency_s=metadata["latency_ms"] / 1000
            )

            content = response["content"]

            # Parse response
            if "SUFFICIENT: yes" in content:
                return False, query
            elif "REFORMULATED_QUERY:" in content:
                reformulated = content.split("REFORMULATED_QUERY:")[-1].strip()
                return True, reformulated[:180]
            else:
                # Fallback: assume insufficient
                return True, f"{query} (detailed evidence)"

        except Exception as e:
            logger.warning(f"Sufficiency check failed: {e}")
            return False, query

    async def _generate_answer(
        self,
        query: str,
        docs: List[Dict[str, Any]],
        iteration: int,
        budget_manager: BudgetManager,
        lang: str
    ) -> str:
        """Generate answer for current iteration"""
        if lang == "ru":
            prompt = f"""На основе источников ниже, ответь на вопрос (итерация {iteration}):

Вопрос: {query}

Важно: опирайся только на факты из источников. Укажи номера источников [1], [2] и т.д."""
        else:
            prompt = f"""Based on the sources below, answer the question (iteration {iteration}):

Question: {query}

Important: use only facts from sources. Cite source numbers [1], [2] etc."""

        try:
            response, metadata = await self.model_router.call_with_fallback(
                prompt=prompt,
                docs=docs[:10],
                primary="gpt-5",
                fallback=["claude-4.5", "gemini-2.5-pro"],
                timeout_s=15,
                max_tokens=400,
                temperature=0.7
            )

            budget_manager.record_usage(
                tokens=metadata["tokens_used"],
                cost_cents=metadata["cost_cents"],
                latency_s=metadata["latency_ms"] / 1000
            )

            return response["content"][:500]

        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return f"Unable to generate answer for iteration {iteration}: {str(e)}"

    async def _synthesize_answer(
        self,
        query: str,
        answer_parts: List[str],
        docs: List[Dict[str, Any]],
        budget_manager: BudgetManager,
        lang: str
    ) -> str:
        """Synthesize final answer from all iterations"""
        combined = "\n\n".join(answer_parts)

        if lang == "ru":
            prompt = f"""Объедини результаты нескольких итераций анализа в финальный ответ на вопрос:

Вопрос: {query}

Результаты итераций:
{combined}

Дай связный итоговый ответ (≤600 символов), указывая номера источников."""
        else:
            prompt = f"""Synthesize the results of multiple analysis iterations into a final answer:

Question: {query}

Iteration results:
{combined}

Provide a coherent final answer (≤600 chars), citing source numbers."""

        try:
            response, metadata = await self.model_router.call_with_fallback(
                prompt=prompt,
                docs=docs[:5],
                primary="gpt-5",
                fallback=["claude-4.5"],
                timeout_s=12,
                max_tokens=600,
                temperature=0.7
            )

            budget_manager.record_usage(
                tokens=metadata["tokens_used"],
                cost_cents=metadata["cost_cents"],
                latency_s=metadata["latency_ms"] / 1000
            )

            return response["content"][:600]

        except Exception as e:
            logger.error(f"Answer synthesis failed: {e}")
            # Fallback: return combined parts truncated
            return combined[:600]

    def _merge_docs(
        self,
        existing: List[Dict[str, Any]],
        new: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge and deduplicate documents"""
        seen_ids = {doc.get("article_id") for doc in existing if doc.get("article_id")}
        seen_urls = {doc.get("url") for doc in existing if doc.get("url")}

        merged = list(existing)

        for doc in new:
            article_id = doc.get("article_id")
            url = doc.get("url")

            # Deduplicate by ID or URL
            if article_id and article_id in seen_ids:
                continue
            if url and url in seen_urls:
                continue

            merged.append(doc)
            if article_id:
                seen_ids.add(article_id)
            if url:
                seen_urls.add(url)

        return merged

    def _generate_followups(
        self,
        query: str,
        answer: str,
        lang: str
    ) -> List[str]:
        """Generate follow-up questions based on answer"""
        if lang == "ru":
            followups = [
                "Нужно ли углубиться в конкретные метрики?",
                "Какие дополнительные источники могут помочь?",
                "Есть ли альтернативные точки зрения?"
            ]
        else:
            followups = [
                "Should we dive deeper into specific metrics?",
                "What additional sources might help?",
                "Are there alternative perspectives to consider?"
            ]

        # Simple heuristics: if answer mentions specific terms, suggest related questions
        if "AI" in answer or "artificial intelligence" in answer.lower():
            followups.insert(0, "What are the regulatory implications?" if lang == "en" else "Каковы регуляторные последствия?")

        return followups


def create_agentic_rag_agent(model_router: Optional[ModelRouter] = None) -> AgenticRAGAgent:
    """Factory function to create agentic RAG agent"""
    return AgenticRAGAgent(model_router=model_router)
