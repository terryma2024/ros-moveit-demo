"""Narrow asynchronous owner boundary for visible RGB-D task batches."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid
from typing import Awaitable, Callable

import yaml

from .backends.profile import BackendProfile, ExecutableSpec
from .backends.protocol import BackendOperation


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_MAX_POINTS_BYTES = 1_048_576


class TaskGatewayError(RuntimeError):
    """The task owner boundary rejected or could not complete a request."""


class TaskGatewayBusy(TaskGatewayError):
    """A second task cannot start while the owned batch is active."""


@dataclass(frozen=True, slots=True)
class TaskOwnerRequest:
    session_id: str
    points_yaml: str
    evidence_root: Path


@dataclass(frozen=True, slots=True)
class TaskHandle:
    run_id: str
    pid: int
    pgid: int
    manifest_path: Path


@dataclass(slots=True)
class _OwnedTask:
    handle: TaskHandle
    process: object
    stdout: object
    stderr: object
    evidence_root: Path


def _default_uuid() -> str:
    return uuid.uuid4().hex


class CliTaskGateway:
    """Run only profile-pinned task CLIs and signal only their owned PGID."""

    def __init__(
        self,
        profile: BackendProfile,
        *,
        package_prefix_resolver: Callable[[str], str] | None = None,
        popen: Callable[..., object] = subprocess.Popen,
        run_process: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        getpgid: Callable[[int], int] = os.getpgid,
        killpg: Callable[[int, int], None] = os.killpg,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        stop_timeout_s: float = 3.0,
        uuid_factory: Callable[[], object] = _default_uuid,
    ) -> None:
        if package_prefix_resolver is None:
            from ament_index_python.packages import get_package_prefix

            package_prefix_resolver = get_package_prefix
        if stop_timeout_s <= 0:
            raise ValueError("stop_timeout_s must be positive")
        self._profile = profile
        self._package_prefix_resolver = package_prefix_resolver
        self._popen = popen
        self._run_process = run_process
        self._getpgid = getpgid
        self._killpg = killpg
        self._sleep = sleep
        self._monotonic = monotonic
        self._stop_timeout_s = stop_timeout_s
        self._uuid_factory = uuid_factory
        self._lock = asyncio.Lock()
        self._active: _OwnedTask | None = None
        self._runs: dict[str, _OwnedTask] = {}

    def _spec(self, operation: BackendOperation, capability: str) -> ExecutableSpec:
        if not getattr(self._profile.capabilities, capability):
            raise TaskGatewayError(f"TASK_CAPABILITY_UNAVAILABLE: {capability}")
        spec = self._profile.operations.get(operation)
        if spec is None:
            raise TaskGatewayError(f"TASK_OWNER_UNCONFIGURED: {operation.value}")
        return spec

    def _resolve(self, spec: ExecutableSpec) -> Path:
        try:
            prefix = Path(self._package_prefix_resolver(spec.package))
        except Exception as error:
            raise TaskGatewayError(f"TASK_OWNER_PACKAGE_NOT_FOUND: {error}") from error
        executable = prefix / "lib" / spec.package / spec.executable
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise TaskGatewayError(f"TASK_OWNER_EXECUTABLE_NOT_FOUND: {executable}")
        return executable

    @staticmethod
    def _root(path: Path) -> Path:
        root = Path(path)
        if not root.is_absolute() or root.is_symlink():
            raise TaskGatewayError("TASK_EVIDENCE_ROOT_INVALID")
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise TaskGatewayError(f"TASK_EVIDENCE_ROOT_INVALID: {error}") from error
        if root.is_symlink() or not root.is_dir():
            raise TaskGatewayError("TASK_EVIDENCE_ROOT_INVALID")
        return root

    @staticmethod
    def _safe_id(label: str, value: str) -> str:
        if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
            raise TaskGatewayError(f"TASK_{label.upper()}_INVALID")
        return value

    @staticmethod
    def _points(value: str) -> str:
        if not isinstance(value, str) or not value or len(value.encode()) > _MAX_POINTS_BYTES:
            raise TaskGatewayError("TASK_POINTS_INVALID")
        try:
            document = yaml.safe_load(value)
        except yaml.YAMLError as error:
            raise TaskGatewayError(f"TASK_POINTS_INVALID: {error}") from error
        if not isinstance(document, dict):
            raise TaskGatewayError("TASK_POINTS_INVALID")
        return value

    @staticmethod
    def _close(task: _OwnedTask) -> None:
        for stream in (task.stdout, task.stderr):
            try:
                stream.close()
            except (AttributeError, OSError):
                pass

    async def start_batch(self, request: TaskOwnerRequest) -> TaskHandle:
        async with self._lock:
            if self._active is not None and self._active.process.poll() is None:
                raise TaskGatewayBusy("TASK_BATCH_ACTIVE")
            if self._active is not None:
                self._close(self._active)
                self._active = None
            if not isinstance(request, TaskOwnerRequest):
                raise TaskGatewayError("TASK_REQUEST_INVALID")
            session_id = self._safe_id("session_id", request.session_id)
            points_yaml = self._points(request.points_yaml)
            root = self._root(request.evidence_root)
            run_id = self._safe_id("run_id", str(self._uuid_factory()))
            inputs = root / ".task-inputs"
            if inputs.is_symlink():
                raise TaskGatewayError("TASK_INPUT_ROOT_INVALID")
            inputs.mkdir(exist_ok=True)
            run_input = inputs / run_id
            try:
                run_input.mkdir()
            except FileExistsError as error:
                raise TaskGatewayError("TASK_RUN_ALREADY_EXISTS") from error
            points_path = run_input / "points.yaml"
            with points_path.open("x", encoding="utf-8") as stream:
                stream.write(points_yaml)
            spec = self._spec(BackendOperation.TASK_BATCH, "task_batch")
            executable = self._resolve(spec)
            manifest = root / "batches" / run_id / "batch-result.json"
            stdout = (run_input / "owner.stdout.log").open("xb")
            stderr = (run_input / "owner.stderr.log").open("xb")
            argv = [
                str(executable), *spec.fixed_args,
                "--points", str(points_path),
                "--batch-id", run_id,
                "--session-id", session_id,
                "--evidence-root", str(root),
            ]
            try:
                process = self._popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    start_new_session=True,
                )
                pgid = self._getpgid(process.pid)
            except Exception as error:
                stdout.close()
                stderr.close()
                raise TaskGatewayError(f"TASK_OWNER_START_FAILED: {error}") from error
            if pgid <= 0:
                stdout.close()
                stderr.close()
                raise TaskGatewayError("TASK_OWNER_PGID_INVALID")
            handle = TaskHandle(run_id, process.pid, pgid, manifest)
            owned = _OwnedTask(handle, process, stdout, stderr, root)
            self._runs[run_id] = owned
            self._active = owned
            return handle

    async def status(self, run_id: str) -> dict[str, object]:
        async with self._lock:
            task = self._runs.get(run_id)
            if task is None:
                raise TaskGatewayError("TASK_RUN_NOT_FOUND")
            manifest = task.handle.manifest_path
            batch_root = task.evidence_root / "batches"
            run_root = batch_root / run_id
            if (
                task.evidence_root.is_symlink()
                or batch_root.is_symlink()
                or run_root.is_symlink()
                or manifest.is_symlink()
            ):
                raise TaskGatewayError("TASK_MANIFEST_INVALID")
            if manifest.exists():
                try:
                    manifest.resolve(strict=True).relative_to(
                        task.evidence_root.resolve(strict=True)
                    )
                except (OSError, ValueError) as error:
                    raise TaskGatewayError("TASK_MANIFEST_INVALID") from error
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
            except FileNotFoundError:
                returncode = task.process.poll()
                if returncode is None:
                    return {
                        "run_id": run_id,
                        "status": "RUNNING",
                        "pid": task.handle.pid,
                    }
                self._close(task)
                if self._active is task:
                    self._active = None
                return {
                    "run_id": run_id,
                    "status": "ERROR",
                    "failure_code": "TASK_MANIFEST_MISSING",
                    "exit_code": returncode,
                }
            except (OSError, json.JSONDecodeError) as error:
                raise TaskGatewayError(f"TASK_MANIFEST_INVALID: {error}") from error
            if not isinstance(payload, dict) or not isinstance(payload.get("status"), str):
                raise TaskGatewayError("TASK_MANIFEST_INVALID")
            payload = dict(payload)
            payload["run_id"] = run_id
            if payload["status"] != "RUNNING":
                self._close(task)
                if self._active is task and task.process.poll() is not None:
                    self._active = None
            return payload

    async def _wait_stopped(self, process: object) -> bool:
        deadline = self._monotonic() + self._stop_timeout_s
        while self._monotonic() < deadline:
            if process.poll() is not None:
                return True
            await self._sleep(min(0.05, self._stop_timeout_s))
        return process.poll() is not None

    async def cancel(self, run_id: str) -> dict[str, object]:
        async with self._lock:
            task = self._active
            if task is None or task.handle.run_id != run_id or task.process.poll() is not None:
                raise TaskGatewayError("TASK_RUN_NOT_ACTIVE")
            if not self._profile.capabilities.task_environment_shutdown:
                raise TaskGatewayError("TASK_CAPABILITY_UNAVAILABLE: task_environment_shutdown")
            self._killpg(task.handle.pgid, signal.SIGINT)
            stopped = await self._wait_stopped(task.process)
            if not stopped:
                self._killpg(task.handle.pgid, signal.SIGTERM)
                stopped = await self._wait_stopped(task.process)
            self._close(task)
            self._active = None
            return {
                "run_id": run_id,
                "status": "CANCELLED" if stopped else "CANCEL_TIMEOUT",
            }

    async def capture(self, session_id: str, evidence_root: Path) -> dict[str, object]:
        self._safe_id("session_id", session_id)
        root = self._root(evidence_root)
        spec = self._spec(BackendOperation.SENSOR_CAPTURE, "sensor_capture")
        executable = self._resolve(spec)
        captures = root / "captures"
        if captures.is_symlink():
            raise TaskGatewayError("TASK_CAPTURE_ROOT_INVALID")
        captures.mkdir(exist_ok=True)
        capture_id = self._safe_id("capture_id", str(self._uuid_factory()))
        output = captures / capture_id
        completed = self._run_process(
            [str(executable), *spec.fixed_args, "--output-directory", str(output)],
            text=True,
            capture_output=True,
            timeout=spec.timeout_s,
            check=False,
            shell=False,
        )
        try:
            payload = json.loads((completed.stdout or "").strip())
        except json.JSONDecodeError as error:
            raise TaskGatewayError("TASK_CAPTURE_OUTPUT_INVALID") from error
        if completed.returncode or not isinstance(payload, dict):
            raise TaskGatewayError(
                f"TASK_CAPTURE_FAILED: exit_code={completed.returncode}"
            )
        result = dict(payload)
        result.setdefault("capture_id", capture_id)
        result.setdefault("output_directory", str(output))
        return result
