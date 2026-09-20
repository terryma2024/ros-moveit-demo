"""The single web factory: one service, one port, one bundle.

Routers are extracted from the two former applications and registered by one top-level
factory. Registration order is: concrete API and WebSocket routes, the instance channel,
health, restricted static assets, explicit page paths, and only then the SPA fallback. API
and artifact namespaces are excluded from the fallback, so an unknown API path returns a
JSON 404 instead of an HTML page.
"""

from __future__ import annotations

import asyncio
import inspect
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from so101_teleop.api import validate_bind_address
from so101_teleop.expert_validation.api import (
    CampaignCancelRequest,
    CapabilitiesResponse as _ValidationCapabilitiesResponse,
    CampaignConfiguration,
    CampaignProjectionResponse,
    CampaignStartRequest,
    CapabilitiesResponse,
    LeaseAcquireRequest,
    LeaseMutationRequest,
    LeaseReleaseResponse,
    LeaseResponse,
    ManifestCreateRequest,
    ManifestResponse,
    PreflightResponse,
    RetryRequest,
    _error,
    _invoke,
    _reject_legacy_execution_contract,
)
from so101_teleop.models import (
    BackendCapabilitiesResponse,
    CaptureResponse,
    CommandResult,
    ReachabilityResponse,
    RenderedImageRequest,
    TaskCaptureRequest,
    TaskMutationRequest,
    TaskRecoveryRequest,
    TaskRunRequest,
    TaskRunSummary,
    TaskShutdownRequest,
    TelemetrySnapshot,
)
from so101_teleop.task_artifacts import ArtifactAccessError
from so101_teleop.task_gateway import TaskGatewayError

from .contracts import LeaseIdentity, MutationError, RequestAuthority
from .lifecycle import UnifiedLifecycle
from .ports import UnknownBudgetSource, UnifiedServices

INSTANCE_ID_HEADER = "X-SO101-Instance-ID"
INSTANCE_PROOF_HEADER = "X-SO101-Instance-Proof"
CHANNEL_REVISION_HEADER = "X-SO101-Channel-Revision"
EXECUTION_GENERATION_HEADER = "X-SO101-Execution-Generation"

#: Namespaces that must never be answered with the SPA fallback.
API_NAMESPACES = (
    "tasks",
    "expert-validation",
    "control",
    "snapshot",
    "capabilities",
    "health",
    "plan",
    "plans",
    "gripper",
    "robot",
    "scene",
    "simulation",
    "attachment",
    "parameters",
    "workflow",
    "execution",
    "gazebo",
    "captures",
    "assets",
    "telemetry",
)


class QualificationViewResponse(BaseModel):
    """Pydantic mirror of the budget provider's read-only view; generated into the schema."""

    model_config = ConfigDict(extra="forbid")

    selected_n: int
    status: str
    reasons: list[str]
    runtime_identity: str
    contract_version: int
    profile_sha256: str | None
    approval_sha256: str | None


class CapabilitiesResponse(_ValidationCapabilitiesResponse):
    """Capability payload: the original read-only fields plus worker qualification.

    The model keeps the reviewed contract name that the generated TypeScript client already
    imports, widens ``extra`` to ``allow`` so unknown read-only fields survive, and requires
    the per-N qualification list so it is a real, reachable part of the schema.
    """

    model_config = ConfigDict(extra="allow")

    worker_qualifications: list[QualificationViewResponse]


def unavailable(code: str, message: str, status_code: int = 503) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


def _authority_from_headers(request: Request) -> RequestAuthority:
    instance_id = request.headers.get(INSTANCE_ID_HEADER)
    proof = request.headers.get(INSTANCE_PROOF_HEADER)
    revision = request.headers.get(CHANNEL_REVISION_HEADER)
    generation = request.headers.get(EXECUTION_GENERATION_HEADER)
    if not instance_id or not proof or not revision or not generation:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONTROLLER_INSTANCE_REQUIRED",
                "message": "this mutation needs instance authority headers",
            },
        )
    return RequestAuthority(
        domain="teleop",  # type: ignore[arg-type]
        instance_id=instance_id,
        proof=proof,
        channel_revision=int(revision),
        execution_generation=int(generation),
    )


def require_authority(domain) -> "callable":
    """FastAPI dependency: instance authority first, then the live controller binding."""

    async def dependency(request: Request) -> RequestAuthority:
        instance_id = request.headers.get(INSTANCE_ID_HEADER)
        proof = request.headers.get(INSTANCE_PROOF_HEADER)
        revision = request.headers.get(CHANNEL_REVISION_HEADER)
        generation = request.headers.get(EXECUTION_GENERATION_HEADER)
        if not (instance_id and proof and revision and generation):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONTROLLER_INSTANCE_REQUIRED",
                    "message": "this mutation needs instance authority headers",
                },
            )
        authority = RequestAuthority(
            domain=domain,
            instance_id=instance_id,
            proof=proof,
            channel_revision=int(revision),
            execution_generation=int(generation),
        )
        registry = getattr(request.app.state.services, "instances", None)
        if registry is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "SERVICE_NOT_COMPOSED", "message": "instance registry unavailable"},
            )
        try:
            registry.require_bound(authority)
        except MutationError as error:
            code = str(error).split(":", 1)[0]
            raise HTTPException(status_code=409, detail={"code": code, "message": str(error)}) from error
        return authority

    return dependency


def instance_router(services: UnifiedServices) -> APIRouter:
    router = APIRouter()

    @router.post("/control/instances", tags=["control"])
    async def register_instance(body: dict):
        registry = services.instances
        if registry is None:
            return unavailable("SERVICE_NOT_COMPOSED", "instance registry unavailable")
        domain = body.get("domain")
        try:
            proof = registry.register(domain)
        except (KeyError, ValueError) as error:
            return unavailable("INSTANCE_DOMAIN_INVALID", str(error), 400)
        return {"instance_id": proof.instance_id, "proof": proof.proof, "domain": str(proof.domain)}

    @router.websocket("/control/instances/{instance_id}/channel")
    async def instance_channel(websocket: WebSocket, instance_id: str):
        registry = services.instances
        await websocket.accept()
        if registry is None:
            await websocket.close(code=1011, reason="SERVICE_NOT_COMPOSED")
            return
        try:
            handshake = await websocket.receive_json()
        except (WebSocketDisconnect, ValueError):
            return
        try:
            binding = registry.connect(
                instance_id, handshake.get("proof", ""), origin=handshake.get("origin", "")
            )
        except MutationError as error:
            await websocket.send_json({"code": str(error)})
            await websocket.close(code=1008, reason="CHANNEL_REJECTED")
            return
        await websocket.send_json(
            {"instance_id": binding.instance_id, "revision": binding.revision, "domain": str(binding.domain)}
        )
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            registry.disconnect(binding)
            return

    @router.post("/control/instances/handoff", tags=["control"])
    async def handoff(body: dict):
        registry = services.instances
        if registry is None:
            return unavailable("SERVICE_NOT_COMPOSED", "instance registry unavailable")
        try:
            moved = registry.handoff(body["current"], body["target"], LeaseIdentity(**body["lease"]))
        except (KeyError, TypeError, MutationError) as error:
            return unavailable(str(error).split(":", 1)[0], str(error), 409)
        return {
            "instance_id": moved.instance_id,
            "channel_revision": moved.channel_revision,
            "execution_generation": moved.execution_generation,
        }

    return router


def health_router(services: UnifiedServices) -> APIRouter:
    router = APIRouter()

    @router.get("/health/live")
    async def live():
        lifecycle: UnifiedLifecycle | None = services.lifecycle
        return {
            "live": True,
            "service_epoch": lifecycle.service_epoch if lifecycle else None,
            "started": bool(lifecycle.started) if lifecycle else False,
        }

    @router.get("/health/ready")
    async def ready():
        domains = services.domain_ready()
        blocked = services.arbiter.blocked_reason() if services.arbiter is not None else None
        payload = {"ready": all(value == "ready" for value in domains.values()), "domains": domains}
        if blocked:
            payload["ready"] = False
            payload["blocked_reason"] = blocked
        if services.schema_only:
            payload["ready"] = False
            payload["schema_only"] = True
        return JSONResponse(status_code=200 if payload["ready"] else 503, content=payload)

    @router.get("/health")
    async def health():
        teleop_health: dict = {}
        if services.teleop is not None:
            try:
                teleop_health = await services.teleop.health()
            except Exception as error:  # noqa: BLE001 - a broken domain must not hide health
                teleop_health = {"ok": False, "code": type(error).__name__, "message": str(error)}
        blocked = services.arbiter.blocked_reason() if services.arbiter is not None else None
        return {
            "ok": bool(teleop_health.get("ok", False)),
            "domains": services.domain_ready(),
            "global_state": services.arbiter.state() if services.arbiter is not None else "UNKNOWN",
            "blocked_reason": blocked,
            "teleop": teleop_health,
        }

    return router


def teleop_router(services: UnifiedServices) -> APIRouter:
    router = APIRouter()

    def owner():
        if services.teleop is None:
            return None
        return services.teleop

    async def command(name: str, body: dict):
        service = owner()
        if service is None:
            return unavailable("TELEOP_UNAVAILABLE", "teleop domain is not available")
        result = await service.command(name, body)
        if getattr(result, "succeeded", False):
            return result
        code = getattr(result, "code", "")
        status = 409 if code.startswith(
            (
                "PLAN_", "LEASE_", "SERVER_", "CHECKPOINT_", "OVERRIDE_", "SESSION_",
                "CONFIRMATION_", "READINESS_", "COMMAND_", "WORKFLOW_", "MOVEIT_IK_",
                "BACKEND_CAPABILITY_", "CONTROLLER_", "GLOBAL_MUTATION_", "BLOCKED",
            )
        ) else 503
        return JSONResponse(status_code=status, content=result.model_dump())

    @router.get("/snapshot", response_model=TelemetrySnapshot)
    async def snapshot():
        if owner() is None:
            return unavailable("TELEOP_UNAVAILABLE", "teleop domain is not available")
        return await services.teleop.current_snapshot()

    @router.get("/capabilities", response_model=BackendCapabilitiesResponse)
    async def capabilities():
        if owner() is None:
            return unavailable("TELEOP_UNAVAILABLE", "teleop domain is not available")
        return await services.teleop.capabilities()

    @router.get("/gazebo/camera/presets")
    async def camera_presets():
        if owner() is None:
            return unavailable("TELEOP_UNAVAILABLE", "teleop domain is not available")
        return await services.teleop.camera_presets()

    mutation = Depends(require_authority("teleop"))

    @router.post("/plans/{plan_id}/execute")
    async def execute(plan_id: str, body: dict, authority: RequestAuthority = mutation):
        if owner() is None:
            return unavailable("TELEOP_UNAVAILABLE", "teleop domain is not available")
        result = await services.teleop.execute_plan(plan_id, body)
        if not getattr(result, "succeeded", False):
            code = getattr(result, "code", "")
            status = 409 if code.startswith(
                ("PLAN_", "LEASE_", "SERVER_", "SESSION_", "READINESS_", "COMMAND_", "CONTROLLER_")
            ) else 503
            return JSONResponse(status_code=status, content=result.model_dump())
        return result

    @router.post("/plans/{plan_id}/execute-all")
    async def execute_all(plan_id: str, body: dict, authority: RequestAuthority = mutation):
        if owner() is None or not hasattr(services.teleop, "execute_all"):
            return unavailable("TELEOP_UNAVAILABLE", "teleop domain is not available")
        projection = await services.teleop.execute_all({**body, "plan_id": plan_id}, authority=authority)
        return {
            "operation_id": projection.operation_id,
            "phase": projection.phase,
            "blocked_reason": projection.blocked_reason,
            "children": [
                {
                    "child_id": child.key.child_id,
                    "goal_uuid": child.key.goal_uuid,
                    "succeeded": child.succeeded,
                    "stopped_confirmed": child.stopped_confirmed,
                    "cleanup_confirmed": child.cleanup_confirmed,
                }
                for child in projection.children
            ],
        }

    @router.post("/control/lease")
    async def acquire_lease(body: dict, authority: RequestAuthority = mutation):
        return await command("lease", body)

    @router.post("/control/lease/renew")
    async def renew_lease(body: dict, authority: RequestAuthority = mutation):
        return await command("lease_renew", body)

    @router.post("/plan/joints")
    async def plan_joints(body: dict, authority: RequestAuthority = mutation):
        return await command("plan_joints", body)

    @router.post("/plan/tcp")
    async def plan_tcp(body: dict, authority: RequestAuthority = mutation):
        return await command("plan_tcp", body)

    @router.post("/gripper/execute")
    async def gripper(body: dict, authority: RequestAuthority = mutation):
        return await command("gripper", body)

    @router.post("/execution/cancel")
    async def cancel(body: dict, authority: RequestAuthority = mutation):
        return await command("cancel", body)

    @router.post("/attachment/{operation}")
    async def attachment(operation: str, body: dict, authority: RequestAuthority = mutation):
        return await command(f"attachment_{operation}", body)

    @router.post("/scene/repair")
    async def scene_repair(body: dict, authority: RequestAuthority = mutation):
        return await command("scene_repair", body)

    @router.post("/robot/home")
    async def home(body: dict, authority: RequestAuthority = mutation):
        return await command("robot_home", body)

    @router.post("/simulation/reset")
    async def reset_simulation(body: dict, authority: RequestAuthority = mutation):
        return await command("simulation_reset", body)

    @router.post("/gazebo/screenshot")
    async def screenshot(body: dict, authority: RequestAuthority = mutation):
        return await command("screenshot", body)

    @router.post("/gazebo/camera/presets/{preset}")
    async def camera_preset(preset: str, body: dict, authority: RequestAuthority = mutation):
        return await command("camera_preset", {**body, "preset": preset})

    @router.post("/parameters/{operation}")
    async def parameters(operation: str, body: dict, authority: RequestAuthority = mutation):
        return await command(f"parameters_{operation}", body)

    @router.post("/workflow/{operation}")
    async def workflow(operation: str, body: dict, authority: RequestAuthority = mutation):
        return await command(f"workflow_{operation}", body)

    @router.websocket("/telemetry")
    async def telemetry(websocket: WebSocket):
        await websocket.accept()
        if owner() is None:
            await websocket.close(code=1011, reason="TELEOP_UNAVAILABLE")
            return
        try:
            while True:
                await websocket.send_json((await services.teleop.current_snapshot()).model_dump())
                await services.teleop.telemetry_wait()
        except WebSocketDisconnect:
            return

    return router


def tasks_router(services: UnifiedServices) -> APIRouter:
    router = APIRouter()

    def owner():
        return services.tasks

    async def guarded(call, *args, not_found: tuple[type, ...] = ()):
        service = owner()
        if service is None:
            return unavailable("TASKS_UNAVAILABLE", "task domain is not available")
        try:
            result = await call(service, *args)
        except not_found:
            return JSONResponse(status_code=404, content={"code": "TASK_RUN_NOT_FOUND"})
        except RuntimeError as error:
            return unavailable(str(error), str(error))
        if isinstance(result, CommandResult) and not result.succeeded:
            status = 409 if result.code.startswith(
                ("LEASE_", "SESSION_", "COMMAND_", "CONFIRMATION_", "TASK_BATCH_", "TASK_RUN_",
                 "TASK_RECOVERY_", "CONTROLLER_", "GLOBAL_MUTATION_", "BLOCKED")
            ) else 503
            return JSONResponse(status_code=status, content=result.model_dump())
        return result

    mutation = Depends(require_authority("teleop"))

    @router.get("/tasks/presets")
    async def presets():
        return await guarded(lambda service: service.presets())

    @router.post("/tasks/reachability", response_model=ReachabilityResponse)
    async def reachability(body: TaskRunRequest, authority: RequestAuthority = mutation):
        return await guarded(lambda service: service.reachability(body))

    @router.post("/tasks/runs", response_model=TaskRunSummary)
    async def start(body: TaskRunRequest, authority: RequestAuthority = mutation):
        return await guarded(lambda service: service.start(body))

    @router.get("/tasks/runs", response_model=list[TaskRunSummary])
    async def runs():
        return await guarded(lambda service: service.list_runs())

    @router.get("/tasks/runs/{run_id}", response_model=TaskRunSummary)
    async def status(run_id: str):
        return await guarded(
            lambda service: service.status(run_id), not_found=(TaskGatewayError, ValueError)
        )

    @router.post("/tasks/runs/{run_id}/cancel", response_model=TaskRunSummary)
    async def cancel(run_id: str, body: TaskMutationRequest, authority: RequestAuthority = mutation):
        return await guarded(lambda service: service.cancel(run_id, body))

    @router.post("/tasks/runs/{run_id}/recovery", response_model=TaskRunSummary)
    async def recovery(run_id: str, body: TaskRecoveryRequest, authority: RequestAuthority = mutation):
        return await guarded(lambda service: service.recovery(run_id, body))

    @router.post("/tasks/captures", response_model=CaptureResponse)
    async def capture(body: TaskCaptureRequest, authority: RequestAuthority = mutation):
        return await guarded(lambda service: service.capture(body))

    @router.post("/tasks/captures/{capture_id}/rendered-image")
    async def rendered_image(
        capture_id: str, body: RenderedImageRequest, authority: RequestAuthority = mutation
    ):
        return await guarded(lambda service: service.rendered_image(capture_id, body))

    @router.get("/tasks/artifacts/{artifact_id}")
    async def artifact(artifact_id: str):
        service = owner()
        if service is None:
            return unavailable("TASKS_UNAVAILABLE", "task domain is not available")
        try:
            opened = service.artifacts.open(artifact_id)
        except (ArtifactAccessError, RuntimeError):
            return JSONResponse(status_code=404, content={"code": "ARTIFACT_NOT_FOUND"})
        return FileResponse(opened.path, media_type=opened.media_type, filename=opened.path.name)

    @router.post("/tasks/environment/shutdown", response_model=TaskRunSummary)
    async def shutdown(body: TaskShutdownRequest, authority: RequestAuthority = mutation):
        return await guarded(lambda service: service.shutdown(body))

    @router.websocket("/tasks/events")
    async def events(websocket: WebSocket):
        service = owner()
        if service is None:
            await websocket.close(code=1011, reason="TASKS_UNAVAILABLE")
            return
        await websocket.accept()
        queue = service.subscribe()
        disconnect = asyncio.create_task(websocket.receive())
        try:
            while True:
                event_ready = asyncio.create_task(queue.get())
                done, _pending = await asyncio.wait(
                    {event_ready, disconnect}, return_when=asyncio.FIRST_COMPLETED
                )
                if disconnect in done:
                    event_ready.cancel()
                    return
                await websocket.send_json(event_ready.result().model_dump())
        except WebSocketDisconnect:
            return
        finally:
            disconnect.cancel()
            service.unsubscribe(queue)

    return router


def validation_router(services: UnifiedServices) -> APIRouter:
    router = APIRouter()

    def owner():
        return services.validation

    async def guarded(call, *args, default_status: int = 409):
        service = owner()
        if service is None:
            return unavailable("VALIDATION_UNAVAILABLE", "validation domain is not available")
        try:
            return await call(service, *args)
        except Exception as error:  # noqa: BLE001 - mirrors the standalone surface
            return _error(error, default_status=default_status)

    mutation = Depends(require_authority("validation"))

    @router.get("/expert-validation/capabilities", response_model=CapabilitiesResponse)
    async def capabilities():
        service = owner()
        if service is None:
            return {
                "available": False,
                "reason": "VALIDATION_SERVER_REQUIRED",
                "worker_qualifications": [
                    _qualification_payload(services.budget_source, n) for n in range(2, 9)
                ],
            }
        payload = dict(await _invoke(service.capabilities))
        payload.setdefault(
            "worker_qualifications",
            [_qualification_payload(services.budget_source, n) for n in range(2, 9)],
        )
        return payload

    @router.post("/expert-validation/lease", response_model=LeaseResponse)
    async def acquire_lease(body: LeaseAcquireRequest, authority: RequestAuthority = mutation):
        return await guarded(lambda service: _invoke(service.acquire_lease, body.model_dump()))

    @router.put("/expert-validation/lease/{lease_id}", response_model=LeaseResponse)
    async def renew_lease(
        lease_id: str, body: LeaseMutationRequest, authority: RequestAuthority = mutation
    ):
        return await guarded(lambda service: _invoke(service.renew_lease, lease_id, body.model_dump()))

    @router.delete("/expert-validation/lease/{lease_id}", response_model=LeaseReleaseResponse)
    async def release_lease(
        lease_id: str, body: LeaseMutationRequest, authority: RequestAuthority = mutation
    ):
        return await guarded(lambda service: _invoke(service.release_lease, lease_id, body.model_dump()))

    @router.post("/expert-validation/manifests", response_model=ManifestResponse)
    async def create_manifest(body: ManifestCreateRequest, authority: RequestAuthority = mutation):
        return await guarded(
            lambda service: _invoke(service.create_manifest_from_count, body.total_points)
        )

    @router.get("/expert-validation/manifests/{manifest_id}", response_model=ManifestResponse)
    async def get_manifest(manifest_id: str):
        return await guarded(
            lambda service: _invoke(
                getattr(service, "get_manifest_api", service.get_manifest), manifest_id
            ),
            default_status=404,
        )

    @router.post(
        "/expert-validation/campaigns/preflight",
        response_model=PreflightResponse,
        dependencies=[Depends(_reject_legacy_execution_contract)],
    )
    async def preflight(body: CampaignConfiguration, authority: RequestAuthority = mutation):
        return await guarded(
            lambda service: _invoke(service.preflight_api, body.model_dump(exclude_none=True))
        )

    @router.post(
        "/expert-validation/campaigns",
        response_model=CampaignProjectionResponse,
        dependencies=[Depends(_reject_legacy_execution_contract)],
    )
    async def start_campaign(body: CampaignStartRequest, authority: RequestAuthority = mutation):
        return await guarded(
            lambda service: _invoke(service.start_campaign_api, body.model_dump(exclude_none=True))
        )

    @router.get("/expert-validation/campaigns", response_model=list[CampaignProjectionResponse])
    async def list_campaigns():
        return await guarded(lambda service: _invoke(service.list_campaigns))

    @router.get(
        "/expert-validation/campaigns/{campaign_id}", response_model=CampaignProjectionResponse
    )
    async def get_campaign(campaign_id: str):
        return await guarded(lambda service: _invoke(service.get_campaign, campaign_id), default_status=404)

    @router.post(
        "/expert-validation/campaigns/{campaign_id}/cancel",
        response_model=CampaignProjectionResponse,
    )
    async def cancel_campaign(
        campaign_id: str, body: CampaignCancelRequest, authority: RequestAuthority = mutation
    ):
        return await guarded(
            lambda service: _invoke(service.cancel_campaign, campaign_id, body.model_dump())
        )

    @router.post(
        "/expert-validation/campaigns/{campaign_id}/full-restart-retries",
        response_model=CampaignProjectionResponse,
    )
    async def retry_campaign(campaign_id: str, body: RetryRequest, authority: RequestAuthority = mutation):
        if body.confirmation != "CONFIRM FULL_RESTART RETRIES":
            return JSONResponse(status_code=409, content={"code": "CONFIRMATION_REQUIRED"})
        return await guarded(
            lambda service: _invoke(service.retry_campaign, campaign_id, body.model_dump())
        )

    @router.get("/expert-validation/artifacts/{artifact_id}")
    async def artifact(artifact_id: str):
        service = owner()
        if service is None:
            return unavailable("VALIDATION_UNAVAILABLE", "validation domain is not available")
        try:
            verified = service.artifacts.resolve_opaque_id(artifact_id)
        except (ArtifactAccessError, KeyError, ValueError):
            return JSONResponse(status_code=404, content={"code": "ARTIFACT_NOT_FOUND"})
        return FileResponse(verified.path, media_type=verified.media_type, filename=verified.path.name)

    @router.websocket("/expert-validation/events")
    async def events(websocket: WebSocket):
        service = owner()
        await websocket.accept()
        subscribe = getattr(service, "subscribe", None) if service is not None else None
        if subscribe is None:
            await websocket.close(code=1011, reason="EVENT_STREAM_UNAVAILABLE")
            return
        queue = subscribe()
        try:
            while True:
                await websocket.send_json((await queue.get()).model_dump())
        except WebSocketDisconnect:
            return
        finally:
            service.unsubscribe(queue)

    return router


def _qualification_payload(source, selected_n: int) -> dict:
    view = source.decision(selected_n, "uncomposed-runtime")
    return {
        "selected_n": view.selected_n,
        "status": view.status,
        "reasons": list(view.reasons),
        "runtime_identity": view.runtime_identity,
        "contract_version": view.contract_version,
        "profile_sha256": view.profile_sha256,
        "approval_sha256": view.approval_sha256,
    }


def _mount_static(app: FastAPI, static_dir, capture_dir) -> None:
    if capture_dir is not None:
        captures = Path(capture_dir)
        captures.mkdir(parents=True, exist_ok=True)
        app.mount("/captures", StaticFiles(directory=captures), name="captures")

    root = Path(static_dir) if static_dir is not None else None
    if root is not None and root.is_dir() and (root / "index.html").is_file():
        app.mount(
            "/assets",
            StaticFiles(directory=root / "assets", follow_symlink=True),
            name="assets",
        )
        app.mount(
            "/expert-validation/assets",
            StaticFiles(directory=root / "assets", follow_symlink=True),
            name="validation-assets",
        )

        @app.get("/", include_in_schema=False)
        async def web_root():
            return FileResponse(root / "index.html")

        @app.get("/tasks", include_in_schema=False)
        @app.get("/expert-validation", include_in_schema=False)
        async def compat_pages():
            return FileResponse(root / "index.html")

        @app.get("/{path:path}", include_in_schema=False)
        async def web_fallback(path: str):
            head = path.split("/", 1)[0]
            if head in API_NAMESPACES:
                return JSONResponse(status_code=404, content={"code": "NOT_FOUND"})
            candidate = root / path
            return FileResponse(candidate if candidate.is_file() else root / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        @app.get("/tasks", include_in_schema=False)
        @app.get("/expert-validation", include_in_schema=False)
        async def web_assets_missing():
            return JSONResponse(status_code=503, content={"code": "WEB_ASSETS_NOT_BUILT"})


def lifecycle_for(services: UnifiedServices) -> UnifiedLifecycle:
    if services.lifecycle is None:
        services.lifecycle = UnifiedLifecycle(services)
    return services.lifecycle


def create_unified_app(
    services: UnifiedServices,
    *,
    static_dir: str | Path | None = None,
    capture_dir: str | Path | None = None,
    bind_address: str = "127.0.0.1",
) -> FastAPI:
    validate_bind_address(bind_address)
    lifecycle = lifecycle_for(services)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await lifecycle.startup()
        try:
            yield
        finally:
            await lifecycle.shutdown()

    app = FastAPI(title="SO-101 Unified", version="1.0.0", lifespan=lifespan)
    app.state.services = services

    @app.exception_handler(HTTPException)
    async def structured_http_error(request: Request, error: HTTPException):
        """Structured refusals keep their own JSON body; everything else is untouched."""
        if isinstance(error.detail, dict) and "code" in error.detail:
            return JSONResponse(
                status_code=error.status_code,
                content=error.detail,
                headers=getattr(error, "headers", None),
            )
        return await http_exception_handler(request, error)

    # Registration order is part of the contract: concrete API and WS routes first.
    app.include_router(instance_router(services))
    app.include_router(health_router(services))
    app.include_router(teleop_router(services))
    app.include_router(tasks_router(services))
    app.include_router(validation_router(services))
    _mount_static(app, static_dir, capture_dir)
    return app


class _SchemaOnlyResult:
    def __init__(self) -> None:
        self.code = "SCHEMA_ONLY"
        self.succeeded = False
        self.command_id = "schema"
        self.accepted = False
        self.message = "schema-only service"
        self.snapshot_revision = 0

    def model_dump(self) -> dict:
        return {"code": self.code, "succeeded": False, "message": self.message}


class _SchemaOnlyService:
    """Satisfies route signatures for schema export; performs no side effects."""

    artifacts = None

    async def health(self):
        return {"ok": True}

    async def current_snapshot(self):
        return None

    async def capabilities(self):
        return {}

    async def camera_presets(self):
        return {"presets": []}

    async def telemetry_wait(self):
        return None

    async def command(self, name, body):
        return _SchemaOnlyResult()

    async def execute_plan(self, plan_id, body):
        return _SchemaOnlyResult()

    async def presets(self):
        return {}

    async def reachability(self, body):
        return _SchemaOnlyResult()

    async def start(self, body):
        return _SchemaOnlyResult()

    async def list_runs(self):
        return []

    async def status(self, run_id):
        return _SchemaOnlyResult()

    async def cancel(self, run_id, body):
        return _SchemaOnlyResult()

    async def recovery(self, run_id, body):
        return _SchemaOnlyResult()

    async def capture(self, body):
        return _SchemaOnlyResult()

    async def rendered_image(self, capture_id, body):
        return _SchemaOnlyResult()

    async def shutdown(self, body):
        return _SchemaOnlyResult()

    def subscribe(self, maxsize: int = 64):
        return asyncio.Queue()

    def unsubscribe(self, queue) -> None:
        return None


class _SchemaOnlyValidation:
    artifacts = None

    def health(self):
        return {"ok": True}

    def capabilities(self):
        return {"available": True}


def schema_services() -> UnifiedServices:
    """A schema-only composition: it opens no store and starts no child process."""
    return UnifiedServices(
        teleop=_SchemaOnlyService(),
        tasks=_SchemaOnlyService(),
        validation=_SchemaOnlyValidation(),
        budget_source=UnknownBudgetSource(),
        schema_only=True,
    )


__all__ = [
    "API_NAMESPACES",
    "create_unified_app",
    "health_router",
    "instance_router",
    "schema_services",
    "tasks_router",
    "teleop_router",
    "validation_router",
]
