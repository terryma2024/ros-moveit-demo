"""Backend-neutral RESET_WORLD batch orchestration and continuation policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol

from ..application.task_reachability import ReachabilityReport, ReachabilityStatus
from ..core.task_points import TaskPoint
from ..runtime.task_artifacts import (
    ArtifactRecord,
    TaskArtifactRegistry,
    atomic_json,
)

_REQUIRED_TERMINAL_FILES = frozenset(
    {
        "rgb.png",
        "full-cloud.ply",
        "cup-cloud.ply",
        "point-cloud-preview.png",
        "viewer.png",
    }
)
_CONSUMER_SUBSCRIPTION_TIMEOUT_S = 30.0


class PointStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED_UNREACHABLE = "SKIPPED_UNREACHABLE"


class BatchStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NEEDS_OPERATOR_RECOVERY = "NEEDS_OPERATOR_RECOVERY"


@dataclass(frozen=True, slots=True)
class ManagedChild:
    role: str
    pid: int
    pgid: int


@dataclass(frozen=True, slots=True)
class ResetPointReceipt:
    old_epoch: int
    new_epoch: int
    simulation_session_id: str
    evidence_file: Path


@dataclass(frozen=True, slots=True)
class SafetyReceipt:
    safe_to_reset: bool
    unsupported_held_cup: bool
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class PointExecutionReceipt:
    succeeded: bool
    failure_code: str | None
    workflow_manifest: Path | None
    safe_state: SafetyReceipt


class _BatchFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        if not code:
            raise ValueError("batch failure code must be non-empty")
        self.code = code.split(":", 1)[0]
        super().__init__(code)


class LocalPointFailure(_BatchFailure):
    pass


class SharedStackFailure(_BatchFailure):
    pass


class HeldCupFailure(_BatchFailure):
    pass


@dataclass(frozen=True, slots=True)
class BatchRequest:
    batch_id: str
    simulation_session_id: str
    points: tuple[TaskPoint, ...]
    evidence_root: Path

    def __post_init__(self) -> None:
        if not self.batch_id or not self.simulation_session_id or not self.points:
            raise ValueError("batch id, session id, and points are required")
        if len({point.id for point in self.points}) != len(self.points):
            raise ValueError("batch point ids must be unique")
        if not self.evidence_root.is_absolute():
            raise ValueError("batch evidence root must be absolute")


@dataclass(frozen=True, slots=True)
class PointResult:
    id: str
    status: PointStatus
    failure_code: str | None
    reachability_status: ReachabilityStatus | None
    reset_epoch: int | None
    artifacts: tuple[ArtifactRecord, ...]
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class BatchResult:
    batch_id: str
    status: BatchStatus
    points: tuple[PointResult, ...]
    first_shared_failure: str | None
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class BatchProgressEvent:
    kind: str
    batch_id: str
    point_id: str | None
    status: str
    failure_code: str | None = None


class BatchRuntimePort(Protocol):
    def check_declared(self, point: TaskPoint) -> ReachabilityReport: ...

    def reset_point(self, point: TaskPoint) -> ResetPointReceipt: ...

    def start_consumer(self, point_root: Path, epoch: int) -> ManagedChild: ...

    def wait_consumer_subscription(
        self, child: ManagedChild, timeout_s: float
    ) -> None: ...

    def start_perception(self, point_root: Path) -> ManagedChild: ...

    def wait_point_result(
        self, point: TaskPoint, epoch: int, point_root: Path
    ) -> PointExecutionReceipt: ...

    def capture_terminal(self, point_root: Path, reason: str) -> tuple[Path, ...]: ...

    def safe_to_continue(self, epoch: int) -> SafetyReceipt: ...

    def stop_point_children(self) -> None: ...

    def pause_world(self) -> None: ...


def _media_type(path: Path) -> str:
    return {
        ".json": "application/json",
        ".png": "image/png",
        ".ply": "application/octet-stream",
        ".log": "text/plain",
    }.get(path.suffix.lower(), "application/octet-stream")


def _artifact_document(artifact: ArtifactRecord) -> dict[str, object]:
    return asdict(artifact)


def _point_document(result: PointResult) -> dict[str, object]:
    return {
        "id": result.id,
        "status": result.status.value,
        "failure_code": result.failure_code,
        "reachability_status": (
            None
            if result.reachability_status is None
            else result.reachability_status.value
        ),
        "reset_epoch": result.reset_epoch,
        "artifacts": [_artifact_document(item) for item in result.artifacts],
        "manifest_path": result.manifest_path.name,
    }


def _finalize_point(
    *,
    point: TaskPoint,
    point_root: Path,
    status: PointStatus,
    failure_code: str | None,
    reachability_status: ReachabilityStatus | None,
    reset_epoch: int | None,
    artifacts: list[ArtifactRecord],
) -> PointResult:
    manifest = point_root / "point-result.json"
    result = PointResult(
        point.id,
        status,
        failure_code,
        reachability_status,
        reset_epoch,
        tuple(artifacts),
        manifest,
    )
    atomic_json(manifest, _point_document(result))
    return result


def _event(
    events: list[BatchProgressEvent],
    request: BatchRequest,
    kind: str,
    status: str,
    *,
    point_id: str | None = None,
    failure_code: str | None = None,
) -> None:
    events.append(
        BatchProgressEvent(kind, request.batch_id, point_id, status, failure_code)
    )


def run_task_batch(
    request: BatchRequest,
    runtime: BatchRuntimePort,
    registry: TaskArtifactRegistry,
    *,
    events: list[BatchProgressEvent] | None = None,
    cancel_requested: Callable[[], bool] = lambda: False,
    stop_on_point_failure: bool = False,
) -> BatchResult:
    if registry.root != request.evidence_root.resolve(strict=True):
        raise ValueError("batch request and artifact registry evidence roots differ")
    progress = [] if events is None else events
    batch_root = registry.allocate_batch(request.batch_id)
    point_results: list[PointResult] = []
    first_shared_failure = None
    batch_status = BatchStatus.RUNNING
    prior_epoch: int | None = None
    any_point_failure = False
    _event(progress, request, "BATCH_STARTED", BatchStatus.RUNNING.value)

    if cancel_requested():
        batch_status = BatchStatus.CANCELLED

    for index, point in enumerate(request.points, start=1):
        if batch_status is not BatchStatus.RUNNING:
            break
        point_root = registry.allocate_point(batch_root, index, point.id)
        atomic_json(
            point_root / "point-input.json",
            {
                "id": point.id,
                "label": point.label,
                "cup_position_world_m": list(point.cup_position_world_m),
            },
        )
        reachability_status = None
        reset_epoch = None
        artifacts: list[ArtifactRecord] = []
        point_status = PointStatus.RUNNING
        failure_code = None
        fatal_kind: str | None = None
        terminal_paths: tuple[Path, ...] = ()
        diagnostic_paths: tuple[Path, ...] = ()

        try:
            report = runtime.check_declared(point)
            reachability_status = report.status
            _event(
                progress,
                request,
                "POINT_REACHABILITY",
                report.status.value,
                point_id=point.id,
                failure_code=report.first_failure_code,
            )
            if report.status is ReachabilityStatus.UNREACHABLE:
                point_status = PointStatus.SKIPPED_UNREACHABLE
                failure_code = report.first_failure_code or "DECLARED_UNREACHABLE"
                any_point_failure = True
            elif report.status is ReachabilityStatus.UNKNOWN:
                raise SharedStackFailure(
                    report.first_failure_code or "DECLARED_REACHABILITY_UNKNOWN"
                )
            else:
                _event(
                    progress,
                    request,
                    "POINT_STARTED",
                    PointStatus.RUNNING.value,
                    point_id=point.id,
                )
                reset = runtime.reset_point(point)
                if reset.simulation_session_id != request.simulation_session_id:
                    raise SharedStackFailure("SESSION_MISMATCH")
                if reset.new_epoch != reset.old_epoch + 1 or (
                    prior_epoch is not None and reset.old_epoch != prior_epoch
                ):
                    raise SharedStackFailure("RESET_EPOCH_DIVERGENCE")
                reset_epoch = reset.new_epoch
                artifacts.append(
                    registry.register_file(
                        "reset",
                        reset.evidence_file,
                        "application/json",
                        request.simulation_session_id,
                        reset_epoch,
                    )
                )
                consumer = runtime.start_consumer(point_root, reset_epoch)
                runtime.wait_consumer_subscription(
                    consumer, _CONSUMER_SUBSCRIPTION_TIMEOUT_S
                )
                runtime.start_perception(point_root)
                receipt = runtime.wait_point_result(
                    point, reset_epoch, point_root
                )
                if receipt.safe_state.unsupported_held_cup:
                    raise HeldCupFailure(
                        receipt.safe_state.failure_code
                        or "PHYSICAL_GRASP_UNSUPPORTED"
                    )
                if not receipt.safe_state.safe_to_reset:
                    raise SharedStackFailure(
                        receipt.safe_state.failure_code or "POINT_NOT_SAFE_TO_RESET"
                    )
                if not receipt.succeeded:
                    raise LocalPointFailure(
                        receipt.failure_code or "POINT_EXECUTION_FAILED"
                    )
                if receipt.workflow_manifest is None:
                    raise LocalPointFailure("WORKFLOW_MANIFEST_MISSING")
                artifacts.append(
                    registry.register_file(
                        "workflow",
                        receipt.workflow_manifest,
                        "application/json",
                        request.simulation_session_id,
                        reset_epoch,
                    )
                )
                point_status = PointStatus.SUCCEEDED
        except HeldCupFailure as error:
            point_status = PointStatus.FAILED
            failure_code = error.code
            fatal_kind = "held"
            any_point_failure = True
        except SharedStackFailure as error:
            point_status = PointStatus.FAILED
            failure_code = error.code
            fatal_kind = "shared"
            first_shared_failure = first_shared_failure or error.code
            any_point_failure = True
        except LocalPointFailure as error:
            point_status = PointStatus.FAILED
            failure_code = error.code
            any_point_failure = True
        except Exception as error:
            point_status = PointStatus.FAILED
            failure_code = "POINT_RUNTIME_FAILED"
            fatal_kind = "shared"
            first_shared_failure = first_shared_failure or failure_code
            any_point_failure = True
            diagnostic = point_root / "point-runtime-error.json"
            atomic_json(
                diagnostic,
                {
                    "error_type": type(error).__name__,
                    "message": str(error),
                },
            )
            diagnostic_paths = (diagnostic,)
        finally:
            if point_status is not PointStatus.SKIPPED_UNREACHABLE:
                try:
                    terminal_paths = runtime.capture_terminal(
                        point_root,
                        failure_code or point_status.value,
                    )
                    terminal_paths = (*terminal_paths, *diagnostic_paths)
                except Exception:
                    if fatal_kind is None:
                        point_status = PointStatus.FAILED
                        failure_code = "TERMINAL_CAPTURE_FAILED"
                        any_point_failure = True
                try:
                    runtime.stop_point_children()
                except Exception:
                    point_status = PointStatus.FAILED
                    failure_code = "POINT_CHILD_CLEANUP_FAILED"
                    fatal_kind = "shared"
                    first_shared_failure = first_shared_failure or failure_code
                    any_point_failure = True

        for path in terminal_paths:
            try:
                artifacts.append(
                    registry.register_file(
                        "terminal-capture",
                        path,
                        _media_type(path),
                        request.simulation_session_id,
                        reset_epoch,
                    )
                )
            except Exception:
                point_status = PointStatus.FAILED
                failure_code = "TERMINAL_ARTIFACT_REGISTRATION_FAILED"
                fatal_kind = "shared"
                first_shared_failure = first_shared_failure or failure_code
                any_point_failure = True
                break
        if point_status is not PointStatus.SKIPPED_UNREACHABLE:
            terminal_names = {path.name for path in terminal_paths}
            if (
                not _REQUIRED_TERMINAL_FILES <= terminal_names
                and fatal_kind is None
                and failure_code is None
            ):
                point_status = PointStatus.FAILED
                failure_code = "TERMINAL_EVIDENCE_INCOMPLETE"
                any_point_failure = True

        if reset_epoch is not None and fatal_kind is None:
            try:
                safety = runtime.safe_to_continue(reset_epoch)
            except Exception:
                point_status = PointStatus.FAILED
                failure_code = "SAFETY_CHECK_FAILED"
                fatal_kind = "shared"
                first_shared_failure = first_shared_failure or failure_code
                any_point_failure = True
            else:
                if safety.unsupported_held_cup:
                    point_status = PointStatus.FAILED
                    failure_code = (
                        safety.failure_code or "PHYSICAL_GRASP_UNSUPPORTED"
                    )
                    fatal_kind = "held"
                    any_point_failure = True
                elif not safety.safe_to_reset:
                    point_status = PointStatus.FAILED
                    failure_code = safety.failure_code or "POINT_NOT_SAFE_TO_RESET"
                    fatal_kind = "shared"
                    first_shared_failure = first_shared_failure or failure_code
                    any_point_failure = True
                else:
                    prior_epoch = reset_epoch

        point_result = _finalize_point(
            point=point,
            point_root=point_root,
            status=point_status,
            failure_code=failure_code,
            reachability_status=reachability_status,
            reset_epoch=reset_epoch,
            artifacts=artifacts,
        )
        point_results.append(point_result)
        _event(
            progress,
            request,
            "POINT_FINISHED",
            point_status.value,
            point_id=point.id,
            failure_code=failure_code,
        )

        if fatal_kind == "held":
            batch_status = BatchStatus.NEEDS_OPERATOR_RECOVERY
        elif fatal_kind == "shared":
            batch_status = BatchStatus.FAILED
        elif stop_on_point_failure and point_status is not PointStatus.SUCCEEDED:
            batch_status = BatchStatus.FAILED
        elif cancel_requested():
            batch_status = BatchStatus.CANCELLED

    if batch_status is BatchStatus.RUNNING:
        batch_status = BatchStatus.FAILED if any_point_failure else BatchStatus.SUCCEEDED
    try:
        runtime.pause_world()
    except Exception:
        if batch_status is not BatchStatus.NEEDS_OPERATOR_RECOVERY:
            batch_status = BatchStatus.FAILED
            first_shared_failure = first_shared_failure or "WORLD_PAUSE_FAILED"

    manifest = batch_root / "batch-result.json"
    atomic_json(
        manifest,
        {
            "batch_id": request.batch_id,
            "simulation_session_id": request.simulation_session_id,
            "status": batch_status.value,
            "first_shared_failure": first_shared_failure,
            "points": [_point_document(point) for point in point_results],
        },
    )
    _event(
        progress,
        request,
        "BATCH_FINISHED",
        batch_status.value,
        failure_code=first_shared_failure,
    )
    return BatchResult(
        request.batch_id,
        batch_status,
        tuple(point_results),
        first_shared_failure,
        manifest,
    )
