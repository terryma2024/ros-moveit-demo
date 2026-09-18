import pytest

from so101_teleop.expert_validation.executor_registry import (
    ExecutorRegistry,
    QualificationProbes,
    UnknownOperation,
)


def _probes(**changes):
    values = dict(
        fixed_upstream=True,
        parallel_config=True,
        broker_image=True,
        resource_probe=True,
        two_worker_live_acceptance="parallel-evidence",
        adaptive_runner=True,
        adaptive_pool=True,
        adaptive_wrapper=True,
        adaptive_cleanup=True,
        adaptive_config=True,
        adaptive_fault_injection=True,
        adaptive_twenty_point_acceptance="adaptive-evidence",
        adaptive_performance_evidence=(1, 2, 4, 6, 8),
    )
    values.update(changes)
    return QualificationProbes(**values)


def test_v1_registry_exposes_three_explicit_modes():
    registry = ExecutorRegistry.v1(_probes())
    capability = registry.require("moveit_expert", "validate_pick_place")
    assert capability.execution_modes == ("SEQUENTIAL", "PARALLEL", "ADAPTIVE")
    assert capability.batch_kinds == ("FIRST_PASS", "FULL_RESTART_RETRY")
    assert capability.default_execution_mode == "SEQUENTIAL"
    with pytest.raises(UnknownOperation):
        registry.require("act_collect", "collect_demonstration")


def test_parallel_capability_fails_closed_without_the_broker():
    """Availability states a functional prerequisite, not a retired budget qualification."""

    capability = ExecutorRegistry.v1(
        _probes(broker_image=False)
    ).require("moveit_expert", "validate_pick_place")
    assert capability.mode_availability["PARALLEL"].available is False
    assert capability.mode_availability["PARALLEL"].reason == "PARALLEL_COMPOSITION_UNAVAILABLE"

    complete = ExecutorRegistry.v1(_probes()).require("moveit_expert", "validate_pick_place")
    assert complete.mode_availability["PARALLEL"].available is True
    assert complete.mode_availability["PARALLEL"].reason is None


def test_adaptive_capability_is_independent_from_fixed_modes():
    """The adaptive ladder needs its runner files installed; fixed modes stay available."""

    missing = ExecutorRegistry.v1(
        _probes(adaptive_pool=False)
    ).require("moveit_expert", "validate_pick_place")
    assert missing.mode_availability["SEQUENTIAL"].available is True
    assert missing.mode_availability["PARALLEL"].available is True
    assert missing.mode_availability["ADAPTIVE"].reason == "ADAPTIVE_COMPOSITION_UNAVAILABLE"

    complete = ExecutorRegistry.v1(_probes()).require("moveit_expert", "validate_pick_place")
    assert complete.mode_availability["ADAPTIVE"].available is True
    assert complete.mode_availability["ADAPTIVE"].reason is None
    assert complete.contract_supported_live_unqualified_tiers == (16,)
