"""
Unit tests for Phase 2 schemas
Tests validation rules for ForecastResult, CompetitorsResult, SynthesisResult
"""

import pytest
from pydantic import ValidationError
from schemas.analysis_schemas import (
    ForecastDriver,
    ForecastItem,
    ForecastResult,
    OverlapMatrix,
    PositioningItem,
    SentimentDelta,
    CompetitorsResult,
    Conflict,
    Action,
    SynthesisResult,
    EvidenceRef,
)


class TestForecastSchemas:
    """Test forecast-related schemas"""

    def test_forecast_driver_valid(self):
        """Test valid ForecastDriver"""
        driver = ForecastDriver(
            signal="Rising mentions",
            rationale="Article count increased by 30% this week",
            evidence_ref=EvidenceRef(
                article_id="art-1",
                url="https://example.com/article",
                date="2025-01-01"
            )
        )
        assert driver.signal == "Rising mentions"
        assert len(driver.rationale) <= 200

    def test_forecast_driver_signal_too_long(self):
        """Test ForecastDriver with signal > 80 chars"""
        with pytest.raises(ValidationError):
            ForecastDriver(
                signal="A" * 81,  # Too long
                rationale="Some rationale",
                evidence_ref=EvidenceRef(url="https://example.com", date="2025-01-01")
            )

    def test_forecast_item_valid(self):
        """Test valid ForecastItem"""
        item = ForecastItem(
            topic="AI trends",
            direction="up",
            confidence_interval=(0.6, 0.8),
            drivers=[
                ForecastDriver(
                    signal="Rising mentions",
                    rationale="Mentions increased",
                    evidence_ref=EvidenceRef(url="https://example.com", date="2025-01-01")
                )
            ],
            horizon="1w"
        )
        assert item.direction == "up"
        assert item.confidence_interval[0] < item.confidence_interval[1]

    def test_forecast_item_invalid_confidence_interval(self):
        """Test ForecastItem with invalid confidence interval"""
        with pytest.raises(ValidationError):
            ForecastItem(
                topic="AI",
                direction="up",
                confidence_interval=(0.8, 0.6),  # Lower > upper
                drivers=[
                    ForecastDriver(
                        signal="Signal",
                        rationale="Rationale",
                        evidence_ref=EvidenceRef(url="https://example.com", date="2025-01-01")
                    )
                ],
                horizon="1w"
            )

    def test_forecast_result_valid(self):
        """Test valid ForecastResult"""
        result = ForecastResult(
            forecast=[
                ForecastItem(
                    topic="AI",
                    direction="up",
                    confidence_interval=(0.5, 0.7),
                    drivers=[
                        ForecastDriver(
                            signal="Signal",
                            rationale="Rationale",
                            evidence_ref=EvidenceRef(url="https://example.com", date="2025-01-01")
                        )
                    ],
                    horizon="1w"
                )
            ]
        )
        assert len(result.forecast) >= 1

    def test_forecast_result_empty_forecast(self):
        """Test ForecastResult with empty forecast list"""
        with pytest.raises(ValidationError):
            ForecastResult(forecast=[])  # min_length=1


class TestCompetitorsSchemas:
    """Test competitors-related schemas"""

    def test_overlap_matrix_valid(self):
        """Test valid OverlapMatrix"""
        overlap = OverlapMatrix(
            domain="techcrunch.com",
            topic="AI",
            overlap_score=0.75
        )
        assert 0.0 <= overlap.overlap_score <= 1.0

    def test_overlap_matrix_invalid_score(self):
        """Test OverlapMatrix with invalid score"""
        with pytest.raises(ValidationError):
            OverlapMatrix(
                domain="example.com",
                topic="AI",
                overlap_score=1.5  # > 1.0
            )

    def test_positioning_item_valid(self):
        """Test valid PositioningItem"""
        positioning = PositioningItem(
            domain="techcrunch.com",
            stance="leader",
            notes="Dominant coverage of AI topics"
        )
        assert positioning.stance in ["leader", "fast_follower", "niche"]

    def test_sentiment_delta_valid(self):
        """Test valid SentimentDelta"""
        delta = SentimentDelta(
            domain="example.com",
            delta=0.5
        )
        assert -2.0 <= delta.delta <= 2.0

    def test_competitors_result_valid(self):
        """Test valid CompetitorsResult"""
        result = CompetitorsResult(
            overlap_matrix=[
                OverlapMatrix(domain="techcrunch.com", topic="AI", overlap_score=0.8)
            ],
            gaps=["VR coverage", "Web3 news"],
            positioning=[
                PositioningItem(domain="techcrunch.com", stance="leader", notes="Strong AI coverage")
            ],
            sentiment_delta=[
                SentimentDelta(domain="techcrunch.com", delta=0.3)
            ],
            top_domains=["techcrunch.com", "wired.com"]
        )
        assert len(result.top_domains) >= 1
        assert len(result.positioning) >= 1

    def test_competitors_result_empty_positioning(self):
        """Test CompetitorsResult with empty positioning"""
        with pytest.raises(ValidationError):
            CompetitorsResult(
                overlap_matrix=[],
                positioning=[],  # min_length=1
                top_domains=["example.com"]
            )


class TestSynthesisSchemas:
    """Test synthesis-related schemas"""

    def test_conflict_valid(self):
        """Test valid Conflict"""
        conflict = Conflict(
            description="Negative sentiment but rising trend detected",
            evidence_refs=[
                EvidenceRef(url="https://example.com/1", date="2025-01-01"),
                EvidenceRef(url="https://example.com/2", date="2025-01-02")
            ]
        )
        assert len(conflict.evidence_refs) >= 2

    def test_conflict_insufficient_evidence(self):
        """Test Conflict with insufficient evidence"""
        with pytest.raises(ValidationError):
            Conflict(
                description="Some conflict",
                evidence_refs=[
                    EvidenceRef(url="https://example.com", date="2025-01-01")
                ]  # min_length=2
            )

    def test_action_valid(self):
        """Test valid Action"""
        action = Action(
            recommendation="Monitor negative sentiment trends closely",
            impact="high",
            evidence_refs=[
                EvidenceRef(url="https://example.com", date="2025-01-01")
            ]
        )
        assert action.impact in ["low", "medium", "high"]

    def test_action_missing_evidence(self):
        """Test Action with missing evidence"""
        with pytest.raises(ValidationError):
            Action(
                recommendation="Some action",
                impact="medium",
                evidence_refs=[]  # min_length=1
            )

    def test_synthesis_result_valid(self):
        """Test valid SynthesisResult"""
        result = SynthesisResult(
            summary="Analysis reveals rising AI trends with positive sentiment and no major conflicts",
            conflicts=[
                Conflict(
                    description="Minor conflict detected",
                    evidence_refs=[
                        EvidenceRef(url="https://example.com/1", date="2025-01-01"),
                        EvidenceRef(url="https://example.com/2", date="2025-01-01")
                    ]
                )
            ],
            actions=[
                Action(
                    recommendation="Continue monitoring AI developments",
                    impact="medium",
                    evidence_refs=[
                        EvidenceRef(url="https://example.com", date="2025-01-01")
                    ]
                )
            ]
        )
        assert len(result.summary) <= 400
        assert len(result.actions) >= 1

    def test_synthesis_result_summary_too_long(self):
        """Test SynthesisResult with summary > 400 chars"""
        with pytest.raises(ValidationError):
            SynthesisResult(
                summary="A" * 401,  # Too long
                conflicts=[],
                actions=[
                    Action(
                        recommendation="Action",
                        impact="low",
                        evidence_refs=[
                            EvidenceRef(url="https://example.com", date="2025-01-01")
                        ]
                    )
                ]
            )

    def test_synthesis_result_no_actions(self):
        """Test SynthesisResult with no actions"""
        with pytest.raises(ValidationError):
            SynthesisResult(
                summary="Some summary",
                conflicts=[],
                actions=[]  # min_length=1
            )


class TestPhase2MetaFields:
    """Test Phase 2 additions to Meta schema"""

    def test_meta_with_ab_test(self):
        """Test Meta with A/B test fields"""
        from schemas.analysis_schemas import Meta

        meta = Meta(
            confidence=0.85,
            model="gpt-5",
            version="phase2-v1.0",
            correlation_id="test-corr-1",
            experiment="model_routing_test",
            arm="A"
        )
        assert meta.experiment == "model_routing_test"
        assert meta.arm == "A"

    def test_meta_without_ab_test(self):
        """Test Meta without A/B test fields (backward compatible)"""
        from schemas.analysis_schemas import Meta

        meta = Meta(
            confidence=0.85,
            model="gpt-5",
            version="phase2-v1.0",
            correlation_id="test-corr-2"
        )
        assert meta.experiment is None
        assert meta.arm is None
