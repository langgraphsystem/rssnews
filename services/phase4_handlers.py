"""
Phase 4 Bot Handlers — Telegram-facing handlers for Phase4 commands
Supports: /dashboard, /reports, /schedule, /alerts, /optimize, /brief, /pricing
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from services.orchestrator import get_phase4_orchestrator, execute_phase4_context
from core.ux.formatter import format_for_telegram
from core.rag.retrieval_client import get_retrieval_client

logger = logging.getLogger(__name__)


class Phase4HandlerService:
    """Service for Phase 4 command handlers"""

    def __init__(self):
        self.retrieval_client = get_retrieval_client()

    async def handle_dashboard_command(
        self,
        *,
        mode: str = "live",  # live | custom
        metrics: Optional[List[str]] = None,
        window: str = "24h",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute /dashboard command

        Args:
            mode: Dashboard mode (live or custom)
            metrics: Metrics to display
            window: Time window
            lang: Language
            correlation_id: Correlation ID

        Returns:
            Telegram-ready payload dict
        """
        correlation_id = correlation_id or f"dashboard-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"[Phase4] /dashboard | mode={mode} window={window}")

            # Retrieve documents for context (minimal set for dashboard)
            docs = await self.retrieval_client.retrieve(
                query="metrics performance",
                window=window,
                lang=lang,
                k_final=5,
                use_rerank=False
            )

            # Build context
            context = {
                "command": f"/dashboard {mode}",
                "params": {
                    "metrics": metrics or ["traffic", "ctr", "conv"],
                    "lang": lang,
                },
                "retrieval": {
                    "docs": docs,
                    "window": window,
                    "lang": lang,
                    "k_final": 5,
                    "rerank_enabled": False
                },
                "history": {
                    "metrics": [],  # Would be populated from DB in production
                    "snapshots": []
                },
                "models": {
                    "primary": "claude-4.5",
                    "fallback": ["gpt-5", "gemini-2.5-pro"]
                },
                "limits": {
                    "max_tokens": 4000,
                    "budget_cents": 25,
                    "timeout_s": 15
                },
                "telemetry": {
                    "correlation_id": correlation_id,
                    "version": "phase4-v1.0"
                }
            }

            # Execute
            response_dict = await execute_phase4_context(context)

            # Format
            payload = format_for_telegram(response_dict)
            payload["correlation_id"] = correlation_id

            logger.info(f"[Phase4] /dashboard completed: {correlation_id}")
            return payload

        except Exception as exc:
            logger.error(f"[Phase4] /dashboard failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_reports_command(
        self,
        *,
        action: str = "generate",  # generate | list
        period: str = "weekly",  # weekly | monthly
        audience: Optional[str] = None,
        window: str = "1w",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute /reports command

        Args:
            action: Report action
            period: Report period
            audience: Target audience
            window: Time window
            lang: Language
            correlation_id: Correlation ID

        Returns:
            Telegram-ready payload dict
        """
        correlation_id = correlation_id or f"reports-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"[Phase4] /reports | action={action} period={period}")

            # Retrieve documents
            docs = await self.retrieval_client.retrieve(
                query="trends performance metrics",
                window=window,
                lang=lang,
                k_final=10,
                use_rerank=True
            )

            # Build context
            context = {
                "command": f"/reports {action} {period}",
                "params": {
                    "period": period,
                    "audience": audience,
                    "lang": lang,
                },
                "retrieval": {
                    "docs": docs,
                    "window": window,
                    "lang": lang,
                    "k_final": 10,
                    "rerank_enabled": True
                },
                "history": {
                    "snapshots": [],
                    "metrics": [],
                    "competitors": []
                },
                "models": {
                    "primary": "gpt-5",
                    "fallback": ["claude-4.5", "gemini-2.5-pro"]
                },
                "limits": {
                    "max_tokens": 8000,
                    "budget_cents": 50,
                    "timeout_s": 30
                },
                "telemetry": {
                    "correlation_id": correlation_id,
                    "version": "phase4-v1.0"
                }
            }

            # Execute
            response_dict = await execute_phase4_context(context)

            # Format
            payload = format_for_telegram(response_dict)
            payload["correlation_id"] = correlation_id

            logger.info(f"[Phase4] /reports completed: {correlation_id}")
            return payload

        except Exception as exc:
            logger.error(f"[Phase4] /reports failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_schedule_command(
        self,
        *,
        action: str = "setup",  # setup | list | delete
        cron: str = "0 9 * * 1",  # Monday 9 AM
        period: str = "weekly",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute /schedule command

        Args:
            action: Schedule action
            cron: Cron expression
            period: Report period
            lang: Language
            correlation_id: Correlation ID

        Returns:
            Telegram-ready payload dict
        """
        correlation_id = correlation_id or f"schedule-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"[Phase4] /schedule | action={action} cron={cron}")

            # Build context
            context = {
                "command": f"/schedule {action}",
                "params": {
                    "schedule": {"cron": cron},
                    "period": period,
                    "lang": lang,
                },
                "retrieval": {
                    "docs": [],
                    "window": "1w",
                    "lang": lang,
                    "k_final": 0,
                    "rerank_enabled": False
                },
                "models": {
                    "primary": "gpt-5",
                    "fallback": ["claude-4.5"]
                },
                "limits": {
                    "max_tokens": 2000,
                    "budget_cents": 10,
                    "timeout_s": 10
                },
                "telemetry": {
                    "correlation_id": correlation_id,
                    "version": "phase4-v1.0"
                }
            }

            # Execute
            response_dict = await execute_phase4_context(context)

            # Format
            payload = format_for_telegram(response_dict)
            payload["correlation_id"] = correlation_id

            logger.info(f"[Phase4] /schedule completed: {correlation_id}")
            return payload

        except Exception as exc:
            logger.error(f"[Phase4] /schedule failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_alerts_command(
        self,
        *,
        action: str = "setup",  # setup | test | list
        conditions: Optional[List[str]] = None,
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute /alerts command

        Args:
            action: Alert action
            conditions: Alert conditions
            lang: Language
            correlation_id: Correlation ID

        Returns:
            Telegram-ready payload dict
        """
        correlation_id = correlation_id or f"alerts-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"[Phase4] /alerts | action={action}")

            # Build context
            context = {
                "command": f"/alerts {action}",
                "params": {
                    "conditions": conditions or [],
                    "lang": lang,
                },
                "retrieval": {
                    "docs": [],
                    "window": "1h",
                    "lang": lang,
                    "k_final": 0,
                    "rerank_enabled": False
                },
                "models": {
                    "primary": "gpt-5",
                    "fallback": ["claude-4.5"]
                },
                "limits": {
                    "max_tokens": 2000,
                    "budget_cents": 10,
                    "timeout_s": 10
                },
                "telemetry": {
                    "correlation_id": correlation_id,
                    "version": "phase4-v1.0"
                }
            }

            # Execute
            response_dict = await execute_phase4_context(context)

            # Format
            payload = format_for_telegram(response_dict)
            payload["correlation_id"] = correlation_id

            logger.info(f"[Phase4] /alerts completed: {correlation_id}")
            return payload

        except Exception as exc:
            logger.error(f"[Phase4] /alerts failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_optimize_listing_command(
        self,
        *,
        goal: str = "ctr",  # ctr | conversion | seo | retention
        product: Optional[str] = None,
        window: str = "1w",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute /optimize listing command

        Args:
            goal: Optimization goal
            product: Product name
            window: Time window
            lang: Language
            correlation_id: Correlation ID

        Returns:
            Telegram-ready payload dict
        """
        correlation_id = correlation_id or f"optimize-listing-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"[Phase4] /optimize listing | goal={goal}")

            # Retrieve documents for context
            docs = await self.retrieval_client.retrieve(
                query=f"{product or 'product'} features benefits",
                window=window,
                lang=lang,
                k_final=5,
                use_rerank=True
            )

            # Build context
            context = {
                "command": "/optimize listing",
                "params": {
                    "goal": goal,
                    "product": product,
                    "lang": lang,
                },
                "retrieval": {
                    "docs": docs,
                    "window": window,
                    "lang": lang,
                    "k_final": 5,
                    "rerank_enabled": True
                },
                "models": {
                    "primary": "claude-4.5",
                    "fallback": ["gpt-5", "gemini-2.5-pro"]
                },
                "limits": {
                    "max_tokens": 6000,
                    "budget_cents": 40,
                    "timeout_s": 25
                },
                "telemetry": {
                    "correlation_id": correlation_id,
                    "version": "phase4-v1.0"
                }
            }

            # Execute
            response_dict = await execute_phase4_context(context)

            # Format
            payload = format_for_telegram(response_dict)
            payload["correlation_id"] = correlation_id

            logger.info(f"[Phase4] /optimize listing completed: {correlation_id}")
            return payload

        except Exception as exc:
            logger.error(f"[Phase4] /optimize listing failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_brief_command(
        self,
        *,
        channels: Optional[List[str]] = None,
        objective: str = "awareness",  # awareness | activation | retention
        window: str = "1w",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute /brief assets command

        Args:
            channels: Target channels
            objective: Campaign objective
            window: Time window
            lang: Language
            correlation_id: Correlation ID

        Returns:
            Telegram-ready payload dict
        """
        correlation_id = correlation_id or f"brief-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"[Phase4] /brief | channels={channels} objective={objective}")

            # Retrieve documents
            docs = await self.retrieval_client.retrieve(
                query="creative trends design",
                window=window,
                lang=lang,
                k_final=5,
                use_rerank=False
            )

            # Build context
            context = {
                "command": "/brief assets",
                "params": {
                    "channels": channels or ["web", "social"],
                    "objective": objective,
                    "lang": lang,
                },
                "retrieval": {
                    "docs": docs,
                    "window": window,
                    "lang": lang,
                    "k_final": 5,
                    "rerank_enabled": False
                },
                "models": {
                    "primary": "gemini-2.5-pro",
                    "fallback": ["gpt-5"]
                },
                "limits": {
                    "max_tokens": 4000,
                    "budget_cents": 30,
                    "timeout_s": 20
                },
                "telemetry": {
                    "correlation_id": correlation_id,
                    "version": "phase4-v1.0"
                }
            }

            # Execute
            response_dict = await execute_phase4_context(context)

            # Format
            payload = format_for_telegram(response_dict)
            payload["correlation_id"] = correlation_id

            logger.info(f"[Phase4] /brief completed: {correlation_id}")
            return payload

        except Exception as exc:
            logger.error(f"[Phase4] /brief failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_pricing_command(
        self,
        *,
        product: Optional[str] = None,
        plan: Optional[str] = None,
        targets: Optional[Dict[str, float]] = None,
        window: str = "1m",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute /pricing advisor command

        Args:
            product: Product name
            plan: Plan name
            targets: ROI targets
            window: Time window
            lang: Language
            correlation_id: Correlation ID

        Returns:
            Telegram-ready payload dict
        """
        correlation_id = correlation_id or f"pricing-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"[Phase4] /pricing | product={product} plan={plan}")

            # Retrieve documents
            docs = await self.retrieval_client.retrieve(
                query="pricing plans competitors",
                window=window,
                lang=lang,
                k_final=5,
                use_rerank=True
            )

            # Build context
            context = {
                "command": "/pricing advisor",
                "params": {
                    "product": product,
                    "plan": plan,
                    "targets": targets or {"roi_min": 2.0, "cac_max": 100.0},
                    "lang": lang,
                },
                "retrieval": {
                    "docs": docs,
                    "window": window,
                    "lang": lang,
                    "k_final": 5,
                    "rerank_enabled": True
                },
                "models": {
                    "primary": "gpt-5",
                    "fallback": ["claude-4.5", "gemini-2.5-pro"]
                },
                "limits": {
                    "max_tokens": 6000,
                    "budget_cents": 40,
                    "timeout_s": 25
                },
                "telemetry": {
                    "correlation_id": correlation_id,
                    "version": "phase4-v1.0"
                }
            }

            # Execute
            response_dict = await execute_phase4_context(context)

            # Format
            payload = format_for_telegram(response_dict)
            payload["correlation_id"] = correlation_id

            logger.info(f"[Phase4] /pricing completed: {correlation_id}")
            return payload

        except Exception as exc:
            logger.error(f"[Phase4] /pricing failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    async def handle_optimize_campaign_command(
        self,
        *,
        channel: str = "web",  # web | social | email | ads
        metrics: Optional[List[str]] = None,
        window: str = "1w",
        lang: str = "auto",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute /optimize campaign command

        Args:
            channel: Campaign channel
            metrics: Metrics to optimize
            window: Time window
            lang: Language
            correlation_id: Correlation ID

        Returns:
            Telegram-ready payload dict
        """
        correlation_id = correlation_id or f"optimize-campaign-{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"[Phase4] /optimize campaign | channel={channel}")

            # Retrieve documents
            docs = await self.retrieval_client.retrieve(
                query=f"{channel} campaign optimization",
                window=window,
                lang=lang,
                k_final=5,
                use_rerank=True
            )

            # Build context
            context = {
                "command": "/optimize campaign",
                "params": {
                    "channels": [channel],
                    "metrics": metrics or ["ctr", "conv", "roi"],
                    "lang": lang,
                },
                "retrieval": {
                    "docs": docs,
                    "window": window,
                    "lang": lang,
                    "k_final": 5,
                    "rerank_enabled": True
                },
                "history": {
                    "metrics": []
                },
                "models": {
                    "primary": "gpt-5",
                    "fallback": ["claude-4.5"]
                },
                "limits": {
                    "max_tokens": 4000,
                    "budget_cents": 30,
                    "timeout_s": 20
                },
                "telemetry": {
                    "correlation_id": correlation_id,
                    "version": "phase4-v1.0"
                }
            }

            # Execute
            response_dict = await execute_phase4_context(context)

            # Format
            payload = format_for_telegram(response_dict)
            payload["correlation_id"] = correlation_id

            logger.info(f"[Phase4] /optimize campaign completed: {correlation_id}")
            return payload

        except Exception as exc:
            logger.error(f"[Phase4] /optimize campaign failed: {exc}", exc_info=True)
            return self._error_payload(str(exc), correlation_id)

    def _error_payload(self, error_msg: str, correlation_id: str) -> Dict[str, Any]:
        """Build error payload"""
        return {
            "success": False,
            "correlation_id": correlation_id,
            "text": f"❌ Error: {error_msg}",
            "parse_mode": "Markdown"
        }


# Singleton instance
_phase4_handler_service: Optional[Phase4HandlerService] = None


def get_phase4_handler_service() -> Phase4HandlerService:
    """Get or create Phase4HandlerService instance"""
    global _phase4_handler_service
    if _phase4_handler_service is None:
        _phase4_handler_service = Phase4HandlerService()
    return _phase4_handler_service
