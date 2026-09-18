from pathlib import Path

import pytest

from so101_teleop.expert_validation.catalog import CatalogPoint, PointSelection
from so101_teleop.expert_validation.preflight import (
    CampaignStartRequest,
    PreflightEngine,
    PreflightRejected,
)


SHA = "a" * 64


def _selection(count):
    points = tuple(
        CatalogPoint(
            id=f"point_{index}",
            label=f"Point {index}",
            source="generated",
            stratum="near/center",
            position_world_m=(float(index), 0.0, 0.0),
            display_id=f"P{index:02d}",
        )
        for index in range(1, count + 1)
    )
    return PointSelection("catalog", 1, SHA, points, tuple(p.id for p in points), SHA)


class Resources:
    def __init__(self, admitted=True, reasons=(), observations=None):
        self.admitted = admitted
        self.reasons = tuple(reasons)
        self.observations = observations or {"memory_pressure": "LOW"}

    def probe(self, _request, _config):
        return self.admitted, self.reasons, dict(self.observations)


def _request(tmp_path, mode="PARALLEL", count=4, **changes):
    values = dict(
        campaign_id="campaign-1",
        batch_id="b001",
        manifest_id="manifest-1",
        selection=_selection(count),
        execution_mode=mode,
        evidence_root=tmp_path.resolve(),
        points_path=(tmp_path / "points.yaml").resolve(),
        parallel_config_path=(tmp_path / "parallel.yaml").resolve(),
        adaptive_config_path=(tmp_path / "adaptive.yaml").resolve(),
        worker_count=2 if mode == "PARALLEL" else (1 if mode == "SEQUENTIAL" else 8),
        max_points_per_worker=None,
        fallback_worker_counts=(6, 4, 2, 1),
        initial_points_per_worker=3,
        worker_start_timeout_s=120.0,
        max_infra_attempts_per_point=5,
        yolo_executor_count=2,
        service_session_id="session-1",
        lease_generation=1,
        source_commit="1" * 40,
        install_prefix="/opt/validation",
        coordinator_executable_sha256=SHA,
        adaptive_runner_module_sha256=SHA,
        adaptive_pool_module_sha256=SHA,
        adaptive_cleanup_executable_sha256=SHA,
        adaptive_wrapper_sha256=SHA,
        parallel_config_sha256=SHA,
        adaptive_config_sha256=SHA,
        yolo_weights_sha256=SHA,
        grounded_sam_manifest_sha256=SHA,
        broker_image_id="sha256:" + SHA,
        resource_manifest_sha256=SHA,
    )
    values.update(changes)
    return CampaignStartRequest(**values)


def test_fixed_selection_capacity_is_shared_and_quota_free(tmp_path):
    receipt = PreflightEngine(Resources()).preflight(
        _request(tmp_path, mode="PARALLEL", count=5, worker_count=2)
    )
    assert receipt.admitted
    assert not hasattr(receipt.execution_config, "max_points_per_worker")
    assert receipt.capacity == 5


@pytest.mark.parametrize(
    ("mode", "worker_count", "error"),
    [
        ("SEQUENTIAL", 2, "SEQUENTIAL_WORKER_COUNT"),
        ("PARALLEL", 1, "PARALLEL_WORKER_COUNT"),
        ("PARALLEL", 9, "PARALLEL_WORKER_COUNT"),
    ],
)
def test_fixed_worker_count_is_closed(tmp_path, mode, worker_count, error):
    with pytest.raises(PreflightRejected, match=error):
        PreflightEngine(Resources()).require_admitted(
            _request(tmp_path, mode=mode, worker_count=worker_count)
        )


def test_fixed_legacy_quota_is_refused_without_downgrade(tmp_path):
    resources = Resources(admitted=False, reasons=("GPU_HEADROOM",))
    receipt = PreflightEngine(resources).preflight(
        _request(tmp_path, count=5, worker_count=2, max_points_per_worker=2)
    )
    assert not receipt.admitted
    assert receipt.reason_codes == (
        "LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED", "GPU_HEADROOM")
    assert receipt.execution_config.worker_count == 2


def test_adaptive_rejects_k_and_invalid_ladder(tmp_path):
    engine = PreflightEngine(Resources())
    with pytest.raises(PreflightRejected, match="ADAPTIVE_FIXED_FIELD"):
        engine.require_admitted(_request(tmp_path, mode="ADAPTIVE", max_points_per_worker=3))
    with pytest.raises(PreflightRejected, match="ADAPTIVE_FALLBACK_TIERS"):
        engine.require_admitted(
            _request(tmp_path, mode="ADAPTIVE", fallback_worker_counts=(6, 6, 1))
        )


def test_adaptive_resource_observations_do_not_reject_start(tmp_path):
    resources = Resources(
        admitted=False,
        reasons=("GPU_HEADROOM",),
        observations={"gpu_headroom": "LOW", "memory_pressure": "HIGH"},
    )
    receipt = PreflightEngine(resources).preflight(_request(tmp_path, mode="ADAPTIVE", count=20))
    assert receipt.admitted is True
    assert receipt.reason_codes == ()
    assert receipt.resource_observations["memory_pressure"] == "HIGH"


def test_receipt_binds_canonical_request_session_and_expiry(tmp_path):
    receipt = PreflightEngine(Resources(), clock_ns=lambda: 100).preflight(
        _request(tmp_path)
    )
    assert receipt.service_session_id == "session-1"
    assert receipt.lease_generation == 1
    assert receipt.observed_at_ns == 100
    assert receipt.expires_at_monotonic_ns > receipt.observed_at_ns
    assert len(receipt.canonical_start_request_sha256) == 64


@pytest.mark.parametrize("workers,maximum,capacity", [(2, 10, 20), (8, 3, 24)])
def test_fixed_twenty_points_keeps_exact_requested_capacity(tmp_path, workers, maximum, capacity):
    receipt = PreflightEngine(Resources()).preflight(
        _request(tmp_path, count=20, worker_count=workers))
    assert receipt.admitted
    assert receipt.capacity == 20
    assert receipt.execution_config.worker_count == workers
    assert not hasattr(receipt.execution_config, "max_points_per_worker")


def test_eight_worker_resource_rejection_keeps_supported_count(tmp_path):
    receipt = PreflightEngine(Resources(False, ("CPU_HEADROOM",))).preflight(
        _request(tmp_path, count=20, worker_count=8))
    assert not receipt.admitted
    assert receipt.reason_codes == ("CPU_HEADROOM",)
    assert receipt.capacity == 20
    assert receipt.execution_config.worker_count == 8


def test_host_fixed_eight_without_a_guard_is_refused():
    """No composed guard means no admission; the probe never fabricates a pass."""

    from so101_teleop.expert_validation.production import _HostResourceProbe
    from so101_teleop.expert_validation.preflight import FixedExecutionConfig

    admitted, reasons, observations = _HostResourceProbe().probe(
        None, FixedExecutionConfig("PARALLEL", 8))
    assert not admitted
    assert reasons == ("START_GUARD_UNAVAILABLE",)
    assert observations["requested_worker_count"] == 8


def _local_check(self, policy, scope):
    """Real reads, real decision; only the probe process boundary is replaced."""

    import dataclasses
    import time

    from so101_demo.parallel_batch import start_guard

    started = time.monotonic()
    ports = dataclasses.replace(start_guard.host_ports(), busy_window_s=0.0)
    try:
        snapshot = start_guard.probe_snapshot(policy, scope, started + policy.timeout_s,
                                              ports=ports)
        return start_guard.evaluate_snapshot(snapshot, policy, scope,
                                             started_monotonic_s=started,
                                             completed_monotonic_s=time.monotonic())
    except start_guard.ProbeError as error:
        return start_guard.GuardResult(
            scope=scope, status=start_guard.FAIL, started_monotonic_s=started,
            completed_monotonic_s=time.monotonic(),
            checks={"probe": start_guard.GuardCheck(start_guard.FAIL, error.reason, None, None,
                                                   "state")},
            snapshot=None, cleanup_state="CLEAR")


def test_host_fixed_eight_admits_through_the_real_guard(monkeypatch, tmp_path):
    from so101_demo.parallel_batch.start_guard import StartGuardPolicy
    from so101_demo.parallel_batch.start_guard_probe import (
        ProbeCoordinator, compose_default_start_guard)
    from so101_teleop.expert_validation.production import _HostResourceProbe
    from so101_teleop.expert_validation.preflight import FixedExecutionConfig

    monkeypatch.setenv("SO101_TASK_ROOT", str(tmp_path))
    monkeypatch.setattr(ProbeCoordinator, "check", _local_check)
    policy = StartGuardPolicy()
    guard = compose_default_start_guard(policy)

    admitted, reasons, observations = _HostResourceProbe(
        start_guard=guard, gpu_selector="INDEX:0").probe(
            None, FixedExecutionConfig("PARALLEL", 8))

    assert admitted, reasons
    assert observations["requested_worker_count"] == 8
    assert observations["start_guard_status"] in ("PASS", "WARN")
    guard = observations["start_guard"]
    assert guard["status"] in ("PASS", "WARN")
    assert set(guard["checks"]) == {"cpu_capacity", "cpu_busy", "ram", "gpu"}
    assert guard["checks"]["ram"]["unit"] == "bytes"


def test_host_probe_reports_a_failing_guard_reason(monkeypatch, tmp_path):
    """A FAIL from the guard becomes the preflight reason, unchanged."""

    from so101_demo.parallel_batch.start_guard import (
        FAIL, GuardCheck, GuardResult, StartGuardPolicy)
    from so101_demo.parallel_batch.start_guard_probe import (
        EpochStartGuard, ProbeCoordinator)
    from so101_teleop.expert_validation.production import _HostResourceProbe
    from so101_teleop.expert_validation.preflight import FixedExecutionConfig

    class RefusingCoordinator(ProbeCoordinator):
        def check(self, policy, scope):
            return GuardResult(scope=scope, status=FAIL, started_monotonic_s=0.0,
                               completed_monotonic_s=0.0,
                               checks={"gpu": GuardCheck(FAIL, "GPU_FREE_BELOW_MINIMUM",
                                                         1, 1 << 30, "bytes")},
                               snapshot=None, cleanup_state="CLEAR")

    policy = StartGuardPolicy()
    guard = EpochStartGuard(RefusingCoordinator(tmp_path / "state"), policy)
    admitted, reasons, observations = _HostResourceProbe(
        start_guard=guard, gpu_selector="INDEX:0").probe(
            None, FixedExecutionConfig("PARALLEL", 8))

    assert not admitted
    assert reasons == ("GPU_FREE_BELOW_MINIMUM",)
    assert observations["start_guard"]["checks"]["gpu"]["status"] == "FAIL"
