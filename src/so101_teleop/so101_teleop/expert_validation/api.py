"""Dedicated FastAPI surface for expert-validation campaigns."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import inspect
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from so101_teleop.api import validate_bind_address
from so101_teleop.task_artifacts import ArtifactAccessError


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LeaseAcquireRequest(ClosedModel):
    service_session_id: str = Field(min_length=1)


class LeaseMutationRequest(ClosedModel):
    service_session_id: str = Field(min_length=1)
    generation: int = Field(ge=1)


class ManifestCreateRequest(ClosedModel):
    total_points: int = Field(ge=4, le=20)


class CampaignConfiguration(ClosedModel):
    service_session_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_generation: int = Field(ge=1)
    manifest_id: str = Field(min_length=1)
    execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"]
    worker_count: int | None = Field(default=None, ge=1, le=3)
    max_points_per_worker: int | None = Field(default=None, ge=1, le=20)
    preferred_worker_count: int | None = Field(default=None, ge=1, le=16)
    fallback_worker_counts: tuple[int, ...] | None = None
    initial_points_per_worker: int | None = Field(default=None, ge=1, le=20)
    worker_start_timeout_s: float | None = Field(default=None, gt=0)
    max_infra_attempts_per_point: int | None = Field(default=None, ge=1)
    yolo_executor_count: Literal[1, 2, 4] | None = None

    @model_validator(mode="after")
    def validate_mode(self):
        fixed = (self.worker_count, self.max_points_per_worker)
        adaptive = (
            self.preferred_worker_count,
            self.fallback_worker_counts,
            self.initial_points_per_worker,
            self.worker_start_timeout_s,
            self.max_infra_attempts_per_point,
            self.yolo_executor_count,
        )
        if self.execution_mode in {"SEQUENTIAL", "PARALLEL"}:
            if any(value is None for value in fixed) or any(value is not None for value in adaptive):
                raise ValueError("FIXED_EXECUTION_CONFIG")
            if self.execution_mode == "SEQUENTIAL" and self.worker_count != 1:
                raise ValueError("SEQUENTIAL_WORKER_COUNT")
            if self.execution_mode == "PARALLEL" and not 2 <= self.worker_count <= 3:
                raise ValueError("PARALLEL_WORKER_COUNT")
        else:
            if any(value is not None for value in fixed):
                raise ValueError("ADAPTIVE_FIXED_FIELD")
            if any(value is None for value in adaptive):
                raise ValueError("ADAPTIVE_EXECUTION_CONFIG")
            levels = (self.preferred_worker_count, *self.fallback_worker_counts)
            if any(next_level >= level for level, next_level in zip(levels, levels[1:])):
                raise ValueError("ADAPTIVE_FALLBACK_TIERS")
            if self.yolo_executor_count != 2:
                raise ValueError("ADAPTIVE_YOLO_EXECUTOR_COUNT")
        return self


class CampaignStartRequest(CampaignConfiguration):
    command_id: str = Field(min_length=1)
    preflight_receipt_id: str = Field(min_length=1)


class CampaignCancelRequest(ClosedModel):
    service_session_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_generation: int = Field(ge=1)
    command_id: str = Field(min_length=1)


class RetryRequest(CampaignCancelRequest):
    point_ids: tuple[str, ...] = Field(min_length=1)
    confirmation: str


class CapabilitiesResponse(ClosedModel):
    available: bool
    execution_modes: tuple[Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"], ...] = ()
    default_execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"] = "SEQUENTIAL"
    minimum_points: int = 4
    maximum_points: int = 20
    fixed_worker_counts: tuple[int, ...] = (1, 2, 3)
    fixed_max_points_per_worker: int = 20
    adaptive_default_ladder: tuple[int, ...] = (8, 6, 4, 2, 1)
    lease_duration_s: float = 30.0
    lease_renewal_margin_s: float = 10.0


class LeaseResponse(ClosedModel):
    lease_id: str
    service_session_id: str
    generation: int
    expires_monotonic_ns: int


class LeaseReleaseResponse(ClosedModel):
    lease_id: str
    released: bool


class ManifestPointResponse(ClosedModel):
    id: str
    display_id: str
    label: str
    source: Literal["anchor", "generated"]
    stratum: str
    position_world_m: tuple[float, float, float]


class ManifestResponse(ClosedModel):
    manifest_id: str
    point_count: int = 0
    catalog_sha256: str | None = None
    selection_sha256: str | None = None
    stale: bool = False
    points: tuple[ManifestPointResponse, ...] = ()


class PreflightResponse(ClosedModel):
    receipt_id: str
    admitted: bool
    manifest_id: str | None = None
    execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"] | None = None
    execution_config: dict[str, object] = {}
    resource_observations: dict[str, object] = {}
    reason_codes: tuple[str, ...] = ()
    expires_at_monotonic_ns: int | None = None


class AttemptProjectionResponse(ClosedModel):
    generation: int
    status: str
    reason: str | None = None
    kind: Literal["FIRST_PASS", "FULL_RESTART_RETRY"] = "FIRST_PASS"
    attempt_id: str | None = None
    worker_id: str | None = None
    worker_generation: int | None = None
    batch_id: str | None = None


class ArtifactProjectionResponse(ClosedModel):
    artifact_id: str
    campaign_id: str
    batch_id: str
    pool_generation: int | None = None
    worker_id: str | None = None
    worker_generation: int | None = None
    attempt_id: str | None = None
    role: str
    media_type: str
    size_bytes: int
    sha256: str


class PointProjectionResponse(ClosedModel):
    point_id: str
    display_id: str | None = None
    status: str
    retry_eligible: bool = False
    active_worker_id: str | None = None
    reason: str | None = None
    attempts: tuple[AttemptProjectionResponse, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    artifacts: tuple[ArtifactProjectionResponse, ...] = ()


class WorkerProjectionResponse(ClosedModel):
    worker_id: str
    generation: int
    state: str
    current_point_id: str | None = None
    lease_count: int = 0
    max_points_per_worker: int | None = None
    heartbeat_deadline_monotonic_s: float | None = None
    recovery_result: str | None = None
    quarantine_reason: str | None = None


class BrokerProjectionResponse(ClosedModel):
    available: bool
    reason: str | None = None


class CampaignProjectionResponse(ClosedModel):
    campaign_id: str
    sequence: int
    execution_mode: Literal["SEQUENTIAL", "PARALLEL", "ADAPTIVE"] | None = None
    owner_kind: Literal["COORDINATOR", "ADAPTIVE_WRAPPER"] | None = None
    batch_id: str | None = None
    status: str | None = None
    points: tuple[PointProjectionResponse, ...] = ()
    workers: tuple[WorkerProjectionResponse, ...] = ()
    broker: BrokerProjectionResponse | None = None
    requested: int = 0
    evaluated: int = 0
    execution_started: int = 0
    valid_succeeded: int = 0
    valid_failed: int = 0
    indeterminate: int = 0
    not_executed: int = 0
    evaluation_coverage: float = 0.0
    execution_coverage: float = 0.0
    qualified_success_rate: float | None = None
    coverage_complete: bool | None = None
    execution_complete: bool | None = None
    batch_cleanup_complete: bool = False
    qualification_passed: bool | None = None
    levels_used: tuple[int, ...] = ()
    fallback_history: tuple[dict[str, object], ...] = ()
    current_generation: int | None = None
    infra_attempts: int = 0
    resource_observations: dict[str, object] = {}


async def _invoke(method, *args):
    value = method(*args)
    return await value if inspect.isawaitable(value) else value


def _error(error: Exception, *, default_status: int = 409) -> JSONResponse:
    code = str(error) or type(error).__name__
    return JSONResponse(status_code=default_status, content={"code": code})


def create_expert_validation_app(
    service,
    static_dir: str | Path | None = None,
    *,
    bind_address: str = "127.0.0.1",
) -> FastAPI:
    validate_bind_address(bind_address)

    async def maintain_lease(app):
        lease_service = getattr(service, "lease_service", None)
        expire_due = getattr(lease_service, "expire_due", None)
        if expire_due is None:
            return
        while True:
            try:
                expire_due()
            except Exception:
                app.state.lease_maintenance_failed = True
                logging.getLogger(__name__).exception("LEASE_MAINTENANCE_FAILED")
                supervisor = getattr(service, "supervisor", None)
                cancel = getattr(supervisor, "cancel_for_reason", None)
                if cancel is not None:
                    try:
                        await _invoke(cancel, "LEASE_MAINTENANCE_FAILED")
                    except Exception:
                        logging.getLogger(__name__).exception("LEASE_OWNER_CANCEL_FAILED")
                return
            await asyncio.sleep(0.25)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(maintain_lease(app))
        try:
            await asyncio.sleep(0)
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="SO-101 Expert Validation", version="1.0.0", lifespan=lifespan)
    app.state.lease_maintenance_failed = False

    @app.middleware("http")
    async def fence_failed_maintenance(request: Request, call_next):
        if (
            app.state.lease_maintenance_failed
            and request.method not in {"GET", "HEAD", "OPTIONS"}
            and not request.url.path.endswith("/cancel")
        ):
            return JSONResponse(status_code=503, content={"code": "LEASE_MAINTENANCE_FAILED"})
        return await call_next(request)

    @app.get("/health")
    async def health():
        if app.state.lease_maintenance_failed:
            return JSONResponse(status_code=503, content={"code": "LEASE_MAINTENANCE_FAILED"})
        return await _invoke(service.health)

    @app.get("/expert-validation/capabilities", response_model=CapabilitiesResponse)
    async def capabilities():
        return await _invoke(service.capabilities)

    @app.post("/expert-validation/lease", response_model=LeaseResponse)
    async def acquire_lease(body: LeaseAcquireRequest):
        try:
            return await _invoke(service.acquire_lease, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.put("/expert-validation/lease/{lease_id}", response_model=LeaseResponse)
    async def renew_lease(lease_id: str, body: LeaseMutationRequest):
        try:
            return await _invoke(service.renew_lease, lease_id, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.delete("/expert-validation/lease/{lease_id}", response_model=LeaseReleaseResponse)
    async def release_lease(lease_id: str, body: LeaseMutationRequest):
        try:
            return await _invoke(service.release_lease, lease_id, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.post("/expert-validation/manifests", response_model=ManifestResponse)
    async def create_manifest(body: ManifestCreateRequest):
        try:
            return await _invoke(service.create_manifest_from_count, body.total_points)
        except Exception as error:
            return _error(error)

    @app.get("/expert-validation/manifests/{manifest_id}", response_model=ManifestResponse)
    async def get_manifest(manifest_id: str):
        try:
            method = getattr(service, "get_manifest_api", service.get_manifest)
            return await _invoke(method, manifest_id)
        except Exception as error:
            return _error(error, default_status=404)

    @app.post("/expert-validation/campaigns/preflight", response_model=PreflightResponse)
    async def preflight(body: CampaignConfiguration):
        try:
            return await _invoke(service.preflight_api, body.model_dump(exclude_none=True))
        except Exception as error:
            return _error(error)

    @app.post("/expert-validation/campaigns", response_model=CampaignProjectionResponse)
    async def start_campaign(body: CampaignStartRequest):
        try:
            return await _invoke(service.start_campaign_api, body.model_dump(exclude_none=True))
        except Exception as error:
            return _error(error)

    @app.get("/expert-validation/campaigns", response_model=list[CampaignProjectionResponse])
    async def list_campaigns():
        return await _invoke(service.list_campaigns)

    @app.get(
        "/expert-validation/campaigns/{campaign_id}",
        response_model=CampaignProjectionResponse,
    )
    async def get_campaign(campaign_id: str):
        try:
            return await _invoke(service.get_campaign, campaign_id)
        except Exception as error:
            return _error(error, default_status=404)

    @app.post(
        "/expert-validation/campaigns/{campaign_id}/cancel",
        response_model=CampaignProjectionResponse,
    )
    async def cancel_campaign(campaign_id: str, body: CampaignCancelRequest):
        try:
            return await _invoke(service.cancel_campaign, campaign_id, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.post(
        "/expert-validation/campaigns/{campaign_id}/full-restart-retries",
        response_model=CampaignProjectionResponse,
    )
    async def retry_campaign(campaign_id: str, body: RetryRequest):
        if body.confirmation != "CONFIRM FULL_RESTART RETRIES":
            return JSONResponse(status_code=409, content={"code": "CONFIRMATION_REQUIRED"})
        try:
            return await _invoke(service.retry_campaign, campaign_id, body.model_dump())
        except Exception as error:
            return _error(error)

    @app.get("/expert-validation/artifacts/{artifact_id}")
    async def artifact(artifact_id: str):
        try:
            verified = service.artifacts.resolve_opaque_id(artifact_id)
        except (ArtifactAccessError, KeyError, ValueError):
            return JSONResponse(status_code=404, content={"code": "ARTIFACT_NOT_FOUND"})
        return FileResponse(
            verified.path,
            media_type=verified.media_type,
            filename=verified.path.name,
        )

    @app.websocket("/expert-validation/events")
    async def events(websocket: WebSocket):
        await websocket.accept()
        subscribe = getattr(service, "subscribe", None)
        if subscribe is None:
            await websocket.close(code=1011, reason="EVENT_STREAM_UNAVAILABLE")
            return
        queue = subscribe()

        async def send_events():
            while True:
                event = await queue.get()
                await websocket.send_json(
                    event.model_dump() if hasattr(event, "model_dump") else event
                )

        async def receive_disconnect():
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return

        tasks = {
            asyncio.create_task(send_events()),
            asyncio.create_task(receive_disconnect()),
        }
        try:
            completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                task.result()
        except WebSocketDisconnect:
            return
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            unsubscribe = getattr(service, "unsubscribe", None)
            if unsubscribe is not None:
                unsubscribe(queue)

    @app.post("/tasks/runs")
    async def disabled_task_runs():
        return JSONResponse(status_code=503, content={"code": "VALIDATION_TASKS_DISABLED"})

    @app.api_route(
        "/tasks/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        include_in_schema=False,
    )
    async def disabled_tasks(path: str):
        return JSONResponse(status_code=503, content={"code": "VALIDATION_TASKS_DISABLED"})

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse("/expert-validation", status_code=307)

    if static_dir is not None:
        root = Path(static_dir)
        if root.is_dir() and (root / "index.html").is_file():
            # The shared Vite build emits absolute /assets URLs for both SPAs.
            app.mount(
                "/assets",
                StaticFiles(directory=root / "assets"),
                name="validation-vite-assets",
            )
            app.mount(
                "/expert-validation/assets",
                StaticFiles(directory=root / "assets", follow_symlink=True),
                name="expert-validation-assets",
            )

            @app.get("/expert-validation", include_in_schema=False)
            async def validation_page():
                return FileResponse(root / "index.html")

            @app.get("/expert-validation/{path:path}", include_in_schema=False)
            async def validation_fallback(path: str):
                candidate = root / path
                return FileResponse(candidate if candidate.is_file() else root / "index.html")
        else:
            @app.get("/expert-validation", include_in_schema=False)
            async def validation_assets_missing():
                return JSONResponse(status_code=503, content={"code": "WEB_ASSETS_NOT_BUILT"})
    else:
        @app.get("/expert-validation", include_in_schema=False)
        async def validation_assets_unconfigured():
            return JSONResponse(status_code=503, content={"code": "WEB_ASSETS_NOT_BUILT"})

    return app
