"""
Graph Builder — Constructs knowledge graphs from documents using NER and relation extraction.
Supports on-demand graph construction with configurable limits.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

from core.models.model_router import ModelRouter, get_model_router
from core.nlp.ner_service import create_ner_service, NERStrategy

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds knowledge graphs from document collections"""

    ENTITY_STOPWORDS = {"the", "this", "that", "there", "these", "those", "and", "for", "with", "from", "into", "of", "in"}
    KNOWN_ORGS = {"openai", "google", "microsoft", "amazon", "apple", "ibm", "meta"}

    def __init__(self, model_router: Optional[ModelRouter] = None, use_advanced_ner: bool = True):
        """
        Initialize graph builder

        Args:
            model_router: Optional ModelRouter for LLM calls
            use_advanced_ner: If True, use spaCy/LLM NER. If False, use regex fallback.
        """
        self.model_router = model_router or get_model_router()
        self.use_advanced_ner = use_advanced_ner
        self.ner_service = None

        # Initialize NER service if advanced mode
        if use_advanced_ner:
            self.ner_service = create_ner_service(
                model_router=self.model_router,
                prefer_strategy=NERStrategy.SPACY
            )

    async def build_graph(
        self,
        docs: List[Dict[str, Any]],
        max_nodes: int = 200,
        max_edges: int = 600,
        lang: str = "en"
    ) -> Dict[str, Any]:
        """
        Build knowledge graph from documents

        Args:
            docs: Documents to process
            max_nodes: Maximum number of nodes
            max_edges: Maximum number of edges
            lang: Language for NER

        Returns:
            Graph dict with nodes and edges
        """
        logger.info(f"Building graph from {len(docs)} docs (max_nodes={max_nodes}, max_edges={max_edges})")

        # Step 1: Extract entities (NER)
        entities = await self._extract_entities(docs, lang=lang)

        # Step 2: Extract relations between entities
        relations = await self._extract_relations(docs, entities, lang=lang)

        # Step 3: Build graph structure
        nodes, edges = self._construct_graph(entities, relations, docs, max_nodes, max_edges)

        graph = {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "source_docs": len(docs),
                "entities_extracted": len(entities),
                "relations_extracted": len(relations),
                "nodes_final": len(nodes),
                "edges_final": len(edges)
            }
        }

        logger.info(
            f"Graph built: {len(nodes)} nodes, {len(edges)} edges "
            f"(from {len(entities)} entities, {len(relations)} relations)"
        )

        return graph

    async def _extract_entities(
        self,
        docs: List[Dict[str, Any]],
        lang: str
    ) -> List[Dict[str, Any]]:
        """
        Extract named entities from documents using advanced NER (spaCy/LLM) or regex fallback

        Returns:
            List of entities: [{"name": str, "type": str, "doc_ids": [str], "confidence": float}]
        """
        entities_map: Dict[str, Dict[str, Any]] = {}

        # Use advanced NER if available
        if self.use_advanced_ner and self.ner_service:
            for doc in docs:
                text = doc.get("title", "") + " " + doc.get("snippet", "")
                doc_id = doc.get("article_id", "")

                try:
                    # Extract entities using NER service
                    entities = await self.ner_service.extract_entities(text, lang=lang)

                    for entity in entities:
                        normalized = entity.text.strip()

                        if normalized not in entities_map:
                            entities_map[normalized] = {
                                "name": normalized,
                                "type": entity.label.lower(),
                                "doc_ids": set(),
                                "confidence": entity.confidence
                            }

                        entities_map[normalized]["doc_ids"].add(doc_id)

                except Exception as e:
                    logger.warning(f"NER failed for doc {doc_id}: {e}, falling back to regex")
                    # Fallback to regex for this document
                    self._extract_entities_regex(text, doc_id, entities_map)

        else:
            # Use simple regex NER (fallback)
            for doc in docs:
                text = doc.get("title", "") + " " + doc.get("snippet", "")
                doc_id = doc.get("article_id", "")
                self._extract_entities_regex(text, doc_id, entities_map)

        # Convert to list and sort by frequency
        entities = []
        for ent_data in entities_map.values():
            ent_data["doc_ids"] = list(ent_data["doc_ids"])
            ent_data["frequency"] = len(ent_data["doc_ids"])
            entities.append(ent_data)

        entities.sort(key=lambda x: x["frequency"], reverse=True)

        logger.info(
            f"Extracted {len(entities)} entities "
            f"({'spaCy/LLM' if self.use_advanced_ner else 'regex'})"
        )

        return entities[:200]  # Limit to top 200 entities

    def _extract_entities_regex(
        self,
        text: str,
        doc_id: str,
        entities_map: Dict[str, Dict[str, Any]]
    ):
        """Extract entities using regex (fallback method)"""
        tokens = re.split(r"\s+", text)
        candidate_parts: List[str] = []

        def flush_candidate() -> None:
            if not candidate_parts:
                return
            normalized = " ".join(candidate_parts).strip()
            candidate_parts.clear()
            if not normalized:
                return
            if normalized.lower() in self.ENTITY_STOPWORDS:
                return
            if not self._should_keep_candidate(normalized):
                return
            entry = entities_map.setdefault(
                normalized,
                {
                    "name": normalized,
                    "type": self._guess_entity_type(normalized),
                    "doc_ids": set(),
                    "confidence": 0.4,
                },
            )
            entry["doc_ids"].add(doc_id)

        for raw_token in tokens:
            token = raw_token.strip(" ,.;:()[]{}<>\"'\n\t")
            if self._looks_like_entity_token(token):
                candidate_parts.append(token)
            else:
                flush_candidate()

        flush_candidate()

        return None

    @staticmethod
    def _looks_like_entity_token(token: str) -> bool:
        """Heuristically decide if token is part of an entity"""
        if not token or len(token) < 2:
            return False
        lowered = token.lower()
        if lowered in {"and", "for", "with", "from", "into", "the"}:
            return False
        if any(char.isdigit() for char in token) and any(char.isalpha() for char in token):
            return True
        if token.isupper() and len(token) > 1:
            return True
        if token[0].isupper() and any(ch.isupper() for ch in token[1:]):
            return True
        if token[0].isupper() and len(token) >= 3:
            return True
        return False

    def _should_keep_candidate(self, value: str) -> bool:
        tokens = value.split()
        if not tokens:
            return False
        if len(tokens) > 1:
            return True
        token = tokens[0]
        lower = token.lower()
        if lower in self.KNOWN_ORGS:
            return True
        if any(ch.isdigit() for ch in token):
            return True
        if token.isupper() and len(token) > 1:
            return True
        if any(ch.isupper() for ch in token[1:]):
            return True
        return False

    def _guess_entity_type(self, entity_name: str) -> str:
        """Guess entity type from name (simple heuristics)"""
        # Common patterns
        name_lower = entity_name.lower()
        if name_lower in self.KNOWN_ORGS:
            return "organization"
        if any(char.isdigit() for char in entity_name):
            return "organization"
        if any(word in entity_name for word in ["Inc", "Corp", "Ltd", "LLC", "Company"]):
            return "organization"
        elif any(word in entity_name for word in ["University", "Institute", "Laboratory"]):
            return "organization"
        elif len(entity_name.split()) == 1 and entity_name[0].isupper():
            if any(ch.isupper() for ch in entity_name[1:]):
                return "organization"
            return "person"  # Single capitalized word
        elif len(entity_name.split()) >= 2:
            tokens = entity_name.split()
            if all(token and token[0].isupper() and token[1:].islower() for token in tokens):
                return "person"
            if any(word in entity_name for word in ["AI", "Tech", "Digital", "Cloud"]):
                return "organization"
            return "location"
        else:
            return "entity"

    async def _extract_relations(
        self,
        docs: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        lang: str
    ) -> List[Dict[str, Any]]:
        """
        Extract relations between entities

        Returns:
            List of relations: [{"src": str, "tgt": str, "type": str, "weight": float, "doc_ids": [str]}]
        """
        relations_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Co-occurrence based relations
        for doc in docs:
            text = (doc.get("title", "") + " " + doc.get("snippet", "")).lower()
            doc_id = doc.get("article_id", "")

            # Find which entities appear in this document
            entities_in_doc = [
                ent for ent in entities
                if ent["name"].lower() in text
            ]

            # Create co-occurrence relations (all pairs)
            for i, ent1 in enumerate(entities_in_doc):
                for ent2 in entities_in_doc[i+1:]:
                    # Create relation (alphabetically sorted to avoid duplicates)
                    src, tgt = sorted([ent1["name"], ent2["name"]])
                    key = (src, tgt)

                    if key not in relations_map:
                        relations_map[key] = {
                            "src": src,
                            "tgt": tgt,
                            "type": self._infer_relation_type(ent1, ent2, text),
                            "weight": 0.0,
                            "doc_ids": set()
                        }

                    relations_map[key]["doc_ids"].add(doc_id)

        # Calculate weights based on co-occurrence frequency
        relations = []
        for rel_data in relations_map.values():
            count = len(rel_data["doc_ids"])
            rel_data["weight"] = min(1.0, count / 5)  # Normalize to [0, 1]
            rel_data["doc_ids"] = list(rel_data["doc_ids"])
            relations.append(rel_data)

        # Sort by weight
        relations.sort(key=lambda x: x["weight"], reverse=True)

        logger.info(f"Extracted {len(relations)} relations (co-occurrence)")

        return relations

    def _infer_relation_type(
        self,
        ent1: Dict[str, Any],
        ent2: Dict[str, Any],
        context: str
    ) -> str:
        """Infer relation type from entity types and context"""
        type1 = ent1["type"]
        type2 = ent2["type"]

        # Simple heuristics
        if "invest" in context or "fund" in context or "acqui" in context:
            return "influences"
        elif "partner" in context or "collaborat" in context:
            return "relates_to"
        elif "mention" in context or "discuss" in context or "said" in context:
            return "mentions"
        else:
            return "relates_to"

    def _construct_graph(
        self,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
        docs: List[Dict[str, Any]],
        max_nodes: int,
        max_edges: int
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Construct final graph structure from entities and relations

        Returns:
            Tuple of (nodes, edges)
        """
        # Create entity nodes (limit to max_nodes - num_docs)
        doc_count = min(len(docs), 20)  # Include top 20 docs as nodes
        entity_limit = max(0, max_nodes - doc_count)

        nodes = []
        entity_names = set()

        # Add entity nodes
        for ent in entities[:entity_limit]:
            nodes.append({
                "id": f"ent_{len(nodes)}",
                "label": ent["name"],
                "type": "entity",
                "entity_type": ent["type"],
                "frequency": ent.get("frequency", 1)
            })
            entity_names.add(ent["name"])

        # Add document nodes
        for idx, doc in enumerate(docs[:doc_count]):
            nodes.append({
                "id": doc.get("article_id", f"doc_{idx}"),
                "label": doc.get("title", "Document")[:120],
                "type": "article",
                "date": doc.get("date"),
                "url": doc.get("url")
            })

        logger.info(f"Created {len(nodes)} nodes ({len(entity_names)} entities, {doc_count} docs)")

        # Create edges
        edges = []

        # 1. Entity-entity edges (from relations)
        for rel in relations[:max_edges]:
            # Check if both entities are in nodes
            if rel["src"] in entity_names and rel["tgt"] in entity_names:
                # Find node IDs
                src_id = next((n["id"] for n in nodes if n.get("label") == rel["src"]), None)
                tgt_id = next((n["id"] for n in nodes if n.get("label") == rel["tgt"]), None)

                if src_id and tgt_id:
                    edges.append({
                        "src": src_id,
                        "tgt": tgt_id,
                        "type": rel["type"],
                        "weight": round(rel["weight"], 2)
                    })

        # 2. Entity-document edges (mentions)
        for ent in entities[:entity_limit]:
            ent_node_id = next((n["id"] for n in nodes if n.get("label") == ent["name"]), None)
            if not ent_node_id:
                continue

            for doc_id in ent.get("doc_ids", [])[:3]:  # Max 3 docs per entity
                if any(n["id"] == doc_id for n in nodes):
                    edges.append({
                        "src": ent_node_id,
                        "tgt": doc_id,
                        "type": "mentions",
                        "weight": 0.8
                    })

                    if len(edges) >= max_edges:
                        break

            if len(edges) >= max_edges:
                break

        logger.info(f"Created {len(edges)} edges (limit={max_edges})")

        return nodes, edges[:max_edges]


def create_graph_builder(model_router: Optional[ModelRouter] = None) -> GraphBuilder:
    """Factory function to create graph builder"""
    return GraphBuilder(model_router=model_router)
