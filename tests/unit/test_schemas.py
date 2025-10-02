"""
Unit tests for schemas/analysis_schemas.py
Tests Pydantic validation, length limits, evidence requirements
"""

import pytest
from datetime import datetime
from schemas.analysis_schemas import (
    BaseAnalysisResponse,
    Insight,
    Evidence,
    EvidenceRef,
    Meta,
    PolicyValidator,
    KeyphraseMiningResult,
    SentimentEmotionResult,
    TopicModelerResult,
    build_base_response,
    build_error_response
)


class TestEvidenceRef:
    """Test EvidenceRef model"""

    def test_valid_evidence_ref(self):
        """Test valid evidence reference"""
        ref = EvidenceRef(
            article_id="art_123",
            url="https://example.com/article",
            date="2025-09-30"
        )
        assert ref.article_id == "art_123"
        assert ref.date == "2025-09-30"

    def test_date_format_validation(self):
        """Test date format must be YYYY-MM-DD"""
        with pytest.raises(ValueError):
            EvidenceRef(
                article_id="art_123",
                url="https://example.com",
                date="30-09-2025"  # Invalid format
            )

    def test_url_validation(self):
        """Test URL must start with http:// or https://"""
        with pytest.raises(ValueError):
            EvidenceRef(
                article_id="art_123",
                url="ftp://example.com",  # Invalid protocol
                date="2025-09-30"
            )


class TestInsight:
    """Test Insight model"""

    def test_valid_insight(self):
        """Test valid insight with evidence"""
        insight = Insight(
            type="fact",
            text="Test insight",
            evidence_refs=[
                EvidenceRef(
                    article_id="art_123",
                    url="https://example.com",
                    date="2025-09-30"
                )
            ]
        )
        assert insight.type == "fact"
        assert len(insight.evidence_refs) == 1

    def test_text_length_limit(self):
        """Test insight text must be ≤ 180 chars"""
        from pydantic import ValidationError as PydanticValidationError
        long_text = "x" * 181
        with pytest.raises(PydanticValidationError, match="at most 180"):
            Insight(
                type="fact",
                text=long_text,
                evidence_refs=[
                    EvidenceRef(article_id="art_1", url="https://example.com", date="2025-09-30")
                ]
            )

    def test_evidence_required(self):
        """Test insight must have at least 1 evidence_ref"""
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises(PydanticValidationError, match="at least 1"):
            Insight(
                type="fact",
                text="Test insight",
                evidence_refs=[]  # Empty list
            )

    def test_invalid_insight_type(self):
        """Test insight type must be fact|hypothesis|recommendation|conflict"""
        with pytest.raises(ValueError):
            Insight(
                type="invalid_type",
                text="Test",
                evidence_refs=[
                    EvidenceRef(article_id="art_1", url="https://example.com", date="2025-09-30")
                ]
            )


class TestEvidence:
    """Test Evidence model"""

    def test_valid_evidence(self):
        """Test valid evidence"""
        evidence = Evidence(
            title="Test Article",
            article_id="art_123",
            url="https://example.com/article",
            date="2025-09-30",
            snippet="This is a test snippet."
        )
        assert evidence.title == "Test Article"

    def test_snippet_length_limit(self):
        """Test snippet must be ≤ 240 chars"""
        from pydantic import ValidationError as PydanticValidationError
        long_snippet = "x" * 241
        with pytest.raises(PydanticValidationError, match="at most 240"):
            Evidence(
                title="Test",
                article_id="art_1",
                url="https://example.com",
                date="2025-09-30",
                snippet=long_snippet
            )

    def test_title_length_limit(self):
        """Test title must be ≤ 200 chars"""
        long_title = "x" * 201
        with pytest.raises(ValueError):
            Evidence(
                title=long_title,
                article_id="art_1",
                url="https://example.com",
                date="2025-09-30",
                snippet="Test snippet"
            )


class TestBaseAnalysisResponse:
    """Test BaseAnalysisResponse model"""

    def test_valid_response(self):
        """Test valid base response"""
        response = BaseAnalysisResponse(
            header="Test Header",
            tldr="Short summary" * 10,  # ~140 chars
            insights=[
                Insight(
                    type="fact",
                    text="Test insight",
                    evidence_refs=[
                        EvidenceRef(article_id="art_1", url="https://example.com", date="2025-09-30")
                    ]
                )
            ],
            evidence=[
                Evidence(
                    title="Test Article",
                    article_id="art_1",
                    url="https://example.com",
                    date="2025-09-30",
                    snippet="Test snippet"
                )
            ],
            result={"test": "data"},
            meta=Meta(
                confidence=0.85,
                model="gpt-5",
                version="phase1-v1.0",
                correlation_id="test-123"
            )
        )
        assert response.header == "Test Header"
        assert len(response.insights) == 1

    def test_tldr_length_limit(self):
        """Test TL;DR must be ≤ 220 chars"""
        from pydantic import ValidationError as PydanticValidationError
        long_tldr = "x" * 221
        with pytest.raises(PydanticValidationError, match="at most 220"):
            BaseAnalysisResponse(
                header="Test",
                tldr=long_tldr,
                insights=[
                    Insight(
                        type="fact",
                        text="Test",
                        evidence_refs=[
                            EvidenceRef(article_id="art_1", url="https://example.com", date="2025-09-30")
                        ]
                    )
                ],
                evidence=[
                    Evidence(
                        title="Test",
                        article_id="art_1",
                        url="https://example.com",
                        date="2025-09-30",
                        snippet="Test"
                    )
                ],
                result={},
                meta=Meta(confidence=0.8, model="gpt-5", version="v1", correlation_id="123")
            )

    def test_min_insights_required(self):
        """Test at least 1 insight required"""
        with pytest.raises(ValueError):
            BaseAnalysisResponse(
                header="Test",
                tldr="Test summary",
                insights=[],  # Empty
                evidence=[
                    Evidence(
                        title="Test",
                        article_id="art_1",
                        url="https://example.com",
                        date="2025-09-30",
                        snippet="Test"
                    )
                ],
                result={},
                meta=Meta(confidence=0.8, model="gpt-5", version="v1", correlation_id="123")
            )

    def test_confidence_range(self):
        """Test confidence must be 0.0-1.0"""
        with pytest.raises(ValueError):
            Meta(
                confidence=1.5,  # Out of range
                model="gpt-5",
                version="v1",
                correlation_id="123"
            )


class TestPolicyValidator:
    """Test PolicyValidator static methods"""

    def test_pii_detection_email(self):
        """Test PII detection for email"""
        text = "Contact me at user@example.com"
        assert PolicyValidator.contains_pii(text) is True

    def test_pii_detection_phone(self):
        """Test PII detection for phone"""
        text = "Call me at +1-555-123-4567"
        assert PolicyValidator.contains_pii(text) is True

    def test_pii_detection_ssn(self):
        """Test PII detection for SSN"""
        text = "My SSN is 123-45-6789"
        assert PolicyValidator.contains_pii(text) is True

    def test_pii_detection_credit_card(self):
        """Test PII detection for credit card"""
        text = "Card number: 1234567890123456"
        assert PolicyValidator.contains_pii(text) is True

    def test_no_pii_in_clean_text(self):
        """Test no PII in clean text"""
        text = "This is a normal article about technology and innovation."
        assert PolicyValidator.contains_pii(text) is False

    def test_domain_blacklist(self):
        """Test blacklisted domain detection"""
        assert PolicyValidator.is_safe_domain("https://spam.com/article") is False
        assert PolicyValidator.is_safe_domain("https://example.com/article") is True

    def test_domain_whitelist_none(self):
        """Test None URL is safe"""
        assert PolicyValidator.is_safe_domain(None) is True


class TestResultSchemas:
    """Test agent-specific result schemas"""

    def test_keyphrase_mining_result(self):
        """Test KeyphraseMiningResult"""
        result = KeyphraseMiningResult(
            keyphrases=[
                {
                    "phrase": "artificial intelligence",
                    "norm": "artificial intelligence",
                    "score": 0.95,
                    "ngram": 2,
                    "variants": ["AI", "A.I."],
                    "examples": ["AI is transforming industries"],
                    "lang": "en"
                }
            ]
        )
        assert len(result.keyphrases) == 1

    def test_sentiment_emotion_result(self):
        """Test SentimentEmotionResult"""
        result = SentimentEmotionResult(
            overall=0.3,
            emotions={
                "joy": 0.2,
                "fear": 0.4,
                "anger": 0.3,
                "sadness": 0.1,
                "surprise": 0.0
            }
        )
        assert result.overall == 0.3
        assert result.emotions.joy == 0.2

    def test_sentiment_score_range(self):
        """Test sentiment score must be -1.0 to +1.0"""
        with pytest.raises(ValueError):
            SentimentEmotionResult(
                overall=2.0,  # Out of range
                emotions={
                    "joy": 0.2,
                    "fear": 0.4,
                    "anger": 0.3,
                    "sadness": 0.1,
                    "surprise": 0.0
                }
            )

    def test_topic_modeler_result(self):
        """Test TopicModelerResult"""
        result = TopicModelerResult(
            topics=[
                {
                    "label": "AI Regulation",
                    "terms": ["regulation", "policy", "governance"],
                    "size": 10,
                    "trend": "rising"
                }
            ]
        )
        assert len(result.topics) == 1
        assert result.topics[0].trend == "rising"


class TestBuilders:
    """Test convenience builders"""

    def test_build_base_response(self):
        """Test build_base_response helper"""
        response = build_base_response(
            header="Test Header",
            tldr="Test summary",
            insights=[
                Insight(
                    type="fact",
                    text="Test insight",
                    evidence_refs=[
                        EvidenceRef(article_id="art_1", url="https://example.com", date="2025-09-30")
                    ]
                )
            ],
            evidence=[
                Evidence(
                    title="Test Article",
                    article_id="art_1",
                    url="https://example.com",
                    date="2025-09-30",
                    snippet="Test snippet"
                )
            ],
            result={"test": "data"},
            meta=Meta(confidence=0.8, model="gpt-5", version="v1", correlation_id="123")
        )
        assert isinstance(response, BaseAnalysisResponse)

    def test_build_error_response(self):
        """Test build_error_response helper"""
        error = build_error_response(
            code="NO_DATA",
            user_message="No articles found",
            tech_message="Retrieval returned 0 documents",
            retryable=True,
            meta=Meta(confidence=0.0, model="unknown", version="v1", correlation_id="123")
        )
        assert error.error.code == "NO_DATA"
        assert error.error.retryable is True