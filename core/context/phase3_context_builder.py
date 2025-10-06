"""
Phase 3 Context Builder — Constructs valid context for Phase3Orchestrator
Handles: /ask, /events, /graph, /memory, /synthesize
"""

import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.rag.retrieval_client import get_retrieval_client

logger = logging.getLogger(__name__)

# Valid window values (Sprint 3: added 7d, 14d, 30d for better granularity)
VALID_WINDOWS = ["6h", "12h", "24h", "1d", "3d", "7d", "1w", "14d", "2w", "30d", "1m", "3m", "6m", "1y"]

# Window expansion sequence for auto-recovery (Sprint 3: 7d → 14d → 30d)
WINDOW_EXPANSION = {
    "6h": "12h",
    "12h": "24h",
    "24h": "3d",
    "1d": "3d",
    "3d": "7d",
    "7d": "14d",     # NEW: 7d (default) → 14d
    "1w": "14d",     # 1w = 7d, also expands to 14d
    "14d": "30d",    # NEW: 14d → 30d
    "2w": "30d",     # 2w = 14d, also expands to 30d
    "30d": "3m",     # NEW: 30d → 3m
    "1m": "3m",      # 1m = 30d, also expands to 3m
    "3m": "6m",
    "6m": "1y",
    "1y": "1y"       # Cannot expand further
}


class Phase3ContextBuilder:
    """Builds valid context for Phase3Orchestrator from raw input"""

    def __init__(self):
        self.retrieval_client = get_retrieval_client()

    async def build_context(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build valid context or return error

        Args:
            raw_input: Raw input with raw_command, args, user_lang, env, ab_test

        Returns:
            Valid context dict or error dict
        """
        correlation_id = self._generate_correlation_id()

        try:
            # Validate raw input
            if not raw_input.get("raw_command"):
                return self._error_response(
                    "VALIDATION_FAILED",
                    "Cannot construct context: no raw input provided",
                    "Missing required field 'raw_command' in input",
                    False,
                    correlation_id
                )

            # Parse command
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
                    f"Command '{raw_command}' not in supported set",
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

            # Build models based on command
            models = self._build_models(command)

            # Build limits
            limits = self._build_limits(defaults)

            # Perform retrieval with auto-recovery
            retrieval, recovery_warnings = await self._perform_retrieval_with_recovery(
                params,
                feature_flags,
                correlation_id
            )

            if not retrieval["docs"]:
                return self._error_response(
                    "NO_DATA",
                    "No documents found for query",
                    f"Retrieval returned 0 documents after auto-recovery attempts. "
                    f"Window={retrieval['window']}, lang={retrieval['lang']}, "
                    f"sources={retrieval['sources']}. Steps: {', '.join(recovery_warnings)}",
                    True,
                    correlation_id
                )

            # Align k_final with actual docs
            params["k_final"] = len(retrieval["docs"])

            # Build graph context (if needed)
            graph = self._build_graph_context(command, parsed_args)

            # Build memory context (if needed)
            memory = self._build_memory_context(command, parsed_args)

            # Build telemetry
            telemetry = {
                "correlation_id": correlation_id,
                "version": env.get("version", "phase3-orchestrator")
            }

            # Construct final context
            context = {
                "command": command,
                "params": params,
                "retrieval": retrieval,
                "graph": graph,
                "memory": memory,
                "models": models,
                "limits": limits,
                "ab_test": ab_test,
                "telemetry": telemetry
            }

            # Final validation
            validation_error = self._validate_context(context)
            if validation_error:
                return self._error_response(
                    "VALIDATION_FAILED",
                    "Context validation failed",
                    validation_error,
                    False,
                    correlation_id
                )

            logger.info(f"[{correlation_id}] Context built successfully: {command}")
            return context

        except Exception as e:
            logger.error(f"[{correlation_id}] Context builder failed: {e}", exc_info=True)
            return self._error_response(
                "INTERNAL",
                "Internal error building context",
                str(e),
                True,
                correlation_id
            )

    # ==========================================================================
    # COMMAND NORMALIZATION
    # ==========================================================================

    def _normalize_command(self, raw_command: str) -> Optional[str]:
        """Normalize raw command to supported Phase3 command"""
        cmd = raw_command.strip().lower()

        if cmd.startswith("/ask"):
            return "/ask --depth=deep"
        elif cmd.startswith("/events"):
            return "/events link"
        elif cmd.startswith("/graph"):
            return "/graph query"
        elif cmd.startswith("/memory"):
            # Extract operation
            if "suggest" in cmd:
                return "/memory suggest"
            elif "store" in cmd:
                return "/memory store"
            elif "recall" in cmd:
                return "/memory recall"
            else:
                return "/memory recall"  # Default
        elif cmd.startswith("/synthesize"):
            return "/synthesize"
        else:
            return None

    # ==========================================================================
    # ARGUMENT PARSING
    # ==========================================================================

    def _parse_args(self, args: str, command: str) -> Dict[str, Any]:
        """Parse argument string into structured dict"""
        parsed = {}

        # Extract window (6h, 24h, 1w, etc.)
        window_match = re.search(r'\b(6h|12h|24h|1d|3d|1w|2w|1m|3m|6m|1y)\b', args)
        if window_match:
            parsed["window"] = window_match.group(1)

        # Extract lang
        lang_match = re.search(r'\blang[=:]?(ru|en|auto)\b', args, re.IGNORECASE)
        if lang_match:
            parsed["lang"] = lang_match.group(1).lower()

        # Extract sources (comma-separated domains)
        sources_match = re.search(r'sources?[=:]?([\w\.,\-]+)', args, re.IGNORECASE)
        if sources_match:
            parsed["sources"] = [s.strip() for s in sources_match.group(1).split(",")]

        # Extract topic
        topic_match = re.search(r'topic[=:]?"?([^"\s]+)"?', args, re.IGNORECASE)
        if topic_match:
            parsed["topic"] = topic_match.group(1)

        # Extract entity
        entity_match = re.search(r'entity[=:]?"?([^"\s]+)"?', args, re.IGNORECASE)
        if entity_match:
            parsed["entity"] = entity_match.group(1)

        # Extract query (quoted string or remaining text)
        query_match = re.search(r'query[=:]?"([^"]+)"', args, re.IGNORECASE)
        if query_match:
            parsed["query"] = query_match.group(1).strip()
        elif command == "/graph query":
            # For /graph query, treat entire args as query if not explicitly marked
            parsed["query"] = args.strip()

        # Extract k_final
        k_match = re.search(r'\bk[_=]?(\d+)\b', args, re.IGNORECASE)
        if k_match:
            parsed["k_final"] = int(k_match.group(1))

        # Extract rerank flag
        if "rerank" in args.lower():
            if "no" in args.lower() or "false" in args.lower():
                parsed["rerank_enabled"] = False
            else:
                parsed["rerank_enabled"] = True

        return parsed

    # ==========================================================================
    # PARAMS BUILDING
    # ==========================================================================

    def _build_params(
        self,
        parsed_args: Dict[str, Any],
        defaults: Dict[str, Any],
        user_lang: str
    ) -> Dict[str, Any]:
        """Build normalized params dict"""
        params = {}

        # Window
        window = parsed_args.get("window") or defaults.get("window", "24h")
        params["window"] = window if window in VALID_WINDOWS else "24h"

        # Lang
        lang = parsed_args.get("lang") or user_lang or defaults.get("lang", "auto")
        params["lang"] = lang if lang in ["ru", "en", "auto"] else "auto"

        # Sources
        params["sources"] = parsed_args.get("sources")

        # Topic/Entity/Domains/Query
        params["topic"] = parsed_args.get("topic")
        params["entity"] = parsed_args.get("entity")
        params["domains"] = parsed_args.get("domains")
        params["query"] = parsed_args.get("query")

        # k_final (clamp to 5-10)
        k_final = parsed_args.get("k_final") or defaults.get("k_final", 6)
        params["k_final"] = max(5, min(10, k_final))

        # Flags
        rerank_default = defaults.get("rerank_enabled", True)
        params["flags"] = {
            "rerank_enabled": parsed_args.get("rerank_enabled", rerank_default)
        }

        return params

    # ==========================================================================
    # MODEL ROUTING
    # ==========================================================================

    def _build_models(self, command: str) -> Dict[str, Any]:
        """Build model routing based on command"""
        routing = {
            "/ask --depth=deep": {
                "primary": "gpt-5",
                "fallback": ["claude-4.5", "gemini-2.5-pro"]
            },
            "/events link": {
                "primary": "gpt-5",
                "fallback": ["gemini-2.5-pro", "claude-4.5"]
            },
            "/graph query": {
                "primary": "claude-4.5",
                "fallback": ["gpt-5", "gemini-2.5-pro"]
            },
            "/synthesize": {
                "primary": "gpt-5",
                "fallback": ["claude-4.5"]
            },
            "/memory suggest": {
                "primary": "gemini-2.5-pro",
                "fallback": ["gpt-5"]
            },
            "/memory store": {
                "primary": "gemini-2.5-pro",
                "fallback": ["gpt-5"]
            },
            "/memory recall": {
                "primary": "gemini-2.5-pro",
                "fallback": ["gpt-5"]
            }
        }

        return routing.get(command, {"primary": "gpt-5", "fallback": ["claude-4.5"]})

    # ==========================================================================
    # LIMITS
    # ==========================================================================

    def _build_limits(self, defaults: Dict[str, Any]) -> Dict[str, int]:
        """Build limits dict"""
        return {
            "max_tokens": max(2048, defaults.get("max_tokens", 4096)),
            "budget_cents": max(25, defaults.get("budget_cents", 60)),
            "timeout_s": max(8, defaults.get("timeout_s", 18))
        }

    # ==========================================================================
    # RETRIEVAL WITH AUTO-RECOVERY
    # ==========================================================================

    async def _perform_retrieval_with_recovery(
        self,
        params: Dict[str, Any],
        feature_flags: Dict[str, bool],
        correlation_id: str
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Perform hybrid retrieval with auto-recovery on empty results

        Returns:
            (retrieval_dict, recovery_warnings)
        """
        warnings = []
        window = params["window"]
        lang = params["lang"]
        sources = params["sources"]
        k_final = params["k_final"]
        rerank_enabled = params["flags"]["rerank_enabled"]

        # Build query
        query = self._build_retrieval_query(params)

        # Attempt 1: Normal retrieval
        docs = await self._retrieve_docs(
            query, window, lang, sources, k_final, rerank_enabled
        )

        if docs:
            return self._build_retrieval_dict(
                docs, window, lang, sources, k_final, rerank_enabled
            ), warnings

        # Auto-recovery starts here
        original_window = window
        original_lang = lang
        original_sources = sources
        original_rerank = rerank_enabled

        # Step 1: Expand window
        if feature_flags.get("auto_expand_window", True):
            max_attempts = 5
            attempts = 0
            while not docs and attempts < max_attempts:
                new_window = WINDOW_EXPANSION.get(window, window)
                if new_window == window:
                    break  # Cannot expand further

                window = new_window
                attempts += 1
                warnings.append(f"expanded window to {window}")

                docs = await self._retrieve_docs(
                    query, window, lang, sources, k_final, rerank_enabled
                )

                if docs:
                    return self._build_retrieval_dict(
                        docs, window, lang, sources, k_final, rerank_enabled
                    ), warnings

        # Step 2: Relax filters
        if feature_flags.get("relax_filters_on_empty", True):
            lang = "auto"
            sources = None
            warnings.append("relaxed lang to auto, removed source filters")

            docs = await self._retrieve_docs(
                query, window, lang, sources, k_final, rerank_enabled
            )

            if docs:
                return self._build_retrieval_dict(
                    docs, window, lang, sources, k_final, rerank_enabled
                ), warnings

        # Step 3: Disable rerank and increase k
        if feature_flags.get("fallback_rerank_false_on_empty", True):
            rerank_enabled = False
            k_final = 10
            warnings.append("disabled rerank, increased k_final to 10")

            docs = await self._retrieve_docs(
                query, window, lang, sources, k_final, rerank_enabled
            )

            if docs:
                return self._build_retrieval_dict(
                    docs, window, lang, sources, k_final, rerank_enabled
                ), warnings

        # All recovery attempts failed
        return self._build_retrieval_dict(
            [], window, lang, sources, k_final, rerank_enabled
        ), warnings

    def _build_retrieval_query(self, params: Dict[str, Any]) -> str:
        """Build retrieval query from params"""
        # Priority: explicit query > topic > entity > generic
        if params.get("query"):
            return params["query"]
        elif params.get("topic"):
            return params["topic"]
        elif params.get("entity"):
            return params["entity"]
        else:
            return "latest news"

    async def _retrieve_docs(
        self,
        query: str,
        window: str,
        lang: str,
        sources: Optional[List[str]],
        k_final: int,
        rerank_enabled: bool
    ) -> List[Dict[str, Any]]:
        """Perform actual retrieval"""
        try:
            docs = await self.retrieval_client.retrieve(
                query=query,
                window=window,
                lang=lang,
                sources=sources,
                k_final=k_final,
                use_rerank=rerank_enabled
            )

            # Clean and validate docs
            cleaned_docs = []
            for doc in docs:
                url_value = doc.get('url') or ''
                source_domain = doc.get('source_domain') or doc.get('source') or ''
                if 'news.google' in url_value or 'news.google' in source_domain:
                    continue

                # Normalize title
                title = doc.get('title') or doc.get('title_norm') or doc.get('headline') or doc.get('name')
                if not title:
                    continue

                # Normalize date
                date = doc.get('date')
                if not date or not self._is_valid_date(date):
                    date = datetime.utcnow().strftime("%Y-%m-%d")

                # Normalize lang
                doc_lang = doc.get('lang') or doc.get('language') or 'en'
                if doc_lang not in ['ru', 'en']:
                    doc_lang = 'en'

                # Normalize snippet and score
                raw_snippet = doc.get('snippet') or doc.get('summary') or doc.get('text') or doc.get('clean_text') or ''
                snippet = raw_snippet[:240]

                score = doc.get('score')
                if score is None:
                    score = doc.get('similarity') or doc.get('semantic_score') or 0.0
                try:
                    score_value = float(score)
                except (TypeError, ValueError):
                    score_value = 0.0

                cleaned_docs.append({
                    'article_id': doc.get('article_id'),
                    'title': title,
                    'url': doc.get('url'),
                    'date': date,
                    'lang': doc_lang,
                    'score': score_value,
                    'snippet': snippet
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

    # ==========================================================================
    # GRAPH CONTEXT
    # ==========================================================================

    def _build_graph_context(
        self,
        command: str,
        parsed_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build graph context (only for /graph query)"""
        if command != "/graph query":
            return {
                "enabled": False,
                "entities": None,
                "relations": None,
                "build_policy": "cached_only",
                "hop_limit": 1
            }

        return {
            "enabled": True,
            "entities": None,  # Will be populated by orchestrator
            "relations": None,
            "build_policy": "on_demand",
            "hop_limit": min(3, parsed_args.get("hop_limit", 2))
        }

    # ==========================================================================
    # MEMORY CONTEXT
    # ==========================================================================

    def _build_memory_context(
        self,
        command: str,
        parsed_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build memory context (only for /memory *)"""
        if not command.startswith("/memory"):
            return {
                "enabled": False,
                "episodic": None,
                "semantic_keys": None
            }

        # Build semantic keys from query/topic
        semantic_keys = []
        if parsed_args.get("query"):
            semantic_keys.append({
                "key": parsed_args["query"],
                "ttl_days": 90
            })
        elif parsed_args.get("topic"):
            semantic_keys.append({
                "key": parsed_args["topic"],
                "ttl_days": 90
            })

        return {
            "enabled": True,
            "episodic": None,  # Will be populated by orchestrator
            "semantic_keys": semantic_keys if semantic_keys else None
        }

    # ==========================================================================
    # VALIDATION
    # ==========================================================================

    def _validate_context(self, context: Dict[str, Any]) -> Optional[str]:
        """Validate final context, return error message if invalid"""
        # Check command
        if not context.get("command"):
            return "Missing command"

        # Check params.window
        if context["params"]["window"] not in VALID_WINDOWS:
            return f"Invalid window: {context['params']['window']}"

        # Check retrieval.docs
        if not context["retrieval"]["docs"]:
            return "No documents in retrieval"

        # Check k_final alignment
        if context["params"]["k_final"] != len(context["retrieval"]["docs"]):
            return "k_final mismatch with docs length"

        # Check k_final range (allow smaller counts when retrieval returns fewer docs)
        k_final_value = context["params"]["k_final"]
        if not (1 <= k_final_value <= 10):
            return f"k_final out of range: {k_final_value}"

        # Check docs format
        for i, doc in enumerate(context["retrieval"]["docs"]):
            if not doc.get("date") or not self._is_valid_date(doc["date"]):
                return f"Doc {i}: invalid date format"
            if doc.get("lang") not in ["ru", "en"]:
                return f"Doc {i}: invalid lang"
            if len(doc.get("snippet", "")) > 240:
                return f"Doc {i}: snippet exceeds 240 chars"

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

    # ==========================================================================
    # UTILITIES
    # ==========================================================================

    def _is_valid_date(self, date_str: str) -> bool:
        """Check if date string is valid YYYY-MM-DD"""
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _generate_correlation_id(self) -> str:
        """Generate correlation ID"""
        return f"ctx-{uuid.uuid4().hex[:12]}"

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
                "version": "phase3-orchestrator",
                "correlation_id": correlation_id
            }
        }


# Factory function
_context_builder_instance: Optional[Phase3ContextBuilder] = None


def get_phase3_context_builder() -> Phase3ContextBuilder:
    """Get or create Phase3ContextBuilder instance"""
    global _context_builder_instance
    if _context_builder_instance is None:
        _context_builder_instance = Phase3ContextBuilder()
    return _context_builder_instance
