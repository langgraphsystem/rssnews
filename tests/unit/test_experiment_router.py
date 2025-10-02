"""
Unit tests for ExperimentRouter (A/B Testing)
"""

import pytest
from core.ab_testing import (
    ExperimentRouter,
    ExperimentConfig,
    ArmConfig,
    ExperimentStatus
)


@pytest.fixture
def router():
    """Create fresh router for each test"""
    return ExperimentRouter()


@pytest.fixture
def simple_experiment():
    """Create a simple 50/50 experiment"""
    return ExperimentConfig(
        experiment_id="test_exp_001",
        name="Test Experiment",
        description="A/B test",
        arms=[
            ArmConfig(
                arm_id="control",
                name="Control",
                weight=0.5,
                config={"model": "gpt-5"}
            ),
            ArmConfig(
                arm_id="treatment",
                name="Treatment",
                weight=0.5,
                config={"model": "claude-4.5"}
            )
        ],
        target_commands=["/ask"],
        status=ExperimentStatus.ACTIVE
    )


def test_register_experiment(router, simple_experiment):
    """Test experiment registration"""
    router.register_experiment(simple_experiment)

    assert "test_exp_001" in router.experiments
    assert "test_exp_001" in router.metrics
    assert len(router.metrics["test_exp_001"]) == 2  # Two arms


def test_deterministic_routing(router, simple_experiment):
    """Test deterministic routing with same user_id"""
    router.register_experiment(simple_experiment)

    # Same user should get same arm
    arm1 = router.get_arm_for_request("/ask", user_id="user_123")
    arm2 = router.get_arm_for_request("/ask", user_id="user_123")

    assert arm1.arm_id == arm2.arm_id


def test_deterministic_distribution(router, simple_experiment):
    """Test that distribution matches weights over many users"""
    router.register_experiment(simple_experiment)

    arm_counts = {"control": 0, "treatment": 0}

    # Route 1000 different users
    for i in range(1000):
        arm = router.get_arm_for_request("/ask", user_id=f"user_{i}")
        arm_counts[arm.arm_id] += 1

    # Should be roughly 50/50 (±10%)
    assert 400 <= arm_counts["control"] <= 600
    assert 400 <= arm_counts["treatment"] <= 600


def test_no_experiment_applies(router):
    """Test when no experiment applies to command"""
    arm = router.get_arm_for_request("/unknown_command", user_id="user_123")
    assert arm is None


def test_inactive_experiment(router, simple_experiment):
    """Test that inactive experiments don't route"""
    simple_experiment.status = ExperimentStatus.PAUSED
    router.register_experiment(simple_experiment)

    arm = router.get_arm_for_request("/ask", user_id="user_123")
    assert arm is None


def test_config_override(router, simple_experiment):
    """Test configuration override with experiment"""
    router.register_experiment(simple_experiment)

    base_config = {
        "model": "base_model",
        "temperature": 0.7
    }

    merged = router.get_arm_config_override(
        "/ask",
        base_config,
        user_id="user_123"
    )

    # Should have model from arm config
    assert merged["model"] in ["gpt-5", "claude-4.5"]
    # Should keep original temperature
    assert merged["temperature"] == 0.7
    # Should have experiment metadata
    assert "_experiment" in merged


def test_record_metric(router, simple_experiment):
    """Test metric recording"""
    router.register_experiment(simple_experiment)

    router.record_metric(
        experiment_id="test_exp_001",
        arm_id="control",
        metric_name="latency_s",
        metric_value=1.5
    )

    metrics = router.metrics["test_exp_001"]["control"]
    assert len(metrics) == 1
    assert metrics[0]["metric_name"] == "latency_s"
    assert metrics[0]["metric_value"] == 1.5


def test_experiment_summary(router, simple_experiment):
    """Test experiment summary statistics"""
    router.register_experiment(simple_experiment)

    # Record some metrics
    for i in range(10):
        router.record_metric(
            experiment_id="test_exp_001",
            arm_id="control",
            metric_name="latency_s",
            metric_value=1.0 + i * 0.1
        )

    for i in range(10):
        router.record_metric(
            experiment_id="test_exp_001",
            arm_id="treatment",
            metric_name="latency_s",
            metric_value=2.0 + i * 0.1
        )

    summary = router.get_experiment_summary("test_exp_001")

    assert summary is not None
    assert len(summary["arms"]) == 2

    # Check control arm stats
    control_arm = next(a for a in summary["arms"] if a["arm_id"] == "control")
    assert control_arm["sample_size"] == 10
    assert "latency_s" in control_arm["statistics"]
    assert 1.0 <= control_arm["statistics"]["latency_s"]["mean"] <= 2.0

    # Check treatment arm stats
    treatment_arm = next(a for a in summary["arms"] if a["arm_id"] == "treatment")
    assert treatment_arm["sample_size"] == 10
    assert treatment_arm["statistics"]["latency_s"]["mean"] > control_arm["statistics"]["latency_s"]["mean"]


def test_weighted_routing():
    """Test weighted routing (80/20 split)"""
    router = ExperimentRouter()

    experiment = ExperimentConfig(
        experiment_id="weighted_test",
        name="Weighted Test",
        description="80/20 split",
        arms=[
            ArmConfig(
                arm_id="control",
                name="Control",
                weight=0.8,
                config={}
            ),
            ArmConfig(
                arm_id="treatment",
                name="Treatment",
                weight=0.2,
                config={}
            )
        ],
        target_commands=["/ask"],
        status=ExperimentStatus.ACTIVE
    )

    router.register_experiment(experiment)

    arm_counts = {"control": 0, "treatment": 0}

    # Route 1000 users
    for i in range(1000):
        arm = router.get_arm_for_request("/ask", user_id=f"user_{i}")
        arm_counts[arm.arm_id] += 1

    # Should be roughly 80/20 (±10%)
    assert 700 <= arm_counts["control"] <= 900
    assert 100 <= arm_counts["treatment"] <= 300


def test_multi_experiment_routing(router):
    """Test routing with multiple active experiments"""
    # Create two experiments for different commands
    exp1 = ExperimentConfig(
        experiment_id="exp_ask",
        name="Ask Experiment",
        description="Test",
        arms=[
            ArmConfig(arm_id="a1", name="A1", weight=0.5, config={"model": "gpt-5"}),
            ArmConfig(arm_id="a2", name="A2", weight=0.5, config={"model": "claude-4.5"})
        ],
        target_commands=["/ask"],
        status=ExperimentStatus.ACTIVE
    )

    exp2 = ExperimentConfig(
        experiment_id="exp_graph",
        name="Graph Experiment",
        description="Test",
        arms=[
            ArmConfig(arm_id="b1", name="B1", weight=0.5, config={"hops": 2}),
            ArmConfig(arm_id="b2", name="B2", weight=0.5, config={"hops": 3})
        ],
        target_commands=["/graph"],
        status=ExperimentStatus.ACTIVE
    )

    router.register_experiment(exp1)
    router.register_experiment(exp2)

    # Route to different commands
    arm_ask = router.get_arm_for_request("/ask", user_id="user_123")
    arm_graph = router.get_arm_for_request("/graph", user_id="user_123")

    # Should get arms from different experiments
    assert arm_ask.arm_id in ["a1", "a2"]
    assert arm_graph.arm_id in ["b1", "b2"]


def test_activate_deactivate(router, simple_experiment):
    """Test activating/deactivating experiments"""
    router.register_experiment(simple_experiment)

    # Initially active
    assert "test_exp_001" in router.list_active_experiments()

    # Deactivate
    router.deactivate_experiment("test_exp_001")
    assert "test_exp_001" not in router.list_active_experiments()

    # Routing should fail
    arm = router.get_arm_for_request("/ask", user_id="user_123")
    assert arm is None

    # Reactivate
    router.activate_experiment("test_exp_001")
    assert "test_exp_001" in router.list_active_experiments()

    # Routing should work
    arm = router.get_arm_for_request("/ask", user_id="user_123")
    assert arm is not None


def test_invalid_experiment_config():
    """Test validation of experiment config"""
    # Weights don't sum to 1.0
    with pytest.raises(ValueError):
        ExperimentConfig(
            experiment_id="bad_exp",
            name="Bad",
            description="Test",
            arms=[
                ArmConfig(arm_id="a1", name="A1", weight=0.3, config={}),
                ArmConfig(arm_id="a2", name="A2", weight=0.3, config={})
            ]
        )

    # Duplicate arm IDs
    with pytest.raises(ValueError):
        ExperimentConfig(
            experiment_id="bad_exp",
            name="Bad",
            description="Test",
            arms=[
                ArmConfig(arm_id="a1", name="A1", weight=0.5, config={}),
                ArmConfig(arm_id="a1", name="A2", weight=0.5, config={})
            ]
        )

    # Invalid arm weight
    with pytest.raises(ValueError):
        ArmConfig(arm_id="a1", name="A1", weight=1.5, config={})
