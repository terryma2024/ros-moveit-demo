"""FastAPI transport with machine-readable command result semantics."""

from __future__ import annotations

import asyncio
import ipaddress
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .models import (
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
from .task_artifacts import ArtifactAccessError
from .task_gateway import TaskGatewayError


def validate_bind_address(address: str) -> str:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as error:
        raise ValueError("BIND_ADDRESS_UNSAFE") from error
    if not (parsed.is_loopback or (isinstance(parsed, ipaddress.IPv4Address) and
                                   parsed in ipaddress.ip_network("100.64.0.0/10"))):
        raise ValueError("BIND_ADDRESS_UNSAFE")
    return address


def create_app(
    service,
    static_dir: str | Path | None = None,
    capture_dir: str | Path | None = None,
    task_service=None,
) -> FastAPI:
    app = FastAPI(title="SO-101 Teleop", version="1.0.0")

    @app.get("/health")
    async def health():
        return await service.health()

    @app.get("/snapshot", response_model=TelemetrySnapshot)
    async def snapshot():
        return await service.current_snapshot()

    @app.get("/capabilities", response_model=BackendCapabilitiesResponse)
    async def capabilities():
        return await service.capabilities()

    @app.get("/gazebo/camera/presets")
    async def camera_presets():
        return await service.camera_presets()

    async def command(name: str, body: dict):
        result = await service.command(name, body)
        if getattr(result, "succeeded", False):
            return result
        return JSONResponse(status_code=409 if getattr(result, "code", "").startswith(
            ("PLAN_", "LEASE_", "SERVER_", "CHECKPOINT_", "OVERRIDE_", "SESSION_", "CONFIRMATION_", "READINESS_", "COMMAND_", "WORKFLOW_", "MOVEIT_IK_", "BACKEND_CAPABILITY_")) else 503,
            content=result.dict())

    @app.post("/plans/{plan_id}/execute")
    async def execute(plan_id: str, body: dict):
        result = await service.execute_plan(plan_id, body)
        if not result.succeeded:
            return JSONResponse(
            status_code=409 if result.code.startswith(("PLAN_", "LEASE_", "SERVER_", "SESSION_", "READINESS_", "COMMAND_")) else 503,
                content=result.dict(),
            )
        return result

    @app.post("/control/lease")
    async def acquire_lease(body: dict): return await command("lease", body)
    @app.post("/control/lease/renew")
    async def renew_lease(body: dict): return await command("lease_renew", body)
    @app.post("/plan/joints")
    async def plan_joints(body: dict): return await command("plan_joints", body)
    @app.post("/plan/tcp")
    async def plan_tcp(body: dict): return await command("plan_tcp", body)
    @app.post("/gripper/execute")
    async def gripper(body: dict): return await command("gripper", body)
    @app.post("/execution/cancel")
    async def cancel(body: dict): return await command("cancel", body)
    @app.post("/attachment/{operation}")
    async def attachment(operation: str, body: dict): return await command(f"attachment_{operation}", body)
    @app.post("/scene/repair")
    async def scene_repair(body: dict): return await command("scene_repair", body)
    @app.post("/robot/home")
    async def home(body: dict): return await command("robot_home", body)
    @app.post("/simulation/reset")
    async def reset_simulation(body: dict): return await command("simulation_reset", body)
    @app.post("/gazebo/screenshot")
    async def screenshot(body: dict): return await command("screenshot", body)
    @app.post("/gazebo/camera/presets/{preset}")
    async def camera_preset(preset: str, body: dict):
        return await command("camera_preset", {**body, "preset": preset})
    @app.post("/parameters/{operation}")
    async def parameters(operation: str, body: dict): return await command(f"parameters_{operation}", body)
    @app.post("/workflow/{operation}")
    async def workflow(operation: str, body: dict): return await command(f"workflow_{operation}", body)

    @app.websocket("/telemetry")
    async def telemetry(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                await websocket.send_json((await service.current_snapshot()).dict())
                await service.telemetry_wait()
        except WebSocketDisconnect:
            return

    def task_owner():
        if task_service is None:
            raise RuntimeError("TASK_SERVICE_UNAVAILABLE")
        return task_service

    def task_response(result):
        if isinstance(result, CommandResult) and not result.succeeded:
            code = result.code
            status = 409 if code.startswith((
                "LEASE_", "SESSION_", "COMMAND_", "CONFIRMATION_",
                "TASK_BATCH_", "TASK_RUN_", "TASK_RECOVERY_",
            )) else 503
            return JSONResponse(status_code=status, content=result.model_dump())
        return result

    @app.get("/tasks/presets")
    async def task_presets():
        try:
            return await task_owner().presets()
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.post("/tasks/reachability", response_model=ReachabilityResponse)
    async def task_reachability(body: TaskRunRequest):
        try:
            return task_response(await task_owner().reachability(body))
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.post("/tasks/runs", response_model=TaskRunSummary)
    async def task_start(body: TaskRunRequest):
        try:
            return task_response(await task_owner().start(body))
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.get("/tasks/runs", response_model=list[TaskRunSummary])
    async def task_runs():
        try:
            return await task_owner().list_runs()
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.get("/tasks/runs/{run_id}", response_model=TaskRunSummary)
    async def task_status(run_id: str):
        try:
            return await task_owner().status(run_id)
        except (TaskGatewayError, ValueError):
            return JSONResponse(status_code=404, content={"code": "TASK_RUN_NOT_FOUND"})
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.post("/tasks/runs/{run_id}/cancel", response_model=TaskRunSummary)
    async def task_cancel(run_id: str, body: TaskMutationRequest):
        try:
            return task_response(await task_owner().cancel(run_id, body))
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.post("/tasks/runs/{run_id}/recovery", response_model=TaskRunSummary)
    async def task_recovery(run_id: str, body: TaskRecoveryRequest):
        try:
            return task_response(await task_owner().recovery(run_id, body))
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.post("/tasks/captures", response_model=CaptureResponse)
    async def task_capture(body: TaskCaptureRequest):
        try:
            return task_response(await task_owner().capture(body))
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.post("/tasks/captures/{capture_id}/rendered-image")
    async def task_rendered_image(capture_id: str, body: RenderedImageRequest):
        try:
            return task_response(
                await task_owner().rendered_image(capture_id, body)
            )
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.get("/tasks/artifacts/{artifact_id}")
    async def task_artifact(artifact_id: str):
        try:
            opened = task_owner().artifacts.open(artifact_id)
        except (ArtifactAccessError, RuntimeError):
            return JSONResponse(status_code=404, content={"code": "ARTIFACT_NOT_FOUND"})
        return FileResponse(
            opened.path,
            media_type=opened.media_type,
            filename=opened.path.name,
        )

    @app.post("/tasks/environment/shutdown", response_model=TaskRunSummary)
    async def task_shutdown(body: TaskShutdownRequest):
        try:
            return task_response(await task_owner().shutdown(body))
        except RuntimeError as error:
            return JSONResponse(status_code=503, content={"code": str(error)})

    @app.websocket("/tasks/events")
    async def task_events(websocket: WebSocket):
        if task_service is None:
            await websocket.close(code=1011, reason="TASK_SERVICE_UNAVAILABLE")
            return
        await websocket.accept()
        queue = task_service.subscribe()
        disconnect = asyncio.create_task(websocket.receive())
        try:
            while True:
                event_ready = asyncio.create_task(queue.get())
                done, _pending = await asyncio.wait(
                    {event_ready, disconnect},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if disconnect in done:
                    event_ready.cancel()
                    return
                event = event_ready.result()
                await websocket.send_json(event.model_dump())
        except WebSocketDisconnect:
            return
        finally:
            disconnect.cancel()
            task_service.unsubscribe(queue)

    if capture_dir is not None:
        captures = Path(capture_dir); captures.mkdir(parents=True, exist_ok=True)
        app.mount("/captures", StaticFiles(directory=captures), name="captures")

    if static_dir is not None:
        root = Path(static_dir)
        if root.is_dir() and (root / "index.html").is_file():
            # Symlink-install keeps production Vite chunks as symlinks into
            # web/dist; permit those verified in-tree targets to be served.
            app.mount("/assets", StaticFiles(directory=root / "assets", follow_symlink=True), name="assets")

            @app.get("/", include_in_schema=False)
            async def web_root():
                return FileResponse(root / "index.html")

            @app.get("/{path:path}", include_in_schema=False)
            async def web_fallback(path: str):
                candidate = root / path
                return FileResponse(candidate if candidate.is_file() else root / "index.html")
        else:
            @app.get("/", include_in_schema=False)
            async def web_assets_missing():
                return JSONResponse(status_code=503, content={"code": "WEB_ASSETS_NOT_BUILT"})
    else:
        @app.get("/", include_in_schema=False)
        async def web_assets_not_configured():
            return JSONResponse(status_code=503, content={"code": "WEB_ASSETS_NOT_BUILT"})

    return app
