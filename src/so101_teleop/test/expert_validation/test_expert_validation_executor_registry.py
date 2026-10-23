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


def test_registry_exposes_the_one_native_mode():
    registry = ExecutorRegistry.v1(_probes())
    capability = registry.require("moveit_expert", "validate_pick_place")
    assert capability.execution_modes == ("SEQUENTIAL",)
    assert set(capability.mode_availability) == {"SEQUENTIAL"}
    assert capability.batch_kinds == ("FIRST_PASS", "FULL_RESTART_RETRY")
    assert capability.default_execution_mode == "SEQUENTIAL"
    with pytest.raises(UnknownOperation):
        registry.require("act_collect", "collect_demonstration")


def test_sequential_capability_fails_closed_without_the_fixed_upstream():
    """Availability states a functional prerequisite, not a retired budget qualification."""

    broken = ExecutorRegistry.v1(
        _probes(fixed_upstream=False)
    ).require("moveit_expert", "validate_pick_place")
    assert broken.mode_availability["SEQUENTIAL"].available is False
    assert broken.mode_availability["SEQUENTIAL"].reason == "FIXED_NOT_QUALIFIED"

    complete = ExecutorRegistry.v1(_probes()).require("moveit_expert", "validate_pick_place")
    assert complete.mode_availability["SEQUENTIAL"].available is True
    assert complete.mode_availability["SEQUENTIAL"].reason is None


def test_multi_worker_files_never_make_a_multi_worker_mode_available():
    """The broker, the adaptive pool and the runner files are installed and still decide nothing."""

    complete = ExecutorRegistry.v1(_probes()).require("moveit_expert", "validate_pick_place")
    assert "PARALLEL" not in complete.mode_availability
    assert "ADAPTIVE" not in complete.mode_availability
    assert complete.contract_supported_live_unqualified_tiers == (16,)
