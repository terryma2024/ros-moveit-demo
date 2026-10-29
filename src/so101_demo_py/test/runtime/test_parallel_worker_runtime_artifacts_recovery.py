"""Point artifacts, numeric evidence, localisation and recovery."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from parallel_worker_runtime_support import (
    _lease,
    _plan_receipt,
    _ProcessGroup,
    _replacement,
    _resources,
    _write_capture,
    _write_numeric,
)
import pytest

from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode


def test_execute_failure_still_captures_terminal_evidence(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_parts.receipts import (
        ExecutionCompletionReceipt,
        RuntimeDecision,
    )
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    lease = _lease()
    admitted = SimpleNamespace(reset_epoch="reset-7")
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-7",
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: admitted,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: (
            _write_numeric(root, boundary + 1.0)
        ),
        admit_pose=lambda _lease, value: value,
        consumer_ready=lambda _child: True,
        publish_pose=lambda _value: True,
        execute_result=lambda *_args: ExecutionCompletionReceipt(
            RuntimeDecision(
                AttemptStatus.FAILED,
                reason="MOTION_FAILED",
                physical_action_proven_absent=False,
            ),
            30.0,
        ),
    )
    runtime.start_physical_runtime()
    runtime.reset_and_validate_point(lease)
    runtime.localize_and_admit_pose(lease, admitted)

    decision = runtime.execute_expert(lease, admitted)

    assert decision.status is AttemptStatus.FAILED
    assert decision.terminal_artifacts[0].name == "terminal-rgb.png"


def test_execute_snapshot_is_not_captured_when_consumer_subscription_is_not_ready(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    lease = _lease()
    admitted = SimpleNamespace(reset_epoch="reset-7")
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=_ProcessGroup(events),
        reset_point=lambda _lease: SimpleNamespace(
            reset_epoch="reset-7",
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=lambda path, boundary: events.append(("capture", path.name))
        or _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: admitted,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: (
            _write_numeric(root, boundary + 1.0)
        ),
        admit_pose=lambda _lease, value: value,
        consumer_ready=lambda _child: events.append(("ready",)) or False,
        publish_pose=lambda _value: events.append(("publish",)),
        execute_result=lambda *_args: events.append(("await",)),
    )
    runtime.start_physical_runtime()
    events.clear()

    with pytest.raises(RuntimeError, match="subscription is not ready"):
        runtime.reset_and_validate_point(lease)

    assert events == [
        ("capture", "initial-rgb.png"),
        ("start", "dynamic-consumer"),
        ("ready",),
    ]


def test_runtime_owns_localization_publication_and_fresh_camera_artifacts(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    events = []
    resources = _resources(tmp_path, "worker-1", 0, 181)
    reset = SimpleNamespace(
        reset_epoch="reset-8", reset_completed_monotonic_s=10.0
    )
    localized = SimpleNamespace(reset_epoch="reset-8", pose="world-pose")
    admitted = SimpleNamespace(reset_epoch="reset-8", pose="accepted")

    def capture(path, newer_than):
        events.append((path.name, newer_than))
        return _write_capture(path, newer_than + 1.0)

    def plan_prefix(_lease, _admitted, states):
        return _plan_receipt(states, completion=20.0)

    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda lease: reset,
        initial_gate=lambda lease, receipt: (lease, receipt),
        localize=lambda lease, result: localized,
        admit_pose=lambda lease, value: admitted,
        publish_pose=lambda value: events.append(("POSE_ACCEPTED", value)),
        capture_rgb=capture,
        capture_numeric_evidence=lambda _lease, _localized, root, boundary: (
            _write_numeric(root, boundary + 1.0)
        ),
        plan_prefix=plan_prefix,
    )
    lease = _lease()
    runtime.start_physical_runtime()

    receipt, gate = runtime.reset_and_validate_point(lease)
    assert receipt is reset
    assert gate == (lease, reset)
    assert runtime.localize_and_admit_pose(lease, "broker-result") is admitted
    decision = runtime.plan_expert(lease, admitted)

    assert events == [
        ("initial-rgb.png", 10.0),
        ("rgb.npy", 10.0),
        ("POSE_ACCEPTED", admitted),
        ("terminal-rgb.png", 20.0),
    ]
    point_root = resources.worker_root / "validations/P01/attempt-1/working"
    assert point_root / "initial-rgb.png" in runtime.captured_artifacts
    assert point_root / "perception/input/rgb.npy" in runtime.captured_artifacts
    assert point_root / "terminal-rgb.png" in runtime.captured_artifacts
    assert decision.numeric_evidence.depth_path == point_root / "numeric/depth.json"


def test_rgb_capture_requires_a_strictly_newer_source_stamp(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    def stale_capture(path, _newer_than):
        return _write_capture(path, 10.0)

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda *_args: object(),
        resume_physics=lambda *_args: True,
        capture_rgb=stale_capture,
    )
    runtime.start_physical_runtime()

    lease = _lease()
    reset = runtime.reset_point(lease)
    with pytest.raises(RuntimeError, match="newer than boundary"):
        runtime.point_initial_gate(lease, reset)


def test_point_artifacts_reject_traversal_before_capture(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    captures = []
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: captures.append((path, boundary)),
    )
    runtime.start_physical_runtime()

    with pytest.raises(RuntimeError, match="identity"):
        runtime.reset_point(_lease(point="../escape"))

    assert captures == []


def test_point_artifacts_reject_symlinked_workspace_and_never_overwrite(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 0, 181)
    outside = tmp_path / "outside"
    outside.mkdir()
    (resources.worker_root / "validations").symlink_to(outside, target_is_directory=True)
    captures = []
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: captures.append((path, boundary)),
    )
    runtime.start_physical_runtime()

    with pytest.raises(RuntimeError, match="symlink"):
        runtime.reset_point(_lease())

    assert captures == []


def test_two_points_have_distinct_non_overwriting_evidence_paths(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    observed = []

    def capture(path, boundary):
        observed.append(path)
        return _write_capture(path, boundary + 1.0)

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        initial_gate=lambda *_args: object(),
        resume_physics=lambda *_args: True,
        capture_rgb=capture,
    )
    runtime.start_physical_runtime()
    for lease in (_lease(point="P01"), _lease(point="P02")):
        reset = runtime.reset_point(lease)
        runtime.point_initial_gate(lease, reset)

    assert len(set(observed)) == 4
    assert observed[0].parts[-5:] == (
        "validations", "P01", "attempt-1", "working", "initial-rgb.png"
    )
    assert observed[2].parts[-5:] == (
        "validations", "P02", "attempt-1", "working", "initial-rgb.png"
    )


def test_localization_fails_closed_without_numeric_depth_tf_physical_receipt(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: SimpleNamespace(pose="localized"),
    )
    runtime.start_physical_runtime()
    runtime.reset_point(_lease())

    with pytest.raises(RuntimeError, match="capture_numeric_evidence"):
        runtime.localize_and_admit_pose(_lease(), "broker-result")


def test_numeric_evidence_requires_a_strictly_newer_source_stamp(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    lease = _lease()
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: SimpleNamespace(pose="localized"),
        capture_numeric_evidence=lambda _lease, _localized, root, _boundary: (
            _write_numeric(root, 10.0)
        ),
    )
    runtime.start_physical_runtime()
    runtime.reset_point(lease)

    with pytest.raises(RuntimeError, match="newer than reset boundary"):
        runtime.localize_and_admit_pose(lease, "broker-result")


def test_recover_and_shutdown_use_only_the_runtime_owned_group(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    processes = _ProcessGroup()
    recoveries = []
    resources = _resources(tmp_path, "worker-1", 0, 181)
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda worker, generation, deadline: recoveries.append(
            (worker, generation, deadline)
        )
        or True,
        replace_resources=lambda _worker, *, expected_generation: (
            _replacement(resources)
            if expected_generation == resources.generation
            else None
        ),
        monotonic=lambda: 1.0,
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 120.0) is True
    runtime.shutdown_owned()

    assert recoveries == [("worker-1", 1, 120.0)]
    assert processes.shutdown_calls == 2
    assert [spec.role for spec in processes.specs] == [
        "task-station",
        "task-station",
    ]


def test_recover_rejects_stale_generation_before_shutdown_or_replacement(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _replacement(_resources(tmp_path, "worker-1", 0, 181))
    processes = _ProcessGroup()
    recoveries = []
    replacements = []
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *args: recoveries.append(args) or True,
        replace_resources=lambda *args, **kwargs: replacements.append(
            (args, kwargs)
        )
        or _replacement(resources),
        monotonic=lambda: 1.0,
    )
    runtime.start_physical_runtime()

    assert resources.generation == 2
    assert runtime.recover("worker-1", 1, 120.0) is False
    assert processes.shutdown_calls == 0
    assert recoveries == []
    assert replacements == []
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_recover_replaces_resources_and_accepts_only_the_next_generation(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    original = _resources(tmp_path, "worker-1", 0, 181)
    replacement = _replacement(original)
    calls = []
    processes = _ProcessGroup()

    def replace_resources(worker_id, *, expected_generation):
        calls.append((worker_id, expected_generation))
        return replacement

    runtime = build_worker_runtime(
        original,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda worker, generation, deadline: calls.append(
            (worker, generation, deadline)
        )
        or True,
        replace_resources=replace_resources,
        monotonic=lambda: 1.0,
        reset_point=lambda _lease: SimpleNamespace(
            reset_completed_monotonic_s=10.0
        ),
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 120.0) is True
    assert runtime.resources is replacement
    assert calls == [("worker-1", 1, 120.0), ("worker-1", 1)]
    assert replacement.generation == 2
    assert replacement.worker_id == original.worker_id
    assert replacement.slot_index == original.slot_index
    assert replacement.ros_domain_id == original.ros_domain_id
    assert replacement.worker_root == original.worker_root
    assert replacement.session_id != original.session_id
    assert processes.environments[-1] == dict(replacement.environment)
    assert f"session_id:={replacement.session_id}" in processes.specs[-1].argv
    runtime.reset_point(
        _lease(generation=2, point="P02", attempt="attempt-2")
    )


@pytest.mark.parametrize(
    "replacement_mutation",
    (
        lambda current: replace(_replacement(current), generation=current.generation),
        lambda current: replace(_replacement(current), session_id=current.session_id),
        lambda current: replace(_replacement(current), worker_id="worker-2"),
        lambda current: replace(_replacement(current), slot_index=2),
        lambda current: replace(_replacement(current), ros_domain_id=182),
        lambda current: replace(
            _replacement(current), worker_root=current.worker_root / "escaped"
        ),
        lambda current: replace(
            _replacement(current),
            environment={
                **dict(_replacement(current).environment),
                "ROS_DOMAIN_ID": "999",
            },
        ),
        lambda _current: object(),
    ),
)
def test_recover_rejects_malformed_replacement_without_starting_new_stack(
    tmp_path: Path, replacement_mutation
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    resources = _resources(tmp_path, "worker-1", 0, 181)
    processes = _ProcessGroup()
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *_args: True,
        replace_resources=lambda *_args, **_kwargs: replacement_mutation(resources),
        monotonic=lambda: 1.0,
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 120.0) is False
    assert runtime.resources is resources
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_recover_does_not_restart_when_resource_replacement_crosses_deadline(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    now = [9.0]
    resources = _resources(tmp_path, "worker-1", 0, 181)
    processes = _ProcessGroup()

    def replace_resources(*_args, **_kwargs):
        now[0] = 10.0
        return _replacement(resources)

    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *_args: True,
        replace_resources=replace_resources,
        monotonic=lambda: now[0],
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 10.0) is False
    assert runtime.resources is resources
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_recover_checks_deadline_immediately_before_replacement_restart(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    times = iter((9.0, 9.0, 9.0, 9.0, 9.0, 10.0))
    resources = _resources(tmp_path, "worker-1", 0, 181)
    processes = _ProcessGroup()
    runtime = build_worker_runtime(
        resources,
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *_args: True,
        replace_resources=lambda *_args, **_kwargs: _replacement(resources),
        monotonic=lambda: next(times),
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 10.0) is False
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_recover_does_not_continue_after_shutdown_crosses_deadline(tmp_path: Path) -> None:
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    now = [9.0]
    recovery_calls = []
    processes = _ProcessGroup(on_shutdown=lambda: now.__setitem__(0, 10.0))
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.PLAN_ONLY,
        process_group=processes,
        recovery=lambda *args: recovery_calls.append(args) or True,
        monotonic=lambda: now[0],
    )
    runtime.start_physical_runtime()

    assert runtime.recover("worker-1", 1, 10.0) is False
    assert recovery_calls == []
    assert [spec.role for spec in processes.specs] == ["task-station"]


def test_a_pose_without_a_camera_localization_is_admitted_without_numeric_evidence_and_still_executes(tmp_path: Path) -> None:
    """Indoor P3 (D2): a privileged-pose episode whose camera detection missed has no localization; its pose is admitted, no camera numeric
    evidence is captured, and the Teacher is started on it."""
    from so101_demo.runtime.parallel_worker_parts.receipts import ExecutionCompletionReceipt, RuntimeDecision
    from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime

    lease = _lease()
    admitted = SimpleNamespace(reset_epoch="reset-7", perception_chain_complete=True, localized=None)
    numeric_calls = []
    runtime = build_worker_runtime(
        _resources(tmp_path, "worker-1", 0, 181),
        RunMode.EXECUTE,
        process_group=_ProcessGroup(),
        reset_point=lambda _lease: SimpleNamespace(reset_epoch="reset-7", reset_completed_monotonic_s=10.0),
        initial_gate=lambda _lease, receipt: receipt,
        capture_rgb=lambda path, boundary: _write_capture(path, boundary + 1.0),
        localize=lambda _lease, _result: pytest.fail("the camera chain is complete"),
        capture_numeric_evidence=lambda *args: numeric_calls.append(args),
        admit_pose=lambda _lease, value: pytest.fail("the chain admitted itself"),
        consumer_ready=lambda _child: True,
        publish_pose=lambda _value: True,
        execute_result=lambda *_args: ExecutionCompletionReceipt(
            RuntimeDecision(AttemptStatus.FAILED, reason="MOTION_FAILED", physical_action_proven_absent=False), 30.0),
    )
    runtime.start_physical_runtime()
    runtime.reset_and_validate_point(lease)
    assert runtime.localize_and_admit_pose(lease, admitted) is admitted
    assert numeric_calls == []
    assert runtime.execute_expert(lease, admitted).status is AttemptStatus.FAILED
