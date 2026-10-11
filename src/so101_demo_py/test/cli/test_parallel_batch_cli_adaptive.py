"""The adaptive pool options of the parallel batch command and its workspace."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from parallel_batch_cli_support import (
    ADAPTIVE_CONFIG,
    CONFIG,
    SimpleLease,
    adaptive_argv,
    argv,
    local_start_guard,  # noqa: F401  (pytest fixtures)
    verified,
)
import pytest

from so101_demo.parallel_batch.contracts.common import (
    RunMode,
    ValidationStatus,
)


def test_artifact_workspace_is_reserved_before_runtime_files_and_reused_for_seal(tmp_path):
    from so101_demo.cli.mujoco_batch.worker_process import _ArtifactResults
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt

    lease = SimpleLease()
    root = tmp_path / "worker-01"
    results = _ArtifactResults({"worker-01": root}, RunMode.PLAN_ONLY)
    receipt = ResetBoundaryReceipt("reset-7", "session-worker-01", 12.5, 31.25)
    assert results.reserve_workspace(lease, receipt) is True
    working = root / "validations/task_start/attempt-1/working"
    identity = json.loads((working / "workspace_identity.json").read_text())
    assert identity["reset_epoch"] == "reset-7"
    assert identity["source_stamp"] == {
        "reset_completed_monotonic_s": 12.5,
        "simulation_session_id": "session-worker-01",
        "simulation_time_s": 31.25,
    }
    (working / "initial-rgb.png").write_bytes(b"png")
    (working / "perception/input").mkdir(parents=True)
    (working / "perception/input/rgb.npy").write_bytes(b"npy")
    decision = SimpleNamespace(
        status=ValidationStatus.VALIDATION_FAILED,
        reason="MODEL_REJECTED",
        physical_action_proven_absent=True,
    )
    sealed = Path(results.seal_validation(lease, decision))
    assert sealed == working.parent / "sealed"
    assert (sealed / "initial-rgb.png").read_bytes() == b"png"
    assert (sealed / "perception/input/rgb.npy").read_bytes() == b"npy"


def test_worker_broker_proxy_rejects_unexpected_generation_before_return(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.rpc_proxies import _WorkerBrokerProxy
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        load_parallel_runtime_config_linux_cuda,
    )
    from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt

    worker_root = tmp_path / "worker-01"
    path = worker_root / "validations/task_start/attempt-1/working/perception/input/rgb.npy"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"npy")
    proxy = _WorkerBrokerProxy(
        SimpleNamespace(
            coordinator_epoch=1, worker_id="worker-01", generation=1,
            token="a" * 64,
            current_broker=lambda: {
                "healthy": True,
                "broker_generation": 2,
                "broker_socket_path": str(tmp_path / "perception-g2.sock"),
                "recovery_deadline_monotonic_s": None,
            },
        ),
        tmp_path / "perception.sock",
        SimpleNamespace(worker_root=worker_root),
        load_parallel_runtime_config_linux_cuda(CONFIG),
        broker_generation=1,
    )
    proxy._call = lambda _message: {
        "request_id": "attempt-1-plastic-cup-yolo11n-seg-v1",
        "model_id": "plastic-cup-yolo11n-seg-v1",
        "model_version": load_parallel_runtime_config_linux_cuda(CONFIG).yolo_weights_sha256,
        "broker_generation": 1,
        "outcome": "NORMAL_REJECTION",
        "candidate": None,
        "reason": "none",
        "queued_monotonic_s": 1.0,
        "queue_deadline_monotonic_s": 2.0,
        "started_monotonic_s": 1.1,
        "inference_deadline_monotonic_s": 2.1,
        "completed_monotonic_s": 1.2,
    }
    with pytest.raises(CliError, match="BROKER_GENERATION_CHANGED"):
        proxy.request_model(
            SimpleLease(), ExecutionKind.VALIDATION,
            snapshot=InferenceSnapshotReceipt(
                path, 11.0, 12_000_000_000, "task_camera_frame", (2, 3, 3),
                hashlib.sha256(b"npy").hexdigest(),
            ),
            start_event_id="validation-start-attempt-1",
            start_event_type="VALIDATION_STARTED",
            reset_epoch="reset-1",
        )


def test_frozen_worker_topology_defaults_to_two_by_ten(tmp_path):
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    values = argv(tmp_path / "defaults")
    for flag in ("--worker-count",):
        index = values.index(flag)
        del values[index:index + 2]
    prepared = prepare_batch(values, provenance_verifier=verified)
    assert prepared.request.worker_count == 2
    assert not hasattr(prepared.request, "max_points_per_worker")
    assert prepared.manifest["worker_count"] == 2
    assert prepared.manifest["schema_version"] == 3
    assert "max_points_per_worker" not in prepared.manifest


def test_adaptive_cli_uses_frozen_options_without_a_hard_capacity(tmp_path):
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    prepared = prepare_batch(
        adaptive_argv(tmp_path / "adaptive"), provenance_verifier=verified
    )

    assert prepared.request is None
    assert prepared.adaptive_request is not None
    assert prepared.adaptive_request.options.levels == (8, 6, 4, 2, 1)
    assert prepared.adaptive_request.options.initial_points_per_worker == 3
    assert prepared.adaptive_request.options.yolo_executor_count == 2
    assert prepared.adaptive_config_path == ADAPTIVE_CONFIG.resolve()
    assert "max_points_per_worker" not in prepared.manifest


def test_adaptive_cli_reuses_registered_root_but_reserves_short_runtime(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    root = tmp_path / "registered"
    root.mkdir(mode=0o700)
    (root / "experiment-ledger.md").write_text("retained", encoding="utf-8")

    prepared = prepare_batch(adaptive_argv(root), provenance_verifier=verified)

    assert prepared.adaptive_request.evidence_root == root
    assert prepared.adaptive_request.runtime_root == root / "r/a001"
    (root / "r/a001").mkdir(parents=True, mode=0o700)
    with pytest.raises(CliError, match="DUPLICATE_BATCH"):
        prepare_batch(adaptive_argv(root), provenance_verifier=verified)


def test_adaptive_cli_rejects_legacy_hard_capacity_flag(tmp_path):
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.contracts.common import ContractError

    # The retired flag is refused before mode handling with the stable legacy code.
    with pytest.raises(ContractError, match="LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED"):
        prepare_batch(
            adaptive_argv(tmp_path / "adaptive")
            + ["--max-points-per-worker", "3"],
            provenance_verifier=verified,
        )


def test_adaptive_readiness_probe_does_not_treat_a_missing_socket_as_success(
    tmp_path
):
    from so101_demo.cli.mujoco_batch.rpc_proxies import _WorkerControlProxy

    token = tmp_path / "control.token"
    token.write_text("ab" * 32, encoding="ascii")
    control = _WorkerControlProxy(
        tmp_path / "missing.sock",
        token,
        worker_id="worker-01",
        generation=1,
        coordinator_epoch=1,
        deadline_s=1.0,
    )

    assert control.readiness() is None
    assert control.release_start() is False


def test_adaptive_cli_overrides_worker_options_and_records_them(tmp_path):
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    prepared = prepare_batch(
        adaptive_argv(
            tmp_path / "adaptive",
            worker_count="6",
            fallback_worker_counts="4,2,1",
            initial_points_per_worker="2",
            worker_start_timeout_s="45.5",
            max_infra_attempts_per_point="4",
            yolo_executor_count="4",
        ),
        provenance_verifier=verified,
    )

    options = prepared.adaptive_request.options
    assert options.levels == (6, 4, 2, 1)
    assert options.initial_points_per_worker == 2
    assert options.worker_start_timeout_s == 45.5
    assert options.max_infra_attempts_per_point == 4
    assert options.yolo_executor_count == 4
    assert prepared.manifest["adaptive_worker_options"] == {
        "worker_count": 6,
        "fallback_worker_counts": [4, 2, 1],
        "initial_points_per_worker": 2,
        "worker_start_timeout_s": 45.5,
        "max_infra_attempts_per_point": 4,
        "ros_domain_ids": list(range(215, 231)),
        "yolo_executor_count": 4,
    }


@pytest.mark.parametrize("value", ["0", "3", "8", "true"])
def test_adaptive_cli_rejects_invalid_yolo_executor_count(tmp_path, value):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match="YOLO_EXECUTOR_COUNT|MALFORMED_INTEGER"):
        prepare_batch(
            adaptive_argv(
                tmp_path / "adaptive",
                yolo_executor_count=value,
            ),
            provenance_verifier=verified,
        )


def test_nonadaptive_cli_rejects_yolo_executor_count(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match="ADAPTIVE_OPTIONS_REQUIRE_FLAG"):
        prepare_batch(
            argv(tmp_path / "ordinary") + ["--yolo-executor-count", "2"],
            provenance_verifier=verified,
        )


@pytest.mark.parametrize(
    ("worker_count", "levels"),
    [("6", (6, 4, 2, 1)), ("1", (1,))],
)
def test_adaptive_cli_filters_default_fallbacks_below_preferred_count(
    tmp_path, worker_count, levels
):
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    prepared = prepare_batch(
        adaptive_argv(tmp_path / worker_count, worker_count=worker_count),
        provenance_verifier=verified,
    )

    assert prepared.adaptive_request.options.levels == levels


def test_adaptive_cli_accepts_w16_and_rejects_w17(tmp_path):
    """The CLI exposes W16 as optional capacity without changing its W8 default."""

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    prepared = prepare_batch(
        adaptive_argv(tmp_path / "w16", worker_count="16"),
        provenance_verifier=verified,
    )

    assert prepared.adaptive_request.options.worker_count == 16
    assert prepared.adaptive_request.options.levels == (16, 6, 4, 2, 1)
    assert prepared.adaptive_request.options.ros_domain_ids == tuple(range(215, 231))

    with pytest.raises(CliError, match="MAX_WORKER_COUNT"):
        prepare_batch(
            adaptive_argv(tmp_path / "w17", worker_count="17"),
            provenance_verifier=verified,
        )


@pytest.mark.parametrize("fallbacks", ["6,4", "8,4", "4,6", "4,4", "4,,2"])
def test_adaptive_cli_rejects_invalid_explicit_fallbacks(tmp_path, fallbacks):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match="FALLBACK_WORKER_COUNTS"):
        prepare_batch(
            adaptive_argv(
                tmp_path / "adaptive",
                worker_count="6",
                fallback_worker_counts=fallbacks,
            ),
            provenance_verifier=verified,
        )


@pytest.mark.parametrize(
    ("changes", "extra", "error"),
    [
        ({"adaptive_config": None}, (), "ADAPTIVE_CONFIG_REQUIRED"),
        ({}, ("--resume",), "ADAPTIVE_RESUME_CONFLICT"),
        (
            {"live_headroom_evidence": "/tmp/headroom"},
            (),
            "ADAPTIVE_LIVE_HEADROOM_CONFLICT",
        ),
    ],
)
def test_adaptive_cli_rejects_missing_config_and_legacy_modes(
    tmp_path, changes, extra, error
):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match=error):
        prepare_batch(
            adaptive_argv(tmp_path / "adaptive", **changes) + list(extra),
            provenance_verifier=verified,
        )
