"""
NER Service — Multi-strategy Named Entity Recognition.
Supports spaCy, LLM-based, and fallback regex extraction.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class NERStrategy(Enum):
    """NER extraction strategies"""
    SPACY = "spacy"
    LLM = "llm"
    REGEX = "regex"


class Entity:
    """Extracted entity"""
    def __init__(self, text: str, label: str, start: int, end: int, confidence: float = 1.0):
        self.text = text
        self.label = label
        self.start = start
        self.end = end
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence
        }


class NERService:
    """
    Multi-strategy NER service with automatic fallback.
    Tries: spaCy → LLM → regex (in order)
    """

    ENTITY_STOPWORDS = {"the", "this", "that", "there", "these", "those", "a", "an", "and", "for", "with", "from", "into", "of", "in"}
    KNOWN_ORGS = {"openai", "google", "microsoft", "amazon", "apple", "ibm", "meta"}

    def __init__(self, model_router=None, prefer_strategy: NERStrategy = NERStrategy.SPACY):
        """
        Initialize NER service

        Args:
            model_router: Optional ModelRouter for LLM-based NER
            prefer_strategy: Preferred extraction strategy
        """
        self.model_router = model_router
        self.prefer_strategy = prefer_strategy
        self._spacy_nlp = None
        self._spacy_available = False

        # Try to load spaCy
        self._init_spacy()

    def _init_spacy(self):
        """Initialize spaCy model"""
        try:
            import spacy
            # Try to load English model
            try:
                self._spacy_nlp = spacy.load("en_core_web_sm")
                self._spacy_available = True
                logger.info("spaCy model loaded successfully: en_core_web_sm")
            except OSError:
                # Model not installed
                logger.warning(
                    "spaCy model 'en_core_web_sm' not found. "
                    "Install with: python -m spacy download en_core_web_sm"
                )
                self._spacy_available = False
        except ImportError:
            logger.warning("spaCy not installed. Install with: pip install spacy")
            self._spacy_available = False

    async def extract_entities(
        self,
        text: str,
        lang: str = "en",
        strategy: Optional[NERStrategy] = None
    ) -> List[Entity]:
        """
        Extract named entities from text

        Args:
            text: Input text
            lang: Language code
            strategy: Force specific strategy (otherwise uses prefer_strategy)

        Returns:
            List of Entity objects
        """
        strategy = strategy or self.prefer_strategy

        # Try strategies in order
        if strategy == NERStrategy.SPACY and self._spacy_available:
            try:
                return self._extract_spacy(text, lang)
            except Exception as e:
                logger.warning(f"spaCy extraction failed: {e}, falling back to LLM")
                strategy = NERStrategy.LLM

        if strategy == NERStrategy.LLM and self.model_router:
            try:
                return await self._extract_llm(text, lang)
            except Exception as e:
                logger.warning(f"LLM extraction failed: {e}, falling back to regex")
                strategy = NERStrategy.REGEX

        # Final fallback: regex
        return self._extract_regex(text)

    def _extract_spacy(self, text: str, lang: str) -> List[Entity]:
        """Extract entities using spaCy"""
        if not self._spacy_available:
            raise RuntimeError("spaCy not available")

        doc = self._spacy_nlp(text)
        entities = []

        for ent in doc.ents:
            # Map spaCy labels to our standard labels
            label = self._normalize_label(ent.label_)

            entities.append(
                Entity(
                    text=ent.text,
                    label=label,
                    start=ent.start_char,
                    end=ent.end_char,
                    confidence=1.0
                )
            )

        logger.info(f"spaCy extracted {len(entities)} entities")
        return entities

    async def _extract_llm(self, text: str, lang: str) -> List[Entity]:
        """Extract entities using LLM"""
        if not self.model_router:
            raise RuntimeError("ModelRouter not available for LLM extraction")

        # Build prompt
        if lang == "ru":
            prompt = f"""Извлеки именованные сущности из текста.

Текст: {text[:500]}

Верни JSON список сущностей:
[
  {{"text": "название", "label": "PERSON|ORG|LOCATION|PRODUCT|EVENT|OTHER", "start": 0, "end": 10}}
]

Только JSON, без пояснений."""
        else:
            prompt = f"""Extract named entities from text.

Text: {text[:500]}

Return JSON list of entities:
[
  {{"text": "name", "label": "PERSON|ORG|LOCATION|PRODUCT|EVENT|OTHER", "start": 0, "end": 10}}
]

JSON only, no explanation."""

        try:
            response, metadata = await self.model_router.call_with_fallback(
                prompt=prompt,
                docs=[],
                primary="gpt-5",
                fallback=["claude-4.5"],
                timeout_s=10,
                max_tokens=500,
                temperature=0.3
            )

            # Parse JSON response
            import json
            content = response["content"]

            # Extract JSON from response (handle markdown code blocks)
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()

            entities_data = json.loads(json_str)

            entities = []
            for ent_data in entities_data:
                entities.append(
                    Entity(
                        text=ent_data["text"],
                        label=self._normalize_label(ent_data["label"]),
                        start=ent_data.get("start", 0),
                        end=ent_data.get("end", 0),
                        confidence=0.8  # LLM-based has slightly lower confidence
                    )
                )

            logger.info(f"LLM extracted {len(entities)} entities")
            return entities

        except Exception as e:
            logger.error(f"LLM entity extraction failed: {e}")
            raise

    def _extract_regex(self, text: str) -> List[Entity]:
        """Extract entities using regex (fallback)"""
        entities: List[Entity] = []
        token_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*")
        candidates: List[Tuple[str, re.Match]] = []

        def flush_candidate() -> None:
            if not candidates:
                return
            tokens = [tok for tok, _ in candidates]
            entity_text = " ".join(tokens)
            lower = entity_text.lower()
            if lower in self.ENTITY_STOPWORDS:
                candidates.clear()
                return
            if not self._should_keep_candidate(tokens):
                candidates.clear()
                return

            label = self._guess_entity_type_regex(entity_text)
            start = candidates[0][1].start()
            end = candidates[-1][1].end()

            entities.append(
                Entity(
                    text=entity_text,
                    label=label,
                    start=start,
                    end=end,
                    confidence=0.5,
                )
            )
            candidates.clear()

        for match in token_pattern.finditer(text):
            token = match.group()
            if self._looks_like_entity_token(token):
                candidates.append((token, match))
            else:
                flush_candidate()

        flush_candidate()

        logger.info(f"Regex extracted {len(entities)} entities")
        return entities

    @staticmethod
    def _looks_like_entity_token(token: str) -> bool:
        if not token or len(token) < 2:
            return False
        lowered = token.lower()
        if lowered in {"and", "for", "with", "from", "into", "the", "of", "in"}:
            return False
        if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
            return True
        if token.isupper() and len(token) > 1:
            return True
        if token[0].isupper() and any(ch.isupper() for ch in token[1:]):
            return True
        if token[0].isupper() and len(token) >= 3:
            return True
        return False

    def _should_keep_candidate(self, tokens: List[str]) -> bool:
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

    def _normalize_label(self, label: str) -> str:
        """Normalize entity labels to standard set"""
        label_upper = label.upper()

        # Map spaCy/LLM labels to standard
        mapping = {
            "PERSON": "PERSON",
            "PER": "PERSON",
            "ORG": "ORGANIZATION",
            "ORGANIZATION": "ORGANIZATION",
            "GPE": "LOCATION",
            "LOC": "LOCATION",
            "LOCATION": "LOCATION",
            "PRODUCT": "PRODUCT",
            "EVENT": "EVENT",
            "DATE": "DATE",
            "TIME": "TIME",
            "MONEY": "MONEY",
            "PERCENT": "PERCENT",
        }

        return mapping.get(label_upper, "OTHER")

    def _guess_entity_type_regex(self, text: str) -> str:
        """Guess entity type from text (simple heuristics)"""
        # Organization indicators
        if any(word in text for word in ["Inc", "Corp", "Ltd", "LLC", "Company", "AI", "Tech"]):
            return "ORGANIZATION"

        # Location indicators
        if any(word in text for word in ["University", "Institute", "Laboratory", "Center"]):
            return "ORGANIZATION"

        # Single capitalized word likely a person or place
        if len(text.split()) == 1:
            lower = text.lower()
            if lower in self.KNOWN_ORGS:
                return "ORGANIZATION"
            if any(ch.isupper() for ch in text[1:]) or text.isupper():
                return "ORGANIZATION"
            return "PERSON"

        # Multi-word: likely organization or location
        if len(text.split()) >= 2:
            return "ORGANIZATION"

        return "OTHER"

    def get_available_strategies(self) -> List[NERStrategy]:
        """Get list of available strategies"""
        available = [NERStrategy.REGEX]  # Always available

        if self._spacy_available:
            available.insert(0, NERStrategy.SPACY)

        if self.model_router:
            available.insert(1, NERStrategy.LLM)

        return available


def create_ner_service(model_router=None, prefer_strategy: NERStrategy = NERStrategy.SPACY) -> NERService:
    """Factory function to create NER service"""
    return NERService(model_router=model_router, prefer_strategy=prefer_strategy)


# Convenience functions for backward compatibility
async def extract_entities_auto(
    text: str,
    lang: str = "en",
    model_router=None
) -> List[Dict[str, Any]]:
    """
    Auto-extract entities with best available strategy

    Args:
        text: Input text
        lang: Language code
        model_router: Optional ModelRouter for LLM fallback

    Returns:
        List of entity dicts
    """
    service = create_ner_service(model_router=model_router)
    entities = await service.extract_entities(text, lang=lang)
    return [ent.to_dict() for ent in entities]
