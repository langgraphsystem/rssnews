"""
Orchestrator Service — Integration layer between bot and Phase 1 orchestrator.
Provides async helpers that return Telegram-friendly payloads.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Dict, List, Optional

import inspect

from core.orchestrator.orchestrator import Phase1Orchestrator, get_orchestrator

try:
    from core.orchestrator.phase3_orchestrator_new import (
        Phase3Orchestrator as AsyncPhase3Orchestrator,
    )
    _PHASE3_ASYNC = True
except ImportError:  # Fallback to stub orchestrator
    from core.orchestrator.phase3_orchestrator import (
        Phase3Orchestrator as AsyncPhase3Orchestrator,
    )
    _PHASE3_ASYNC = False

try:
    from core.orchestrator.phase4_orchestrator import (
        Phase4Orchestrator as AsyncPhase4Orchestrator,
        create_phase4_orchestrator,
    )
    _PHASE4_ASYNC = True
except Exception:
    AsyncPhase4Orchestrator = None
    _PHASE4_ASYNC = False

from core.ux.formatter import format_for_telegram, format_result_details
from schemas.analysis_schemas import BaseAnalysisResponse, ErrorResponse

logger = logging.getLogger(__name__)


class OrchestratorService:
    """Service wrapper around Phase1Orchestrator with Telegram formatting."""

    def __init__(self) -> None:
        self._orchestrator: Phase1Orchestrator = get_orchestrator()

    async def handle_trends_command(
        self,
        *,
        window: str = "24h",
        lang: str = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 5,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute orchestrator /trends flow and return formatting payload."""

        correlation_id = correlation_id or f"trends-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(
                "[OrchestratorService] /trends | window=%s lang=%s k=%s", window, lang, k_final
            )
            response = await self._orchestrator.execute_trends(
                window=window,
                lang=lang,
                sources=sources,
                k_final=k_final,
            )
            payload = format_for_telegram(response)
            context = {
                "command": "trends",
                "window": window,
                "lang": lang,
                "sources": sources or [],
                "k_final": k_final,
                "correlation_id": getattr(response.meta, "correlation_id", correlation_id)
                if isinstance(response, BaseAnalysisResponse)
                else correlation_id,
            }
            return self._augment_payload(payload, context=context)
        except Exception as exc:
            logger.error("/trends orchestrator failure: %s", exc, exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_analyze_command(
        self,
        *,
        mode: str,
        query: Optional[str] = None,
        window: str = "24h",
        lang: str = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 5,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute orchestrator /analyze flow for a given mode."""

        correlation_id = correlation_id or f"analyze-{mode}-{uuid.uuid4().hex[:8]}"
        mode_normalized = mode.lower()

        if mode_normalized not in {"keywords", "sentiment", "topics"}:
            return self._error_payload(
                f"Unsupported analysis mode '{mode}'. Use keywords, sentiment, or topics.",
                correlation_id,
            )

        try:
            logger.info(
                "[OrchestratorService] /analyze | mode=%s query='%s' window=%s",
                mode_normalized,
                (query or ""),
                window,
            )
            response = await self._orchestrator.execute_analyze(
                mode=mode_normalized,
                query=query,
                window=window,
                lang=lang,
                sources=sources,
                k_final=k_final,
            )
            payload = format_for_telegram(response)
            context = {
                "command": "analyze",
                "mode": mode_normalized,
                "query": query or "",
                "window": window,
                "lang": lang,
                "sources": sources or [],
                "k_final": k_final,
                "correlation_id": getattr(response.meta, "correlation_id", correlation_id)
                if isinstance(response, BaseAnalysisResponse)
                else correlation_id,
            }
            return self._augment_payload(payload, context=context)
        except Exception as exc:
            logger.error("/analyze orchestrator failure: %s", exc, exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_predict_trends_command(
        self,
        *,
        topic: Optional[str] = None,
        window: str = "1w",
        lang: str = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 5,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute orchestrator /predict trends flow (Phase 2)"""

        correlation_id = correlation_id or f"predict-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(
                "[OrchestratorService] /predict trends | topic=%s window=%s k=%s", topic or "general", window, k_final
            )
            response = await self._orchestrator.execute_predict_trends(
                topic=topic,
                window=window,
                lang=lang,
                sources=sources,
                k_final=k_final,
            )
            payload = format_for_telegram(response)
            context = {
                "command": "predict",
                "topic": topic or "",
                "window": window,
                "lang": lang,
                "sources": sources or [],
                "k_final": k_final,
                "correlation_id": getattr(response.meta, "correlation_id", correlation_id)
                if isinstance(response, BaseAnalysisResponse)
                else correlation_id,
            }
            return self._augment_payload(payload, context=context)
        except Exception as exc:
            logger.error("/predict trends orchestrator failure: %s", exc, exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_analyze_competitors_command(
        self,
        *,
        domains: Optional[List[str]] = None,
        niche: Optional[str] = None,
        window: str = "1w",
        lang: str = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 10,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute orchestrator /analyze competitors flow (Phase 2)"""

        correlation_id = correlation_id or f"competitors-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(
                "[OrchestratorService] /analyze competitors | domains=%s niche=%s window=%s k=%s",
                domains, niche, window, k_final
            )
            response = await self._orchestrator.execute_analyze_competitors(
                domains=domains,
                niche=niche,
                window=window,
                lang=lang,
                sources=sources,
                k_final=k_final,
            )
            payload = format_for_telegram(response)
            context = {
                "command": "competitors",
                "domains": domains or [],
                "niche": niche or "",
                "window": window,
                "lang": lang,
                "sources": sources or [],
                "k_final": k_final,
                "correlation_id": getattr(response.meta, "correlation_id", correlation_id)
                if isinstance(response, BaseAnalysisResponse)
                else correlation_id,
            }
            return self._augment_payload(payload, context=context)
        except Exception as exc:
            logger.error("/analyze competitors orchestrator failure: %s", exc, exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_synthesize_command(
        self,
        *,
        agent_outputs: Dict[str, Any],
        window: str = "24h",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute orchestrator /synthesize flow (Phase 2)"""

        correlation_id = correlation_id or f"synthesize-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(
                "[OrchestratorService] /synthesize | agent_count=%s", len(agent_outputs)
            )
            response = await self._orchestrator.execute_synthesize(
                agent_outputs=agent_outputs,
                window=window,
                lang=lang,
                correlation_id=correlation_id,
            )
            payload = format_for_telegram(response)
            context = {
                "command": "synthesize",
                "window": window,
                "lang": lang,
                "correlation_id": getattr(response.meta, "correlation_id", correlation_id)
                if isinstance(response, BaseAnalysisResponse)
                else correlation_id,
            }
            return self._augment_payload(payload, context=context)
        except Exception as exc:
            logger.error("/synthesize orchestrator failure: %s", exc, exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_detail_request(
        self,
        response: BaseAnalysisResponse,
        detail_type: str,
    ) -> str:
        """Expose detail formatting utility for callbacks."""

        return format_result_details(response, detail_type=detail_type)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _augment_payload(self, payload: Dict[str, Any], *, context: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure payload has parse mode, context, and refresh buttons."""

        enriched = dict(payload)
        enriched.setdefault("parse_mode", "Markdown")
        enriched["context"] = context

        buttons: List[List[Dict[str, str]]] = []
        refresh_button = self._build_refresh_button(context)
        if refresh_button:
            buttons = [refresh_button] + buttons
        enriched["buttons"] = buttons
        return enriched

    def _build_refresh_button(self, context: Dict[str, Any]) -> List[Dict[str, str]]:
        """Build first-row refresh button based on command context."""

        command = context.get("command")
        if command == "trends":
            window = context.get("window", "24h")
            return [{"text": "🔄 Обновить", "callback_data": f"trends:refresh:{window}"}]

        if command == "analyze":
            window = context.get("window", "24h")
            mode = context.get("mode", "keywords")
            query_key = self._compact_query(context.get("query", ""))
            return [
                {
                    "text": "🔄 Обновить",
                    "callback_data": f"analyze:refresh:{mode}:{window}:{query_key}",
                }
            ]

        return []

    @staticmethod
    def _compact_query(query: str) -> str:
        """Produce compact token for callbacks (<= 32 chars)."""

        if not query:
            return "none"
        normalized = "_".join(query.strip().split())[:32]
        if len(query) <= 32:
            return normalized or "none"
        digest = hashlib.md5(query.encode("utf-8")).hexdigest()[:8]
        prefix = normalized[:24] if normalized else "query"
        return f"{prefix}-{digest}"

    @staticmethod
    def _error_payload(message: str, correlation_id: str) -> Dict[str, Any]:
        """Return Markdown formatted error payload."""

        text = (
            "❌ **Ошибка выполнения команды**\n\n"
            f"{message}\n\n"
            f"ID: `{correlation_id}`"
        )
        return {"text": text, "buttons": None, "parse_mode": "Markdown"}


_service_instance: Optional[OrchestratorService] = None


def get_orchestrator_service() -> OrchestratorService:
    """Singleton accessor used by bot handlers."""

    global _service_instance
    if _service_instance is None:
        _service_instance = OrchestratorService()
    return _service_instance


async def execute_trends_command(
    *,
    window: str = "24h",
    lang: str = "auto",
    sources: Optional[List[str]] = None,
    k_final: int = 5,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Public helper used by Telegram bot to run /trends."""

    service = get_orchestrator_service()
    return await service.handle_trends_command(
        window=window,
        lang=lang,
        sources=sources,
        k_final=k_final,
        correlation_id=correlation_id,
    )


async def execute_analyze_command(
    *,
    mode: str,
    query: Optional[str] = None,
    window: str = "24h",
    lang: str = "auto",
    sources: Optional[List[str]] = None,
    k_final: int = 5,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Public helper used by Telegram bot to run /analyze."""

    service = get_orchestrator_service()
    return await service.handle_analyze_command(
        mode=mode,
        query=query,
        window=window,
        lang=lang,
        sources=sources,
        k_final=k_final,
        correlation_id=correlation_id,
    )


async def execute_predict_trends_command(
    *,
    topic: Optional[str] = None,
    window: str = "1w",
    lang: str = "auto",
    sources: Optional[List[str]] = None,
    k_final: int = 5,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Public helper used by Telegram bot to run /predict trends (Phase 2)."""

    service = get_orchestrator_service()
    return await service.handle_predict_trends_command(
        topic=topic,
        window=window,
        lang=lang,
        sources=sources,
        k_final=k_final,
        correlation_id=correlation_id,
    )


async def execute_analyze_competitors_command(
    *,
    domains: Optional[List[str]] = None,
    niche: Optional[str] = None,
    window: str = "1w",
    lang: str = "auto",
    sources: Optional[List[str]] = None,
    k_final: int = 10,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Public helper used by Telegram bot to run /analyze competitors (Phase 2)."""

    service = get_orchestrator_service()
    return await service.handle_analyze_competitors_command(
        domains=domains,
        niche=niche,
        window=window,
        lang=lang,
        sources=sources,
        k_final=k_final,
        correlation_id=correlation_id,
    )


async def execute_synthesize_command(
    *,
    agent_outputs: Dict[str, Any],
    window: str = "24h",
    lang: str = "auto",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Public helper used by Telegram bot to run /synthesize (Phase 2)."""

    service = get_orchestrator_service()
    return await service.handle_synthesize_command(
        agent_outputs=agent_outputs,
        window=window,
        lang=lang,
        correlation_id=correlation_id,
    )


_phase3_instance: Optional[AsyncPhase3Orchestrator] = None
_phase4_instance: Optional[AsyncPhase4Orchestrator] = None


def get_phase3_orchestrator() -> AsyncPhase3Orchestrator:
    global _phase3_instance
    if _phase3_instance is None:
        _phase3_instance = AsyncPhase3Orchestrator()
    return _phase3_instance


def get_phase4_orchestrator() -> AsyncPhase4Orchestrator:
    """Get or create Phase4Orchestrator instance"""
    global _phase4_instance
    if _phase4_instance is None:
        if not _PHASE4_ASYNC or AsyncPhase4Orchestrator is None:
            raise ImportError("Phase4Orchestrator not available")
        _phase4_instance = create_phase4_orchestrator()
    return _phase4_instance


async def execute_phase3_context(context: Dict[str, Any]) -> Dict[str, Any]:
    orchestrator = get_phase3_orchestrator()
    result = orchestrator.execute(context)
    if inspect.isawaitable(result):
        return await result
    return result


async def execute_phase4_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Phase4 command with context"""
    orchestrator = get_phase4_orchestrator()
    result = orchestrator.execute(context)
    if inspect.isawaitable(result):
        return await result
    return result
