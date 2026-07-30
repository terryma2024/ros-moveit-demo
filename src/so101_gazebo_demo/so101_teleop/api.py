"""FastAPI transport with machine-readable command result semantics."""

from __future__ import annotations

import ipaddress
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse


def validate_bind_address(address: str) -> str:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as error:
        raise ValueError("BIND_ADDRESS_UNSAFE") from error
    if not (parsed.is_loopback or (isinstance(parsed, ipaddress.IPv4Address) and
                                   parsed in ipaddress.ip_network("100.64.0.0/10"))):
        raise ValueError("BIND_ADDRESS_UNSAFE")
    return address


def create_app(service, static_dir: str | Path | None = None, capture_dir: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="SO-101 Teleop", version="1.0.0")

    @app.get("/health")
    async def health():
        return await service.health()

    @app.get("/snapshot")
    async def snapshot():
        return await service.current_snapshot()

    @app.get("/capabilities")
    async def capabilities():
        return await service.capabilities()

    async def command(name: str, body: dict):
        result = await service.command(name, body)
        if getattr(result, "succeeded", False):
            return result
        return JSONResponse(status_code=409 if getattr(result, "code", "").startswith(
            ("PLAN_", "LEASE_", "SERVER_", "CHECKPOINT_", "OVERRIDE_", "SESSION_", "CONFIRMATION_", "READINESS_", "COMMAND_", "WORKFLOW_", "MOVEIT_IK_")) else 503,
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
