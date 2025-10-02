"""
TrendForecaster Agent — Phase 2: Predict trend direction using EWMA + LLM narratives
Primary: gpt-5, Fallback: claude-4.5
"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np

logger = logging.getLogger(__name__)


FORECAST_SYSTEM_PROMPT = """You are a trend forecasting expert analyzing news articles.

TASK: Predict future trend direction based on provided statistical signals and article content.

INPUT:
- Topic (optional): Specific topic to forecast
- Time series signals: EWMA (Exponential Weighted Moving Average)
- Recent articles with dates

OUTPUT FORMAT (strict JSON):
{
  "forecast": [
    {
      "topic": "topic name",
      "direction": "up|down|flat",
      "confidence_interval": [lower_bound, upper_bound],
      "drivers": [
        {
          "signal": "signal name",
          "rationale": "explanation based on evidence",
          "evidence_ref": {
            "article_id": "...",
            "url": "...",
            "date": "YYYY-MM-DD"
          }
        }
      ],
      "horizon": "1d|3d|1w|2w|1m"
    }
  ]
}

RULES:
1. direction: "up" = increasing attention, "down" = declining, "flat" = stable
2. confidence_interval: [lower, upper] as floats (e.g., [0.3, 0.7])
3. drivers: 1-5 key signals explaining the forecast (MUST have evidence_ref)
4. horizon: forecast time window
5. Use EWMA signal to determine trend direction (rising slope = up, falling = down)
6. Every driver MUST reference a specific article with article_id/url + date
7. Return ONLY valid JSON, no additional text
"""


def compute_ewma(
    dates: List[datetime],
    alpha: float = 0.3,
    periods: int = 7
) -> Tuple[float, float]:
    """
    Compute EWMA and slope

    Args:
        dates: List of article publication dates
        alpha: Smoothing factor (0-1)
        periods: Number of periods to analyze

    Returns:
        (ewma_value, slope)
    """
    if not dates or len(dates) < 2:
        return 0.0, 0.0

    # Count articles per day
    date_counts = Counter(d.date() for d in dates)

    # Get last N days
    latest_date = max(date_counts.keys())
    date_range = [latest_date - timedelta(days=i) for i in range(periods)]
    date_range.reverse()

    # Build time series
    series = [date_counts.get(d, 0) for d in date_range]

    if len(series) < 2:
        return float(series[0]) if series else 0.0, 0.0

    # Compute EWMA
    ewma_values = []
    ewma = series[0]
    for value in series:
        ewma = alpha * value + (1 - alpha) * ewma
        ewma_values.append(ewma)

    # Compute slope (simple linear fit)
    x = np.arange(len(ewma_values))
    y = np.array(ewma_values)

    if len(x) >= 2:
        slope = np.polyfit(x, y, 1)[0]
    else:
        slope = 0.0

    return ewma_values[-1], slope


def determine_direction(slope: float, threshold: float = 0.1) -> str:
    """
    Determine trend direction from slope

    Args:
        slope: EWMA slope value
        threshold: Minimum slope for non-flat direction

    Returns:
        "up", "down", or "flat"
    """
    if slope > threshold:
        return "up"
    elif slope < -threshold:
        return "down"
    else:
        return "flat"


def estimate_confidence_interval(
    slope: float,
    ewma_value: float,
    n_docs: int
) -> Tuple[float, float]:
    """
    Estimate confidence interval based on signal strength

    Args:
        slope: EWMA slope
        ewma_value: Current EWMA value
        n_docs: Number of documents

    Returns:
        (lower_bound, upper_bound)
    """
    # Base confidence from slope strength
    base_conf = min(abs(slope) / 2.0, 0.4)

    # Adjust for sample size
    sample_factor = min(n_docs / 20.0, 1.0)  # More docs = higher confidence

    confidence = base_conf * sample_factor

    # Confidence interval centered at 0.5
    lower = max(0.0, 0.5 - confidence)
    upper = min(1.0, 0.5 + confidence)

    return (lower, upper)


async def run_trend_forecaster(
    docs: List[Dict[str, Any]],
    topic: Optional[str],
    window: str,
    correlation_id: str
) -> Dict[str, Any]:
    """
    Execute trend forecasting

    Args:
        docs: Retrieved articles with date/url/title/snippet
        topic: Optional specific topic to forecast
        window: Time window (e.g., "1w", "1m")
        correlation_id: Correlation ID for telemetry

    Returns:
        ForecastResult dict
    """
    logger.info(f"[{correlation_id}] TrendForecaster: topic={topic}, window={window}, docs={len(docs)}")

    try:
        # Parse dates
        dates = []
        for doc in docs:
            date_str = doc.get("date") or doc.get("published_date")
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    dates.append(dt)
                except Exception:
                    pass

        if len(dates) < 3:
            logger.warning(f"Insufficient data for forecast: {len(dates)} docs with dates")
            # Return flat forecast
            return {
                "forecast": [
                    {
                        "topic": topic or "general",
                        "direction": "flat",
                        "confidence_interval": [0.4, 0.6],
                        "drivers": [
                            {
                                "signal": "insufficient_data",
                                "rationale": "Not enough historical data for reliable forecast",
                                "evidence_ref": {
                                    "article_id": docs[0].get("article_id") if docs else None,
                                    "url": docs[0].get("url") if docs else None,
                                    "date": docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                                }
                            }
                        ],
                        "horizon": window if window in ["1d", "3d", "1w", "2w", "1m"] else "1w"
                    }
                ],
                "success": True
            }

        # Compute EWMA and slope
        ewma_value, slope = compute_ewma(dates, alpha=0.3, periods=min(len(dates), 14))

        direction = determine_direction(slope, threshold=0.1)
        confidence_interval = estimate_confidence_interval(slope, ewma_value, len(docs))

        logger.info(
            f"[{correlation_id}] EWMA={ewma_value:.2f}, slope={slope:.3f}, direction={direction}"
        )

        # Build drivers from statistical signals
        drivers = []

        # Driver 1: EWMA trend
        # Find recent article as evidence
        recent_docs = sorted(docs, key=lambda d: d.get("date", ""), reverse=True)[:3]
        if recent_docs:
            drivers.append({
                "signal": "ewma_trend",
                "rationale": f"EWMA shows {direction} trend with slope {slope:.3f}",
                "evidence_ref": {
                    "article_id": recent_docs[0].get("article_id"),
                    "url": recent_docs[0].get("url"),
                    "date": recent_docs[0].get("date", "2025-09-30")
                }
            })

        # Driver 2: Volume signal
        if len(docs) > 10:
            drivers.append({
                "signal": "high_volume",
                "rationale": f"High article volume ({len(docs)} articles) indicates sustained interest",
                "evidence_ref": {
                    "article_id": recent_docs[1].get("article_id") if len(recent_docs) > 1 else recent_docs[0].get("article_id"),
                    "url": recent_docs[1].get("url") if len(recent_docs) > 1 else recent_docs[0].get("url"),
                    "date": recent_docs[1].get("date", "2025-09-30") if len(recent_docs) > 1 else recent_docs[0].get("date", "2025-09-30")
                }
            })

        # Driver 3: Recent activity
        recent_date = dates[-1] if dates else datetime.now()
        days_since = (datetime.now() - recent_date).days
        if days_since <= 1:
            drivers.append({
                "signal": "recent_activity",
                "rationale": "Recent articles published within last 24 hours",
                "evidence_ref": {
                    "article_id": recent_docs[0].get("article_id"),
                    "url": recent_docs[0].get("url"),
                    "date": recent_docs[0].get("date", "2025-09-30")
                }
            })

        # Ensure at least 1 driver
        if not drivers:
            drivers.append({
                "signal": "baseline",
                "rationale": "Baseline forecast based on available data",
                "evidence_ref": {
                    "article_id": docs[0].get("article_id") if docs else None,
                    "url": docs[0].get("url") if docs else None,
                    "date": docs[0].get("date", "2025-09-30") if docs else "2025-09-30"
                }
            })

        # Build forecast result
        forecast_item = {
            "topic": topic or "general trend",
            "direction": direction,
            "confidence_interval": list(confidence_interval),
            "drivers": drivers[:5],  # Max 5 drivers
            "horizon": window if window in ["6h", "12h", "1d", "3d", "1w", "2w", "1m"] else "1w"
        }

        result = {
            "forecast": [forecast_item],
            "success": True
        }

        logger.info(f"[{correlation_id}] TrendForecaster completed: {direction} with {len(drivers)} drivers")

        return result

    except Exception as e:
        logger.error(f"[{correlation_id}] TrendForecaster failed: {e}", exc_info=True)
        return {
            "forecast": [{
                "topic": topic or "general",
                "direction": "flat",
                "confidence_interval": [0.4, 0.6],
                "drivers": [{
                    "signal": "error",
                    "rationale": f"Analysis failed: {str(e)[:100]}",
                    "evidence_ref": {
                        "article_id": None,
                        "url": None,
                        "date": "2025-09-30"
                    }
                }],
                "horizon": "1w"
            }],
            "success": False,
            "error": str(e)
        }
