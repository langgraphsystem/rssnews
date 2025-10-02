"""
Unit tests for TrendForecaster agent (Phase 2)
Tests EWMA computation, direction determination, forecast building
"""

import pytest
from datetime import datetime, timedelta
from core.agents.trend_forecaster import (
    compute_ewma,
    determine_direction,
    estimate_confidence_interval,
    run_trend_forecaster,
)


class TestEWMAComputation:
    """Test EWMA computation logic"""

    def test_ewma_rising_trend(self):
        """Test EWMA with rising trend (increasing doc counts over time)"""
        # Simulate increasing article counts: [1, 2, 3, 4, 5]
        dates = [
            datetime(2025, 1, 1),
            datetime(2025, 1, 2),
            datetime(2025, 1, 2),
            datetime(2025, 1, 3),
            datetime(2025, 1, 3),
            datetime(2025, 1, 3),
            datetime(2025, 1, 4),
            datetime(2025, 1, 4),
            datetime(2025, 1, 4),
            datetime(2025, 1, 4),
        ]
        ewma_value, slope = compute_ewma(dates, alpha=0.3, periods=7)
        assert ewma_value > 0
        assert slope > 0  # Rising trend

    def test_ewma_falling_trend(self):
        """Test EWMA with falling trend (decreasing doc counts over time)"""
        # Simulate decreasing article counts: [5, 4, 3, 2, 1]
        dates = [
            datetime(2025, 1, 1),
            datetime(2025, 1, 1),
            datetime(2025, 1, 1),
            datetime(2025, 1, 1),
            datetime(2025, 1, 1),
            datetime(2025, 1, 2),
            datetime(2025, 1, 2),
            datetime(2025, 1, 2),
            datetime(2025, 1, 3),
            datetime(2025, 1, 3),
            datetime(2025, 1, 4),
        ]
        ewma_value, slope = compute_ewma(dates, alpha=0.3, periods=7)
        assert ewma_value >= 0
        assert slope < 0  # Falling trend

    def test_ewma_flat_trend(self):
        """Test EWMA with flat trend (constant doc counts)"""
        dates = [datetime(2025, 1, 1) for _ in range(10)]
        ewma_value, slope = compute_ewma(dates, alpha=0.3, periods=7)
        assert ewma_value >= 0
        assert abs(slope) < 0.1  # Flat trend


class TestDirectionDetermination:
    """Test direction classification logic"""

    def test_direction_up(self):
        """Test direction classification for upward trend"""
        assert determine_direction(0.5, threshold=0.1) == "up"

    def test_direction_down(self):
        """Test direction classification for downward trend"""
        assert determine_direction(-0.5, threshold=0.1) == "down"

    def test_direction_flat(self):
        """Test direction classification for flat trend"""
        assert determine_direction(0.05, threshold=0.1) == "flat"
        assert determine_direction(-0.05, threshold=0.1) == "flat"


class TestConfidenceInterval:
    """Test confidence interval estimation"""

    def test_confidence_interval_strong_signal(self):
        """Test CI with strong slope and many docs"""
        lower, upper = estimate_confidence_interval(slope=0.8, ewma_value=5.0, n_docs=50)
        assert 0.0 <= lower <= 1.0
        assert 0.0 <= upper <= 1.0
        assert lower < upper
        assert upper - lower < 0.5  # Narrow interval for strong signal

    def test_confidence_interval_weak_signal(self):
        """Test CI with weak slope and few docs"""
        lower, upper = estimate_confidence_interval(slope=0.1, ewma_value=2.0, n_docs=5)
        assert 0.0 <= lower <= 1.0
        assert 0.0 <= upper <= 1.0
        assert lower < upper
        assert upper - lower > 0.3  # Wide interval for weak signal


@pytest.mark.asyncio
class TestRunTrendForecaster:
    """Integration tests for run_trend_forecaster"""

    async def test_forecast_rising_trend(self):
        """Test forecast generation for rising trend"""
        docs = [
            {
                "article_id": f"art-{i}",
                "title": f"Article {i}",
                "url": f"https://example.com/article-{i}",
                "date": (datetime(2025, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d"),
                "content": "AI trends are rising",
            }
            for i in range(10)
        ]
        result = await run_trend_forecaster(docs, topic="AI", window="1w", correlation_id="test-corr-1")

        assert result["success"] is True
        assert "forecast" in result
        forecast_items = result["forecast"]
        assert len(forecast_items) >= 1

        item = forecast_items[0]
        assert item["topic"] == "AI"
        assert item["direction"] in ["up", "down", "flat"]
        assert "confidence_interval" in item
        assert len(item["confidence_interval"]) == 2
        assert "drivers" in item
        assert len(item["drivers"]) >= 1

    async def test_forecast_no_topic(self):
        """Test forecast generation without topic (general)"""
        docs = [
            {
                "article_id": f"art-{i}",
                "title": f"Article {i}",
                "url": f"https://example.com/article-{i}",
                "date": (datetime(2025, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d"),
                "content": "General news content",
            }
            for i in range(10)
        ]
        result = await run_trend_forecaster(docs, topic=None, window="1w", correlation_id="test-corr-2")

        assert result["success"] is True
        assert result["forecast"][0]["topic"] == "general"

    async def test_forecast_insufficient_data(self):
        """Test forecast with too few docs"""
        docs = [
            {
                "article_id": "art-1",
                "title": "Article 1",
                "url": "https://example.com/article-1",
                "date": "2025-01-01",
                "content": "Single article",
            }
        ]
        result = await run_trend_forecaster(docs, topic="AI", window="1w", correlation_id="test-corr-3")

        # Should return flat trend with low confidence
        assert result["success"] is True
        assert result["forecast"][0]["direction"] == "flat"
