"""
Production-ready Ranking Service for RSS News System
Implements hybrid scoring, deduplication, and explainability
"""

from .scorer import ProductionScorer
from .deduplication import DeduplicationEngine
from .diversification import MMRDiversifier
from .explainability import ExplainabilityEngine

__version__ = "1.0.0"
__all__ = [
    "ProductionScorer",
    "DeduplicationEngine",
    "MMRDiversifier",
    "ExplainabilityEngine"
]