"""
Phase 4 Schemas — Business Analytics & Optimization
"""

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, validator

class HistorySnapshot(BaseModel):
    ts: str
    topic: str
    momentum: float
    sentiment: float

class MetricRecord(BaseModel):
    ts: str
    metric: Literal["traffic", "ctr", "conv", "roi", "cac", "ltv"]
    value: float

class HistoryData(BaseModel):
    snapshots: Optional[List[HistorySnapshot]] = None
    metrics: Optional[List[MetricRecord]] = None
    competitors: Optional[List[Dict[str, Any]]] = None

class Phase4Params(BaseModel):
    window: str = "24h"
    lang: str = "auto"
    sources: Optional[List[str]] = None
    metrics: Optional[List[str]] = None
    k_final: int = 6
    flags: Dict[str, bool] = Field(default_factory=dict)

class Phase4Context(BaseModel):
    command: str
    params: Phase4Params
    retrieval: Dict[str, Any]
    history: HistoryData
    models: Dict[str, Any]
    limits: Dict[str, int]
    ab_test: Dict[str, Optional[str]]
    personalization: Dict[str, Any]
    telemetry: Dict[str, str]
