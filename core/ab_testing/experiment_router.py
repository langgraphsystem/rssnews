"""
Experiment Router — Routes requests to A/B test arms and tracks metrics.
"""

import hashlib
import logging
import random
from typing import Any, Dict, List, Optional
from datetime import datetime

from core.ab_testing.experiment_config import ExperimentConfig, ArmConfig, ExperimentStatus

logger = logging.getLogger(__name__)


class ExperimentRouter:
    """
    Routes requests to experiment arms and tracks metrics.

    Features:
    - Deterministic routing based on user_id (consistent experience)
    - Random routing when no user_id provided
    - Metrics collection per arm
    - Support for multiple active experiments
    """

    def __init__(self):
        self.experiments: Dict[str, ExperimentConfig] = {}
        self.metrics: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}  # exp_id -> arm_id -> metrics

    def register_experiment(self, experiment: ExperimentConfig):
        """
        Register an experiment

        Args:
            experiment: ExperimentConfig to register
        """
        self.experiments[experiment.experiment_id] = experiment
        self.metrics[experiment.experiment_id] = {
            arm.arm_id: [] for arm in experiment.arms
        }
        logger.info(
            f"Registered experiment: {experiment.experiment_id} "
            f"({len(experiment.arms)} arms, status={experiment.status.value})"
        )

    def get_arm_for_request(
        self,
        command: str,
        user_id: Optional[str] = None,
        experiment_id: Optional[str] = None
    ) -> Optional[ArmConfig]:
        """
        Get experiment arm for a request

        Args:
            command: Command being executed (e.g., "/ask")
            user_id: User ID for consistent routing (optional)
            experiment_id: Specific experiment to use (optional, otherwise first matching)

        Returns:
            ArmConfig or None if no experiment applies
        """
        # Find applicable experiment
        experiment = None

        if experiment_id:
            # Use specific experiment
            experiment = self.experiments.get(experiment_id)
            if not experiment or not experiment.is_active():
                logger.warning(f"Experiment {experiment_id} not found or inactive")
                return None
        else:
            # Find first active experiment for this command
            for exp in self.experiments.values():
                if exp.is_active() and exp.applies_to_command(command):
                    experiment = exp
                    break

        if not experiment:
            # No experiment applies
            return None

        # Get active arms
        active_arms = experiment.get_active_arms()
        if not active_arms:
            logger.warning(f"No active arms for experiment {experiment.experiment_id}")
            return None

        # Route to arm
        if user_id:
            # Deterministic routing based on user_id hash
            arm = self._deterministic_route(user_id, experiment, active_arms)
        else:
            # Random routing
            arm = self._random_route(active_arms)

        logger.info(
            f"Routed to arm '{arm.arm_id}' for experiment {experiment.experiment_id} "
            f"(command={command}, user={user_id or 'anonymous'})"
        )

        return arm

    def _deterministic_route(
        self,
        user_id: str,
        experiment: ExperimentConfig,
        arms: List[ArmConfig]
    ) -> ArmConfig:
        """
        Deterministic routing based on user_id hash

        Ensures consistent experience for same user across sessions.
        """
        # Hash user_id + experiment_id to get deterministic value
        hash_input = f"{user_id}:{experiment.experiment_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)

        # Normalize to [0, 1)
        normalized = (hash_value % 10000) / 10000.0

        # Select arm based on cumulative weights
        cumulative = 0.0
        for arm in arms:
            cumulative += arm.weight
            if normalized < cumulative:
                return arm

        # Fallback: return last arm
        return arms[-1]

    def _random_route(self, arms: List[ArmConfig]) -> ArmConfig:
        """Random routing based on arm weights"""
        weights = [arm.weight for arm in arms]
        return random.choices(arms, weights=weights)[0]

    def record_metric(
        self,
        experiment_id: str,
        arm_id: str,
        metric_name: str,
        metric_value: Any,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record a metric for an experiment arm

        Args:
            experiment_id: Experiment ID
            arm_id: Arm ID
            metric_name: Metric name (e.g., "latency_s", "cost_cents", "quality_score")
            metric_value: Metric value
            metadata: Optional metadata
        """
        if experiment_id not in self.metrics:
            logger.warning(f"Unknown experiment: {experiment_id}")
            return

        if arm_id not in self.metrics[experiment_id]:
            logger.warning(f"Unknown arm {arm_id} for experiment {experiment_id}")
            return

        metric = {
            "metric_name": metric_name,
            "metric_value": metric_value,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }

        self.metrics[experiment_id][arm_id].append(metric)

    def get_arm_config_override(
        self,
        command: str,
        base_config: Dict[str, Any],
        user_id: Optional[str] = None,
        experiment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get configuration with experiment arm overrides applied

        Args:
            command: Command being executed
            base_config: Base configuration dict
            user_id: User ID for routing
            experiment_id: Specific experiment to use

        Returns:
            Configuration dict with arm overrides applied
        """
        arm = self.get_arm_for_request(command, user_id, experiment_id)

        if not arm:
            # No experiment applies, return base config
            return base_config

        # Merge arm config into base config
        merged = dict(base_config)
        merged.update(arm.config)

        # Add experiment metadata
        merged["_experiment"] = {
            "experiment_id": experiment_id or "auto",
            "arm_id": arm.arm_id,
            "arm_name": arm.name
        }

        return merged

    def get_experiment_summary(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get summary statistics for an experiment

        Args:
            experiment_id: Experiment ID

        Returns:
            Summary dict with per-arm statistics
        """
        if experiment_id not in self.experiments:
            return None

        experiment = self.experiments[experiment_id]
        arm_metrics = self.metrics.get(experiment_id, {})

        summary = {
            "experiment_id": experiment_id,
            "name": experiment.name,
            "status": experiment.status.value,
            "arms": []
        }

        for arm in experiment.arms:
            metrics = arm_metrics.get(arm.arm_id, [])

            # Calculate statistics
            sample_size = len(metrics)

            # Group by metric name
            by_metric = {}
            for metric in metrics:
                name = metric["metric_name"]
                value = metric["metric_value"]

                if name not in by_metric:
                    by_metric[name] = []

                if isinstance(value, (int, float)):
                    by_metric[name].append(value)

            # Calculate mean for numeric metrics
            stats = {}
            for metric_name, values in by_metric.items():
                if values:
                    stats[metric_name] = {
                        "mean": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "count": len(values)
                    }

            summary["arms"].append({
                "arm_id": arm.arm_id,
                "arm_name": arm.name,
                "sample_size": sample_size,
                "statistics": stats
            })

        return summary

    def list_active_experiments(self) -> List[str]:
        """Get list of active experiment IDs"""
        return [
            exp_id for exp_id, exp in self.experiments.items()
            if exp.is_active()
        ]

    def deactivate_experiment(self, experiment_id: str):
        """Deactivate an experiment"""
        if experiment_id in self.experiments:
            self.experiments[experiment_id].status = ExperimentStatus.PAUSED
            logger.info(f"Deactivated experiment: {experiment_id}")

    def activate_experiment(self, experiment_id: str):
        """Activate an experiment"""
        if experiment_id in self.experiments:
            self.experiments[experiment_id].status = ExperimentStatus.ACTIVE
            logger.info(f"Activated experiment: {experiment_id}")


# Singleton instance
_router_instance: Optional[ExperimentRouter] = None


def create_experiment_router() -> ExperimentRouter:
    """Factory function to create/get experiment router singleton"""
    global _router_instance
    if _router_instance is None:
        _router_instance = ExperimentRouter()
        logger.info("Created ExperimentRouter singleton")
    return _router_instance


def get_experiment_router() -> ExperimentRouter:
    """Get experiment router singleton"""
    return create_experiment_router()
