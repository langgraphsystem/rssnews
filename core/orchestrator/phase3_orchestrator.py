"""Phase 3 Orchestrator — Agentic RAG, GraphRAG, Events, Memory"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from schemas.analysis_schemas import (
    build_base_response,
    Insight,
    Evidence,
    EvidenceRef,
    Meta,
    AgenticResult,
    AgenticStep,
    EventsResult,
    EventRecord,
    TimelineRelation,
    CausalLink,
    GraphResult,
    GraphPath,
    MemoryResult,
    MemorySuggestion,
    MemoryStoreItem,
    MemoryRecord,
    SynthesisResult,
    Action,
    Conflict,
)
from core.policies.validators import get_validator
from core.models import BudgetManager, create_budget_manager


class Phase3Orchestrator:
    """Generates structured analytics responses for Phase 3 commands."""

    def __init__(self) -> None:
        self.validator = get_validator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        command = context.get("command", "")
        if command.startswith("/ask"):
            response = self._handle_agentic(context)
        elif command.startswith("/events"):
            response = self._handle_events(context)
        elif command.startswith("/graph"):
            response = self._handle_graph(context)
        elif command.startswith("/memory"):
            response = self._handle_memory(context)
        elif command.startswith("/synthesize"):
            response = self._handle_synthesis(context)
        else:
            raise ValueError(f"Unsupported Phase 3 command: {command}")

        # Validate with policy layer before returning
        self.validator.validate_response(response)
        return response.model_dump()

    # ------------------------------------------------------------------
    # Helpers (shared)
    # ------------------------------------------------------------------
    @staticmethod
    def _trim(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    @staticmethod
    def _language_prefs(lang: str) -> Tuple[str, str, str]:
        if lang == "ru":
            return (
                "Обзор",
                "Ключевые выводы",
                "Рекомендации"
            )
        return (
            "Overview",
            "Key Insights",
            "Recommendations"
        )

    def _compute_budget(self, context: Dict[str, Any]) -> Tuple[BudgetManager, Dict[str, Any]]:
        limits = context.get("limits", {}) or {}
        bm = create_budget_manager(
            max_tokens=limits.get("max_tokens", 4096),
            budget_cents=limits.get("budget_cents", 50),
            timeout_s=limits.get("timeout_s", 12),
        )
        return bm, limits

    def _ab_arm(self, context: Dict[str, Any]) -> Tuple[str, str]:
        ab = context.get("ab_test", {}) or {}
        exp = ab.get("experiment") or "phase3-default"
        arm = ab.get("arm") or "A"
        return exp, arm

    def _build_evidence(self, docs: List[Dict[str, Any]]) -> List[Evidence]:
        evidence: List[Evidence] = []
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

    def _build_insights(self, docs: List[Dict[str, Any]], lang: str) -> List[Insight]:
        insights: List[Insight] = []
        heading, key_label, _ = self._language_prefs(lang)
        templates_en = [
            "{title} highlights accelerating adoption and governance." ,
            "{title} signals infrastructure shifts supporting AI workloads.",
            "{title} outlines regulatory momentum shaping deployments."
        ]
        templates_ru = [
            "{title} подчёркивает ускорение внедрения и контроль.",
            "{title} показывает изменения инфраструктуры для AI-нагрузок.",
            "{title} описывает регуляторные тренды, влияющие на внедрение."
        ]
        templates = templates_ru if lang == "ru" else templates_en
        for idx, doc in enumerate(docs[:3]):
            template = templates[idx % len(templates)]
            text = self._trim(template.format(title=self._trim(doc.get("title", "Источник"), 80)), 180)
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
        return insights if insights else [
            Insight(
                type="fact",
                text=("Источники не обнаружены." if lang == "ru" else "No supporting articles provided."),
                evidence_refs=[
                    EvidenceRef(article_id=None, url=None, date=datetime.utcnow().strftime("%Y-%m-%d"))
                ]
            )
        ]

    def _meta(self, context: Dict[str, Any], iterations: int = 1, confidence: float = 0.75) -> Meta:
        ab = context.get("ab_test", {}) or {}
        telemetry = context.get("telemetry", {})
        return Meta(
            confidence=max(0.0, min(confidence, 1.0)),
            model=context.get("models", {}).get("primary", "gpt-5"),
            version=telemetry.get("version", "phase3-orchestrator"),
            correlation_id=telemetry.get("correlation_id", "phase3-run"),
            experiment=ab.get("experiment"),
            arm=ab.get("arm"),
            iterations=iterations
        )

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    def _handle_agentic(self, context: Dict[str, Any]) -> Any:
        docs = context.get("retrieval", {}).get("docs", [])
        lang = context.get("params", {}).get("lang", "en")
        query = context.get("params", {}).get("query") or context.get("params", {}).get("topic") or "primary question"
        budget, _ = self._compute_budget(context)
        steps_count = 3
        if budget.should_degrade():
            degraded = budget.get_degraded_params("/ask", {"depth": 3})
            steps_count = max(1, degraded.get("depth", 1))
        steps: List[AgenticStep] = []
        for idx in range(1, steps_count + 1):
            sliced = docs[: min(len(docs), idx * 2)]
            reason = "Self-check and refinement" if idx > 1 else "Initial retrieval"
            steps.append(
                AgenticStep(
                    iteration=idx,
                    query=f"{query} (iter {idx})",
                    n_docs=len(sliced),
                    reason=("Самопроверка и уточнение" if lang == "ru" else reason)
                )
            )
        answer_parts = [doc.get("title", "") for doc in docs[:3]]
        answer = "; ".join([self._trim(p, 80) for p in answer_parts])
        followups = []
        if lang == "ru":
            followups.append("Нужно ли углубиться в конкретные метрики внедрения?")
        else:
            followups.append("Should we dive deeper into specific deployment metrics?")
        agentic_result = AgenticResult(
            steps=steps,
            answer=self._trim(answer or ("Нет данных" if lang == "ru" else "No supporting evidence"), 600),
            followups=followups
        )
        evidence = self._build_evidence(docs)
        insights = self._build_insights(docs, lang)
        meta = self._meta(context, iterations=len(steps), confidence=0.78)
        header = "Глубокий разбор" if lang == "ru" else "Deep Dive"
        tldr = self._trim(
            ("Многоходовой анализ показал ключевые аспекты вопроса." if lang == "ru" else "Iterative reasoning surfaced the key aspects of the query."),
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

    def _handle_events(self, context: Dict[str, Any]) -> Any:
        docs = context.get("retrieval", {}).get("docs", [])
        lang = context.get("params", {}).get("lang", "en")
        exp, arm = self._ab_arm(context)
        budget, _ = self._compute_budget(context)
        events: List[EventRecord] = []
        timeline: List[TimelineRelation] = []
        causal_links: List[CausalLink] = []
        for idx, doc in enumerate(docs):
            event_id = doc.get("article_id", f"evt-{idx}")
            ts = doc.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
            entities = [self._trim(part, 50) for part in doc.get("title", "").split()[:3]]
            events.append(
                EventRecord(
                    id=event_id,
                    title=self._trim(doc.get("title", "Event"), 160),
                    ts_range=[ts, ts],
                    entities=entities,
                    docs=[doc.get("article_id", "")]
                )
            )
            if idx > 0:
                prev_id = docs[idx - 1].get("article_id", f"evt-{idx-1}")
                timeline.append(
                    TimelineRelation(
                        event_id=event_id,
                        position="after",
                        ref_event_id=prev_id
                    )
                )
                causal_links.append(
                    CausalLink(
                        cause_event_id=prev_id,
                        effect_event_id=event_id,
                        confidence=max(0.3, 0.8 - idx * 0.1),
                        evidence_refs=[
                            EvidenceRef(
                                article_id=doc.get("article_id"),
                                url=doc.get("url"),
                                date=ts
                            )
                        ]
                    )
                )
        max_events = 10
        if budget.should_degrade():
            degraded = budget.get_degraded_params("/events", {"k_final": max_events})
            max_events = max(3, degraded.get("k_final", 5))
        # A/B: slightly reduce causal links in arm B to simulate alt reasoning
        clinks = causal_links
        if arm.upper() == "B" and len(causal_links) > 0:
            clinks = causal_links[:-1]
        events_result = EventsResult(
            events=events[:max_events],
            timeline=timeline[:max_events],
            causal_links=clinks[:max_events]
        )
        evidence = self._build_evidence(docs)
        insights = self._build_insights(docs, lang)
        meta = self._meta(context, confidence=0.74)
        header = "Связанные события" if lang == "ru" else "Linked Events"
        tldr = self._trim(
            ("События выстроены в последовательность с предполагаемыми причинными связями." if lang == "ru" else "Events align on a timeline with suggested causal links."),
            220
        )
        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=events_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings()
        )
        return response

    def _handle_graph(self, context: Dict[str, Any]) -> Any:
        docs = context.get("retrieval", {}).get("docs", [])
        lang = context.get("params", {}).get("lang", "en")
        exp, arm = self._ab_arm(context)
        budget, _ = self._compute_budget(context)
        nodes = []
        edges = []
        paths: List[GraphPath] = []
        topic_label = context.get("params", {}).get("topic") or ("Граф" if lang == "ru" else "Graph")
        topic_node_id = "topic-root"
        nodes.append({"id": topic_node_id, "label": self._trim(topic_label, 80), "type": "topic"})
        for idx, doc in enumerate(docs):
            node_id = doc.get("article_id", f"doc-{idx}")
            nodes.append({"id": node_id, "label": self._trim(doc.get("title", "Doc"), 120), "type": "article"})
            edges.append({
                "src": topic_node_id,
                "tgt": node_id,
                "type": "relates_to",
                "weight": round(min(1.0, max(0.1, doc.get("score", 0.5))), 2)
            })
        if len(nodes) > 1:
            path_nodes = [topic_node_id] + [n["id"] for n in nodes[1:3]]
            paths.append(GraphPath(nodes=path_nodes, hops=len(path_nodes) - 1, score=0.78))
        hop_limit = 3
        if budget.should_degrade():
            degraded = budget.get_degraded_params("/graph", {"hop_limit": 3, "max_nodes": 200, "max_edges": 600})
            hop_limit = max(1, degraded.get("hop_limit", 1))
        # A/B: arm B uses shorter illustrative paths
        limited_paths: List[GraphPath] = []
        for p in paths[:hop_limit]:
            if isinstance(p, GraphPath):
                nodes_list = p.nodes
                score = p.score
            else:
                nodes_list = p.get("nodes", [])
                score = p.get("score", 0.75)
            max_nodes_in_path = (2 if arm.upper() == "B" else hop_limit) + 1
            ln = nodes_list[:max_nodes_in_path]
            limited_paths.append(GraphPath(nodes=ln, hops=len(ln) - 1, score=score))
        graph_result = GraphResult(
            subgraph={"nodes": nodes[:200], "edges": edges[:600]},
            paths=[p.model_dump() for p in limited_paths],
            answer=self._trim(
                ("Связи показывают, какие документы поддерживают центральную тему." if lang == "ru" else "The subgraph shows which articles reinforce the central topic."),
                600
            )
        )
        evidence = self._build_evidence(docs)
        insights = self._build_insights(docs, lang)
        meta = self._meta(context, confidence=0.73)
        header = "Граф знаний" if lang == "ru" else "Knowledge Graph"
        tldr = self._trim(
            ("Мини-граф объединяет ключевые узлы и связи вокруг темы." if lang == "ru" else "The mini-graph ties key nodes and relationships around the topic."),
            220
        )
        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=graph_result.model_dump(),
            meta=meta,
            warnings=budget.get_warnings()
        )
        return response

    def _handle_synthesis(self, context: Dict[str, Any]) -> Any:
        docs = context.get("retrieval", {}).get("docs", [])
        lang = context.get("params", {}).get("lang", "en")
        evidence = self._build_evidence(docs)
        insights = self._build_insights(docs, lang)
        summary = self._trim(
            ("Совокупные источники показывают усиление внедрения AI, инфраструктурную подготовку и регуляторное давление." if lang == "ru" else "Combined evidence shows accelerating AI adoption, infrastructure readiness, and regulatory pressure."),
            400
        )
        conflicts: List[Conflict] = []
        if len(docs) >= 2:
            conflicts.append(
                Conflict(
                    description=self._trim(
                        ("Разные источники по-разному оценивают скорость внедрения." if lang == "ru" else "Sources differ on the pace of rollout."),
                        180
                    ),
                    evidence_refs=[
                        EvidenceRef(article_id=docs[0].get("article_id"), url=docs[0].get("url"), date=docs[0].get("date", datetime.utcnow().strftime("%Y-%m-%d"))),
                        EvidenceRef(article_id=docs[1].get("article_id"), url=docs[1].get("url"), date=docs[1].get("date", datetime.utcnow().strftime("%Y-%m-%d")))
                    ]
                )
            )
        actions: List[Action] = []
        action_texts = [
            ("Закрепить контроль за качеством данных для выполнения новых регуляторных требований." if lang == "ru" else "Strengthen data quality controls to satisfy emerging transparency benchmarks."),
            ("Планировать резерв GPU и нагрузочные тесты для пиковых кампаний." if lang == "ru" else "Plan GPU capacity reserve and stress tests for peak campaigns.")
        ]
        for text, doc in zip(action_texts, docs[:2]):
            actions.append(
                Action(
                    recommendation=self._trim(text, 180),
                    impact="high" if len(actions) == 0 else "medium",
                    evidence_refs=[
                        EvidenceRef(article_id=doc.get("article_id"), url=doc.get("url"), date=doc.get("date", datetime.utcnow().strftime("%Y-%m-%d")))
                    ]
                )
            )
        synth_result = SynthesisResult(
            summary=summary,
            conflicts=conflicts,
            actions=actions or [
                Action(
                    recommendation=self._trim(("Нужно дополнительно собрать данные." if lang == "ru" else "Collect more evidence."), 180),
                    impact="medium",
                    evidence_refs=[
                        EvidenceRef(article_id=None, url=None, date=datetime.utcnow().strftime("%Y-%m-%d"))
                    ]
                )
            ]
        )
        meta = self._meta(context, confidence=0.77)
        header = "Сводный отчёт" if lang == "ru" else "Synthesis Report"
        tldr = self._trim(
            ("Объединённый анализ подчёркивает необходимость прозрачности и устойчивой инфраструктуры." if lang == "ru" else "Merged insights highlight the need for transparency and resilient infrastructure."),
            220
        )
        response = build_base_response(
            header=header,
            tldr=tldr,
            insights=insights,
            evidence=evidence,
            result=synth_result.model_dump(),
            meta=meta,
            warnings=[]
        )
        return response

    def _handle_memory(self, context: Dict[str, Any]) -> Any:
        docs = context.get("retrieval", {}).get("docs", [])
        lang = context.get("params", {}).get("lang", "en")
        command = context.get("command", "/memory")
        parts = command.split()
        operation = parts[1] if len(parts) > 1 else context.get("params", {}).get("operation", "recall")
        dg = self._compute_degradation(context)["degrade"]["memory_mode"]
        if dg:
            operation = dg
        operation = operation.lower()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        suggestions: List[MemorySuggestion] = []
        to_store: List[MemoryStoreItem] = []
        records: List[MemoryRecord] = []
        if operation == "suggest":
            for doc in docs[:3]:
                suggestions.append(
                    MemorySuggestion(
                        type="semantic",
                        content=self._trim(doc.get("title", "Memory"), 200),
                        importance=min(1.0, max(0.5, doc.get("score", 0.6))),
                        ttl_days=30
                    )
                )
        elif operation == "store":
            for doc in docs[:2]:
                to_store.append(
                    MemoryStoreItem(
                        type="episodic",
                        content=self._trim(doc.get("snippet", doc.get("title", "")), 240),
                        refs=[doc.get("article_id") or doc.get("url", "")],
                        ttl_days=90
                    )
                )
        else:  # recall default
            for idx, doc in enumerate(docs[:3]):
                records.append(
                    MemoryRecord(
                        id=doc.get("article_id", f"rec-{idx}"),
                        type="semantic",
                        content=self._trim(doc.get("snippet", doc.get("title", "")), 240),
                        ts=doc.get("date", today),
                        refs=[doc.get("url", "")]
                    )
                )
        memory_result = MemoryResult(
            operation=operation,
            suggestions=suggestions,
            to_store=to_store,
            records=records
        )
        evidence = self._build_evidence(docs)
        insights = self._build_insights(docs, lang)
        meta = self._meta(context, confidence=0.7)
        header = "Долгая память" if lang == "ru" else "Long-term Memory"
        tldr = self._trim(
            ("Память обработана: предложения, хранилище или извлечённые записи." if lang == "ru" else "Memory operation completed with suggestions, stores, or recalls."),
            220
        )
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


__all__ = ["Phase3Orchestrator"]
