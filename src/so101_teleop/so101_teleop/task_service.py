"""Lease-gated task lifecycle, event, and evidence application service."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import time
from typing import Awaitable, Callable

import yaml

from .models import (
    CaptureResponse,
    CommandResult,
    ReachabilityResponse,
    RenderedImageRequest,
    TaskCaptureRequest,
    TaskEvent,
    TaskMutationRequest,
    TaskPointModel,
    TaskPointSummary,
    TaskArtifactSummary,
    TaskRecoveryRequest,
    TaskRunRequest,
    TaskRunSummary,
    TaskShutdownRequest,
)
from .task_artifacts import ArtifactAccessError, ManifestArtifactStore
from .task_gateway import (
    TaskCaptureOwnerRequest,
    TaskGatewayError,
    TaskOwnerRequest,
    TaskReachabilityOwnerRequest,
)


_TERMINAL = frozenset(
    {"SUCCEEDED", "FAILED", "CANCELLED", "NEEDS_OPERATOR_RECOVERY", "ERROR"}
)


class TaskService:
    def __init__(
        self,
        teleop,
        gateway,
        artifacts: ManifestArtifactStore,
        *,
        presets: tuple[TaskPointModel, ...],
        policy_path: Path | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.teleop = teleop
        self._gateway = gateway
        self.artifacts = artifacts
        self._presets = tuple(presets)
        self._policy_path = policy_path
        self._monotonic = monotonic
        self._sleep = sleep
        self._active_run_id: str | None = None
        self._run_sessions: dict[str, str] = {}
        self._summaries: dict[str, TaskRunSummary] = {}
        self._finished_events: set[str] = set()
        self._subscribers: set[asyncio.Queue] = set()
        self._event_sequence = 0
        self._commands: dict[str, tuple[str, object]] = {}
        self._command_lock = asyncio.Lock()
        teleop.bind_task_active(self.is_active)

    def is_active(self) -> bool:
        return self._active_run_id is not None

    def subscribe(self, maxsize: int = 64) -> asyncio.Queue:
        if maxsize <= 0 or maxsize > 1024:
            raise ValueError("task event queue size is invalid")
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _emit(
        self,
        kind: str,
        status: str,
        *,
        run_id: str | None = None,
        point_id: str | None = None,
        failure_code: str | None = None,
    ) -> None:
        self._event_sequence += 1
        event = TaskEvent(
            sequence=self._event_sequence,
            kind=kind,
            run_id=run_id,
            point_id=point_id,
            status=status,
            failure_code=failure_code,
        )
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    @staticmethod
    def _body(request) -> dict:
        return request.model_dump()

    @staticmethod
    def _error(request, code: str, message: str) -> CommandResult:
        return CommandResult(
            command_id=request.command_id,
            accepted=False,
            succeeded=False,
            code=code,
            message=message,
        )

    async def _idempotent(
        self,
        request,
        operation: Callable[[], Awaitable[object]],
    ) -> object:
        fingerprint = repr(sorted(self._body(request).items()))
        cached = self._commands.get(request.command_id)
        if cached is not None:
            if cached[0] != fingerprint:
                return self._error(
                    request,
                    "COMMAND_ID_REUSED",
                    "command_id payload differs",
                )
            return cached[1]
        async with self._command_lock:
            cached = self._commands.get(request.command_id)
            if cached is not None:
                if cached[0] != fingerprint:
                    return self._error(
                        request,
                        "COMMAND_ID_REUSED",
                        "command_id payload differs",
                    )
                return cached[1]
            result = await operation()
            self._commands[request.command_id] = (fingerprint, result)
            return result

    def _gate(self, request, capability: str) -> CommandResult | None:
        return self.teleop.task_mutation_gate(self._body(request), capability)

    @staticmethod
    def _points_yaml(request: TaskRunRequest) -> str:
        return yaml.safe_dump(
            {
                "schema_version": 1,
                "points": [
                    {
                        "id": point.id,
                        "label": point.label,
                        "cup_position_world_m": list(point.cup_position_world_m),
                    }
                    for point in request.points
                ],
            },
            sort_keys=False,
        )

    @staticmethod
    def _point_summary(document: dict) -> TaskPointSummary:
        artifact_ids = [
            item["artifact_id"]
            for item in document.get("artifacts", [])
            if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
        ]
        return TaskPointSummary(
            id=str(document.get("id", "unknown")),
            status=str(document.get("status", "UNKNOWN")),
            failure_code=document.get("failure_code"),
            reachability_status=document.get("reachability_status"),
            reset_epoch=document.get("reset_epoch"),
            artifact_ids=artifact_ids,
        )

    def _summary(
        self,
        run_id: str,
        document: dict,
        session_id: str | None = None,
    ) -> TaskRunSummary:
        return TaskRunSummary(
            run_id=run_id,
            status=str(document.get("status", "UNKNOWN")),
            simulation_session_id=(
                session_id
                or str(document.get("simulation_session_id", "unknown"))
            ),
            points=[
                self._point_summary(point)
                for point in document.get("points", [])
                if isinstance(point, dict)
            ],
            first_shared_failure=document.get("first_shared_failure"),
        )

    def _ingest_batch(self, run_id: str) -> None:
        root = self.artifacts.root / "batches" / run_id
        manifest = root / "batch-result.json"
        if manifest.is_file() and not manifest.is_symlink():
            self.artifacts.register_file(
                manifest, "application/json", run_id=run_id
            )
        points = root / "points"
        if not points.is_dir() or points.is_symlink():
            return
        for point_manifest in sorted(points.glob("*/point-result.json")):
            if point_manifest.is_symlink() or not point_manifest.is_file():
                continue
            try:
                document = json.loads(point_manifest.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            self.artifacts.register_file(
                point_manifest, "application/json", run_id=run_id
            )
            for item in document.get("artifacts", []):
                if not isinstance(item, dict):
                    continue
                relative = item.get("relative_path")
                media_type = item.get("media_type")
                if isinstance(relative, str) and isinstance(media_type, str):
                    self.artifacts.register_file(
                        self.artifacts.root / relative,
                        media_type,
                        run_id=run_id,
                    )

    async def presets(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "points": [point.model_dump() for point in self._presets],
        }

    async def start(self, request: TaskRunRequest):
        async def operation():
            if gate := self._gate(request, "task_batch"):
                return gate
            if self.is_active():
                return self._error(
                    request, "TASK_BATCH_ACTIVE", "one task is already active"
                )
            try:
                handle = await self._gateway.start_batch(TaskOwnerRequest(
                    request.session_id,
                    self._points_yaml(request),
                    self.artifacts.root,
                ))
            except TaskGatewayError as error:
                return self._error(request, str(error).split(":", 1)[0], str(error))
            self._active_run_id = handle.run_id
            self._run_sessions[handle.run_id] = request.session_id
            summary = TaskRunSummary(
                run_id=handle.run_id,
                status="RUNNING",
                simulation_session_id=request.session_id,
                points=[
                    TaskPointSummary(id=point.id, status="PENDING")
                    for point in request.points
                ],
            )
            self._summaries[handle.run_id] = summary
            self._emit("BATCH_STARTED", "RUNNING", run_id=handle.run_id)
            return summary

        return await self._idempotent(request, operation)

    async def status(self, run_id: str) -> TaskRunSummary:
        if run_id in self._run_sessions:
            document = await self._gateway.status(run_id)
            summary = self._summary(
                run_id, document, self._run_sessions[run_id]
            )
            self._summaries[run_id] = summary
            if summary.status in _TERMINAL:
                owner_running = document.get("owner_running") is True
                if self._active_run_id == run_id and not owner_running:
                    self._active_run_id = None
                if not owner_running and run_id not in self._finished_events:
                    self._finished_events.add(run_id)
                    self._emit(
                        "BATCH_FINISHED",
                        summary.status,
                        run_id=run_id,
                        failure_code=summary.first_shared_failure,
                    )
                self._ingest_batch(run_id)
            return summary
        path = self.artifacts.root / "batches" / run_id / "batch-result.json"
        if path.is_symlink() or not path.is_file():
            raise TaskGatewayError("TASK_RUN_NOT_FOUND")
        document = json.loads(path.read_text())
        return self._summary(run_id, document)

    async def list_runs(self) -> list[TaskRunSummary]:
        result = dict(self._summaries)
        batches = self.artifacts.root / "batches"
        if batches.is_dir() and not batches.is_symlink():
            for manifest in sorted(batches.glob("*/batch-result.json")):
                run_id = manifest.parent.name
                if run_id in result or manifest.is_symlink():
                    continue
                try:
                    result[run_id] = self._summary(
                        run_id, json.loads(manifest.read_text())
                    )
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
        return [result[key] for key in sorted(result)]

    async def _cancel_now(self, run_id: str, request: TaskMutationRequest):
        if gate := self._gate(request, "task_environment_shutdown"):
            return gate
        if self._active_run_id != run_id:
            return self._error(
                request, "TASK_RUN_NOT_ACTIVE", "task run is not active"
            )
        try:
            document = await self._gateway.cancel(run_id)
        except TaskGatewayError as error:
            return self._error(request, str(error).split(":", 1)[0], str(error))
        summary = self._summary(
            run_id, document, self._run_sessions.get(run_id, request.session_id)
        )
        self._summaries[run_id] = summary
        if summary.status == "CANCELLED":
            self._active_run_id = None
            self._emit("BATCH_FINISHED", summary.status, run_id=run_id)
            self._finished_events.add(run_id)
        return summary

    async def cancel(self, run_id: str, request: TaskMutationRequest):
        return await self._idempotent(
            request, lambda: self._cancel_now(run_id, request)
        )

    async def reachability(self, request: TaskRunRequest):
        async def operation():
            if gate := self._gate(request, "task_reachability"):
                return gate
            if self.is_active():
                return self._error(
                    request, "TASK_BATCH_ACTIVE", "one task is already active"
                )
            if self._policy_path is None:
                return self._error(
                    request, "TASK_POLICY_UNAVAILABLE", "task policy is unavailable"
                )
            try:
                handle = await self._gateway.start_batch(
                    TaskReachabilityOwnerRequest(
                        request.session_id,
                        self._points_yaml(request),
                        self.artifacts.root,
                        self._policy_path,
                    )
                )
                self._active_run_id = handle.run_id
                deadline = self._monotonic() + 190.0
                while True:
                    document = await self._gateway.status(handle.run_id)
                    if (
                        document.get("status") != "RUNNING"
                        and document.get("owner_running") is not True
                    ):
                        break
                    if self._monotonic() >= deadline:
                        document = await self._gateway.cancel(handle.run_id)
                        return self._error(
                            request,
                            "TASK_REACHABILITY_TIMEOUT",
                            "reachability owner timed out",
                        )
                    await self._sleep(0.05)
            except TaskGatewayError as error:
                return self._error(request, str(error).split(":", 1)[0], str(error))
            finally:
                if "document" in locals() and document.get("status") != "CANCEL_TIMEOUT":
                    self._active_run_id = None
            self._emit("REACHABILITY_FINISHED", str(document["status"]))
            return ReachabilityResponse(
                status=str(document["status"]),
                reports=list(document.get("reports", [])),
                simulation_session_id=request.session_id,
            )

        return await self._idempotent(request, operation)

    async def capture(self, request: TaskCaptureRequest):
        async def operation():
            if gate := self._gate(request, "sensor_capture"):
                return gate
            try:
                document = await self._gateway.capture(TaskCaptureOwnerRequest(
                    request.session_id, self.artifacts.root
                ))
            except TaskGatewayError as error:
                return self._error(request, str(error).split(":", 1)[0], str(error))
            capture_id = str(document.get("capture_id", ""))
            output = Path(str(document.get("output_directory", "")))
            expected = self.artifacts.root / "captures" / capture_id
            if output.absolute() != expected.absolute() or output.is_symlink():
                return self._error(
                    request, "TASK_CAPTURE_PATH_INVALID", "capture path is invalid"
                )
            artifact_ids = []
            artifacts = []
            media = {
                ".png": "image/png",
                ".ply": "application/octet-stream",
                ".json": "application/json",
            }
            for path in sorted(output.iterdir()):
                if path.is_file() and not path.is_symlink():
                    record = self.artifacts.register_file(
                        path,
                        media.get(path.suffix.lower(), "application/octet-stream"),
                        capture_id=capture_id,
                    )
                    artifact_ids.append(record.artifact_id)
                    artifacts.append(TaskArtifactSummary(
                        artifact_id=record.artifact_id,
                        name=path.name,
                        media_type=record.media_type,
                        byte_size=record.byte_size,
                        sha256=record.sha256,
                    ))
            summary: dict[str, object] = {}
            summary_path = output / "summary.json"
            if summary_path.is_file() and not summary_path.is_symlink():
                loaded = json.loads(summary_path.read_text())
                if isinstance(loaded, dict):
                    summary = loaded
            stamp = summary.get("source_stamp_ns")
            return CaptureResponse(
                capture_id=capture_id,
                status=str(document.get("status", "SUCCEEDED")),
                artifact_ids=artifact_ids,
                source_stamp_ns=stamp if isinstance(stamp, int) and stamp >= 0 else None,
                summary=summary,
                artifacts=artifacts,
            )

        return await self._idempotent(request, operation)

    async def rendered_image(
        self, capture_id: str, request: RenderedImageRequest
    ):
        async def operation():
            if gate := self._gate(request, "sensor_capture"):
                return gate
            try:
                png = base64.b64decode(request.png_base64, validate=True)
                record = self.artifacts.register_rendered_image(
                    capture_id,
                    request.source_artifact_id,
                    png,
                    {
                        "view_matrix": request.view_matrix,
                        "projection_matrix": request.projection_matrix,
                        "point_size": request.point_size,
                        "color_mode": request.color_mode,
                        "background_rgb": request.background_rgb,
                        "viewport_px": request.viewport_px,
                        "source_sha256": request.source_sha256,
                        "original_point_count": request.original_point_count,
                        "displayed_point_count": request.displayed_point_count,
                        "sampling_rule": request.sampling_rule,
                        "sampling_stride": request.sampling_stride,
                        "captured_at": request.captured_at,
                    },
                )
            except (ValueError, ArtifactAccessError) as error:
                return self._error(request, str(error).split(":", 1)[0], str(error))
            return {"artifact_id": record.artifact_id}

        return await self._idempotent(request, operation)

    async def recovery(self, run_id: str, request: TaskRecoveryRequest):
        async def operation():
            if request.confirmation != "CONFIRM TASK RECOVERY":
                return self._error(
                    request, "CONFIRMATION_REQUIRED",
                    "task recovery confirmation required",
                )
            if request.action == "stop":
                return await self._cancel_now(run_id, request)
            return self._error(
                request,
                "TASK_RECOVERY_RESTART_REQUIRED",
                "reset-and-continue requires a new explicit batch",
            )

        return await self._idempotent(request, operation)

    async def shutdown(self, request: TaskShutdownRequest):
        async def operation():
            if request.confirmation != "CONFIRM TASK ENVIRONMENT SHUTDOWN":
                return self._error(
                    request, "CONFIRMATION_REQUIRED", "shutdown confirmation required"
                )
            if self._active_run_id is None:
                return self._error(
                    request, "TASK_ENVIRONMENT_NOT_OWNED", "no owned task environment"
                )
            return await self._cancel_now(self._active_run_id, request)

        return await self._idempotent(request, operation)
