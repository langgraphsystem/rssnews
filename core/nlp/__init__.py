"""NLP utilities for entity extraction and text processing"""

from core.nlp.ner_service import (
    NERService,
    NERStrategy,
    Entity,
    create_ner_service,
    extract_entities_auto
)

__all__ = [
    "NERService",
    "NERStrategy",
    "Entity",
    "create_ner_service",
    "extract_entities_auto"
]
