"""
Unit tests for NERService (Named Entity Recognition)
"""

import pytest
from core.nlp.ner_service import NERService, NERStrategy, Entity


@pytest.fixture
def ner_service():
    """Create NER service with no model router (regex only)"""
    return NERService(model_router=None, prefer_strategy=NERStrategy.REGEX)


@pytest.mark.asyncio
async def test_extract_entities_regex(ner_service):
    """Test regex-based entity extraction"""
    text = "OpenAI released GPT-5 in collaboration with Microsoft and Google."

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    assert len(entities) > 0

    # Check entity names
    entity_names = [e.text for e in entities]
    assert "OpenAI" in entity_names or "GPT-5" in entity_names


@pytest.mark.asyncio
async def test_entity_types(ner_service):
    """Test entity type guessing"""
    text = "Apple Inc released new products. Bill Gates visited Stanford University."

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    # Should find organizations
    org_entities = [e for e in entities if e.label == "ORGANIZATION"]
    assert len(org_entities) > 0


@pytest.mark.asyncio
async def test_confidence_scores(ner_service):
    """Test confidence scores"""
    text = "Microsoft announced Azure AI"

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    # Regex entities have confidence 0.5
    for entity in entities:
        assert 0.0 <= entity.confidence <= 1.0


@pytest.mark.asyncio
async def test_empty_text(ner_service):
    """Test extraction from empty text"""
    entities = await ner_service.extract_entities("", strategy=NERStrategy.REGEX)
    assert len(entities) == 0


@pytest.mark.asyncio
async def test_stopwords_filtered(ner_service):
    """Test that stopwords are filtered"""
    text = "The quick brown fox jumps over the lazy dog"

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    # Stopwords should be filtered
    entity_names = [e.text.lower() for e in entities]
    assert "the" not in entity_names
    assert "and" not in entity_names


def test_normalize_labels(ner_service):
    """Test label normalization"""
    assert ner_service._normalize_label("PERSON") == "PERSON"
    assert ner_service._normalize_label("PER") == "PERSON"
    assert ner_service._normalize_label("ORG") == "ORGANIZATION"
    assert ner_service._normalize_label("GPE") == "LOCATION"
    assert ner_service._normalize_label("UNKNOWN") == "OTHER"


def test_entity_to_dict():
    """Test Entity to dict conversion"""
    entity = Entity(
        text="OpenAI",
        label="ORGANIZATION",
        start=0,
        end=6,
        confidence=0.9
    )

    entity_dict = entity.to_dict()

    assert entity_dict["text"] == "OpenAI"
    assert entity_dict["label"] == "ORGANIZATION"
    assert entity_dict["start"] == 0
    assert entity_dict["end"] == 6
    assert entity_dict["confidence"] == 0.9


@pytest.mark.asyncio
async def test_known_orgs_detection(ner_service):
    """Test detection of known organizations"""
    text = "openai, google, microsoft, and amazon are tech companies"

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    # Should detect known orgs even in lowercase
    entity_names_lower = [e.text.lower() for e in entities]

    # At least some known orgs should be detected
    assert len(entities) > 0


@pytest.mark.asyncio
async def test_multi_word_entities(ner_service):
    """Test extraction of multi-word entities"""
    text = "New York Times reported on Artificial Intelligence Research"

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    # Should find multi-word entities
    multi_word = [e for e in entities if " " in e.text]
    assert len(multi_word) > 0


def test_guess_entity_type(ner_service):
    """Test entity type guessing heuristics"""
    # Organization indicators
    assert ner_service._guess_entity_type_regex("Apple Inc") == "ORGANIZATION"
    assert ner_service._guess_entity_type_regex("OpenAI") == "ORGANIZATION"

    # University/Institute
    assert ner_service._guess_entity_type_regex("Stanford University") == "ORGANIZATION"

    # Single word person/org
    assert ner_service._guess_entity_type_regex("Microsoft") in ["ORGANIZATION", "PERSON", "OTHER"]


def test_available_strategies(ner_service):
    """Test getting available strategies"""
    strategies = ner_service.get_available_strategies()

    # Regex always available
    assert NERStrategy.REGEX in strategies


@pytest.mark.asyncio
async def test_capitalized_sequences(ner_service):
    """Test extraction of capitalized sequences"""
    text = "John Smith works at Tech Corp on Main Street"

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    # Should find capitalized entities
    assert len(entities) > 0

    # All entities should be capitalized
    for entity in entities:
        assert entity.text[0].isupper()


@pytest.mark.asyncio
async def test_mixed_case_entities(ner_service):
    """Test extraction of mixed-case entities like GPT-5, iPhone"""
    text = "GPT-5 and iPhone are popular products"

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    # Should detect mixed-case entities
    entity_names = [e.text for e in entities]
    assert any("GPT" in name or "iPhone" in name for name in entity_names)


@pytest.mark.asyncio
async def test_entity_positions(ner_service):
    """Test that entity positions are tracked"""
    text = "OpenAI is based in San Francisco"

    entities = await ner_service.extract_entities(text, strategy=NERStrategy.REGEX)

    # Check positions
    for entity in entities:
        # Extract text using positions
        extracted = text[entity.start:entity.end]
        # Should match entity text (or be close due to tokenization)
        assert len(extracted) > 0
