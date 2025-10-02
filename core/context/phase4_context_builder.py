"""
Phase 4 Context Builder — Constructs valid context for Phase4Orchestrator
Handles: /dashboard, /reports, /schedule, /alerts, /optimize, /brief, /pricing, /campaign
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.rag.retrieval_client import get_retrieval_client

logger = logging.getLogger(__name__)

VALID_WINDOWS = ["6h", "12h", "24h", "1d", "3d", "1w", "2w", "1m", "3m", "6m", "1y"]

WINDOW_EXPANSION = {
    "6h": "12h", "12h": "24h", "24h": "3d", "3d": "1w",
    "1w": "2w", "2w": "1m", "1m": "3m", "3m": "6m", "6m": "1y", "1y": "1y"
}


class Phase4ContextBuilder:
    """Builds valid context for Phase4Orchestrator from raw input"""

    def __init__(self):
        self.retrieval_client = get_retrieval_client()

    async def build_context(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """Build valid context or return error"""
        correlation_id = self._generate_correlation_id()

        try:
            if not raw_input.get("raw_command"):
                return self._error_response(
                    "VALIDATION_FAILED",
                    "Cannot construct context: no raw input provided",
                    "Missing required field 'raw_command'",
                    False,
                    correlation_id
                )

            raw_command = raw_input["raw_command"]
            args = raw_input.get("args", "")
            user_lang = raw_input.get("user_lang", "auto")
            env = raw_input.get("env", {})
            ab_test = raw_input.get("ab_test", {})

            # Normalize command
            command = self._normalize_command(raw_command)
            if not command:
                return self._error_response(
                    "VALIDATION_FAILED",
                    f"Unsupported command: {raw_command}",
                    f"Command '{raw_command}' not in Phase4 supported set",
                    False,
                    correlation_id
                )

            # Parse arguments
            parsed_args = self._parse_args(args, command)

            # Get defaults
            defaults = env.get("defaults", {})
            feature_flags = env.get("feature_flags", {})

            # Build params
            params = self._build_params(parsed_args, defaults, user_lang)

            # Build models
            models = self._build_models(command)

            # Build limits
            limits = self._build_limits(defaults)

            # Determine if retrieval needed
            needs_retrieval = self._command_needs_retrieval(command)

            # Perform retrieval if needed
            if needs_retrieval:
                retrieval, recovery_warnings = await self._perform_retrieval_with_recovery(
                    params, feature_flags, correlation_id
                )
            else:
                retrieval = self._build_empty_retrieval(params)
                recovery_warnings = []

            # Build history
            history = self._build_history(command, params)

            # Validate data availability
            if needs_retrieval and not retrieval["docs"] and not self._has_history_data(history):
                return self._error_response(
                    "NO_DATA",
                    "No data available for analysis",
                    f"Retrieval returned 0 documents and no history data. "
                    f"Steps: {', '.join(recovery_warnings) if recovery_warnings else 'none'}",
                    True,
                    correlation_id
                )

            # Align k_final
            params["k_final"] = len(retrieval["docs"]) if retrieval["docs"] else params["k_final"]

            # Build personalization
            personalization = self._build_personalization(params, user_lang, feature_flags)

            # Build telemetry
            telemetry = {
                "correlation_id": correlation_id,
                "version": env.get("version", "phase4-orchestrator")
            }

            # Construct context
            context = {
                "command": command,
                "params": params,
                "retrieval": retrieval,
                "history": history,
                "models": models,
                "limits": limits,
                "ab_test": ab_test,
                "personalization": personalization,
                "telemetry": telemetry
            }

            # Validate
            validation_error = self._validate_context(context)
            if validation_error:
                return self._error_response(
                    "VALIDATION_FAILED",
                    "Context validation failed",
                    validation_error,
                    False,
                    correlation_id
                )

            logger.info(f"[{correlation_id}] Phase4 context built: {command}")
            return context

        except Exception as e:
            logger.error(f"[{correlation_id}] Phase4 context builder failed: {e}", exc_info=True)
            return self._error_response(
                "INTERNAL",
                "Internal error building context",
                str(e),
                True,
                correlation_id
            )

    def _normalize_command(self, raw_command: str) -> Optional[str]:
        """Normalize to Phase4 command"""
        cmd = raw_command.strip().lower()

        if "/dashboard" in cmd:
            if "custom" in cmd:
                return "/dashboard custom"
            return "/dashboard live"
        elif "/reports" in cmd and "generate" in cmd:
            return "/reports generate"
        elif "/schedule" in cmd and "report" in cmd:
            return "/schedule report"
        elif "/alerts" in cmd:
            if "test" in cmd:
                return "/alerts test"
            return "/alerts setup"
        elif "/optimize" in cmd and "listing" in cmd:
            return "/optimize listing"
        elif "/brief" in cmd and "assets" in cmd:
            return "/brief assets"
        elif "/pricing" in cmd and "advisor" in cmd:
            return "/pricing advisor"
        elif "/optimize" in cmd and "campaign" in cmd:
            return "/optimize campaign"
        else:
            return None

    def _parse_args(self, args: str, command: str) -> Dict[str, Any]:
        """Parse arguments"""
        parsed = {}

        # Window
        window_match = re.search(r'\b(6h|12h|24h|1d|3d|1w|2w|1m|3m|6m|1y)\b', args)
        if window_match:
            parsed["window"] = window_match.group(1)

        # Lang
        lang_match = re.search(r'\blang[=:]?(ru|en|auto)\b', args, re.IGNORECASE)
        if lang_match:
            parsed["lang"] = lang_match.group(1).lower()

        # Sources
        sources_match = re.search(r'sources?[=:]?([\w\.,\-]+)', args, re.IGNORECASE)
        if sources_match:
            parsed["sources"] = [s.strip() for s in sources_match.group(1).split(",")]

        # Metrics (comma-separated)
        metrics_match = re.search(r'metrics?[=:]?([\w,]+)', args, re.IGNORECASE)
        if metrics_match:
            parsed["metrics"] = [m.strip() for m in metrics_match.group(1).split(",")]

        # Audience
        audience_match = re.search(r'audience[=:]?"?([^"\s]+)"?', args, re.IGNORECASE)
        if audience_match:
            parsed["audience"] = audience_match.group(1)

        # Channels
        channels_match = re.search(r'channels?[=:]?([\w,]+)', args, re.IGNORECASE)
        if channels_match:
            parsed["channels"] = [c.strip() for c in channels_match.group(1).split(",")]

        # Goal
        goal_match = re.search(r'goal[=:]?(seo|ctr|conversion|retention)', args, re.IGNORECASE)
        if goal_match:
            parsed["goal"] = goal_match.group(1).lower()

        # Product
        product_match = re.search(r'product[=:]?"?([^"\s]+)"?', args, re.IGNORECASE)
        if product_match:
            parsed["product"] = product_match.group(1)

        # Plan
        plan_match = re.search(r'plan[=:]?"?([^"\s]+)"?', args, re.IGNORECASE)
        if plan_match:
            parsed["plan"] = plan_match.group(1)

        # Targets (roi_min, cac_max, budget)
        targets = {}
        roi_match = re.search(r'roi_min[=:]?([\d.]+)', args, re.IGNORECASE)
        if roi_match:
            targets["roi_min"] = float(roi_match.group(1))

        cac_match = re.search(r'cac_max[=:]?([\d.]+)', args, re.IGNORECASE)
        if cac_match:
            targets["cac_max"] = float(cac_match.group(1))

        budget_match = re.search(r'budget[=:]?([\d.]+)', args, re.IGNORECASE)
        if budget_match:
            targets["budget"] = float(budget_match.group(1))

        if targets:
            parsed["targets"] = targets

        # Schedule (cron)
        cron_match = re.search(r'cron[=:]?"([^"]+)"', args, re.IGNORECASE)
        if cron_match:
            parsed["schedule"] = {"cron": cron_match.group(1)}

        # k_final
        k_match = re.search(r'\bk[_=]?(\d+)\b', args, re.IGNORECASE)
        if k_match:
            parsed["k_final"] = int(k_match.group(1))

        # Flags
        if "rerank" in args.lower():
            if "no" in args.lower() or "false" in args.lower():
                parsed["rerank_enabled"] = False
            else:
                parsed["rerank_enabled"] = True

        if "personalize" in args.lower():
            parsed["personalize"] = True

        return parsed

    def _build_params(self, parsed_args: Dict[str, Any], defaults: Dict[str, Any], user_lang: str) -> Dict[str, Any]:
        """Build params dict"""
        params = {}

        # Window
        window = parsed_args.get("window") or defaults.get("window", "24h")
        params["window"] = window if window in VALID_WINDOWS else "24h"

        # Lang
        lang = parsed_args.get("lang") or user_lang or defaults.get("lang", "auto")
        params["lang"] = lang if lang in ["ru", "en", "auto"] else "auto"

        # Sources
        params["sources"] = parsed_args.get("sources")

        # Metrics
        params["metrics"] = parsed_args.get("metrics")

        # Audience
        params["audience"] = parsed_args.get("audience")

        # Channels
        params["channels"] = parsed_args.get("channels")

        # Goal
        params["goal"] = parsed_args.get("goal")

        # Product
        params["product"] = parsed_args.get("product")

        # Plan
        params["plan"] = parsed_args.get("plan")

        # Targets
        params["targets"] = parsed_args.get("targets")

        # Schedule
        params["schedule"] = parsed_args.get("schedule")

        # k_final
        k_final = parsed_args.get("k_final") or defaults.get("k_final", 6)
        params["k_final"] = max(5, min(10, k_final))

        # Flags
        rerank_default = defaults.get("rerank_enabled", True)
        personalize_default = defaults.get("personalize_default", False)

        params["flags"] = {
            "rerank_enabled": parsed_args.get("rerank_enabled", rerank_default),
            "personalize": parsed_args.get("personalize", personalize_default)
        }

        return params

    def _build_models(self, command: str) -> Dict[str, Any]:
        """Build model routing"""
        routing = {
            "/dashboard live": {"primary": "claude-4.5", "fallback": ["gpt-5", "gemini-2.5-pro"]},
            "/dashboard custom": {"primary": "claude-4.5", "fallback": ["gpt-5", "gemini-2.5-pro"]},
            "/reports generate": {"primary": "gpt-5", "fallback": ["claude-4.5", "gemini-2.5-pro"]},
            "/schedule report": {"primary": "gpt-5", "fallback": ["claude-4.5"]},
            "/alerts setup": {"primary": "gpt-5", "fallback": ["claude-4.5"]},
            "/alerts test": {"primary": "gpt-5", "fallback": ["claude-4.5"]},
            "/optimize listing": {"primary": "claude-4.5", "fallback": ["gpt-5", "gemini-2.5-pro"]},
            "/brief assets": {"primary": "gemini-2.5-pro", "fallback": ["gpt-5"]},
            "/pricing advisor": {"primary": "gpt-5", "fallback": ["claude-4.5", "gemini-2.5-pro"]},
            "/optimize campaign": {"primary": "gpt-5", "fallback": ["claude-4.5"]}
        }

        return routing.get(command, {"primary": "gpt-5", "fallback": ["claude-4.5"]})

    def _build_limits(self, defaults: Dict[str, Any]) -> Dict[str, int]:
        """Build limits"""
        return {
            "max_tokens": max(2048, defaults.get("max_tokens", 4096)),
            "budget_cents": max(25, defaults.get("budget_cents", 60)),
            "timeout_s": max(8, defaults.get("timeout_s", 12))
        }

    def _command_needs_retrieval(self, command: str) -> bool:
        """Check if command needs document retrieval"""
        no_retrieval_commands = ["/schedule report", "/alerts setup", "/alerts test"]
        return command not in no_retrieval_commands

    async def _perform_retrieval_with_recovery(
        self,
        params: Dict[str, Any],
        feature_flags: Dict[str, bool],
        correlation_id: str
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Perform retrieval with auto-recovery"""
        warnings = []
        window = params["window"]
        lang = params["lang"]
        sources = params["sources"]
        k_final = params["k_final"]
        rerank_enabled = params["flags"]["rerank_enabled"]

        # Build query
        query = self._build_retrieval_query(params)

        # Attempt 1: Normal
        docs = await self._retrieve_docs(query, window, lang, sources, k_final, rerank_enabled)

        if docs:
            return self._build_retrieval_dict(docs, window, lang, sources, k_final, rerank_enabled), warnings

        # Auto-recovery
        # Step 1: Expand window
        if feature_flags.get("auto_expand_window", True):
            for _ in range(5):
                new_window = WINDOW_EXPANSION.get(window, window)
                if new_window == window:
                    break
                window = new_window
                warnings.append(f"expanded window to {window}")
                docs = await self._retrieve_docs(query, window, lang, sources, k_final, rerank_enabled)
                if docs:
                    return self._build_retrieval_dict(docs, window, lang, sources, k_final, rerank_enabled), warnings

        # Step 2: Relax filters
        if feature_flags.get("relax_filters_on_empty", True):
            lang = "auto"
            sources = None
            warnings.append("relaxed filters (lang=auto, no sources)")
            docs = await self._retrieve_docs(query, window, lang, sources, k_final, rerank_enabled)
            if docs:
                return self._build_retrieval_dict(docs, window, lang, sources, k_final, rerank_enabled), warnings

        # Step 3: Fallback mode
        if feature_flags.get("fallback_rerank_false_on_empty", True):
            rerank_enabled = False
            k_final = 10
            warnings.append("disabled rerank, k_final=10")
            docs = await self._retrieve_docs(query, window, lang, sources, k_final, rerank_enabled)
            if docs:
                return self._build_retrieval_dict(docs, window, lang, sources, k_final, rerank_enabled), warnings

        return self._build_retrieval_dict([], window, lang, sources, k_final, rerank_enabled), warnings

    def _build_retrieval_query(self, params: Dict[str, Any]) -> str:
        """Build query from params"""
        if params.get("product"):
            return f"{params['product']} features benefits"
        elif params.get("metrics"):
            return f"metrics {' '.join(params['metrics'][:3])}"
        elif params.get("audience"):
            return f"{params['audience']} insights"
        else:
            return "latest trends performance"

    async def _retrieve_docs(
        self,
        query: str,
        window: str,
        lang: str,
        sources: Optional[List[str]],
        k_final: int,
        rerank_enabled: bool
    ) -> List[Dict[str, Any]]:
        """Perform retrieval"""
        try:
            docs = await self.retrieval_client.retrieve(
                query=query,
                window=window,
                lang=lang,
                sources=sources,
                k_final=k_final,
                use_rerank=rerank_enabled
            )

            cleaned_docs = []
            for doc in docs:
                if not doc.get("title"):
                    continue

                date = doc.get("date")
                if not date or not self._is_valid_date(date):
                    date = datetime.utcnow().strftime("%Y-%m-%d")

                doc_lang = doc.get("lang", "en")
                if doc_lang not in ["ru", "en"]:
                    doc_lang = "en"

                snippet = doc.get("snippet", "")[:240]

                cleaned_docs.append({
                    "article_id": doc.get("article_id"),
                    "title": doc.get("title", ""),
                    "url": doc.get("url"),
                    "date": date,
                    "lang": doc_lang,
                    "score": doc.get("score", 0.0),
                    "snippet": snippet
                })

            return cleaned_docs[:k_final]

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    def _build_retrieval_dict(
        self,
        docs: List[Dict[str, Any]],
        window: str,
        lang: str,
        sources: Optional[List[str]],
        k_final: int,
        rerank_enabled: bool
    ) -> Dict[str, Any]:
        """Build retrieval dict"""
        return {
            "docs": docs,
            "window": window,
            "lang": lang,
            "sources": sources,
            "k_final": len(docs),
            "rerank_enabled": rerank_enabled
        }

    def _build_empty_retrieval(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build empty retrieval for commands that don't need docs"""
        return {
            "docs": [],
            "window": params["window"],
            "lang": params["lang"],
            "sources": None,
            "k_final": 0,
            "rerank_enabled": False
        }

    def _build_history(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build history context (mock - would query DB in production)"""
        # Commands that benefit from history
        if command in ["/dashboard live", "/dashboard custom", "/reports generate"]:
            return {
                "snapshots": None,  # Would be populated from DB
                "metrics": None,
                "competitors": None
            }
        else:
            return {
                "snapshots": None,
                "metrics": None,
                "competitors": None
            }

    def _has_history_data(self, history: Dict[str, Any]) -> bool:
        """Check if history has any data"""
        return bool(
            history.get("snapshots") or
            history.get("metrics") or
            history.get("competitors")
        )

    def _build_personalization(
        self,
        params: Dict[str, Any],
        user_lang: str,
        feature_flags: Dict[str, bool]
    ) -> Dict[str, Any]:
        """Build personalization context"""
        enabled = params["flags"].get("personalize", False)

        return {
            "enabled": enabled,
            "segment": params.get("audience"),  # Use audience as segment
            "locale": params["lang"] if params["lang"] != "auto" else user_lang
        }

    def _validate_context(self, context: Dict[str, Any]) -> Optional[str]:
        """Validate context"""
        # Check command
        if not context.get("command"):
            return "Missing command"

        # Check window
        if context["params"]["window"] not in VALID_WINDOWS:
            return f"Invalid window: {context['params']['window']}"

        # Check data availability for retrieval commands
        if self._command_needs_retrieval(context["command"]):
            if not context["retrieval"]["docs"] and not self._has_history_data(context.get("history", {})):
                return "No retrieval docs and no history data"

        # Check k_final alignment (if docs present)
        if context["retrieval"]["docs"]:
            if context["params"]["k_final"] != len(context["retrieval"]["docs"]):
                return "k_final mismatch with docs length"

            if not (5 <= context["params"]["k_final"] <= 10):
                return f"k_final out of range: {context['params']['k_final']}"

        # Check docs format
        for i, doc in enumerate(context["retrieval"]["docs"]):
            if not doc.get("date") or not self._is_valid_date(doc["date"]):
                return f"Doc {i}: invalid date"
            if doc.get("lang") not in ["ru", "en"]:
                return f"Doc {i}: invalid lang"
            if len(doc.get("snippet", "")) > 240:
                return f"Doc {i}: snippet too long"

        # Check models
        if not context.get("models", {}).get("primary"):
            return "Missing primary model"

        # Check limits
        limits = context.get("limits", {})
        if limits.get("max_tokens", 0) < 2048:
            return "max_tokens too low"
        if limits.get("budget_cents", 0) < 25:
            return "budget_cents too low"
        if limits.get("timeout_s", 0) < 8:
            return "timeout_s too low"

        # Check telemetry
        if not context.get("telemetry", {}).get("correlation_id"):
            return "Missing correlation_id"

        return None

    def _is_valid_date(self, date_str: str) -> bool:
        """Check YYYY-MM-DD format"""
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _generate_correlation_id(self) -> str:
        """Generate correlation ID"""
        return f"p4ctx-{uuid.uuid4().hex[:12]}"

    def _error_response(
        self,
        code: str,
        user_message: str,
        tech_message: str,
        retryable: bool,
        correlation_id: str
    ) -> Dict[str, Any]:
        """Build error response"""
        return {
            "error": {
                "code": code,
                "user_message": user_message,
                "tech_message": tech_message,
                "retryable": retryable
            },
            "meta": {
                "version": "phase4-orchestrator",
                "correlation_id": correlation_id
            }
        }


_phase4_context_builder_instance: Optional[Phase4ContextBuilder] = None


def get_phase4_context_builder() -> Phase4ContextBuilder:
    """Get or create Phase4ContextBuilder instance"""
    global _phase4_context_builder_instance
    if _phase4_context_builder_instance is None:
        _phase4_context_builder_instance = Phase4ContextBuilder()
    return _phase4_context_builder_instance
