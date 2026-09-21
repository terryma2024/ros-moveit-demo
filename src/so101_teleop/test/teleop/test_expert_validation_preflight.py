import hashlib
from pathlib import Path

import pytest

from so101_teleop.expert_validation.catalog import CatalogPoint, PointSelection
from so101_teleop.expert_validation.preflight import (
    CampaignStartRequest,
    PreflightEngine,
    PreflightRejected,
)


SHA = "a" * 64

REPO = Path(__file__).parents[4]
CONFIG_DIR = REPO / "src" / "so101_demo_py" / "config" / "mujoco"

#: The three installed macOS combinations (design section 6). The document, not the caller,
#: decides which profile/config hash/scope a preflight binds.
MACOS_DOCUMENTS = {
    4: CONFIG_DIR / "parallel_batch_v4_macos_mps_w2.yaml",
    5: CONFIG_DIR / "parallel_batch_v5_macos_mps_w1_retry.yaml",
    6: CONFIG_DIR / "parallel_batch_v6_macos_mps_w1_first_pass.yaml",
}
V3_DOCUMENT = CONFIG_DIR / "parallel_batch_v3.yaml"

W2_CLAIM = {"execution_profile": "MPS_W2_FIRST_PASS", "batch_kind": "FIRST_PASS"}
W1_RETRY_CLAIM = {
    "execution_profile": "MPS_W1_FULL_RESTART_RETRY",
    "batch_kind": "FULL_RESTART_RETRY",
}
W1_FIRST_PASS_CLAIM = {
    "execution_profile": "MPS_W1_FIRST_PASS",
    "batch_kind": "FIRST_PASS",
}

#: (profile, schema_version, execution_mode, worker_count, batch_kind) per installed document.
MATRIX = {
    4: ("MPS_W2_FIRST_PASS", 4, "PARALLEL", 2, "FIRST_PASS"),
    5: ("MPS_W1_FULL_RESTART_RETRY", 5, "SEQUENTIAL", 1, "FULL_RESTART_RETRY"),
    6: ("MPS_W1_FIRST_PASS", 6, "SEQUENTIAL", 1, "FIRST_PASS"),
}
CLAIMS = {4: W2_CLAIM, 5: W1_RETRY_CLAIM, 6: W1_FIRST_PASS_CLAIM}


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


def _macos_request(tmp_path, schema_version, *, count=4, claim=None, **changes):
    """A request that names one installed macOS document and its exact routing-key claim."""

    document = MACOS_DOCUMENTS[schema_version]
    _profile, _schema, mode, workers, _batch_kind = MATRIX[schema_version]
    values = dict(
        mode=mode,
        count=count,
        worker_count=workers,
        parallel_config_path=document,
        parallel_config_sha256=hashlib.sha256(document.read_bytes()).hexdigest(),
        **(CLAIMS[schema_version] if claim is None else claim),
    )
    values.update(changes)
    return _request(
        tmp_path, mode=values.pop("mode"), count=values.pop("count"), **values)


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


# --------------------------------------------------------------------------------------
# The macOS W1/W2 support matrix, driven from the installed v4/v5/v6 documents
#
# The routing key is `(schema_version, execution_profile, batch_kind, worker_count)` and the
# document - not the caller, and never the selected-point count - decides it. A request that
# does not name the combination its document declares is refused before any resource work.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("schema_version", [4, 5, 6])
def test_a_macos_document_admits_only_its_own_routing_key(tmp_path, schema_version):
    profile, schema, mode, workers, batch_kind = MATRIX[schema_version]
    document = MACOS_DOCUMENTS[schema_version]

    receipt = PreflightEngine(Resources()).preflight(
        _macos_request(tmp_path, schema_version)
    )

    assert receipt.admitted, receipt.reason_codes
    assert receipt.execution_config.worker_count == workers
    assert receipt.execution_config.execution_mode == mode
    assert receipt.parallel_config_sha256 == hashlib.sha256(document.read_bytes()).hexdigest()
    assert receipt.execution_profile == profile
    assert receipt.schema_version == schema
    assert receipt.batch_kind == batch_kind
    observations = receipt.resource_observations
    assert observations["execution_profile"] == profile
    assert observations["execution_schema_version"] == schema
    assert observations["execution_batch_kind"] == batch_kind
    assert observations["execution_config_sha256"] == receipt.parallel_config_sha256
    assert observations["execution_worker_count"] == workers


def test_a_v4_document_refuses_a_w1_claim(tmp_path):
    """v4 is frozen exact-W2: a W1 claim is a different platform claim, not a W2 run."""

    from so101_teleop.expert_validation.preflight import UNSUPPORTED_ON_MACOS

    receipt = PreflightEngine(Resources()).preflight(
        _macos_request(tmp_path, 4, claim=W1_FIRST_PASS_CLAIM,
                       mode="SEQUENTIAL", worker_count=1)
    )

    assert receipt.admitted is False
    assert UNSUPPORTED_ON_MACOS in receipt.reason_codes
    assert receipt.execution_config.worker_count == 1


def test_a_v5_document_refuses_a_first_pass_claim(tmp_path):
    from so101_teleop.expert_validation.preflight import UNSUPPORTED_ON_MACOS

    receipt = PreflightEngine(Resources()).preflight(
        _macos_request(tmp_path, 5, claim=W1_FIRST_PASS_CLAIM)
    )

    assert receipt.admitted is False
    assert UNSUPPORTED_ON_MACOS in receipt.reason_codes


def test_a_v6_document_refuses_a_retry_claim(tmp_path):
    from so101_teleop.expert_validation.preflight import UNSUPPORTED_ON_MACOS

    receipt = PreflightEngine(Resources()).preflight(
        _macos_request(tmp_path, 6, claim=W1_RETRY_CLAIM)
    )

    assert receipt.admitted is False
    assert UNSUPPORTED_ON_MACOS in receipt.reason_codes


def test_adaptive_is_refused_on_a_macos_document(tmp_path):
    from so101_teleop.expert_validation.preflight import UNSUPPORTED_ON_MACOS

    receipt = PreflightEngine(Resources()).preflight(
        _macos_request(tmp_path, 4, mode="ADAPTIVE", count=8, **W2_CLAIM)
    )

    assert receipt.admitted is False
    assert UNSUPPORTED_ON_MACOS in receipt.reason_codes


def test_the_selected_point_count_never_infers_the_profile_or_the_worker_count(tmp_path):
    """Four points do not mean W1 and twenty points do not mean W2."""

    from so101_teleop.expert_validation.preflight import (
        EXECUTION_PROFILE_REQUIRED,
        UNSUPPORTED_ON_MACOS,
    )

    for count in (4, 5, 8, 20):
        receipt = PreflightEngine(Resources()).preflight(
            _macos_request(tmp_path, 4, count=count)
        )
        assert receipt.admitted, (count, receipt.reason_codes)
        assert receipt.execution_config.worker_count == 2
        assert receipt.execution_config.execution_mode == "PARALLEL"

    # Without the explicit routing key nothing is inferred, however many points were selected.
    unclaimed = PreflightEngine(Resources()).preflight(
        _macos_request(tmp_path, 4, count=8, claim={})
    )
    assert unclaimed.admitted is False
    assert EXECUTION_PROFILE_REQUIRED in unclaimed.reason_codes

    # N>2 is refused with the stable platform reason, claim or no claim.
    oversized = PreflightEngine(Resources()).preflight(
        _macos_request(tmp_path, 4, count=20, worker_count=8)
    )
    assert oversized.admitted is False
    assert UNSUPPORTED_ON_MACOS in oversized.reason_codes


def test_a_declared_config_hash_that_does_not_match_the_document_is_refused(tmp_path):
    receipt = PreflightEngine(Resources()).preflight(
        _macos_request(tmp_path, 4, parallel_config_sha256="b" * 64)
    )

    assert receipt.admitted is False
    assert "PARALLEL_CONFIG_HASH_MISMATCH" in receipt.reason_codes


def test_a_v3_document_keeps_the_existing_fixed_semantics(tmp_path):
    """The Linux v3 fixture is untouched: no matrix, no profile, the same counts as before."""

    receipt = PreflightEngine(Resources()).preflight(
        _request(
            tmp_path,
            mode="PARALLEL",
            count=20,
            worker_count=8,
            parallel_config_path=V3_DOCUMENT,
            parallel_config_sha256=hashlib.sha256(V3_DOCUMENT.read_bytes()).hexdigest(),
        )
    )

    assert receipt.admitted, receipt.reason_codes
    assert receipt.execution_config.worker_count == 8
    assert receipt.execution_profile is None
    assert "execution_profile" not in receipt.resource_observations


def test_the_macos_binding_follows_the_accelerator_not_the_schema_number():
    """A Linux/CUDA v4 document is not a macOS profile; only MPS gets the platform matrix."""

    from types import SimpleNamespace

    from so101_teleop.expert_validation.preflight import (
        MACOS_EXECUTION_PROFILES,
        macos_execution_profile_for_config,
    )

    def document(kind, worker_count=2):
        return SimpleNamespace(
            schema_version=4,
            worker_count=worker_count,
            accelerator=SimpleNamespace(kind=kind, resolved_selector="default"),
            start_guard=SimpleNamespace(mps_minimum_headroom_bytes=1 << 30),
        )

    assert macos_execution_profile_for_config(document("mps")) is MACOS_EXECUTION_PROFILES[0]
    assert macos_execution_profile_for_config(document("cuda")) is None
    # A v3 document has no accelerator selection at all and keeps its NVML semantics.
    assert macos_execution_profile_for_config(
        SimpleNamespace(schema_version=3, worker_count=8)
    ) is None


def test_a_macos_document_probes_with_the_mps_selector_and_a_fresh_epoch_per_request(tmp_path):
    """One fresh StartGuard epoch per request; the composition is reused, the verdict is not."""

    from so101_demo.parallel_batch.start_guard import PASS, GuardCheck, GuardResult
    from so101_teleop.expert_validation.production import _HostResourceProbe
    from so101_teleop.expert_validation.preflight import FixedExecutionConfig

    scopes = []

    class RecordingGuard:
        gpu_selector = "MPS:default"

        def begin_epoch(self, scope):
            scopes.append(scope)
            return GuardResult(
                scope=scope, status=PASS, started_monotonic_s=1.0, completed_monotonic_s=2.0,
                checks={"mps_headroom": GuardCheck(PASS, "MPS_HEADROOM_OK", 8 << 30,
                                                   1 << 30, "bytes")},
                snapshot=None, cleanup_state="CLEAR")

    request = _macos_request(tmp_path, 4)
    config = FixedExecutionConfig("PARALLEL", 2)
    probe = _HostResourceProbe(start_guard=RecordingGuard())

    first = probe.probe(request, config)
    second = probe.probe(request, config)

    assert first[0] and second[0], (first[1], second[1])
    assert [scope.gpu_selector for scope in scopes] == ["MPS:default", "MPS:default"]
    assert scopes[0].epoch != scopes[1].epoch
    assert scopes[0].worker_count == 2
    assert scopes[0].owner_pid == scopes[1].owner_pid
    observations = first[2]["start_guard"]
    assert observations["admission_kind"] == "unified-memory-proxy"
    assert "gpu" not in observations["checks"]
