"""
Phase 1 Orchestrator — retrieval → agents → format → validate with monitoring hooks.
"""

import logging
import uuid
from typing import Any, Dict, Literal, Optional

from core.orchestrator.nodes.retrieval_node import retrieval_node
from core.orchestrator.nodes.agents_node import agents_node
from core.orchestrator.nodes.validate_node import validate_node
from core.orchestrator.nodes.format_node import format_node

from schemas.analysis_schemas import BaseAnalysisResponse, ErrorResponse, Meta, build_error_response
from infra.config.phase1_config import get_config
from monitoring.metrics import (
    ensure_metrics_server,
    record_orchestrator_error,
    record_orchestrator_start,
    record_orchestrator_success,
)

logger = logging.getLogger(__name__)


class Phase1Orchestrator:
    """Coordinates Phase 1 analysis commands."""

    def __init__(self) -> None:
        self.config = get_config()
        ensure_metrics_server()

    async def execute_trends(
        self,
        window: str = "24h",
        lang: str = "auto",
        sources: Optional[list] = None,
        k_final: int = 5,
    ) -> BaseAnalysisResponse | ErrorResponse:
        command_name = "trends"
        correlation_id = str(uuid.uuid4())
        timer = record_orchestrator_start(command_name)

        logger.info(
            f"[{correlation_id}] Executing /trends: window={window}, lang={lang}, k={k_final}"
        )

        state = {
            "command": "/trends",
            "params": {
                "window": window,
                "lang": lang,
                "sources": sources,
                "k_final": k_final,
            },
            "query": None,
            "window": window,
            "lang": lang,
            "sources": sources,
            "k_final": k_final,
            "use_rerank": self.config.retrieval.enable_rerank,
            "correlation_id": correlation_id,
        }

        try:
            state = await retrieval_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "retrieval")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            docs = state.get("docs", [])

            state = await agents_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "agent_failure")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await format_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "format_error")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await validate_node(state)
            if not state.get("validation_passed", False):
                errors = state.get("validation_errors", ["Unknown validation error"])
                record_orchestrator_error(command_name, timer, "validation_failed")
                return self._build_validation_error_response(errors, correlation_id)

            response = state["response_draft"]
            evidence_count = len(response.evidence) if isinstance(response, BaseAnalysisResponse) else 0
            record_orchestrator_success(command_name, timer, evidence_count, len(docs))
            logger.info(f"[{correlation_id}] /trends completed successfully")
            return response

        except Exception as exc:  # pragma: no cover - defensive
            record_orchestrator_error(command_name, timer, "exception")
            logger.error(f"[{correlation_id}] /trends failed: {exc}", exc_info=True)
            return self._build_exception_error_response(exc, correlation_id)

    async def execute_analyze(
        self,
        mode: Literal["keywords", "sentiment", "topics"],
        query: Optional[str] = None,
        window: str = "24h",
        lang: str = "auto",
        sources: Optional[list] = None,
        k_final: int = 5,
    ) -> BaseAnalysisResponse | ErrorResponse:
        mode_normalized = mode.lower()
        command_name = f"analyze_{mode_normalized}"
        correlation_id = str(uuid.uuid4())
        timer = record_orchestrator_start(command_name)

        logger.info(
            f"[{correlation_id}] Executing /analyze {mode_normalized}: query={query or 'none'}, window={window}, k={k_final}"
        )

        if not self._is_mode_enabled(mode_normalized):
            record_orchestrator_error(command_name, timer, "feature_disabled")
            return self._build_feature_disabled_response(mode_normalized, correlation_id)

        state = {
            "command": "/analyze",
            "params": {
                "mode": mode_normalized,
                "window": window,
                "lang": lang,
                "sources": sources,
                "k_final": k_final,
            },
            "query": query,
            "window": window,
            "lang": lang,
            "sources": sources,
            "k_final": k_final,
            "use_rerank": self.config.retrieval.enable_rerank,
            "correlation_id": correlation_id,
        }

        try:
            state = await retrieval_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "retrieval")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            docs = state.get("docs", [])
            if not docs:
                record_orchestrator_error(command_name, timer, "no_data")
                return self._build_no_data_response(correlation_id)

            state = await agents_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "agent_failure")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await format_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "format_error")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await validate_node(state)
            if not state.get("validation_passed", False):
                errors = state.get("validation_errors", ["Unknown validation error"])
                record_orchestrator_error(command_name, timer, "validation_failed")
                return self._build_validation_error_response(errors, correlation_id)

            response = state["response_draft"]
            evidence_count = len(response.evidence) if isinstance(response, BaseAnalysisResponse) else 0
            record_orchestrator_success(command_name, timer, evidence_count, len(docs))
            logger.info(f"[{correlation_id}] /analyze {mode_normalized} completed successfully")
            return response

        except Exception as exc:  # pragma: no cover - defensive
            record_orchestrator_error(command_name, timer, "exception")
            logger.error(f"[{correlation_id}] /analyze {mode_normalized} failed: {exc}", exc_info=True)
            return self._build_exception_error_response(exc, correlation_id)

    async def execute_predict_trends(
        self,
        topic: Optional[str] = None,
        window: str = "1w",
        lang: str = "auto",
        sources: Optional[list] = None,
        k_final: int = 5,
    ) -> BaseAnalysisResponse | ErrorResponse:
        """Execute /predict trends command (Phase 2)"""
        command_name = "predict_trends"
        correlation_id = str(uuid.uuid4())
        timer = record_orchestrator_start(command_name)

        logger.info(
            f"[{correlation_id}] Executing /predict trends: topic={topic or 'general'}, window={window}, k={k_final}"
        )

        state = {
            "command": "/predict",
            "params": {
                "topic": topic,
                "window": window,
                "lang": lang,
                "sources": sources,
                "k_final": k_final,
            },
            "query": topic,  # topic acts as query for retrieval
            "window": window,
            "lang": lang,
            "sources": sources,
            "k_final": k_final,
            "use_rerank": self.config.retrieval.enable_rerank,
            "correlation_id": correlation_id,
        }

        try:
            state = await retrieval_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "retrieval")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            docs = state.get("docs", [])
            if not docs:
                record_orchestrator_error(command_name, timer, "no_data")
                return self._build_no_data_response(correlation_id)

            state = await agents_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "agent_failure")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await format_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "format_error")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await validate_node(state)
            if not state.get("validation_passed", False):
                errors = state.get("validation_errors", ["Unknown validation error"])
                record_orchestrator_error(command_name, timer, "validation_failed")
                return self._build_validation_error_response(errors, correlation_id)

            response = state["response_draft"]
            evidence_count = len(response.evidence) if isinstance(response, BaseAnalysisResponse) else 0
            record_orchestrator_success(command_name, timer, evidence_count, len(docs))
            logger.info(f"[{correlation_id}] /predict trends completed successfully")
            return response

        except Exception as exc:  # pragma: no cover - defensive
            record_orchestrator_error(command_name, timer, "exception")
            logger.error(f"[{correlation_id}] /predict trends failed: {exc}", exc_info=True)
            return self._build_exception_error_response(exc, correlation_id)

    async def execute_analyze_competitors(
        self,
        domains: Optional[list] = None,
        niche: Optional[str] = None,
        window: str = "1w",
        lang: str = "auto",
        sources: Optional[list] = None,
        k_final: int = 10,
    ) -> BaseAnalysisResponse | ErrorResponse:
        """Execute /analyze competitors command (Phase 2)"""
        command_name = "analyze_competitors"
        correlation_id = str(uuid.uuid4())
        timer = record_orchestrator_start(command_name)

        logger.info(
            f"[{correlation_id}] Executing /analyze competitors: domains={domains}, niche={niche}, window={window}, k={k_final}"
        )

        # Build query from niche or use general query
        query = niche if niche else None

        state = {
            "command": "/competitors",
            "params": {
                "domains": domains,
                "niche": niche,
                "window": window,
                "lang": lang,
                "sources": sources,
                "k_final": k_final,
            },
            "query": query,
            "window": window,
            "lang": lang,
            "sources": sources,
            "k_final": k_final,
            "use_rerank": self.config.retrieval.enable_rerank,
            "correlation_id": correlation_id,
        }

        try:
            state = await retrieval_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "retrieval")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            docs = state.get("docs", [])
            if not docs:
                record_orchestrator_error(command_name, timer, "no_data")
                return self._build_no_data_response(correlation_id)

            state = await agents_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "agent_failure")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await format_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "format_error")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await validate_node(state)
            if not state.get("validation_passed", False):
                errors = state.get("validation_errors", ["Unknown validation error"])
                record_orchestrator_error(command_name, timer, "validation_failed")
                return self._build_validation_error_response(errors, correlation_id)

            response = state["response_draft"]
            evidence_count = len(response.evidence) if isinstance(response, BaseAnalysisResponse) else 0
            record_orchestrator_success(command_name, timer, evidence_count, len(docs))
            logger.info(f"[{correlation_id}] /analyze competitors completed successfully")
            return response

        except Exception as exc:  # pragma: no cover - defensive
            record_orchestrator_error(command_name, timer, "exception")
            logger.error(f"[{correlation_id}] /analyze competitors failed: {exc}", exc_info=True)
            return self._build_exception_error_response(exc, correlation_id)

    async def execute_synthesize(
        self,
        agent_outputs: Dict[str, Any],
        window: str = "24h",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> BaseAnalysisResponse | ErrorResponse:
        """Execute /synthesize command (Phase 2) - meta-analysis of agent outputs"""
        command_name = "synthesize"
        correlation_id = correlation_id or str(uuid.uuid4())
        timer = record_orchestrator_start(command_name)

        logger.info(
            f"[{correlation_id}] Executing /synthesize: agent_count={len(agent_outputs)}"
        )

        # Synthesis doesn't need retrieval - it works with existing agent outputs
        # But we need docs for evidence, so extract from agent_outputs if available
        docs = agent_outputs.get("_docs", [])

        state = {
            "command": "/synthesize",
            "params": {
                "window": window,
                "lang": lang,
            },
            "docs": docs,
            "agent_results": agent_outputs,  # Pass existing agent outputs
            "window": window,
            "lang": lang,
            "correlation_id": correlation_id,
        }

        try:
            # Skip retrieval - synthesis works with existing data
            state = await agents_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "agent_failure")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await format_node(state)
            if "error" in state:
                reason = state.get("error", {}).get("code", "format_error")
                record_orchestrator_error(command_name, timer, reason)
                return self._build_error_response(state, correlation_id)

            state = await validate_node(state)
            if not state.get("validation_passed", False):
                errors = state.get("validation_errors", ["Unknown validation error"])
                record_orchestrator_error(command_name, timer, "validation_failed")
                return self._build_validation_error_response(errors, correlation_id)

            response = state["response_draft"]
            evidence_count = len(response.evidence) if isinstance(response, BaseAnalysisResponse) else 0
            record_orchestrator_success(command_name, timer, evidence_count, len(docs))
            logger.info(f"[{correlation_id}] /synthesize completed successfully")
            return response

        except Exception as exc:  # pragma: no cover - defensive
            record_orchestrator_error(command_name, timer, "exception")
            logger.error(f"[{correlation_id}] /synthesize failed: {exc}", exc_info=True)
            return self._build_exception_error_response(exc, correlation_id)

    def _is_mode_enabled(self, mode: str) -> bool:
        feature_map = {
            "keywords": self.config.features.enable_analyze_keywords,
            "sentiment": self.config.features.enable_analyze_sentiment,
            "topics": self.config.features.enable_analyze_topics,
        }
        return feature_map.get(mode, False)

    def _build_error_response(self, state: Dict[str, Any], correlation_id: str) -> ErrorResponse:
        error_info = state.get("error", {})
        code = error_info.get("code", "INTERNAL")
        message = error_info.get("message", "Unknown error")

        meta = Meta(
            confidence=0.0,
            model="unknown",
            version="phase1-v1.0",
            correlation_id=correlation_id,
        )

        safe_code = code if code in {"VALIDATION_FAILED", "NO_DATA", "BUDGET_EXCEEDED", "MODEL_UNAVAILABLE", "INTERNAL"} else "INTERNAL"

        return build_error_response(
            code=safe_code,
            user_message=f"Analysis failed: {message}",
            tech_message=message,
            retryable=safe_code != "VALIDATION_FAILED",
            meta=meta,
        )

    def _build_validation_error_response(self, errors: list, correlation_id: str) -> ErrorResponse:
        meta = Meta(
            confidence=0.0,
            model="unknown",
            version="phase1-v1.0",
            correlation_id=correlation_id,
        )

        return build_error_response(
            code="VALIDATION_FAILED",
            user_message="Response validation failed",
            tech_message="; ".join(errors),
            retryable=False,
            meta=meta,
        )

    def _build_exception_error_response(self, exception: Exception, correlation_id: str) -> ErrorResponse:
        meta = Meta(
            confidence=0.0,
            model="unknown",
            version="phase1-v1.0",
            correlation_id=correlation_id,
        )

        return build_error_response(
            code="INTERNAL",
            user_message="Internal error occurred",
            tech_message=str(exception),
            retryable=True,
            meta=meta,
        )

    def _build_no_data_response(self, correlation_id: str) -> ErrorResponse:
        meta = Meta(
            confidence=0.0,
            model="unknown",
            version="phase1-v1.0",
            correlation_id=correlation_id,
        )

        return build_error_response(
            code="NO_DATA",
            user_message="No articles found for the specified criteria",
            tech_message="Retrieval returned 0 documents",
            retryable=True,
            meta=meta,
        )

    def _build_feature_disabled_response(self, mode: str, correlation_id: str) -> ErrorResponse:
        meta = Meta(
            confidence=0.0,
            model="unknown",
            version="phase1-v1.0",
            correlation_id=correlation_id,
        )

        return build_error_response(
            code="INTERNAL",
            user_message=f"Analysis mode '{mode}' is not available",
            tech_message=f"Feature flag for {mode} is disabled",
            retryable=False,
            meta=meta,
        )


def get_orchestrator() -> Phase1Orchestrator:
    """Return singleton orchestrator instance."""
    global _ORCHESTRATOR_INSTANCE
    if _ORCHESTRATOR_INSTANCE is None:
        _ORCHESTRATOR_INSTANCE = Phase1Orchestrator()
    return _ORCHESTRATOR_INSTANCE


_ORCHESTRATOR_INSTANCE: Phase1Orchestrator | None = None
