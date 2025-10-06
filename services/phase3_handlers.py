"""
Phase 3 Bot Handlers — Telegram-facing handlers for /ask, /events, /graph, /memory commands.
Integrates with Phase3Orchestrator and returns formatted payloads.
"""

import hashlib
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.orchestrator.phase3_orchestrator_new import Phase3Orchestrator
from core.ux.formatter import format_for_telegram
from core.context.phase3_context_builder import get_phase3_context_builder
from core.rag.retrieval_client import get_retrieval_client
from schemas.analysis_schemas import BaseAnalysisResponse
from schemas.analysis_schemas import ErrorResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class Phase3HandlerService:
    """Service for Phase 3 command handlers"""

    def __init__(self):
        self.orchestrator = Phase3Orchestrator()
        self.context_builder = get_phase3_context_builder()
        self.retrieval_client = get_retrieval_client()

    def _normalize_response(self, raw_response: Any) -> BaseAnalysisResponse | ErrorResponse:
        """Ensure orchestrator output is a schema instance for downstream formatting."""
        if isinstance(raw_response, (BaseAnalysisResponse, ErrorResponse)):
            return raw_response

        if isinstance(raw_response, dict):
            try:
                if 'error' in raw_response:
                    if hasattr(ErrorResponse, 'model_validate'):
                        return ErrorResponse.model_validate(raw_response)
                    return ErrorResponse.parse_obj(raw_response)

                if hasattr(BaseAnalysisResponse, 'model_validate'):
                    return BaseAnalysisResponse.model_validate(raw_response)
                return BaseAnalysisResponse.parse_obj(raw_response)
            except ValidationError as exc:
                logger.error(f"Phase3 response validation failed: {exc}", exc_info=True)
                raise

        raise TypeError(f"Unsupported Phase3 response type: {type(raw_response)!r}")

    async def handle_ask_command(
        self,
        *,
        query: str,
        depth: int = 3,
        window: str = "7d",  # Changed default from 24h to 7d
        lang: str = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 10,  # Increased from 5 to 10
        max_tokens: int = 8000,
        budget_cents: int = 50,
        timeout_s: int = 30,
        correlation_id: Optional[str] = None,
        intent: str = "news_current_events",  # NEW: intent classification
        after_date: Optional[Any] = None,  # NEW: after: date filter
        before_date: Optional[Any] = None,  # NEW: before: date filter
    ) -> Dict[str, Any]:
        """Execute /ask --depth=deep command"""

        correlation_id = correlation_id or f"ask-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(
                f"[Phase3] /ask | intent={intent} query='{query[:50]}...' "
                f"depth={depth} window={window} k={k_final}"
            )

            args_tokens: List[str] = []
            if query:
                args_tokens.append(f'query="{self._escape_quotes(query)}"')
            if window:
                args_tokens.append(f"window={window}")
            if lang and lang != "auto":
                args_tokens.append(f"lang={lang}")
            if sources:
                args_tokens.append(f"sources={','.join(sources)}")
            if k_final:
                args_tokens.append(f"k={k_final}")
            if depth != 3:
                args_tokens.append(f"depth={depth}")
            if intent:
                args_tokens.append(f"intent={intent}")

            context, error_payload = await self._build_context(
                raw_command="/ask",
                args_tokens=args_tokens,
                correlation_id=correlation_id,
                lang=lang,
                window=window,
                k_final=k_final,
                max_tokens=max_tokens,
                budget_cents=budget_cents,
                timeout_s=timeout_s,
            )
            if error_payload:
                return error_payload

            params = context.setdefault("params", {})
            params["depth"] = depth
            params["intent"] = intent  # Add intent to context
            params["after_date"] = after_date
            params["before_date"] = before_date

            raw_response = await self.orchestrator.execute(context)
            response = self._normalize_response(raw_response)

            payload = format_for_telegram(response)

            response_correlation = getattr(getattr(response, 'meta', None), 'correlation_id', correlation_id)

            context_meta = {
                "command": "ask",
                "query": query,
                "depth": depth,
                "window": window,
                "lang": lang,
                "k_final": params.get("k_final", k_final),
                "sources": sources or [],
                "correlation_id": response_correlation,
                "intent": intent,  # Add intent to meta
            }

            return self._augment_payload(payload, context=context_meta)

        except Exception as exc:
            logger.error(f"[Phase3] /ask failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_events_command(
        self,
        *,
        topic: Optional[str] = None,
        entity: Optional[str] = None,
        window: str = "12h",
        lang: str = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 10,
        max_tokens: int = 8000,
        budget_cents: int = 50,
        timeout_s: int = 30,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute /events link command"""

        correlation_id = correlation_id or f"events-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(
                f"[Phase3] /events | topic={topic} entity={entity} window={window} k={k_final}"
            )

            args_tokens: List[str] = []
            if topic:
                args_tokens.append(f'topic="{self._escape_quotes(topic)}"')
            if entity:
                args_tokens.append(f'entity="{self._escape_quotes(entity)}"')
            if window:
                args_tokens.append(f"window={window}")
            if lang and lang != "auto":
                args_tokens.append(f"lang={lang}")
            if sources:
                args_tokens.append(f"sources={','.join(sources)}")
            if k_final:
                args_tokens.append(f"k={k_final}")

            context, error_payload = await self._build_context(
                raw_command="/events link",
                args_tokens=args_tokens,
                correlation_id=correlation_id,
                lang=lang,
                window=window,
                k_final=k_final,
                max_tokens=max_tokens,
                budget_cents=budget_cents,
                timeout_s=timeout_s,
            )
            if error_payload:
                return error_payload

            raw_response = await self.orchestrator.execute(context)
            response = self._normalize_response(raw_response)

            payload = format_for_telegram(response)

            response_correlation = getattr(getattr(response, 'meta', None), 'correlation_id', correlation_id)

            context_meta = {
                "command": "events",
                "topic": topic or "",
                "entity": entity or "",
                "window": window,
                "lang": lang,
                "k_final": context.get("params", {}).get("k_final", k_final),
                "sources": sources or [],
                "correlation_id": response_correlation,
            }

            return self._augment_payload(payload, context=context_meta)

        except Exception as exc:
            logger.error(f"[Phase3] /events failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_graph_command(
        self,
        *,
        query: str,
        hops: int = 3,
        window: str = "24h",
        lang: str = "auto",
        sources: Optional[List[str]] = None,
        k_final: int = 10,
        max_tokens: int = 8000,
        budget_cents: int = 50,
        timeout_s: int = 30,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute /graph command - Phase 3 knowledge graph construction"""

        correlation_id = correlation_id or f"graph-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(
                f"[Phase3] /graph | query='{query[:60]}...' hops={hops} window={window}"
            )

            args_tokens: List[str] = []
            if query:
                args_tokens.append(f'query="{self._escape_quotes(query)}"')
            if window:
                args_tokens.append(f"window={window}")
            if lang and lang != "auto":
                args_tokens.append(f"lang={lang}")
            if sources:
                args_tokens.append(f"sources={','.join(sources)}")
            if k_final:
                args_tokens.append(f"k={k_final}")
            if hops:
                args_tokens.append(f"hops={hops}")

            context, error_payload = await self._build_context(
                raw_command="/graph query",
                args_tokens=args_tokens,
                correlation_id=correlation_id,
                lang=lang,
                window=window,
                k_final=k_final,
                max_tokens=max_tokens,
                budget_cents=budget_cents,
                timeout_s=timeout_s,
            )
            if error_payload:
                return error_payload

            graph_ctx = context.setdefault("graph", {})
            graph_ctx["hop_limit"] = max(1, min(4, hops))
            
            raw_response = await self.orchestrator.execute(context)
            response = self._normalize_response(raw_response)

            payload = format_for_telegram(response)

            response_correlation = getattr(getattr(response, 'meta', None), 'correlation_id', correlation_id)

            context_meta = {
                "command": "graph",
                "query": query,
                "hops": max(1, min(4, hops)),
                "window": window,
                "lang": lang,
                "k_final": context.get("params", {}).get("k_final", k_final),
                "sources": sources or [],
                "correlation_id": response_correlation,
            }

            return self._augment_payload(payload, context=context_meta)

        except Exception as exc:
            logger.error(f"[Phase3] /graph failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_memory_command(
        self,
        *,
        operation: str = "recall",  # suggest|store|recall
        query: Optional[str] = None,
        window: str = "1w",
        lang: str = "auto",
        k_final: int = 5,
        user_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute /memory command with context builder"""

        correlation_id = correlation_id or f"memory-{uuid.uuid4().hex[:8]}"
        operation_normalized = (operation or "recall").strip().lower()
        if operation_normalized not in {"suggest", "store", "recall"}:
            operation_normalized = "recall"

        try:
            logger.info(
                f"[Phase3] /memory | operation={operation_normalized} query='{(query or '')[:40]}...'"
            )

            args_tokens: List[str] = []
            if query:
                args_tokens.append(f'query="{self._escape_quotes(query)}"')
            if window:
                args_tokens.append(f"window={window}")
            if lang and lang != "auto":
                args_tokens.append(f"lang={lang}")
            if k_final:
                args_tokens.append(f"k={k_final}")

            raw_command = f"/memory {operation_normalized}"
            context, error_payload = await self._build_context(
                raw_command=raw_command,
                args_tokens=args_tokens,
                correlation_id=correlation_id,
                lang=lang,
                window=window,
                k_final=k_final,
                max_tokens=4000,
                budget_cents=25,
                timeout_s=12,
            )
            if error_payload:
                return error_payload

            params = context.setdefault("params", {})
            params["user_id"] = user_id

            raw_response = await self.orchestrator.execute(context)
            response = self._normalize_response(raw_response)

            payload = format_for_telegram(response)

            response_correlation = getattr(getattr(response, 'meta', None), 'correlation_id', correlation_id)

            context_meta = {
                "command": "memory",
                "operation": operation_normalized,
                "query": query or "",
                "window": window,
                "lang": lang,
                "correlation_id": response_correlation,
            }

            return self._augment_payload(payload, context=context_meta)

        except Exception as exc:
            logger.error(f"[Phase3] /memory failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def _build_context(
        self,
        *,
        raw_command: str,
        args_tokens: List[str],
        correlation_id: str,
        lang: str,
        window: str,
        k_final: int,
        max_tokens: int,
        budget_cents: int,
        timeout_s: int,
        ab_test: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Build Phase 3 context via builder and handle errors"""

        args_string = " ".join(token for token in args_tokens if token).strip()
        builder_input = {
            "raw_command": raw_command,
            "args": args_string,
            "user_lang": lang,
            "env": {
                "defaults": {
                    "window": window,
                    "lang": lang,
                    "k_final": k_final,
                    "max_tokens": max_tokens,
                    "budget_cents": budget_cents,
                    "timeout_s": timeout_s,
                    "rerank_enabled": True,
                },
                "feature_flags": {
                    "auto_expand_window": True,
                    "relax_filters_on_empty": True,
                    "fallback_rerank_false_on_empty": True,
                },
                "version": "phase3-v1.1",
            },
            "ab_test": ab_test or {},
        }

        context = await self.context_builder.build_context(builder_input)
        if context.get("error"):
            return {}, self._builder_error_payload(context)

        context.setdefault("telemetry", {})["correlation_id"] = correlation_id
        return context, None

    def _builder_error_payload(self, builder_result: Dict[str, Any]) -> Dict[str, Any]:
        """Convert context builder error into Telegram payload"""

        error = builder_result.get("error", {})
        meta = builder_result.get("meta", {})
        correlation_id = meta.get("correlation_id", "phase3-context")
        user_message = error.get("user_message") or "Context builder failed"
        tech_message = error.get("tech_message")
        retryable = error.get("retryable")

        details_lines = [user_message]
        if tech_message:
            safe_tech = tech_message.replace("`", "'")
            details_lines.append(f"`{safe_tech}`")
        if retryable is not None:
            details_lines.append("Повтор возможен" if retryable else "Повтор не гарантирован")

        text = (
            "❌ **Phase 3 context builder error**\n\n"
            + "\n".join(details_lines)
            + "\n\n"
            + f"ID: `{correlation_id}`"
        )
        return {"text": text, "buttons": None, "parse_mode": "Markdown"}

    @staticmethod
    def _escape_quotes(value: str) -> str:
        """Escape double quotes for builder args"""
        return value.replace("", "\"")


    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _augment_payload(self, payload: Dict[str, Any], *, context: Dict[str, Any]) -> Dict[str, Any]:
        """Augment payload with context and buttons"""
        enriched = dict(payload)
        enriched.setdefault("parse_mode", "Markdown")
        enriched["context"] = context

        # Add refresh button
        buttons = []
        refresh_button = self._build_refresh_button(context)
        if refresh_button:
            buttons.append(refresh_button)

        enriched["buttons"] = buttons
        return enriched

    def _build_refresh_button(self, context: Dict[str, Any]) -> List[Dict[str, str]]:
        """Build refresh button based on command"""
        command = context.get("command")

        if command == "ask":
            query_key = self._compact_query(context.get("query", ""))
            depth = context.get("depth", 3)
            window = context.get("window", "24h")
            return [{"text": "🔄 Повторить", "callback_data": f"ask:refresh:{query_key}:{depth}:{window}"}]

        elif command == "events":
            topic = context.get("topic", "")
            window = context.get("window", "12h")
            return [{"text": "🔄 Обновить", "callback_data": f"events:refresh:{topic}:{window}"}]

        elif command == "graph":
            query_key = self._compact_query(context.get("query", ""))
            hops = context.get("hops", 3)
            window = context.get("window", "24h")
            return [{"text": "🔄 Перестроить", "callback_data": f"graph:refresh:{query_key}:{hops}:{window}"}]

        elif command == "memory":
            operation = context.get("operation", "recall")
            return [{"text": "🔄 Обновить", "callback_data": f"memory:refresh:{operation}"}]

        return []

    @staticmethod
    def _compact_query(query: str) -> str:
        """Create compact query token for callbacks"""
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
        """Build error payload"""
        text = (
            "❌ **Ошибка выполнения команды Phase 3**\n\n"
            f"{message}\n\n"
            f"ID: `{correlation_id}`"
        )
        return {"text": text, "buttons": None, "parse_mode": "Markdown"}


# Singleton instance
_phase3_handler_instance: Optional[Phase3HandlerService] = None


def get_phase3_handler_service() -> Phase3HandlerService:
    """Get singleton Phase3HandlerService"""
    global _phase3_handler_instance
    if _phase3_handler_instance is None:
        _phase3_handler_instance = Phase3HandlerService()
    return _phase3_handler_instance


# Public helper functions for bot integration
async def execute_ask_command(
    *,
    query: str,
    depth: int = 3,
    window: str = "7d",  # Changed default from 24h to 7d
    lang: str = "auto",
    sources: Optional[List[str]] = None,
    k_final: int = 10,  # Increased from 5 to 10 for better diversity
    max_tokens: int = 8000,
    budget_cents: int = 50,
    timeout_s: int = 30,
    correlation_id: Optional[str] = None,
    intent: str = "news_current_events",  # NEW: intent classification
    domains: Optional[List[str]] = None,  # NEW: site: domains
    after_date: Optional[Any] = None,  # NEW: after: date filter
    before_date: Optional[Any] = None,  # NEW: before: date filter
) -> Dict[str, Any]:
    """Public helper for /ask command"""
    service = get_phase3_handler_service()
    return await service.handle_ask_command(
        query=query,
        depth=depth,
        window=window,
        lang=lang,
        sources=sources or domains,  # Use domains from site: if provided
        k_final=k_final,
        max_tokens=max_tokens,
        budget_cents=budget_cents,
        timeout_s=timeout_s,
        correlation_id=correlation_id,
        intent=intent,
        after_date=after_date,
        before_date=before_date
    )


async def execute_events_command(
    *,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    window: str = "12h",
    lang: str = "auto",
    sources: Optional[List[str]] = None,
    k_final: int = 10,
    max_tokens: int = 8000,
    budget_cents: int = 50,
    timeout_s: int = 30,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Public helper for /events command"""
    service = get_phase3_handler_service()
    return await service.handle_events_command(
        topic=topic,
        entity=entity,
        window=window,
        lang=lang,
        sources=sources,
        k_final=k_final,
        max_tokens=max_tokens,
        budget_cents=budget_cents,
        timeout_s=timeout_s,
        correlation_id=correlation_id
    )


async def execute_graph_command(
    *,
    query: str,
    hops: int = 3,
    window: str = "24h",
    lang: str = "auto",
    sources: Optional[List[str]] = None,
    k_final: int = 10,
    max_tokens: int = 8000,
    budget_cents: int = 50,
    timeout_s: int = 30,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Public helper for /graph command"""
    service = get_phase3_handler_service()
    return await service.handle_graph_command(
        query=query,
        hops=hops,
        window=window,
        lang=lang,
        sources=sources,
        k_final=k_final,
        max_tokens=max_tokens,
        budget_cents=budget_cents,
        timeout_s=timeout_s,
        correlation_id=correlation_id
    )


async def execute_memory_command(
    *,
    operation: str = "recall",
    query: Optional[str] = None,
    window: str = "1w",
    lang: str = "auto",
    k_final: int = 5,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Public helper for /memory command"""
    service = get_phase3_handler_service()
    return await service.handle_memory_command(
        operation=operation,
        query=query,
        window=window,
        lang=lang,
        k_final=k_final,
        correlation_id=correlation_id
    )

async def handle_phase3_request_cli(query: str, lang: str):
    """
    Handles a Phase 3 request from the CLI.
    """
    service = get_phase3_handler_service()
    # This is a simplified example. In a real scenario, you might want to
    # parse more arguments from the CLI.
    result = await service.handle_ask_command(query=query, lang=lang)
    print(result.get("text"))