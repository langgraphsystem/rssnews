"""
A/B Testing Framework — Experiment management and routing for Phase 3.
"""

from core.ab_testing.experiment_router import ExperimentRouter, create_experiment_router
from core.ab_testing.experiment_config import ExperimentConfig, ExperimentArm, ArmConfig

__all__ = [
    "ExperimentRouter",
    "create_experiment_router",
    "ExperimentConfig",
    "ExperimentArm",
    "ArmConfig",
]
