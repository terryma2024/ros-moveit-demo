"""Fail-closed adapter for fixed package-installed backend executables."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import uuid
from typing import Callable

from .profile import BackendProfile, ExecutableSpec
from .protocol import (
    BackendEnvelope,
    BackendError,
    BackendOperation,
    CameraPresetRequest,
    ResetRequest,
    SceneRequest,
    WorkflowRequest,
)


_CAPTURE_LIMIT = 16_384
_FAILURE_CODE = re.compile(r"(?:failure|failure_code)=([A-Z][A-Z0-9_]*)")


def build_scene_args(spec: ExecutableSpec, request: SceneRequest) -> list[str]:
    if spec.scene_style == "positional":
        return [request.operation]
    if spec.scene_style == "flag":
        return ["--operation", request.operation]
    raise ValueError("BACKEND_PROFILE_SCENE_STYLE_INVALID")


def _workflow_args(request: WorkflowRequest) -> list[str]:
    args = [
        "--mode", "execute", "--checkpoint", str(request.checkpoint),
        "--session-id", request.session_id,
    ]
    if request.operation == "start":
        args.append("--step")
    elif request.operation == "step":
        args.extend(("--resume", "true", "--step"))
    elif request.operation in {"resume", "force-continue"}:
        args.extend(("--resume", "true"))
    if request.operation == "force-continue":
        args.append("--force-continue")
    return args


def _parse_result(stdout: str, allow_empty: bool) -> dict | None:
    text = stdout.strip()
    if not text:
        return {"status": "SUCCEEDED"} if allow_empty else None
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    pairs = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        key = key.strip()
        if separator and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key):
            pairs[key] = value.strip()
    if "trace" not in pairs and "state_trace" in pairs:
        pairs["trace"] = " -> ".join(
            state.strip()
            for state in pairs["state_trace"].split(",")
            if state.strip()
        )
    return pairs or None


def _safe_session(value: str | None) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "no-session")
    return sanitized[:80] or "no-session"


class CliBackendAdapter:
    def __init__(
        self,
        profile: BackendProfile,
        package_prefix_resolver: Callable[[str], str] | None = None,
        run_process: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        diagnostics_root: Path = Path("/tmp/so101-teleop"),
    ) -> None:
        self.profile = profile
        if package_prefix_resolver is None:
            from ament_index_python.packages import get_package_prefix
            package_prefix_resolver = get_package_prefix
        self._package_prefix_resolver = package_prefix_resolver
        self._run_process = run_process
        self._diagnostics_root = Path(diagnostics_root)

    def capabilities(self):
        return self.profile.capabilities

    def _envelope(
        self,
        operation: str,
        spec: ExecutableSpec,
        session_id: str | None,
        *,
        ok: bool,
        exit_code: int | None = None,
        result: dict | None = None,
        error: BackendError | None = None,
    ) -> BackendEnvelope:
        return BackendEnvelope(
            ok=ok,
            backend=self.profile.backend,
            operation=operation,
            session_id=session_id,
            owner_package=spec.package,
            owner_executable=spec.executable,
            exit_code=exit_code,
            result=result,
            error=error,
        )

    def _resolve(self, spec: ExecutableSpec) -> tuple[Path | None, BackendError | None]:
        try:
            prefix = Path(self._package_prefix_resolver(spec.package))
        except Exception as error:
            return None, BackendError("BACKEND_PACKAGE_NOT_FOUND", str(error))
        executable = prefix / "lib" / spec.package / spec.executable
        if not executable.is_file() or not os.access(executable, os.X_OK):
            return None, BackendError(
                "BACKEND_EXECUTABLE_NOT_FOUND",
                f"installed executable is absent or not executable: {executable}",
            )
        return executable, None

    def probe(self) -> BackendEnvelope:
        spec = self.profile.probe
        executable, error = self._resolve(spec)
        if error is not None:
            return self._envelope("backend_probe", spec, None, ok=False, error=error)
        return self._envelope(
            "backend_probe", spec, None, ok=True, exit_code=0,
            result={"executable": str(executable)},
        )

    def _unsupported(self, operation: str, session_id: str | None) -> BackendEnvelope:
        return self._envelope(
            operation,
            self.profile.probe,
            session_id,
            ok=False,
            error=BackendError(
                "BACKEND_CAPABILITY_UNAVAILABLE",
                f"{operation} is unavailable for backend {self.profile.backend}",
            ),
        )

    def _write_diagnostic(
        self,
        operation: str,
        session_id: str | None,
        argv: list[str],
        returncode: int | None,
        stdout: str,
        stderr: str,
    ) -> None:
        directory = self._diagnostics_root / _safe_session(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"last-{operation}.log"
        temporary = directory / f".{target.name}.{uuid.uuid4()}.tmp"
        temporary.write_text(
            f"argv={argv!r}\nreturncode={returncode!r}\n"
            f"--- stdout ---\n{stdout[-_CAPTURE_LIMIT:]}\n"
            f"--- stderr ---\n{stderr[-_CAPTURE_LIMIT:]}\n"
        )
        os.replace(temporary, target)

    def _invoke(
        self,
        operation: str,
        spec: ExecutableSpec,
        session_id: str | None,
        arguments: list[str],
        *,
        allow_empty: bool = False,
    ) -> BackendEnvelope:
        executable, error = self._resolve(spec)
        if error is not None:
            return self._envelope(operation, spec, session_id, ok=False, error=error)
        argv = [str(executable), *spec.fixed_args, *arguments]
        try:
            completed = self._run_process(
                argv,
                text=True,
                capture_output=True,
                timeout=spec.timeout_s,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            self._write_diagnostic(operation, session_id, argv, None, stdout, stderr)
            return self._envelope(
                operation, spec, session_id, ok=False,
                error=BackendError("BACKEND_TIMEOUT", str(error)),
            )
        except OSError as error:
            self._write_diagnostic(operation, session_id, argv, None, "", str(error))
            return self._envelope(
                operation, spec, session_id, ok=False,
                error=BackendError("BACKEND_EXECUTION_FAILED", str(error)),
            )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode:
            combined = f"{stdout}\n{stderr}"
            match = _FAILURE_CODE.search(combined)
            self._write_diagnostic(
                operation, session_id, argv, completed.returncode, stdout, stderr
            )
            return self._envelope(
                operation, spec, session_id, ok=False,
                exit_code=completed.returncode,
                error=BackendError(
                    "BACKEND_OPERATION_FAILED",
                    f"owner exited with {completed.returncode}",
                    match.group(1) if match else None,
                ),
            )
        result = _parse_result(stdout, allow_empty)
        if result is None:
            self._write_diagnostic(
                operation, session_id, argv, completed.returncode, stdout, stderr
            )
            return self._envelope(
                operation, spec, session_id, ok=False,
                exit_code=completed.returncode,
                error=BackendError(
                    "BACKEND_OUTPUT_INVALID", "owner output has no structured result"
                ),
            )
        return self._envelope(
            operation, spec, session_id, ok=True,
            exit_code=completed.returncode, result=result,
        )

    def run_workflow(self, request: WorkflowRequest) -> BackendEnvelope:
        capability = {
            "start": self.profile.capabilities.workflow_start,
            "run": self.profile.capabilities.workflow_run,
            "step": self.profile.capabilities.workflow_resume,
            "resume": self.profile.capabilities.workflow_resume,
            "force-continue": self.profile.capabilities.workflow_resume,
        }[request.operation]
        spec = self.profile.operations.get(BackendOperation.WORKFLOW)
        if not self.profile.capabilities.workflow_execute or not capability or spec is None:
            return self._unsupported(f"workflow_{request.operation}", request.session_id)
        return self._invoke(
            f"workflow_{request.operation}", spec, request.session_id,
            _workflow_args(request),
        )

    def reset_world(self, request: ResetRequest) -> BackendEnvelope:
        spec = self.profile.operations.get(BackendOperation.RESET_WORLD)
        if not self.profile.capabilities.reset_world or spec is None:
            return self._unsupported("reset_world", request.session_id)
        arguments = (
            ["--session-id", request.session_id]
            if spec.session_style == "flag"
            else []
        )
        return self._invoke(
            "reset_world", spec, request.session_id, arguments, allow_empty=True
        )

    def scene_operation(self, request: SceneRequest) -> BackendEnvelope:
        spec = self.profile.operations.get(BackendOperation.SCENE)
        if not self.profile.capabilities.scene_operations or spec is None:
            return self._unsupported(f"scene_{request.operation}", request.session_id)
        return self._invoke(
            f"scene_{request.operation}", spec, request.session_id,
            build_scene_args(spec, request),
        )

    def apply_camera_preset(self, request: CameraPresetRequest) -> BackendEnvelope:
        spec = self.profile.operations.get(BackendOperation.CAMERA_PRESET)
        if not self.profile.capabilities.camera_presets or spec is None:
            return self._unsupported("camera_preset", request.session_id)
        if request.preset not in self.profile.camera_presets:
            return self._envelope(
                "camera_preset", spec, request.session_id, ok=False,
                error=BackendError(
                    "CAMERA_PRESET_NOT_FOUND",
                    f"unknown preset {request.preset!r} for {self.profile.backend}",
                ),
            )
        return self._invoke(
            "camera_preset", spec, request.session_id, [request.preset],
            allow_empty=True,
        )
