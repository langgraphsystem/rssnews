"""
Experiment Configuration — Defines A/B test experiments and arms.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class ExperimentStatus(Enum):
    """Experiment status"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass
class ArmConfig:
    """Configuration for a single experiment arm"""
    arm_id: str
    name: str
    weight: float  # Allocation percentage (0.0-1.0)
    config: Dict[str, Any]  # Arm-specific configuration
    enabled: bool = True

    def __post_init__(self):
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"Arm weight must be in [0.0, 1.0], got {self.weight}")


@dataclass
class ExperimentConfig:
    """
    A/B test experiment configuration

    Example:
        experiment = ExperimentConfig(
            experiment_id="model_routing_001",
            name="GPT-5 vs Claude 4.5 for /ask",
            description="Test which model performs better for agentic RAG",
            arms=[
                ArmConfig(
                    arm_id="control",
                    name="GPT-5 Primary",
                    weight=0.5,
                    config={
                        "primary_model": "gpt-5",
                        "fallback": ["claude-4.5", "gemini-2.5-pro"]
                    }
                ),
                ArmConfig(
                    arm_id="treatment",
                    name="Claude 4.5 Primary",
                    weight=0.5,
                    config={
                        "primary_model": "claude-4.5",
                        "fallback": ["gpt-5", "gemini-2.5-pro"]
                    }
                )
            ],
            target_commands=["/ask"],
            status=ExperimentStatus.ACTIVE
        )
    """
    experiment_id: str
    name: str
    description: str
    arms: List[ArmConfig]
    target_commands: List[str] = field(default_factory=list)  # Empty = all commands
    status: ExperimentStatus = ExperimentStatus.DRAFT
    min_sample_size: int = 100  # Minimum samples per arm before analysis
    max_duration_days: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validate arm weights sum to ~1.0
        total_weight = sum(arm.weight for arm in self.arms if arm.enabled)
        if not (0.99 <= total_weight <= 1.01):
            raise ValueError(
                f"Total arm weights must sum to 1.0, got {total_weight:.3f}"
            )

        # Ensure unique arm IDs
        arm_ids = [arm.arm_id for arm in self.arms]
        if len(arm_ids) != len(set(arm_ids)):
            raise ValueError("Arm IDs must be unique")

    def get_active_arms(self) -> List[ArmConfig]:
        """Get list of enabled arms"""
        return [arm for arm in self.arms if arm.enabled]

    def get_arm(self, arm_id: str) -> Optional[ArmConfig]:
        """Get arm by ID"""
        for arm in self.arms:
            if arm.arm_id == arm_id:
                return arm
        return None

    def is_active(self) -> bool:
        """Check if experiment is active"""
        return self.status == ExperimentStatus.ACTIVE

    def applies_to_command(self, command: str) -> bool:
        """Check if experiment applies to given command"""
        if not self.target_commands:
            return True  # Apply to all commands
        return any(command.startswith(target) for target in self.target_commands)


# Predefined experiment examples
EXPERIMENT_MODEL_ROUTING_ASK = ExperimentConfig(
    experiment_id="model_routing_ask_001",
    name="GPT-5 vs Claude 4.5 for /ask",
    description="Compare model quality and latency for agentic RAG",
    arms=[
        ArmConfig(
            arm_id="control",
            name="GPT-5 Primary",
            weight=0.5,
            config={
                "primary_model": "gpt-5",
                "fallback": ["claude-4.5", "gemini-2.5-pro"]
            }
        ),
        ArmConfig(
            arm_id="treatment",
            name="Claude 4.5 Primary",
            weight=0.5,
            config={
                "primary_model": "claude-4.5",
                "fallback": ["gpt-5", "gemini-2.5-pro"]
            }
        )
    ],
    target_commands=["/ask"],
    status=ExperimentStatus.DRAFT,
    min_sample_size=50
)

EXPERIMENT_DEPTH_THRESHOLD = ExperimentConfig(
    experiment_id="depth_threshold_001",
    name="Agentic RAG depth=2 vs depth=3",
    description="Test if depth=3 provides better quality vs cost",
    arms=[
        ArmConfig(
            arm_id="control",
            name="Depth 2",
            weight=0.5,
            config={"max_depth": 2}
        ),
        ArmConfig(
            arm_id="treatment",
            name="Depth 3",
            weight=0.5,
            config={"max_depth": 3}
        )
    ],
    target_commands=["/ask"],
    status=ExperimentStatus.DRAFT
)

EXPERIMENT_RERANK_STRATEGY = ExperimentConfig(
    experiment_id="rerank_strategy_001",
    name="Rerank enabled vs disabled",
    description="Test impact of reranking on retrieval quality",
    arms=[
        ArmConfig(
            arm_id="control",
            name="No Rerank",
            weight=0.5,
            config={"use_rerank": False}
        ),
        ArmConfig(
            arm_id="treatment",
            name="With Rerank",
            weight=0.5,
            config={"use_rerank": True}
        )
    ],
    target_commands=["/ask", "/events", "/graph"],
    status=ExperimentStatus.DRAFT
)


def create_experiment_config(
    experiment_id: str,
    name: str,
    arms: List[Dict[str, Any]],
    target_commands: Optional[List[str]] = None
) -> ExperimentConfig:
    """
    Factory function to create experiment config from dict

    Args:
        experiment_id: Unique experiment ID
        name: Experiment name
        arms: List of arm configs as dicts
        target_commands: Commands to target (None = all)

    Returns:
        ExperimentConfig
    """
    arm_configs = [
        ArmConfig(
            arm_id=arm["arm_id"],
            name=arm["name"],
            weight=arm["weight"],
            config=arm["config"],
            enabled=arm.get("enabled", True)
        )
        for arm in arms
    ]

    return ExperimentConfig(
        experiment_id=experiment_id,
        name=name,
        description=name,
        arms=arm_configs,
        target_commands=target_commands or []
    )
