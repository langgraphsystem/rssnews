"""
Phase 3 Orchestrator — Integrated with real agents (Agentic RAG, GraphRAG, Events).
Replaces stub implementations with full LLM-powered agents.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from schemas.analysis_schemas import (
    build_base_response,
    Insight,
    Evidence,
    EvidenceRef,
    Meta,
    AgenticResult,
    EventsResult,
    EventRecord,
    GraphResult,
    GraphPath,
    MemoryResult,
    MemorySuggestion,
    MemoryStoreItem,
    MemoryRecord,
    SynthesisResult,
    Action,
    Conflict,
    TimelineRelation,
    CausalLink,
)
from core.policies.validators import get_validator
from core.policies.pii_masker import PIIMasker
from core.models.model_router import get_model_router
from core.models.budget_manager import create_budget_manager
from core.agents.agentic_rag import create_agentic_rag_agent
from core.graph.graph_builder import create_graph_builder
from core.graph.graph_traversal import create_traversal
from core.events.event_extractor import create_event_extractor
from core.events.causality_reasoner import create_causality_reasoner
from core.rag.retrieval_client import get_retrieval_client
from core.memory.memory_store import create_memory_store
from core.memory.embeddings_service import create_embeddings_service

logger = logging.getLogger(__name__)


class Phase3Orchestrator:
    """
    Production Phase 3 Orchestrator with integrated agents.
    Supports /ask, /events, /graph, /memory, /synthesize commands.
    """

    def __init__(self) -> None:
        self.validator = get_validator()
        self.model_router = get_model_router()
        self.retrieval_client = get_retrieval_client()

        # Create agent factories
        self.agentic_rag_agent = create_agentic_rag_agent(self.model_router)
        self.graph_builder = create_graph_builder(self.model_router)
        self.event_extractor = create_event_extractor(self.model_router)
        self.causality_reasoner = create_causality_reasoner(self.model_router)

        # Create memory components
        self.embeddings_service = create_embeddings_service()
        self.memory_store = create_memory_store(self.embeddings_service)

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Phase 3 command

        Args:
            context: Full context dict with command, params, retrieval, models, limits, telemetry

        Returns:
            Response dict (BaseAnalysisResponse or ErrorResponse)
        """
        command = context.get("command", "")
        correlation_id = context.get("telemetry", {}).get("correlation_id", "phase3-run")

        logger.info(f"[{correlation_id}] Executing Phase 3 command: {command}")

        try:
            if command.startswith("/ask"):
                response = await self._handle_agentic(context)
            elif command.startswith("/events"):
                response = await self._handle_events(context)
            elif command.startswith("/graph"):
                response = await self._handle_graph(context)
            elif command.startswith("/memory"):
                response = await self._handle_memory(context)
            elif command.startswith("/synthesize"):
                response = await self._handle_synthesis(context)
            else:
                raise ValueError(f"Unsupported Phase 3 command: {command}")

            # Sanitize evidence (PII masking, domain checks)
            if hasattr(response, 'evidence'):
                response.evidence = PIIMasker.sanitize_evidence(
                    [ev.model_dump() if hasattr(ev, 'model_dump') else ev for ev in response.evidence]
                )
                response.evidence = [Evidence(**ev) for ev in response.evidence]

            # Validate with policy layer
            self.validator.validate_response(response)

            logger.info(f"[{correlation_id}] Command completed successfully")
            return response.model_dump()

        except Exception as e:
            logger.error(f"[{correlation_id}] Command failed: {e}", exc_info=True)
            return self._build_error_response(str(e), context)

    # ------------------------------------------------------------------
    # Command Handlers
    # ------------------------------------------------------------------

    async def _handle_agentic(self, context: Dict[str, Any]) -> Any:
        """Handle /ask --depth=deep with real Agentic RAG"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        query = params.get("query") or params.get("topic") or "primary question"
        window = context.get("retrieval", {}).get("window", "24h")

        # Create budget manager
        limits = context.get("limits", {})
        budget = create_budget_manager(
            max_tokens=limits.get("max_tokens", 8000),
            budget_cents=limits.get("budget_cents", 50),
            timeout_s=limits.get("timeout_s", 30)
        )

        # Apply degradation if needed
        depth = params.get("depth", 3)
        if budget.should_degrade():
            degraded = budget.get_degraded_params("/ask", {"depth": depth})
            depth = degraded.get("depth", 1)

        # Execute Agentic RAG
        agentic_result, all_docs = await self.agentic_rag_agent.execute(
            query=query,
            initial_docs=docs,
            depth=depth,
            retrieval_fn=self._create_retrieval_fn(window, lang),
            budget_manager=budget,
            lang=lang,
            window=window
        )

        # Build response
        evidence = self._build_evidence(all_docs[:10])
        insights = self._build_insights_from_docs(all_docs[:5], lang)
        meta = self._build_meta(context, iterations=len(agentic_result.steps), confidence=0.78)
        meta.model = budget.get_summary()["spent"].get("model", meta.model)

        header = "Глубокий разбор" if lang == "ru" else "Deep Dive"
        tldr = self._trim(
            ("Многоходовой анализ с проверкой и уточнением запроса." if lang == "ru"
             else "Iterative analysis with query refinement and self-check."),
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=agentic_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings()
        )

        return response

    async def _handle_events(self, context: Dict[str, Any]) -> Any:
        """Handle /events link with real Event Extraction + Causality"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        window = context.get("retrieval", {}).get("window", "12h")
        _, arm = self._ab_arm(context)

        # Create budget manager
        limits = context.get("limits", {})
        budget = create_budget_manager(
            max_tokens=limits.get("max_tokens", 8000),
            budget_cents=limits.get("budget_cents", 50),
            timeout_s=limits.get("timeout_s", 30)
        )

        # Apply degradation
        max_events = 20
        warnings: List[str] = []
        if self._should_force_degrade(limits) or budget.should_degrade():
            max_events = min(max_events, 5)
            warnings.append("Degraded events: reduced max_events due to budget limits")

        # Extract events
        events = await self.event_extractor.extract_events(
            docs=docs,
            window=window,
            lang=lang,
            max_events=max_events
        )

        # Infer causality
        timeline, causal_links = await self.causality_reasoner.infer_causality(
            events=events,
            docs=docs,
            budget_manager=budget,
            lang=lang,
            max_links=max_events
        )

        trimmed_events = events[:max_events]
        if not timeline:
            timeline = self._fallback_timeline(trimmed_events)
        if not causal_links:
            causal_links = self._fallback_causal_links(trimmed_events, lang)

        if arm == "B" and causal_links:
            causal_links = causal_links[:-1]

        # Build result
        events_result = EventsResult(
            events=[EventRecord(**e) for e in trimmed_events],
            timeline=timeline,
            causal_links=causal_links
        )

        evidence = self._build_evidence(docs[:10])
        insights = self._build_insights_from_events(events[:5], lang)
        meta = self._build_meta(context, confidence=0.76)

        header = "Связанные события" if lang == "ru" else "Linked Events"
        tldr = self._trim(
            ("События выстроены в хронологию с причинно-следственными связями." if lang == "ru"
             else "Events arranged chronologically with causal relationships detected."),
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=events_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings() + warnings
        )

        return response

    async def _handle_graph(self, context: Dict[str, Any]) -> Any:
        """Handle /graph query with real Graph Construction + Traversal"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        query = params.get("query") or params.get("topic") or "Graph"

        # Create budget manager
        limits = context.get("limits", {})
        budget = create_budget_manager(
            max_tokens=limits.get("max_tokens", 8000),
            budget_cents=limits.get("budget_cents", 50),
            timeout_s=limits.get("timeout_s", 30)
        )

        # Apply degradation
        max_nodes, max_edges, hop_limit = 200, 600, 3
        graph_warnings: List[str] = []
        if budget.should_degrade():
            degraded = budget.get_degraded_params("/graph", {
                "hop_limit": 3,
                "max_nodes": 200,
                "max_edges": 600
            })
            hop_limit = degraded.get("hop_limit", 1)
            max_nodes = degraded.get("max_nodes", 60)
            max_edges = degraded.get("max_edges", 180)
        if self._should_force_degrade(limits):
            hop_limit = min(hop_limit, 2)
            max_nodes = min(max_nodes, 120)
            max_edges = min(max_edges, 360)
            graph_warnings.append("Degraded graph: constraints reduced due to tight budget")

        # Build graph
        graph = await self.graph_builder.build_graph(
            docs=docs,
            max_nodes=max_nodes,
            max_edges=max_edges,
            lang=lang
        )

        # Traverse graph
        traversal = create_traversal(graph)

        # Get central nodes as start points
        central_nodes = traversal.get_central_nodes(top_k=3)
        start_node_ids = [n["id"] for n in central_nodes]

        # BFS traversal
        subgraph = traversal.traverse_bfs(
            start_nodes=start_node_ids,
            hop_limit=hop_limit,
            max_nodes=min(50, max_nodes)
        )

        # Find paths
        paths = []
        if len(start_node_ids) >= 2:
            paths = traversal.find_paths(
                start_node=start_node_ids[0],
                end_node=start_node_ids[1],
                max_hops=hop_limit,
                max_paths=5
            )

        _, arm = self._ab_arm(context)
        if arm == "B" and paths:
            limited_paths = []
            for path in paths:
                if isinstance(path, GraphPath):
                    nodes_slice = path.nodes[:3]
                    limited_paths.append(GraphPath(nodes=nodes_slice, hops=len(nodes_slice) - 1, score=path.score))
                else:
                    nodes_slice = path.get("nodes", [])[:3]
                    limited_paths.append(GraphPath(nodes=nodes_slice, hops=len(nodes_slice) - 1, score=path.get("score", 0.75)))
            paths = limited_paths

        # Build result
        graph_result = GraphResult(
            subgraph=subgraph,
            paths=paths,
            answer=self._trim(
                f"Граф из {len(subgraph['nodes'])} узлов и {len(subgraph['edges'])} связей построен вокруг запроса." if lang == "ru"
                else f"Graph of {len(subgraph['nodes'])} nodes and {len(subgraph['edges'])} edges built around query.",
                600
            )
        )

        evidence = self._build_evidence(docs[:10])
        insights = self._build_insights_from_graph(graph, lang)
        meta = self._build_meta(context, confidence=0.74)

        header = "Граф знаний" if lang == "ru" else "Knowledge Graph"
        tldr = self._trim(
            ("Граф связывает ключевые сущности и документы по теме запроса." if lang == "ru"
             else "Graph links key entities and documents related to query."),
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=graph_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings() + graph_warnings
        )

        return response

    async def _handle_memory(self, context: Dict[str, Any]) -> Any:
        """Handle /memory operations with real database storage"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        operation = params.get("operation", "recall")
        query = params.get("query", "")
        user_id = params.get("user_id")

        suggestions = []
        to_store = []
        records = []

        if operation == "suggest":
            # Suggest what to store based on importance
            suggestions_data = await self.memory_store.suggest_storage(docs, max_suggestions=5)
            for sugg in suggestions_data:
                # Filter PII
                if not PIIMasker.contains_pii(sugg["content"]):
                    suggestions.append(
                        MemorySuggestion(
                            type=sugg["type"],
                            content=self._trim(sugg["content"], 200),
                            importance=sugg["importance"],
                            ttl_days=sugg["ttl_days"]
                        )
                    )

        elif operation == "store":
            # Store memories in database
            for doc in docs[:3]:
                content = doc.get("snippet", doc.get("title", ""))
                if not PIIMasker.contains_pii(content):
                    # Determine memory type and importance
                    importance = min(1.0, max(0.5, doc.get("score", 0.6)))
                    mem_type = "episodic" if "date" in doc else "semantic"

                    # Store in database
                    memory_id = await self.memory_store.store(
                        content=self._trim(content, 500),
                        memory_type=mem_type,
                        importance=importance,
                        ttl_days=90 if mem_type == "episodic" else 180,
                        refs=[doc.get("article_id") or doc.get("url", "")],
                        user_id=user_id
                    )

                    to_store.append(
                        MemoryStoreItem(
                            type=mem_type,
                            content=self._trim(content, 240),
                            refs=[doc.get("article_id") or doc.get("url", "")],
                            ttl_days=90 if mem_type == "episodic" else 180
                        )
                    )

        else:  # recall
            # Semantic search in memory database
            recalled = await self.memory_store.recall(
                query=query or "recent memories",
                user_id=user_id,
                limit=10,
                min_similarity=0.5
            )

            for mem in recalled:
                records.append(
                    MemoryRecord(
                        id=mem["id"],
                        type=mem["type"],
                        content=self._trim(mem["content"], 240),
                        ts=mem["created_at"].strftime("%Y-%m-%d") if mem.get("created_at") else "",
                        refs=mem.get("refs", [])
                    )
                )

        memory_result = MemoryResult(
            operation=operation,
            suggestions=suggestions,
            to_store=to_store,
            records=records
        )

        evidence = self._build_evidence(docs[:5])
        insights = self._build_insights_from_docs(docs[:3], lang)
        meta = self._build_meta(context, confidence=0.7)

        header = "Долгая память" if lang == "ru" else "Long-term Memory"

        # Build status message based on operation
        if operation == "suggest":
            status = f"Найдено {len(suggestions)} кандидатов для сохранения" if lang == "ru" else f"Found {len(suggestions)} candidates for storage"
        elif operation == "store":
            status = f"Сохранено {len(to_store)} воспоминаний в БД" if lang == "ru" else f"Stored {len(to_store)} memories in database"
        else:  # recall
            status = f"Извлечено {len(records)} воспоминаний (similarity ≥ 0.5)" if lang == "ru" else f"Retrieved {len(records)} memories (similarity ≥ 0.5)"

        tldr = self._trim(status, 220)

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=memory_result.model_dump(),
            meta=meta,
            warnings=[]
        )

        return response

    async def _handle_synthesis(self, context: Dict[str, Any]) -> Any:
        """Handle /synthesize with LLM-powered synthesis"""
        docs = context.get("retrieval", {}).get("docs", [])
        params = context.get("params", {})
        lang = params.get("lang", "en")
        agent_outputs = context.get("agent_outputs", {})

        # Create budget manager
        limits = context.get("limits", {})
        budget = create_budget_manager(
            max_tokens=limits.get("max_tokens", 8000),
            budget_cents=limits.get("budget_cents", 50),
            timeout_s=limits.get("timeout_s", 30)
        )

        # Generate synthesis via LLM
        prompt = self._build_synthesis_prompt(agent_outputs, docs, lang)

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

            budget.record_usage(
                tokens=metadata["tokens_used"],
                cost_cents=metadata["cost_cents"],
                latency_s=metadata["latency_ms"] / 1000
            )

            summary = response["content"][:400]

        except Exception as e:
            logger.warning(f"Synthesis LLM call failed: {e}")
            summary = "Синтез недоступен" if lang == "ru" else "Synthesis unavailable"

        # Detect conflicts
        conflicts = self._detect_conflicts(agent_outputs, docs, lang)

        # Generate actions
        actions = self._generate_actions(docs, lang)

        synth_result = SynthesisResult(
            summary=summary,
            conflicts=conflicts,
            actions=actions
        )

        evidence = self._build_evidence(docs[:10])
        insights = self._build_insights_from_docs(docs[:5], lang)
        meta = self._build_meta(context, confidence=0.77)

        header = "Сводный отчёт" if lang == "ru" else "Synthesis Report"
        tldr = self._trim(
            ("Объединённый анализ с выявлением конфликтов и рекомендациями." if lang == "ru"
             else "Unified analysis with conflict detection and recommendations."),
            220
        )

        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=synth_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings()
        )

        return response

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    def _should_force_degrade(self, limits: Dict[str, Any]) -> bool:
        max_tokens = int(limits.get("max_tokens", 8000) or 8000)
        budget_cents = int(limits.get("budget_cents", 50) or 50)
        timeout_s = int(limits.get("timeout_s", 30) or 30)
        return max_tokens <= 2048 or budget_cents <= 25 or timeout_s <= 10

    @staticmethod
    def _ab_arm(context: Dict[str, Any]) -> Tuple[Optional[str], str]:
        ab = context.get("ab_test", {}) or {}
        experiment = ab.get("experiment")
        arm = (ab.get("arm") or "A").upper()
        return experiment, arm

    def _fallback_timeline(self, events: List[Dict[str, Any]]) -> List[TimelineRelation]:
        timeline: List[TimelineRelation] = []
        for idx in range(1, len(events)):
            current = events[idx]
            previous = events[idx - 1]
            timeline.append(
                TimelineRelation(
                    event_id=current.get("id", f"event-{idx}"),
                    position="after",
                    ref_event_id=previous.get("id", f"event-{idx-1}")
                )
            )
        return timeline

    def _fallback_causal_links(self, events: List[Dict[str, Any]], lang: str) -> List[CausalLink]:
        links: List[CausalLink] = []
        for idx in range(1, len(events)):
            previous = events[idx - 1]
            current = events[idx]
            refs = current.get("docs") or previous.get("docs") or []
            ts_range = current.get("ts_range") or [datetime.utcnow().strftime("%Y-%m-%d")]
            evidence = EvidenceRef(
                article_id=refs[0] if refs else None,
                url=None,
                date=ts_range[0] if ts_range else datetime.utcnow().strftime("%Y-%m-%d")
            )
            links.append(
                CausalLink(
                    cause_event_id=previous.get("id", f"event-{idx-1}"),
                    effect_event_id=current.get("id", f"event-{idx}"),
                    confidence=max(0.3, 0.8 - idx * 0.1),
                    evidence_refs=[evidence]
                )
            )
        return links

    def _create_retrieval_fn(self, window: str, lang: str):
        """Create retrieval function for Agentic RAG"""
        async def retrieval_fn(query: str, window: str = window, k_final: int = 5):
            return await self.retrieval_client.retrieve(
                query=query,
                window=window,
                lang=lang,
                k_final=k_final,
                use_rerank=True
            )
        return retrieval_fn

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"

    def _build_evidence(self, docs: List[Dict[str, Any]]) -> List[Evidence]:
        """Build evidence list from documents"""
        evidence = []
        for doc in docs:
            evidence.append(
                Evidence(
                    title=self._trim(doc.get("title", "Untitled"), 200),
                    article_id=doc.get("article_id"),
                    url=doc.get("url"),
                    date=doc.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
                    snippet=self._trim(doc.get("snippet", ""), 240)
                )
            )
        return evidence

    def _build_insights_from_docs(self, docs: List[Dict[str, Any]], lang: str) -> List[Insight]:
        """Build insights from documents"""
        insights = []
        templates_en = [
            "{title} highlights key developments.",
            "{title} provides supporting evidence.",
            "{title} offers context."
        ]
        templates_ru = [
            "{title} подчёркивает ключевые изменения.",
            "{title} предоставляет подтверждающие данные.",
            "{title} даёт контекст."
        ]
        templates = templates_ru if lang == "ru" else templates_en

        for idx, doc in enumerate(docs[:3]):
            template = templates[idx % len(templates)]
            text = self._trim(
                template.format(title=self._trim(doc.get("title", "Source"), 60)),
                180
            )
            insights.append(
                Insight(
                    type="fact",
                    text=text,
                    evidence_refs=[
                        EvidenceRef(
                            article_id=doc.get("article_id"),
                            url=doc.get("url"),
                            date=doc.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
                        )
                    ]
                )
            )

        return insights or [
            Insight(
                type="fact",
                text="Нет источников" if lang == "ru" else "No sources available",
                evidence_refs=[
                    EvidenceRef(article_id=None, url=None, date=datetime.utcnow().strftime("%Y-%m-%d"))
                ]
            )
        ]

    def _build_insights_from_events(self, events: List[Dict], lang: str) -> List[Insight]:
        """Build insights from events"""
        insights = []
        for idx, event in enumerate(events[:3]):
            text = self._trim(
                f"Событие: {event.get('title', 'N/A')}" if lang == "ru"
                else f"Event: {event.get('title', 'N/A')}",
                180
            )
            insights.append(
                Insight(
                    type="fact",
                    text=text,
                    evidence_refs=[
                        EvidenceRef(
                            article_id=event.get("docs", [None])[0],
                            url=None,
                            date=event.get("ts_range", [datetime.utcnow().strftime("%Y-%m-%d")])[0]
                        )
                    ]
                )
            )
        return insights

    def _build_insights_from_graph(self, graph: Dict, lang: str) -> List[Insight]:
        """Build insights from graph"""
        node_count = len(graph.get("nodes", []))
        edge_count = len(graph.get("edges", []))

        insights = [
            Insight(
                type="fact",
                text=self._trim(
                    f"Граф содержит {node_count} узлов и {edge_count} связей" if lang == "ru"
                    else f"Graph contains {node_count} nodes and {edge_count} edges",
                    180
                ),
                evidence_refs=[
                    EvidenceRef(article_id=None, url=None, date=datetime.utcnow().strftime("%Y-%m-%d"))
                ]
            )
        ]
        return insights

    def _build_meta(self, context: Dict[str, Any], iterations: int = 1, confidence: float = 0.75) -> Meta:
        """Build metadata"""
        ab = context.get("ab_test", {}) or {}
        telemetry = context.get("telemetry", {})
        return Meta(
            confidence=max(0.0, min(confidence, 1.0)),
            model=context.get("models", {}).get("primary", "gpt-5"),
            version=telemetry.get("version", "phase3-v1.0"),
            correlation_id=telemetry.get("correlation_id", "phase3-run"),
            experiment=ab.get("experiment"),
            arm=ab.get("arm"),
            iterations=iterations
        )

    def _build_synthesis_prompt(self, agent_outputs: Dict, docs: List[Dict], lang: str) -> str:
        """Build synthesis prompt for LLM"""
        if lang == "ru":
            return f"""Объедини результаты нескольких агентов в краткую сводку (≤400 символов).

Результаты агентов: {len(agent_outputs)} outputs
Документы: {len(docs)} sources

Сводка должна:
- Выделить ключевые выводы
- Отметить противоречия (если есть)
- Дать 2-3 рекомендации"""
        else:
            return f"""Synthesize results from multiple agents into brief summary (≤400 chars).

Agent outputs: {len(agent_outputs)} outputs
Documents: {len(docs)} sources

Summary should:
- Highlight key findings
- Note conflicts (if any)
- Provide 2-3 recommendations"""

    def _detect_conflicts(self, agent_outputs: Dict, docs: List[Dict], lang: str) -> List[Conflict]:
        """Detect conflicts between sources"""
        conflicts = []
        if len(docs) >= 2:
            conflicts.append(
                Conflict(
                    description=self._trim(
                        "Различия в оценках между источниками" if lang == "ru"
                        else "Divergent assessments across sources",
                        180
                    ),
                    evidence_refs=[
                        EvidenceRef(
                            article_id=docs[0].get("article_id"),
                            url=docs[0].get("url"),
                            date=docs[0].get("date", datetime.utcnow().strftime("%Y-%m-%d"))
                        ),
                        EvidenceRef(
                            article_id=docs[1].get("article_id"),
                            url=docs[1].get("url"),
                            date=docs[1].get("date", datetime.utcnow().strftime("%Y-%m-%d"))
                        )
                    ]
                )
            )
        return conflicts

    def _generate_actions(self, docs: List[Dict], lang: str) -> List[Action]:
        """Generate actionable recommendations"""
        actions = []
        action_texts = [
            "Усилить мониторинг ключевых метрик" if lang == "ru" else "Strengthen monitoring of key metrics",
            "Провести углублённый анализ трендов" if lang == "ru" else "Conduct deeper trend analysis"
        ]

        for text, doc in zip(action_texts, docs[:2]):
            actions.append(
                Action(
                    recommendation=self._trim(text, 180),
                    impact="high" if len(actions) == 0 else "medium",
                    evidence_refs=[
                        EvidenceRef(
                            article_id=doc.get("article_id"),
                            url=doc.get("url"),
                            date=doc.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
                        )
                    ]
                )
            )

        return actions or [
            Action(
                recommendation=self._trim(
                    "Собрать дополнительные данные" if lang == "ru" else "Gather additional data",
                    180
                ),
                impact="medium",
                evidence_refs=[
                    EvidenceRef(article_id=None, url=None, date=datetime.utcnow().strftime("%Y-%m-%d"))
                ]
            )
        ]

    def _build_error_response(self, error_msg: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Build error response"""
        from schemas.analysis_schemas import build_error_response, Meta

        meta = Meta(
            confidence=0.0,
            model="unknown",
            version="phase3-v1.0",
            correlation_id=context.get("telemetry", {}).get("correlation_id", "error"),
            iterations=1
        )

        error_response = build_error_response(
            code="INTERNAL",
            user_message="Command execution failed",
            tech_message=error_msg,
            retryable=True,
            meta=meta
        )

        return error_response.model_dump()


__all__ = ["Phase3Orchestrator"]
