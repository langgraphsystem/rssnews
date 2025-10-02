"""
Unit tests for core/policies/validators.py
Tests Policy Layer v1 validation rules
"""

import pytest
from core.policies.validators import PolicyValidator, ValidationError
from schemas.analysis_schemas import (
    BaseAnalysisResponse,
    Insight,
    Evidence,
    EvidenceRef,
    Meta
)


class TestPolicyValidator:
    """Test PolicyValidator class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.validator = PolicyValidator()

    def test_valid_response_passes(self):
        """Test valid response passes all validations"""
        response = BaseAnalysisResponse(
            header="Test Header",
            tldr="This is a valid summary that is under 220 characters.",
            insights=[
                Insight(
                    type="fact",
                    text="Valid insight with evidence",
                    evidence_refs=[
                        EvidenceRef(
                            article_id="art_123",
                            url="https://example.com/article",
                            date="2025-09-30"
                        )
                    ]
                )
            ],
            evidence=[
                Evidence(
                    title="Test Article",
                    article_id="art_123",
                    url="https://example.com/article",
                    date="2025-09-30",
                    snippet="This is a valid snippet under 240 characters."
                )
            ],
            result={"test": "data"},
            meta=Meta(
                confidence=0.85,
                model="gpt-5",
                version="phase1-v1.0",
                correlation_id="test-correlation-id"
            ),
            warnings=[]
        )

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is True
        assert error is None

    def test_header_length_validation(self):
        """Test header length must be ≤ 100"""
        response = self._build_test_response()
        response.header = "x" * 101

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "header too long" in error.lower()

    def test_tldr_length_validation(self):
        """Test TL;DR length must be ≤ 220"""
        response = self._build_test_response()
        response.tldr = "x" * 221

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "too long" in error.lower()

    def test_insight_text_length_validation(self):
        """Test insight text length must be ≤ 180"""
        response = self._build_test_response()
        response.insights[0].text = "x" * 181

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "too long" in error.lower()

    def test_snippet_length_validation(self):
        """Test evidence snippet length must be ≤ 240"""
        response = self._build_test_response()
        response.evidence[0].snippet = "x" * 241

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "too long" in error.lower()

    def test_evidence_required_validation(self):
        """Test every insight must have ≥1 evidence_ref"""
        response = self._build_test_response()
        response.insights[0].evidence_refs = []

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "evidence" in error.lower()

    def test_date_format_validation(self):
        """Test date must be in YYYY-MM-DD format"""
        response = self._build_test_response()
        response.insights[0].evidence_refs[0].date = "30-09-2025"  # Wrong format

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "date" in error.lower()

    def test_pii_detection_in_tldr(self):
        """Test PII detection in TL;DR"""
        response = self._build_test_response()
        response.tldr = "Contact me at user@example.com for more info."

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "sensitive" in error.lower()

    def test_pii_detection_in_insight(self):
        """Test PII detection in insight text"""
        response = self._build_test_response()
        response.insights[0].text = "Call +1-555-123-4567 for details"

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "sensitive" in error.lower()

    def test_pii_detection_in_snippet(self):
        """Test PII detection in evidence snippet"""
        response = self._build_test_response()
        response.evidence[0].snippet = "SSN: 123-45-6789"

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "sensitive" in error.lower()

    def test_domain_blacklist_validation(self):
        """Test blacklisted domain rejection"""
        response = self._build_test_response()
        response.evidence[0].url = "https://spam.com/article"

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "untrusted" in error.lower()

    def test_invalid_url_format(self):
        """Test URL must start with http:// or https://"""
        response = self._build_test_response()
        response.evidence[0].url = "ftp://example.com/article"

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "url" in error.lower()

    def test_missing_header(self):
        """Test header is required"""
        response = self._build_test_response()
        response.header = ""

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "header" in error.lower()

    def test_missing_tldr(self):
        """Test TL;DR is required"""
        response = self._build_test_response()
        response.tldr = ""

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "summary" in error.lower()

    def test_missing_model_info(self):
        """Test model information is required"""
        response = self._build_test_response()
        response.meta.model = ""

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "model" in error.lower()

    def test_missing_correlation_id(self):
        """Test correlation ID is required"""
        response = self._build_test_response()
        response.meta.correlation_id = ""

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "correlation" in error.lower()

    def test_result_schema_keyphrase_valid(self):
        """Test valid keyphrase result schema"""
        result = {
            "keyphrases": [
                {
                    "phrase": "test",
                    "norm": "test",
                    "score": 0.9,
                    "ngram": 1,
                    "variants": [],
                    "examples": [],
                    "lang": "en"
                }
            ]
        }

        is_valid, error = self.validator.validate_result_schema(result, "keyphrases")
        assert is_valid is True
        assert error is None

    def test_result_schema_keyphrase_missing_field(self):
        """Test keyphrase result with missing field"""
        result = {}  # Missing keyphrases

        is_valid, error = self.validator.validate_result_schema(result, "keyphrases")
        assert is_valid is False
        assert "keyphrases" in error.lower()

    def test_result_schema_sentiment_valid(self):
        """Test valid sentiment result schema"""
        result = {
            "overall": 0.5,
            "emotions": {
                "joy": 0.2,
                "fear": 0.3,
                "anger": 0.2,
                "sadness": 0.2,
                "surprise": 0.1
            }
        }

        is_valid, error = self.validator.validate_result_schema(result, "sentiment")
        assert is_valid is True
        assert error is None

    def test_result_schema_sentiment_out_of_range(self):
        """Test sentiment with out-of-range score"""
        result = {
            "overall": 2.0,  # Out of range
            "emotions": {}
        }

        is_valid, error = self.validator.validate_result_schema(result, "sentiment")
        assert is_valid is False

    def test_result_schema_topics_valid(self):
        """Test valid topics result schema"""
        result = {
            "topics": [
                {
                    "label": "Test Topic",
                    "terms": ["term1", "term2"],
                    "size": 5,
                    "trend": "rising"
                }
            ]
        }

        is_valid, error = self.validator.validate_result_schema(result, "topics")
        assert is_valid is True
        assert error is None

    def test_min_insights_required(self):
        """Test at least 1 insight is required"""
        response = self._build_test_response()
        response.insights = []

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "insight" in error.lower()

    def test_max_insights_limit(self):
        """Test max 5 insights allowed"""
        response = self._build_test_response()
        # Add 5 more insights (total 6)
        for i in range(5):
            response.insights.append(
                Insight(
                    type="fact",
                    text=f"Insight {i}",
                    evidence_refs=[
                        EvidenceRef(
                            article_id=f"art_{i}",
                            url="https://example.com",
                            date="2025-09-30"
                        )
                    ]
                )
            )

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "many" in error.lower()

    def test_min_evidence_required(self):
        """Test at least 1 evidence item is required"""
        response = self._build_test_response()
        response.evidence = []

        is_valid, error = self.validator.validate_response(response)
        assert is_valid is False
        assert "evidence" in error.lower()

    # Helper methods

    def _build_test_response(self) -> BaseAnalysisResponse:
        """Build a valid test response"""
        return BaseAnalysisResponse(
            header="Test Header",
            tldr="This is a test summary.",
            insights=[
                Insight(
                    type="fact",
                    text="Test insight",
                    evidence_refs=[
                        EvidenceRef(
                            article_id="art_123",
                            url="https://example.com/article",
                            date="2025-09-30"
                        )
                    ]
                )
            ],
            evidence=[
                Evidence(
                    title="Test Article",
                    article_id="art_123",
                    url="https://example.com/article",
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