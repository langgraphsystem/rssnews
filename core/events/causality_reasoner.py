"""
Causality Reasoner — Infers cause-effect relationships between events.
Uses temporal ordering and LLM-based reasoning to detect causal links.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from core.models.model_router import ModelRouter, get_model_router
from core.models.budget_manager import BudgetManager
from schemas.analysis_schemas import CausalLink, EvidenceRef, TimelineRelation

logger = logging.getLogger(__name__)


class CausalityReasoner:
    """Infers causal relationships between events"""

    def __init__(self, model_router: Optional[ModelRouter] = None):
        """Initialize causality reasoner"""
        self.model_router = model_router or get_model_router()

    async def infer_causality(
        self,
        events: List[Dict[str, Any]],
        docs: List[Dict[str, Any]],
        budget_manager: BudgetManager,
        lang: str = "en",
        max_links: int = 20
    ) -> Tuple[List[TimelineRelation], List[CausalLink]]:
        """
        Infer timeline and causal relationships

        Args:
            events: List of events (from EventExtractor)
            docs: Original documents
            budget_manager: Budget manager
            lang: Language
            max_links: Maximum causal links to return

        Returns:
            Tuple of (timeline_relations, causal_links)
        """
        logger.info(f"Inferring causality for {len(events)} events")

        # Step 1: Build timeline (temporal ordering)
        timeline = self._build_timeline(events)

        # Step 2: Detect causal links using LLM
        causal_links = await self._detect_causal_links(
            events=events,
            timeline=timeline,
            docs=docs,
            budget_manager=budget_manager,
            lang=lang
        )

        logger.info(
            f"Inferred {len(timeline)} timeline relations, {len(causal_links)} causal links"
        )

        return timeline[:20], causal_links[:max_links]

    def _build_timeline(
        self,
        events: List[Dict[str, Any]]
    ) -> List[TimelineRelation]:
        """
        Build timeline from events based on temporal ordering

        Returns:
            List of TimelineRelation
        """
        timeline = []

        # Sort events by start date
        sorted_events = sorted(
            events,
            key=lambda e: datetime.strptime(e["ts_range"][0], "%Y-%m-%d")
        )

        for i, event in enumerate(sorted_events):
            if i == 0:
                continue  # First event has no predecessor

            prev_event = sorted_events[i - 1]

            # Determine position
            prev_start = datetime.strptime(prev_event["ts_range"][0], "%Y-%m-%d")
            prev_end = datetime.strptime(prev_event["ts_range"][1], "%Y-%m-%d")
            curr_start = datetime.strptime(event["ts_range"][0], "%Y-%m-%d")
            curr_end = datetime.strptime(event["ts_range"][1], "%Y-%m-%d")

            if curr_start > prev_end:
                position = "after"
            elif curr_end < prev_start:
                position = "before"
            else:
                position = "overlap"

            timeline.append(
                TimelineRelation(
                    event_id=event["id"],
                    position=position,
                    ref_event_id=prev_event["id"]
                )
            )

        return timeline

    async def _detect_causal_links(
        self,
        events: List[Dict[str, Any]],
        timeline: List[TimelineRelation],
        docs: List[Dict[str, Any]],
        budget_manager: BudgetManager,
        lang: str
    ) -> List[CausalLink]:
        """
        Detect causal links using LLM reasoning

        Returns:
            List of CausalLink
        """
        causal_links = []

        # For each pair of consecutive events, check for causality
        for rel in timeline:
            if rel.position == "before":
                continue  # Skip reverse temporal order

            # Check budget
            if not budget_manager.can_afford(estimated_tokens=300, estimated_cents=0.3):
                logger.warning("Budget insufficient for causal reasoning, stopping early")
                break

            # Find events
            cause_event = next((e for e in events if e["id"] == rel.ref_event_id), None)
            effect_event = next((e for e in events if e["id"] == rel.event_id), None)

            if not cause_event or not effect_event:
                continue

            # Check for causal relationship
            is_causal, confidence = await self._check_causality(
                cause_event=cause_event,
                effect_event=effect_event,
                docs=docs,
                budget_manager=budget_manager,
                lang=lang
            )

            if is_causal and confidence > 0.3:
                # Find supporting evidence
                evidence_refs = self._find_evidence(cause_event, effect_event, docs)

                causal_links.append(
                    CausalLink(
                        cause_event_id=cause_event["id"],
                        effect_event_id=effect_event["id"],
                        confidence=round(confidence, 2),
                        evidence_refs=evidence_refs
                    )
                )

        return causal_links

    async def _check_causality(
        self,
        cause_event: Dict[str, Any],
        effect_event: Dict[str, Any],
        docs: List[Dict[str, Any]],
        budget_manager: BudgetManager,
        lang: str
    ) -> Tuple[bool, float]:
        """
        Check if cause_event could have caused effect_event

        Returns:
            Tuple of (is_causal, confidence)
        """
        if lang == "ru":
            prompt = f"""Проанализируй, могло ли событие A вызвать событие B.

Событие A (причина?): {cause_event['title']}
Дата A: {cause_event['ts_range']}

Событие B (следствие?): {effect_event['title']}
Дата B: {effect_event['ts_range']}

Ответь в формате:
CAUSAL: yes|no
CONFIDENCE: 0.0-1.0
REASONING: <краткое обоснование>"""
        else:
            prompt = f"""Analyze if event A could have caused event B.

Event A (cause?): {cause_event['title']}
Date A: {cause_event['ts_range']}

Event B (effect?): {effect_event['title']}
Date B: {effect_event['ts_range']}

Answer in format:
CAUSAL: yes|no
CONFIDENCE: 0.0-1.0
REASONING: <brief reasoning>"""

        try:
            # Get docs for context
            doc_ids = set(cause_event.get("docs", []) + effect_event.get("docs", []))
            context_docs = [d for d in docs if d.get("article_id") in doc_ids][:3]

            response, metadata = await self.model_router.call_with_fallback(
                prompt=prompt,
                docs=context_docs,
                primary="gpt-5",
                fallback=["gemini-2.5-pro", "claude-4.5"],
                timeout_s=12,
                max_tokens=300,
                temperature=0.3
            )

            budget_manager.record_usage(
                tokens=metadata["tokens_used"],
                cost_cents=metadata["cost_cents"],
                latency_s=metadata["latency_ms"] / 1000
            )

            content = response["content"]

            # Parse response
            is_causal = "CAUSAL: yes" in content
            confidence = 0.5  # Default

            # Try to extract confidence
            import re
            conf_match = re.search(r'CONFIDENCE:\s*(0?\.\d+|1\.0)', content)
            if conf_match:
                confidence = float(conf_match.group(1))

            return is_causal, confidence

        except Exception as e:
            logger.warning(f"Causality check failed: {e}")
            # Fallback: simple heuristic based on temporal proximity
            cause_end = datetime.strptime(cause_event["ts_range"][1], "%Y-%m-%d")
            effect_start = datetime.strptime(effect_event["ts_range"][0], "%Y-%m-%d")

            days_diff = (effect_start - cause_end).days

            if 0 <= days_diff <= 7:
                return True, 0.4  # Weak causal link
            else:
                return False, 0.0

    def _find_evidence(
        self,
        cause_event: Dict[str, Any],
        effect_event: Dict[str, Any],
        docs: List[Dict[str, Any]]
    ) -> List[EvidenceRef]:
        """Find supporting evidence for causal link"""
        evidence_refs = []

        # Get docs for both events
        doc_ids = set(cause_event.get("docs", []) + effect_event.get("docs", []))

        for doc in docs:
            if doc.get("article_id") in doc_ids:
                evidence_refs.append(
                    EvidenceRef(
                        article_id=doc.get("article_id"),
                        url=doc.get("url"),
                        date=doc.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
                    )
                )

                if len(evidence_refs) >= 3:
                    break

        # Ensure at least 1 evidence
        if not evidence_refs:
            evidence_refs.append(
                EvidenceRef(
                    article_id=None,
                    url=None,
                    date=datetime.utcnow().strftime("%Y-%m-%d")
                )
            )

        return evidence_refs


def create_causality_reasoner(model_router: Optional[ModelRouter] = None) -> CausalityReasoner:
    """Factory function to create causality reasoner"""
    return CausalityReasoner(model_router=model_router)
