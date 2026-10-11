"""The point gate resume, the owned process tree, generation replacement and station environment."""

from dataclasses import replace
from pathlib import Path
import signal
from types import SimpleNamespace

from parallel_worker_runtime_support import (
    _Child,
    _lease,
    _ProcessGroup,
    _replacement,
    _resources,
    _write_capture,
    _write_numeric,
)
import pytest

from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode


def test_point_gate_resumes_only_after_fresh_camera_frame_newer_than_reset_watermark(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_parts.process_tree import SourceStampedCapture
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    resources = _resources(tmp_path, "worker-1", 0, 181)
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(events=events),
        ready_probe=lambda _requirements: True,
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-7", reset_epoch_value=7,
            reset_completed_monotonic_s=10.0, simulation_time_s=20.0,
        ),
        reserve_workspace=lambda *_args: True,
        initial_gate=lambda *_args: events.append(("initial-gate",)) or object(),
        resume_physics=lambda _lease, _reset: events.append(("resume",)) or True,
        capture_rgb=lambda path, boundary: (
            events.append(("capture", path.name))
            or (
                SourceStampedCapture(
                    _write_capture(path, boundary + 1.0).path,
                    boundary + 1.0,
                    21_000_000_000,
                )
                if path.name == "initial-rgb.png"
                    else _write_capture(path, boundary + 1.0, 21_000_000_001)
            )
        ),
        replace_resources=lambda *_args, **_kwargs: _replacement(resources),
    )
    runtime.start_physical_runtime()
    lease = _lease()
    reset = runtime.reset_point(lease)
    runtime.point_initial_gate(lease, reset)
    assert events[1:] == [
        ("initial-gate",),
        ("resume",),
        ("capture", "initial-rgb.png"),
        ("capture", "rgb.npy"),
    ]

    stale_root = tmp_path / "stale"
    stale_resources = _resources(stale_root, "worker-1", 0, 181)

    def stale_capture(path, boundary):
        from so101_demo.runtime.parallel_worker_parts.process_tree import SourceStampedCapture

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"rgb")
        return SourceStampedCapture(
            path, boundary + 1.0, source_stamp_ns=20_000_000_000
        )

    stale = build_worker_runtime(
        stale_resources, RunMode.PLAN_ONLY, process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-7", reset_epoch_value=7,
            reset_completed_monotonic_s=10.0, simulation_time_s=20.0,
        ),
        reserve_workspace=lambda *_args: True,
        initial_gate=lambda *_args: object(),
        resume_physics=lambda *_args: True,
        capture_rgb=stale_capture,
        replace_resources=lambda *_args, **_kwargs: _replacement(
            stale_resources
        ),
    )
    stale.start_physical_runtime()
    reset = stale.reset_point(lease)
    with pytest.raises(RuntimeError, match="simulation watermark"):
        stale.point_initial_gate(lease, reset)


def test_worker_owned_tree_reaps_exact_child_when_identity_or_manifest_fails(
    monkeypatch, tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree

    class Child(_Child):
        def __init__(self, pid):
            super().__init__(pid)
            self.events = []

        def terminate(self):
            self.events.append("terminate")

        def kill(self):
            self.events.append("kill")

        def wait(self, timeout):
            self.events.append(("wait", timeout))
            self.returncode = 0
            return 0

    monkeypatch.setattr("os.getpgrp", lambda: 401)
    bad = Child(502)
    tree = WorkerOwnedProcessTree(
        popen=lambda *_args, **_kwargs: bad,
        identity_probe=lambda _pid: (999, ("other",), 5),
    )
    with pytest.raises(RuntimeError, match="escaped"):
        tree.start(SimpleNamespace(role="task-station", argv=("child",)))
    assert bad.events[0] == "terminate"
    assert bad.returncode == 0
    assert tree.manifest.processes == ()

    child = Child(503)
    tree = WorkerOwnedProcessTree(
        popen=lambda *_args, **_kwargs: child,
        identity_probe=lambda _pid: (401, ("child",), 6),
        manifest_path=tmp_path / "owned.json",
    )
    tree._write_manifest = lambda: (_ for _ in ()).throw(OSError("fsync"))
    with pytest.raises(OSError, match="fsync"):
        tree.start(SimpleNamespace(role="task-station", argv=("child",)))
    assert child.events[0] == "terminate"
    assert child.returncode == 0
    assert tree.manifest.processes == ()


def test_worker_owned_tree_retries_transient_incomplete_proc_identity(
    monkeypatch,
) -> None:
    from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree

    child = _Child(504)
    observations = iter(
        (
            RuntimeError("incomplete process identity for PID 504"),
            (401, ("ros2", "launch", "worker"), 7),
        )
    )
    calls = []

    def identity_probe(pid):
        calls.append(pid)
        observed = next(observations)
        if isinstance(observed, Exception):
            raise observed
        return observed

    monkeypatch.setattr("os.getpgrp", lambda: 401)
    tree = WorkerOwnedProcessTree(
        popen=lambda *_args, **_kwargs: child,
        identity_probe=identity_probe,
    )

    identity = tree.start(
        SimpleNamespace(role="task-station", argv=("ros2", "launch", "worker"))
    )

    assert calls == [504, 504]
    assert identity.pid == 504
    assert identity.pgid == 401
    assert identity.start_time_ticks == 7
    assert tree.manifest.processes == (identity,)


def test_worker_owned_tree_stops_only_the_exact_owned_child(monkeypatch) -> None:
    from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree

    children = [_Child(504), _Child(505)]
    signals = []
    monkeypatch.setattr("os.getpgrp", lambda: 401)
    tree = WorkerOwnedProcessTree(
        popen=lambda *_args, **_kwargs: children.pop(0),
        identity_probe=lambda pid: (401, (f"child-{pid}",), pid + 10),
        signal_process=lambda pid, signal_number: signals.append(
            (pid, signal_number)
        ),
    )
    first = tree.start(
        SimpleNamespace(role="dynamic-consumer", argv=("child-504",))
    )
    second = tree.start(SimpleNamespace(role="task-station", argv=("child-505",)))

    assert tree.stop(first) is True

    assert signals == [(504, signal.SIGINT)]
    assert tree.manifest.processes == (second,)


def test_worker_owned_tree_serializes_concurrent_shutdown_manifest_publication(
    monkeypatch, tmp_path: Path,
) -> None:
    import json
    import os
    import threading
    import time

    from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree

    path = tmp_path / "owned.json"
    tree = WorkerOwnedProcessTree(manifest_path=path)
    real_replace = os.replace
    entered = threading.Event()
    release = threading.Event()
    replace_calls = [0]
    replace_lock = threading.Lock()

    def blocking_first_replace(source, target):
        with replace_lock:
            replace_calls[0] += 1
            call = replace_calls[0]
        if call == 1:
            entered.set()
            assert release.wait(timeout=1.0)
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", blocking_first_replace)
    errors = []

    def shutdown():
        try:
            tree.shutdown()
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)

    first = threading.Thread(target=shutdown)
    second = threading.Thread(target=shutdown)
    first.start()
    assert entered.wait(timeout=1.0)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(timeout=1.0)
    second.join(timeout=1.0)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "processes": [],
        "schema_version": 1,
    }


def test_ros_planner_adapter_closes_owned_node_and_context() -> None:
    from so101_demo.runtime.parallel_worker_parts.plan_prefix import RosDynamicPlanPrefixAdapter

    events = []
    planner = SimpleNamespace(
        control=object(), close=lambda: events.append("planner-close")
    )
    node = SimpleNamespace(destroy_node=lambda: events.append("node-destroy"))
    context = SimpleNamespace(shutdown=lambda: events.append("context-shutdown"))
    template = SimpleNamespace(
        arm_joint_names=("shoulder",), planning_frame="world", planning_group="arm",
        tcp_link="tcp", position_tolerance_m=0.01,
        orientation_tolerance_rad=(0.1, 0.1, 0.1), planning_timeout_s=1.0,
        velocity_scaling=0.2, acceleration_scaling=0.2,
    )
    adapter = RosDynamicPlanPrefixAdapter(
        node, template, object(), planner_factory=lambda *_args: planner,
        target_resolver=lambda *_args: object(), plan_state=lambda **_kwargs: None,
        owned_context=context,
    )
    adapter.close()
    adapter.close()
    assert events == ["planner-close", "node-destroy", "context-shutdown"]


def test_execute_consumer_receives_integer_reset_epoch_not_wire_label(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181), RunMode.EXECUTE,
        process_group=_ProcessGroup(),
    )
    command = runtime.consumer_argv("reset-17", _lease())
    index = command.index("--expected-reset-epoch")
    assert command[index + 1] == "17"
    timeout_index = command.index("--cup-pose-timeout-s")
    assert command[timeout_index + 1] == "240.0"
    ready_index = command.index("--ready-receipt")
    assert command[ready_index + 1] == str(
        tmp_path
        / "worker-1/attempts/P01/attempt-1/working/dynamic/consumer-ready.json"
    )
    lease = _lease()
    for flag, expected in {
        "--batch-id": lease.batch_id,
        "--coordinator-epoch": str(lease.coordinator_epoch),
        "--worker-id": lease.worker_id,
        "--worker-generation": str(lease.worker_generation),
        "--point-id": lease.point_id,
        "--attempt-id": lease.attempt_id,
        "--lease-generation": str(lease.lease_generation),
    }.items():
        assert command[command.index(flag) + 1] == expected
    with pytest.raises(RuntimeError, match="reset epoch"):
        runtime.consumer_argv("not-an-epoch", _lease())


def test_generation_replacement_rebinds_runtime_ports_before_restart(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    original = _resources(tmp_path, "worker-1", 0, 181)
    replacement = _replacement(original)
    events = []
    runtime = build_worker_runtime(
        original, RunMode.PLAN_ONLY, process_group=_ProcessGroup(events=events),
        recovery=lambda *_args: True,
        replace_resources=lambda *_args, **_kwargs: replacement,
        rebind_resources=lambda value: events.append(("rebind", value.session_id)) or True,
        monotonic=lambda: 1.0,
    )
    runtime.start_physical_runtime()
    assert runtime.recover("worker-1", 1, 10.0) is True
    assert events[-2:] == [
        ("rebind", replacement.session_id),
        ("start", "task-station"),
    ]


def test_default_worker_process_tree_joins_outer_worker_pgid(monkeypatch, tmp_path: Path):
    from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree

    calls = []
    child = _Child(502)
    monkeypatch.setattr("os.getpgrp", lambda: 401)
    tree = WorkerOwnedProcessTree(
        popen=lambda argv, **kwargs: calls.append((tuple(argv), kwargs)) or child,
        identity_probe=lambda _pid: (401, ("child",), 99),
        signal_process=lambda *_args: None,
    )
    tree.start(SimpleNamespace(role="task-station", argv=("child",)), environment={"PATH": "/bin"})
    assert calls == [(("child",), {"start_new_session": False, "env": {"PATH": "/bin"}})]
    assert tree.manifest.processes[0].pgid == 401


def test_recover_does_not_restart_when_recovery_crosses_deadline(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    now = [9.0]
    processes = _ProcessGroup()
    resources = _resources(tmp_path, "worker-1", 0, 181)

    def recovery(*_args):
        now[0] = 10.0
        return True

    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=recovery,
        replace_resources=lambda *_args, **_kwargs: _replacement(resources),
        monotonic=lambda: now[0],
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 10.0) is False
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_station_environment_scrubs_and_refuses_a_canonical_prefix(tmp_path: Path) -> None:
    """A station must never resolve its nodes from another checkout.

    CP-UQ261: the canonical project install was in AMENT_PREFIX_PATH, `ros2_control_node` came from
    it, and it waited forever for a `/robot_description` that node set never published.
    """

    import os

    from so101_demo.runtime.parallel_worker_parts.station import (
        CANONICAL_INSTALL_MARKER,
        station_environment,
    )

    resources = _resources(tmp_path, "worker-1", 0, 181)
    base = {
        "AMENT_PREFIX_PATH": os.pathsep.join(
            ["/branch/install/so101_demo_py", f"/canonical/{CANONICAL_INSTALL_MARKER}/so101_demo_py"]
        ),
        "PATH": os.pathsep.join(["/usr/bin", f"/canonical/{CANONICAL_INSTALL_MARKER}/bin"]),
        "DYLD_LIBRARY_PATH": f"/canonical/{CANONICAL_INSTALL_MARKER}/lib",
        "ROS_DOMAIN_ID": "999",
    }

    environment = station_environment(resources, base=base)

    assert CANONICAL_INSTALL_MARKER not in environment["AMENT_PREFIX_PATH"]
    assert environment["AMENT_PREFIX_PATH"] == "/branch/install/so101_demo_py"
    assert environment["PATH"] == "/usr/bin"
    assert environment["DYLD_LIBRARY_PATH"] == ""
    # The Worker's own environment wins, and its domain is the one the allocator granted.
    assert environment["ROS_DOMAIN_ID"] == str(resources.ros_domain_id)

    poisoned = dict(resources.environment or {})
    poisoned["AMENT_PREFIX_PATH"] = f"/canonical/{CANONICAL_INSTALL_MARKER}/so101_demo_py"
    with pytest.raises(RuntimeError, match="CANONICAL_INSTALL_PREFIX"):
        station_environment(replace(resources, environment=poisoned), base=base)


def test_terminal_capture_failure_keeps_the_teacher_decision_and_only_marks_the_data_invalid(tmp_path: Path) -> None:
    """Terminal capture and the episode seal are data work: a failure there cannot change the Teacher's result."""
    from so101_demo.runtime.parallel_worker_parts.receipts import (
        ExecutionCompletionReceipt,
        RuntimeDecision,
    )
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    lease = _lease()
    admitted = SimpleNamespace(reset_epoch="reset-7")

    def capture(path, boundary):
        if path.name == "terminal-rgb.png":
            raise RuntimeError("TERMINAL_RGB_UNAVAILABLE")
        return _write_capture(path, boundary + 1.0)

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(reset_epoch="reset-7", reset_completed_monotonic_s=10.0),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=capture,
        localize=lambda _lease, _result: admitted,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: _write_numeric(root, boundary + 1.0),
        admit_pose=lambda _lease, value: value,
        consumer_ready=lambda _child: True,
        publish_pose=lambda _value: True,
        execute_result=lambda *_args: ExecutionCompletionReceipt(
            RuntimeDecision(AttemptStatus.PASSED, physical_action_proven_absent=False,
                teacher_execution_status="COMPLETED", teacher_task_result="PASS", act_data_status="PENDING_QC"),
            30.0,
        ),
    )
    runtime.start_physical_runtime()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, admitted)

    decision = runtime.execute_expert(lease, admitted)

    assert decision.status is AttemptStatus.PASSED
    assert (decision.teacher_execution_status, decision.teacher_task_result) == ("COMPLETED", "PASS")
    assert decision.act_data_status == "INVALID" and "TERMINAL_CAPTURE_FAILED" in decision.act_data_reason
    assert "TERMINAL_RGB_UNAVAILABLE" in decision.act_data_reason and decision.terminal_artifacts == ()


def test_station_environment_annotations_resolve() -> None:
    """The module defers annotations, so an unimported name in one only fails when something resolves it."""
    import typing

    from so101_demo.runtime.parallel_worker_parts import station as parallel_worker_runtime_station

    hints = typing.get_type_hints(parallel_worker_runtime_station.station_environment)
    assert hints["return"] == dict[str, str]
