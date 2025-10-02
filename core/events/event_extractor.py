"""
Event Extractor — Extracts events from documents with temporal information.
Supports NER, temporal extraction, and event clustering by time windows.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict

from core.models.model_router import ModelRouter, get_model_router

logger = logging.getLogger(__name__)


class EventExtractor:
    """Extracts and clusters events from documents"""

    def __init__(self, model_router: Optional[ModelRouter] = None):
        """Initialize event extractor"""
        self.model_router = model_router or get_model_router()

    async def extract_events(
        self,
        docs: List[Dict[str, Any]],
        window: str = "12h",
        lang: str = "en",
        max_events: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Extract events from documents

        Args:
            docs: Documents to process
            window: Time window for clustering (6h, 12h, 24h, etc.)
            lang: Language
            max_events: Maximum number of events

        Returns:
            List of events with temporal info and entities
        """
        logger.info(f"Extracting events from {len(docs)} docs (window={window})")

        # Step 1: Extract raw events from each document
        raw_events = []
        for doc in docs:
            event = self._extract_event_from_doc(doc, lang)
            if event:
                raw_events.append(event)

        # Step 2: Cluster events by time window
        clustered_events = self._cluster_by_time(raw_events, window)

        # Step 3: Extract entities for each event
        enriched_events = await self._enrich_with_entities(clustered_events, lang)

        logger.info(f"Extracted {len(enriched_events)} events (from {len(raw_events)} raw)")

        return enriched_events[:max_events]

    def _extract_event_from_doc(
        self,
        doc: Dict[str, Any],
        lang: str
    ) -> Optional[Dict[str, Any]]:
        """Extract event from single document"""
        title = doc.get("title", "")
        snippet = doc.get("snippet", "")
        article_id = doc.get("article_id", "")
        date_str = doc.get("date")

        if not title and not snippet:
            return None

        # Parse date
        try:
            if date_str:
                event_date = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                event_date = datetime.utcnow()
        except:
            event_date = datetime.utcnow()

        # Event title: use document title or first sentence
        event_title = title if title else snippet.split(".")[0][:160]

        return {
            "title": event_title,
            "date": event_date,
            "date_str": event_date.strftime("%Y-%m-%d"),
            "doc_ids": [article_id],
            "text": f"{title} {snippet}"[:500]
        }

    def _cluster_by_time(
        self,
        events: List[Dict[str, Any]],
        window: str
    ) -> List[Dict[str, Any]]:
        """
        Cluster events by time window

        Args:
            events: Raw events
            window: Time window (6h, 12h, 24h, 1d, 3d, etc.)

        Returns:
            Clustered events
        """
        # Parse window to timedelta
        window_delta = self._parse_window(window)

        if not window_delta:
            return events  # No clustering

        # Sort events by date
        sorted_events = sorted(events, key=lambda e: e["date"])

        clusters: List[List[Dict[str, Any]]] = []
        current_cluster: List[Dict[str, Any]] = []
        cluster_start_date = None

        for event in sorted_events:
            event_date = event["date"]

            if not current_cluster:
                # Start new cluster
                current_cluster = [event]
                cluster_start_date = event_date
            else:
                # Check if event fits in current cluster window
                if event_date - cluster_start_date <= window_delta:
                    current_cluster.append(event)
                else:
                    # Close current cluster, start new one
                    clusters.append(current_cluster)
                    current_cluster = [event]
                    cluster_start_date = event_date

        # Add last cluster
        if current_cluster:
            clusters.append(current_cluster)

        # Merge events in each cluster
        clustered_events = []
        for cluster in clusters:
            merged = self._merge_cluster(cluster)
            clustered_events.append(merged)

        logger.info(f"Clustered {len(events)} events into {len(clustered_events)} groups (window={window})")

        return clustered_events

    def _merge_cluster(self, cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge events in a cluster"""
        if len(cluster) == 1:
            event = cluster[0]
            return {
                "title": event["title"],
                "ts_range": [event["date_str"], event["date_str"]],
                "doc_ids": event["doc_ids"],
                "text": event["text"]
            }

        # Multiple events: merge
        titles = [e["title"] for e in cluster]
        dates = [e["date"] for e in cluster]
        doc_ids = []
        for e in cluster:
            doc_ids.extend(e["doc_ids"])

        # Combined title (use first event's title)
        merged_title = titles[0]

        # Date range
        min_date = min(dates).strftime("%Y-%m-%d")
        max_date = max(dates).strftime("%Y-%m-%d")

        # Combined text
        texts = [e["text"] for e in cluster[:3]]  # Max 3 texts
        merged_text = " | ".join(texts)

        return {
            "title": merged_title,
            "ts_range": [min_date, max_date],
            "doc_ids": list(set(doc_ids)),
            "text": merged_text
        }

    async def _enrich_with_entities(
        self,
        events: List[Dict[str, Any]],
        lang: str
    ) -> List[Dict[str, Any]]:
        """Extract entities for each event"""
        enriched = []

        for idx, event in enumerate(events):
            # Simple entity extraction (capitalized sequences)
            text = event.get("text", "")
            entities = self._extract_entities_simple(text)

            enriched.append({
                "id": f"evt_{idx}",
                "title": event["title"],
                "ts_range": event["ts_range"],
                "entities": entities[:10],
                "docs": event["doc_ids"]
            })

        return enriched

    def _extract_entities_simple(self, text: str) -> List[str]:
        """Simple entity extraction using regex"""
        # Extract capitalized sequences (2+ chars)
        candidates = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)

        # Filter and deduplicate
        entities = []
        seen = set()

        for entity in candidates:
            normalized = entity.strip()

            # Skip common words
            if normalized.lower() in {"the", "this", "that", "there", "these", "those", "a", "an"}:
                continue

            if normalized not in seen:
                seen.add(normalized)
                entities.append(normalized)

        return entities

    def _parse_window(self, window: str) -> Optional[timedelta]:
        """Parse window string to timedelta"""
        match = re.match(r'(\d+)([hdwm])', window.lower())

        if not match:
            return None

        value = int(match.group(1))
        unit = match.group(2)

        if unit == 'h':
            return timedelta(hours=value)
        elif unit == 'd':
            return timedelta(days=value)
        elif unit == 'w':
            return timedelta(weeks=value)
        elif unit == 'm':
            return timedelta(days=value * 30)  # Approximate
        else:
            return None


def create_event_extractor(model_router: Optional[ModelRouter] = None) -> EventExtractor:
    """Factory function to create event extractor"""
    return EventExtractor(model_router=model_router)
