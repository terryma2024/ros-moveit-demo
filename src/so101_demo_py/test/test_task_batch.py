import json
from pathlib import Path

from so101_demo.application.task_reachability import (
    ReachabilityReport,
    ReachabilityStatus,
)
from so101_demo.core.task_points import TaskPoint
from so101_demo.runtime.task_artifacts import TaskArtifactRegistry


def _point(point_id: str) -> TaskPoint:
    return TaskPoint(point_id, point_id.title(), (0.02, -0.28, 0.165))


def _request(root: Path, *ids: str):
    from so101_demo.application.task_batch import BatchRequest

    return BatchRequest(
        batch_id="batch-1",
        simulation_session_id="sim-a",
        points=tuple(_point(point_id) for point_id in ids),
        evidence_root=root,
    )


class FakeRuntime:
    def __init__(
        self,
        root: Path,
        *,
        outcomes=None,
        reachability=None,
        incomplete=frozenset(),
        epoch_pairs=None,
    ) -> None:
        from so101_demo.application.task_batch import SafetyReceipt

        self.root = root
        self.outcomes = outcomes or {}
        self.reachability = reachability or {}
        self.incomplete = incomplete
        self.epoch_pairs = iter(epoch_pairs or ((0, 1), (1, 2), (2, 3), (3, 4)))
        self.safe = SafetyReceipt(True, False, None)
        self.events = []
        self.started_points = []
        self.reset_calls = []

    def check_declared(self, point):
        outcome = self.outcomes.get(point.id)
        if outcome is not None and outcome.__class__.__name__ == "HeldCupFailure":
            raise outcome
        status = self.reachability.get(point.id, ReachabilityStatus.REACHABLE)
        self.events.append(f"reachability:{point.id}")
        return ReachabilityReport(
            point.id,
            status,
            (),
            None if status is ReachabilityStatus.REACHABLE else "MOVEIT_PLAN_FAILED",
            0,
        )

    def reset_point(self, point):
        from so101_demo.application.task_batch import ResetPointReceipt

        outcome = self.outcomes.get(point.id)
        if outcome is not None and outcome.__class__.__name__ == "SharedStackFailure":
            raise outcome
        self.started_points.append(point.id)
        self.reset_calls.append(point.id)
        self.events.append(f"reset:{point.id}")
        old_epoch, new_epoch = next(self.epoch_pairs)
        evidence = self.root / f"reset-{point.id}.json"
        evidence.write_text("{}\n")
        return ResetPointReceipt(old_epoch, new_epoch, "sim-a", evidence)

    def start_consumer(self, point_root, epoch):
        from so101_demo.application.task_batch import ManagedChild

        self.events.append(f"consumer:{point_root.name}:{epoch}")
        return ManagedChild("consumer", 100, 100)

    def wait_consumer_subscription(self, child, timeout_s):
        assert child.role == "consumer" and timeout_s == 5.0
        self.events.append("consumer-ready")

    def start_perception(self, point_root):
        from so101_demo.application.task_batch import ManagedChild

        self.events.append(f"perception:{point_root.name}")
        return ManagedChild("perception", 101, 101)

    def wait_point_result(self, point, epoch, point_root):
        from so101_demo.application.task_batch import PointExecutionReceipt

        outcome = self.outcomes.get(point.id)
        if outcome is not None:
            raise outcome
        workflow = point_root / "dynamic-execute-manifest.json"
        workflow.write_text('{"status":"DONE"}\n')
        self.events.append(f"workflow:{point.id}:{epoch}")
        return PointExecutionReceipt(True, None, workflow, self.safe)

    def capture_terminal(self, point_root, reason):
        names = {
            "rgb.png",
            "full-cloud.ply",
            "cup-cloud.ply",
            "point-cloud-preview.png",
            "viewer.png",
        }
        if point_root.name.split("-", 1)[-1] in self.incomplete:
            names.remove("viewer.png")
        paths = []
        for name in sorted(names):
            path = point_root / name
            path.write_bytes(b"evidence")
            paths.append(path)
        self.events.append(f"capture:{point_root.name}:{reason}")
        return tuple(paths)

    def safe_to_continue(self, epoch):
        self.events.append(f"safe:{epoch}")
        return self.safe

    def stop_point_children(self):
        self.events.append("children-stop")

    def pause_world(self):
        self.events.append("world-pause")


def test_point_failure_is_finalized_and_later_point_runs(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import (
        BatchStatus,
        LocalPointFailure,
        PointStatus,
        run_task_batch,
    )

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(
        tmp_path, outcomes={"first": LocalPointFailure("PERCEPTION_TIMEOUT")}
    )
    events = []
    result = run_task_batch(
        _request(tmp_path, "first", "second"), runtime, registry, events=events
    )

    assert [point.status for point in result.points] == [
        PointStatus.FAILED,
        PointStatus.SUCCEEDED,
    ]
    assert runtime.started_points == ["first", "second"]
    assert result.status is BatchStatus.FAILED
    assert (tmp_path / "batches/batch-1/points/01-first/point-result.json").is_file()
    assert runtime.events.index("children-stop") < runtime.events.index("reset:second")


def test_shared_failure_aborts_remaining_points(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import (
        BatchStatus,
        SharedStackFailure,
        run_task_batch,
    )

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(
        tmp_path, outcomes={"first": SharedStackFailure("SESSION_MISMATCH")}
    )
    result = run_task_batch(_request(tmp_path, "first", "second"), runtime, registry)

    assert [point.id for point in result.points] == ["first"]
    assert result.status is BatchStatus.FAILED
    assert result.first_shared_failure == "SESSION_MISMATCH"
    assert runtime.started_points == []


def test_unsupported_held_cup_requires_operator_recovery(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import (
        BatchStatus,
        HeldCupFailure,
        run_task_batch,
    )

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(
        tmp_path,
        outcomes={"first": HeldCupFailure("PHYSICAL_GRASP_UNSUPPORTED")},
    )
    result = run_task_batch(_request(tmp_path, "first", "second"), runtime, registry)

    assert result.status is BatchStatus.NEEDS_OPERATOR_RECOVERY
    assert runtime.reset_calls == []
    assert [point.id for point in result.points] == ["first"]


def test_declared_unreachable_is_skipped_without_reset(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import PointStatus, run_task_batch

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(
        tmp_path,
        reachability={"first": ReachabilityStatus.UNREACHABLE},
    )
    result = run_task_batch(_request(tmp_path, "first", "second"), runtime, registry)

    assert [point.status for point in result.points] == [
        PointStatus.SKIPPED_UNREACHABLE,
        PointStatus.SUCCEEDED,
    ]
    assert runtime.reset_calls == ["second"]


def test_epoch_mismatch_is_shared_failure_and_aborts(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import BatchStatus, run_task_batch

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(tmp_path, epoch_pairs=((0, 1), (8, 9)))
    result = run_task_batch(_request(tmp_path, "first", "second", "third"), runtime, registry)

    assert result.status is BatchStatus.FAILED
    assert result.first_shared_failure == "RESET_EPOCH_DIVERGENCE"
    assert runtime.reset_calls == ["first", "second"]
    assert [point.id for point in result.points] == ["first", "second"]


def test_missing_terminal_artifact_fails_point_but_continues(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import PointStatus, run_task_batch

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(tmp_path, incomplete=frozenset({"first"}))
    result = run_task_batch(_request(tmp_path, "first", "second"), runtime, registry)

    assert result.points[0].status is PointStatus.FAILED
    assert result.points[0].failure_code == "TERMINAL_EVIDENCE_INCOMPLETE"
    assert result.points[1].status is PointStatus.SUCCEEDED


def test_terminal_evidence_gap_does_not_overwrite_point_root_cause(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import LocalPointFailure, run_task_batch

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(
        tmp_path,
        outcomes={"first": LocalPointFailure("RGBD_PERCEPTION_EXITED_EARLY")},
        incomplete=frozenset({"first"}),
    )

    result = run_task_batch(_request(tmp_path, "first"), runtime, registry)

    assert result.points[0].failure_code == "RGBD_PERCEPTION_EXITED_EARLY"


def test_unexpected_point_exception_is_retained_as_json_evidence(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import run_task_batch

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(tmp_path, outcomes={"first": RuntimeError("probe exploded")})

    result = run_task_batch(_request(tmp_path, "first"), runtime, registry)

    error_path = tmp_path / "batches/batch-1/points/01-first/point-runtime-error.json"
    assert json.loads(error_path.read_text()) == {
        "error_type": "RuntimeError",
        "message": "probe exploded",
    }
    assert any(item.relative_path.endswith("point-runtime-error.json") for item in result.points[0].artifacts)


def test_cancel_is_honored_only_after_safe_finalized_checkpoint(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import BatchStatus, run_task_batch

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(tmp_path)

    def cancel_requested() -> bool:
        return (tmp_path / "batches/batch-1/points/01-first/point-result.json").exists()

    result = run_task_batch(
        _request(tmp_path, "first", "second"),
        runtime,
        registry,
        cancel_requested=cancel_requested,
    )

    assert result.status is BatchStatus.CANCELLED
    assert runtime.started_points == ["first"]
    assert "safe:1" in runtime.events


def test_progress_and_final_manifest_are_stable(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import BatchStatus, run_task_batch

    registry = TaskArtifactRegistry(tmp_path)
    runtime = FakeRuntime(tmp_path)
    events = []
    result = run_task_batch(
        _request(tmp_path, "first"), runtime, registry, events=events
    )

    assert result.status is BatchStatus.SUCCEEDED
    assert [event.kind for event in events] == [
        "BATCH_STARTED",
        "POINT_REACHABILITY",
        "POINT_STARTED",
        "POINT_FINISHED",
        "BATCH_FINISHED",
    ]
    document = json.loads(result.manifest_path.read_text())
    assert document["status"] == "SUCCEEDED"
    assert document["points"][0]["status"] == "SUCCEEDED"
    assert runtime.events[-1] == "world-pause"
