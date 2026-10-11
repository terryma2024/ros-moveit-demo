"""Stop control, revocation receipts, inference capture and the execute consumer."""

import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace

from parallel_worker_runtime_support import _lease, _ProcessGroup, _resources, _write_capture
import pytest

from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode, ValidationStatus


def test_stop_control_fences_new_runtime_side_effects(tmp_path):
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: pytest.fail("reset started after stop"),
    )
    runtime.start_physical_runtime()

    assert runtime.shutdown_control("stop", deadline_monotonic_s=99.0) is True
    assert runtime.stop_requested is True
    with pytest.raises(RuntimeError, match="STOP_REQUESTED"):
        runtime.reset_point(_lease())


def test_cancel_motion_starts_controller_cancel_while_consumer_stop_is_blocked(
    tmp_path,
):
    """A slow consumer exit must not delay the safety-critical controller cancel."""

    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    stop_entered = threading.Event()
    release_stop = threading.Event()
    controller_cancelled = threading.Event()

    class BlockingProcessGroup(_ProcessGroup):
        def stop(self, child):
            events.append(("stop-entered", child.pid))
            stop_entered.set()
            assert release_stop.wait(2.0)
            events.append(("stop-complete", child.pid))
            return True

    processes = BlockingProcessGroup(events=events)
    lease = _lease()
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=processes,
        cancel_motion=lambda current: (
            events.append(("cancel", current.attempt_id))
            or controller_cancelled.set()
            or True
        ),
    )
    key = runtime._lease_key(lease)
    child = SimpleNamespace(pid=417, role="dynamic-consumer")
    runtime._active_lease = lease
    runtime._execute_consumers[key] = child

    results = []
    call = threading.Thread(target=lambda: results.append(runtime.cancel_motion(lease)))
    call.start()
    assert stop_entered.wait(1.0)

    assert controller_cancelled.wait(0.2), (
        "controller cancellation waited for the blocked consumer exit"
    )
    assert call.is_alive()
    release_stop.set()
    call.join(2.0)

    assert results == [True]
    assert events == [
        ("stop-entered", 417),
        ("cancel", "attempt-1"),
        ("stop-complete", 417),
    ]
    assert key not in runtime._execute_consumers


def test_revocation_receipts_are_durable_exact_lease_events(tmp_path):
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=_ProcessGroup(),
    )
    lease = _lease()
    runtime._active_lease = lease

    assert runtime.record_revocation(
        lease, "WATCHDOG_REVOKED", reason="COORDINATOR_LOST"
    ) is True
    assert runtime.record_revocation(lease, "CANCEL_REQUESTED") is True
    assert runtime.record_revocation(
        lease,
        "CONTROLLER_CANCEL_RESULT",
        motion_stopped=True,
        controllers_confirmed=True,
    ) is True
    assert runtime.record_revocation(
        lease,
        "CANCEL_RESULT",
        broker_fenced=True,
        motion_stopped=True,
        controllers_confirmed=True,
    ) is True

    path = runtime.resources.worker_root / "revocation-events.jsonl"
    assert path.stat().st_mode & 0o777 == 0o600
    receipts = [json.loads(line) for line in path.read_text().splitlines()]
    assert [value["phase"] for value in receipts] == [
        "WATCHDOG_REVOKED", "CANCEL_REQUESTED",
        "CONTROLLER_CANCEL_RESULT", "CANCEL_RESULT",
    ]
    assert all(value["attempt_id"] == lease.attempt_id for value in receipts)
    assert all(value["worker_generation"] == lease.worker_generation for value in receipts)
    assert all(type(value["monotonic_ns"]) is int for value in receipts)

    with pytest.raises(RuntimeError, match="not active"):
        runtime.record_revocation(
            SimpleNamespace(**{**vars(lease), "attempt_id": "stale-attempt"}),
            "WATCHDOG_REVOKED",
            reason="COORDINATOR_LOST",
        )


def test_inference_rgb_must_be_newer_than_reset_sim_clock_and_same_session(tmp_path):
    from so101_demo.runtime.parallel_worker_parts.process_tree import SourceStampedCapture
    from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    def capture(path, boundary):
        if path.suffix != ".npy":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"rgb")
            return SourceStampedCapture(path, boundary + 1.0, source_stamp_ns=12_000_000_001)
        receipt = _write_capture(path, boundary + 1.0)
        return InferenceSnapshotReceipt(
            receipt.path, receipt.source_stamp_monotonic_s,
            source_stamp_ns=12_000_000_000,
            source_frame_id=receipt.source_frame_id,
            shape=receipt.shape,
            input_sha256=receipt.input_sha256,
            simulation_session_id="stale-session",
            source_clock="ros_sim",
        )

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0,
            simulation_time_s=12.0,
            simulation_session_id="session-worker-1",
        ),
        initial_gate=lambda *_args: object(),
        resume_physics=lambda *_args: True,
        capture_rgb=capture,
    )
    runtime.start_physical_runtime()
    reset = runtime.reset_point(_lease())

    with pytest.raises(RuntimeError, match="simulation watermark|simulation session"):
        runtime.point_initial_gate(_lease(), reset)


@pytest.mark.parametrize(
    "mode,disposition,expected",
    [
        (RunMode.PLAN_ONLY, "FAILED", ValidationStatus.VALIDATION_FAILED),
        (RunMode.PLAN_ONLY, "INVALID", ValidationStatus.VALIDATION_INVALID),
        (RunMode.EXECUTE, "FAILED", AttemptStatus.FAILED),
        (RunMode.EXECUTE, "INVALID", AttemptStatus.INVALID),
    ],
)
def test_perception_terminal_maps_without_planning_or_execution(
    tmp_path, mode, disposition, expected
):
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    called = []
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 1, 181),
        mode,
        plan_prefix=lambda *_args: called.append("plan"),
        execute_result=lambda *_args: called.append("execute"),
    )
    terminal = SimpleNamespace(
        perception_terminal=True,
        disposition=disposition,
        reason="PERCEPTION_TEST",
    )
    if mode is RunMode.PLAN_ONLY:
        decision = runtime.plan_expert(_lease(), terminal)
    else:
        decision = runtime.execute_expert(_lease(), terminal)
    assert decision.status is expected
    assert decision.reason == "PERCEPTION_TEST"
    assert called == []


def test_workspace_reservation_precedes_first_post_reset_artifact(tmp_path):
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 1, 31)
    events = []
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-1",
            simulation_session_id=resources.session_id,
            reset_completed_monotonic_s=10.0,
        ),
        reserve_workspace=lambda _lease, receipt: events.append(
            ("reserved", receipt.reset_epoch)
        ) or True,
        capture_rgb=lambda path, boundary: events.append(
            ("capture", path.name)
        ) or _write_capture(path, boundary + 1.0),
    )
    runtime.start_physical_runtime()
    lease = _lease()
    reset = runtime.reset_point(lease)
    assert events == [("reserved", "reset-1")]
    runtime._initial_gate = lambda *_args: events.append(("initial-gate",)) or object()
    runtime._resume_physics = lambda *_args: events.append(("resume",)) or True
    runtime.point_initial_gate(lease, reset)
    assert events == [
        ("reserved", "reset-1"),
        ("initial-gate",),
        ("resume",),
        ("capture", "initial-rgb.png"),
        ("capture", "rgb.npy"),
    ]


def test_post_reset_snapshot_is_canonical_immutable_and_lease_bound(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 0, 181)
    lease = _lease()
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
    )
    runtime.start_physical_runtime()

    runtime.reset_point(lease)
    runtime.point_initial_gate(
        lease, SimpleNamespace(reset_completed_monotonic_s=10.0)
    )
    snapshot = runtime.inference_snapshot(lease)

    expected = (
        resources.worker_root
        / "validations/P01/attempt-1/working/perception/input/rgb.npy"
    )
    assert snapshot.path == expected
    assert snapshot.shape == (4, 5, 3)
    assert snapshot.source_stamp_ns == 12_000_000_000
    assert snapshot.source_frame_id == "task_camera_frame"
    assert snapshot.input_sha256 == hashlib.sha256(expected.read_bytes()).hexdigest()
    assert expected.stat().st_mode & 0o777 == 0o400
    with pytest.raises(RuntimeError, match="lease identity"):
        runtime.inference_snapshot(_lease(point="P02"))


def test_execute_consumer_is_ready_before_its_inference_snapshot(tmp_path: Path) -> None:
    """Catch constructing fresh sim-time participants after the source frame."""

    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    resources = _resources(tmp_path, "worker-1", 0, 181)
    processes = _ProcessGroup(events)
    lease = _lease()

    def capture(path, boundary):
        events.append(("capture", path.name))
        return _write_capture(path, boundary + 1.0)

    runtime = build_worker_runtime(
        resources,
        RunMode.EXECUTE,
        process_group=processes,
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-7",
            reset_completed_monotonic_s=10.0,
        ),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=capture,
        consumer_ready=lambda child: events.append(("ready", child.role)) or True,
        pause_physics=lambda _lease, _reset: events.append(("pause",)) or True,
    )
    runtime.start_physical_runtime()
    events.clear()

    runtime.reset_and_validate_point(lease)
    runtime.inference_snapshot(lease)

    assert events == [
        ("capture", "initial-rgb.png"),
        ("start", "dynamic-consumer"),
        ("ready", "dynamic-consumer"),
        ("capture", "rgb.npy"),
        ("pause",),
    ]
