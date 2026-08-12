"""Fail-visible repeatability qualification for the production MuJoCo workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_FINGERPRINT_KEYS = (
    "source_commit",
    "dependency_sha256",
    "task_scene_sha256",
    "scene_sha256",
    "robot_mjcf_sha256",
    "urdf_sha256",
    "motion_policy_sha256",
    "contact_policy_sha256",
)
REQUIRED_PHASES = (
    "staged_approach",
    "contact_hold",
    "micro_lift",
    "policy_lift_waypoint1",
    "remaining_lift",
    "transport",
    "descend",
    "place_alignment",
    "release_retreat",
)
INVALID_WORKFLOW_FAILURE_CODES = frozenset(
    {
        "CONTACT_POLICY_NOT_APPROVED",
        "EXPLICIT_EXECUTE_REQUIRED",
        "LIVE_RUNTIME_CONFIG_REQUIRED",
        "POLICY_FINGERPRINT_MISMATCH",
        "STALE_OR_MISMATCHED_MUJOCO_EVIDENCE",
        "TELEOP_WORKFLOW_EVIDENCE_INVALID",
    }
)


class Lifecycle(StrEnum):
    FULL_RESTART = "FULL_RESTART"
    RESET_WORLD = "RESET_WORLD"


class RunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    VALID_FAILURE = "VALID_FAILURE"
    INVALID = "INVALID"


class QualificationError(RuntimeError):
    """Base class for fail-visible qualification errors."""


class InvalidRun(QualificationError):
    """Environment or provenance contamination invalidates the whole batch."""


class ValidRunFailure(QualificationError):
    """A qualified runtime failed its physical workflow contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_fingerprint(fingerprint: Mapping[str, str]) -> dict[str, str]:
    missing = [key for key in REQUIRED_FINGERPRINT_KEYS if key not in fingerprint]
    if missing:
        raise InvalidRun(f"fingerprint missing keys: {', '.join(missing)}")
    normalized = {str(key): str(value) for key, value in fingerprint.items()}
    if not COMMIT_RE.fullmatch(normalized["source_commit"]):
        raise InvalidRun("source_commit must be a full 40-character commit")
    for key in REQUIRED_FINGERPRINT_KEYS[1:]:
        if not SHA256_RE.fullmatch(normalized[key]):
            raise InvalidRun(f"{key} must be a full lowercase SHA-256")
    return normalized


def _validate_artifact_hashes(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(isinstance(item, str) and SHA256_RE.fullmatch(item) for item in value.values())
    )


def summarize_records(
    records: Sequence[Mapping[str, Any]],
    *,
    lifecycle: Lifecycle,
    fingerprint: Mapping[str, str],
    target_count: int,
) -> dict[str, Any]:
    """Validate a batch without hiding failures or contaminated attempts."""
    expected = validate_fingerprint(fingerprint)
    if target_count <= 0:
        raise ValueError("target_count must be positive")
    sessions: set[str] = set()
    reset_epochs: list[int] = []
    consecutive = 0
    invalid_reason: str | None = None
    for index, record in enumerate(records, start=1):
        if record.get("lifecycle") != lifecycle.value:
            invalid_reason = f"run {index} lifecycle mismatch"
            break
        if record.get("fingerprint") != expected:
            invalid_reason = f"run {index} fingerprint mismatch"
            break
        session_id = str(record.get("simulation_session_id", ""))
        if not session_id:
            invalid_reason = f"run {index} missing session ID"
            break
        if lifecycle is Lifecycle.FULL_RESTART and session_id in sessions:
            invalid_reason = f"run {index} duplicate session ID"
            break
        if lifecycle is Lifecycle.RESET_WORLD and sessions and session_id not in sessions:
            invalid_reason = f"run {index} changed RESET_WORLD session ID"
            break
        sessions.add(session_id)
        try:
            reset_epoch = int(record["reset_epoch"])
        except (KeyError, TypeError, ValueError):
            invalid_reason = f"run {index} missing reset epoch"
            break
        if lifecycle is Lifecycle.RESET_WORLD and reset_epochs and reset_epoch <= reset_epochs[-1]:
            invalid_reason = f"run {index} reset epoch did not increase"
            break
        reset_epochs.append(reset_epoch)
        if record.get("status") == RunStatus.INVALID.value:
            invalid_reason = str(record.get("failure", f"run {index} invalid"))
            break
        if not record.get("clean_shutdown", {}).get("passed"):
            invalid_reason = f"run {index} missing clean shutdown"
            break
        if not _validate_artifact_hashes(record.get("artifact_sha256")):
            invalid_reason = f"run {index} has missing or truncated artifact hashes"
            break
        if record.get("status") == RunStatus.SUCCESS.value:
            physical = record.get("physical_outcome")
            if not isinstance(physical, Mapping) or physical.get("primary_failure") is not None:
                invalid_reason = f"run {index} missing successful physical evidence"
                break
            consecutive += 1
        elif record.get("status") == RunStatus.VALID_FAILURE.value:
            consecutive = 0
        else:
            invalid_reason = f"run {index} has unknown status"
            break
    return {
        "target_count": target_count,
        "attempt_count": len(records),
        "consecutive_successes": consecutive,
        "qualified": invalid_reason is None and consecutive == target_count,
        "batch_invalid": invalid_reason is not None,
        "invalid_reason": invalid_reason,
    }


@dataclass(frozen=True)
class StackHandle:
    process: subprocess.Popen[str]
    process_group_id: int
    log_path: Path
    environment: dict[str, str]
    base_url: str
    session_id: str


class StackStartupError(InvalidRun):
    """A startup failure that retains the owned stack for exact cleanup."""

    def __init__(self, message: str, handle: StackHandle) -> None:
        super().__init__(message)
        self.handle = handle


class ProductionQualificationRunner:
    def __init__(
        self,
        *,
        evidence_root: Path,
        fingerprint: Mapping[str, str],
        headless: bool = True,
        startup_timeout_s: float = 90.0,
        workflow_timeout_s: float = 900.0,
    ) -> None:
        self.evidence_root = evidence_root
        self.fingerprint = validate_fingerprint(fingerprint)
        self.headless = headless
        self.startup_timeout_s = startup_timeout_s
        self.workflow_timeout_s = workflow_timeout_s
        evidence_root.mkdir(parents=True, exist_ok=True)

    def _stack_environment(self, *, domain_id: int) -> dict[str, str]:
        environment = dict(os.environ)
        environment["ROS_DOMAIN_ID"] = str(domain_id)
        environment["SO101_TELEOP_EVIDENCE_BASE"] = str(self.evidence_root / "teleop-evidence")
        return environment

    @staticmethod
    def _request(
        base_url: str, path: str, body: Mapping[str, Any] | None = None, *, timeout: float = 30.0
    ) -> dict[str, Any]:
        url = base_url + path
        if body is None:
            request = urllib.request.Request(url)
        else:
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={"content-type": "application/json"},
                method="POST",
            )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read())
                return {"http": response.status, "response": payload}
        except urllib.error.HTTPError as error:
            payload = json.loads(error.read())
            return {"http": error.code, "response": payload}

    def start_stack(
        self, *, session_id: str, domain_id: int, port: int, run_root: Path
    ) -> StackHandle:
        environment = self._stack_environment(domain_id=domain_id)
        log_path = run_root / "launch.log"
        command = [
            "ros2",
            "launch",
            "so101_mujoco_demo_py",
            "so101_mujoco_teleop.launch.py",
            f"headless:={'true' if self.headless else 'false'}",
            f"simulation_session_id:={session_id}",
            "bind_address:=127.0.0.1",
            f"port:={port}",
            "build_web_if_needed:=false",
        ]
        log_stream = log_path.open("w")
        process = subprocess.Popen(
            command,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env=environment,
        )
        log_stream.close()
        handle = StackHandle(
            process=process,
            process_group_id=os.getpgid(process.pid),
            log_path=log_path,
            environment=environment,
            base_url=f"http://127.0.0.1:{port}",
            session_id=session_id,
        )
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise StackStartupError(
                    f"stack exited during startup with {process.returncode}",
                    handle,
                )
            try:
                health = self._request(handle.base_url, "/health", timeout=2.0)
                log_text = log_path.read_text(errors="replace")
                required_markers = (
                    "Created viewer camera services",
                    "Configured and activated arm_controller",
                    "Configured and activated gripper_controller",
                    "SCENE_SETUP_OK",
                )
                if (
                    health["http"] == 200
                    and health["response"].get("mode") == "READY"
                    and all(marker in log_text for marker in required_markers)
                ):
                    return handle
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            time.sleep(0.5)
        raise StackStartupError("Teleop health did not become READY before timeout", handle)

    @staticmethod
    def stop_stack(handle: StackHandle, *, timeout_s: float = 60.0) -> dict[str, Any]:
        if handle.process.poll() is None:
            os.killpg(handle.process_group_id, signal.SIGINT)
        try:
            returncode = handle.process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(handle.process_group_id, signal.SIGTERM)
            returncode = handle.process.wait(timeout=10.0)
        log_text = handle.log_path.read_text(errors="replace")
        marker = "SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK"
        process_died = "process has died" in log_text
        fatal_signal = any(
            value in log_text for value in ("exit code -11", "Segmentation fault", "SIGSEGV")
        )
        return {
            "passed": returncode == 0
            and marker in log_text
            and not process_died
            and not fatal_signal,
            "returncode": returncode,
            "ordered_shutdown_marker": marker in log_text,
            "process_died": process_died,
            "fatal_signal": fatal_signal,
            "signal": "SIGINT",
        }

    def _post_command(
        self,
        handle: StackHandle,
        path: str,
        lease_id: str,
        *,
        confirmation: str | None = None,
        timeout: float = 30.0,
        allow_failure: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "command_id": str(uuid.uuid4()),
            "lease_id": lease_id,
            "session_id": handle.session_id,
        }
        if confirmation is not None:
            body["confirmation"] = confirmation
        result = self._request(handle.base_url, path, body, timeout=timeout)
        response = result.get("response", {})
        if not allow_failure and (
            result.get("http") != 200 or not response.get("succeeded", False)
        ):
            raise InvalidRun(f"{path} failed: {json.dumps(result, sort_keys=True)}")
        return result

    def execute_workflow(
        self, handle: StackHandle, *, experiment_id: str, run_root: Path
    ) -> dict[str, Any]:
        health = self._request(handle.base_url, "/health")
        capabilities = self._request(handle.base_url, "/capabilities")
        lease1 = self._post_command(handle, "/control/lease", "")
        lease1_id = str(lease1["response"]["layers"]["lease_id"])
        camera = self._post_command(handle, "/gazebo/camera/presets/table_corner_nw", lease1_id)
        reset = self._post_command(
            handle,
            "/simulation/reset",
            lease1_id,
            confirmation="CONFIRM SIMULATION_RESET",
            timeout=120.0,
        )
        receipt = reset["response"].get("data", {}).get("reset", {})
        if (
            receipt.get("simulation_session_id") != handle.session_id
            or int(receipt.get("simulation_step", -1)) != 0
            or int(receipt.get("new_epoch", -1)) <= int(receipt.get("old_epoch", -1))
        ):
            raise InvalidRun("transactional reset receipt is stale or mismatched")
        lease2 = self._post_command(handle, "/control/lease", "")
        lease2_id = str(lease2["response"]["layers"]["lease_id"])
        workflow = self._post_command(
            handle,
            "/workflow/run",
            lease2_id,
            timeout=self.workflow_timeout_s,
            allow_failure=True,
        )
        owner = workflow["response"].get("data", {}).get("workflow", {})
        trace = owner.get("trace", [])
        physical = owner.get("physical_outcome")
        actions = {
            "health": health,
            "capabilities": capabilities,
            "camera": camera,
            "reset": reset,
            "workflow": workflow,
        }
        actions_path = run_root / "actions.json"
        actions_path.write_text(json.dumps(actions, indent=2, sort_keys=True))
        base_record = {
            "experiment_id": experiment_id,
            "simulation_session_id": handle.session_id,
            "reset_epoch": int(receipt["new_epoch"]),
            "simulation_step": int(receipt["simulation_step"]),
            "artifact_paths": {"actions": str(actions_path)},
        }
        if workflow.get("http") != 200 or not workflow["response"].get("succeeded", False):
            owner_failure = workflow["response"].get("layers", {}).get("owner_failure_code")
            if owner_failure in INVALID_WORKFLOW_FAILURE_CODES:
                raise InvalidRun(f"workflow owner configuration failed: {owner_failure}")
            return {
                **base_record,
                "status": RunStatus.VALID_FAILURE.value,
                "failure": json.dumps(workflow, sort_keys=True),
            }
        if trace != list(REQUIRED_PHASES) or not owner.get("checkpoint_fresh"):
            raise InvalidRun("workflow trace or checkpoint freshness contract failed")
        manifest_path = Path(str(owner.get("evidence_manifest", "")))
        if not manifest_path.is_file():
            raise InvalidRun("owner evidence manifest is missing")
        if not isinstance(physical, Mapping) or physical.get("primary_failure") is not None:
            return {
                **base_record,
                "status": RunStatus.VALID_FAILURE.value,
                "failure": "production workflow lacks successful physical outcome",
                "physical_outcome": dict(physical or {}),
                "owner_evidence_manifest": str(manifest_path),
                "artifact_paths": {
                    **base_record["artifact_paths"],
                    "owner_evidence_manifest": str(manifest_path),
                },
            }
        graph = subprocess.run(
            ["ros2", "node", "list"],
            check=False,
            capture_output=True,
            text=True,
            env=handle.environment,
            timeout=15.0,
        )
        return {
            **base_record,
            "ros_graph": sorted(line for line in graph.stdout.splitlines() if line),
            "ros_graph_exit_code": graph.returncode,
            "moveit_controller_result": {
                "workflow_succeeded": True,
                "completed_phases": trace,
            },
            "physical_outcome": dict(physical),
            "owner_evidence_manifest": str(manifest_path),
            "artifact_paths": {
                **base_record["artifact_paths"],
                "owner_evidence_manifest": str(manifest_path),
            },
        }

    def _failure_record(
        self,
        *,
        experiment_id: str,
        session_id: str,
        error: QualificationError,
        run_root: Path,
    ) -> dict[str, Any]:
        status = RunStatus.INVALID if isinstance(error, InvalidRun) else RunStatus.VALID_FAILURE
        failure_path = run_root / "failure.json"
        failure_path.write_text(
            json.dumps({"status": status.value, "failure": str(error)}, indent=2, sort_keys=True)
        )
        return {
            "experiment_id": experiment_id,
            "simulation_session_id": session_id,
            "reset_epoch": -1,
            "status": status.value,
            "failure": str(error),
            "artifact_paths": {"failure": str(failure_path)},
        }

    def _finalize_record(
        self,
        record: dict[str, Any],
        *,
        lifecycle: Lifecycle,
        shutdown: Mapping[str, Any],
        launch_log: Path,
    ) -> dict[str, Any]:
        paths = dict(record.pop("artifact_paths", {}))
        paths["launch_log"] = str(launch_log)
        record.update(
            {
                "lifecycle": lifecycle.value,
                "status": record.get("status", RunStatus.SUCCESS.value),
                "fingerprint": self.fingerprint,
                "clean_shutdown": dict(shutdown),
                "artifact_sha256": {name: sha256_file(Path(path)) for name, path in paths.items()},
                "artifact_paths": paths,
            }
        )
        if not shutdown.get("passed"):
            record["status"] = RunStatus.INVALID.value
            record.setdefault("failure", "clean shutdown contract failed")
        return record

    def _finalize_startup_failure(
        self,
        error: StackStartupError,
        *,
        experiment_id: str,
        session_id: str,
        lifecycle: Lifecycle,
        run_root: Path,
    ) -> dict[str, Any]:
        shutdown = self.stop_stack(error.handle)
        record = self._failure_record(
            experiment_id=experiment_id,
            session_id=session_id,
            error=error,
            run_root=run_root,
        )
        return self._finalize_record(
            record,
            lifecycle=lifecycle,
            shutdown=shutdown,
            launch_log=error.handle.log_path,
        )

    def run_batch(
        self,
        *,
        batch_id: str,
        lifecycle: Lifecycle,
        count: int,
        base_domain_id: int,
        base_port: int,
    ) -> dict[str, Any]:
        if count <= 0:
            raise ValueError("count must be positive")
        records: list[dict[str, Any]] = []
        if lifecycle is Lifecycle.FULL_RESTART:
            for index in range(1, count + 1):
                run_root = self.evidence_root / f"run-{index:02d}"
                run_root.mkdir(parents=True, exist_ok=False)
                session = f"{batch_id}-full-{index:02d}"
                try:
                    handle = self.start_stack(
                        session_id=session,
                        domain_id=base_domain_id + index - 1,
                        port=base_port + index - 1,
                        run_root=run_root,
                    )
                except StackStartupError as error:
                    records.append(
                        self._finalize_startup_failure(
                            error,
                            experiment_id=f"{batch_id}-{index:02d}",
                            session_id=session,
                            lifecycle=lifecycle,
                            run_root=run_root,
                        )
                    )
                    break
                try:
                    record = self.execute_workflow(
                        handle, experiment_id=f"{batch_id}-{index:02d}", run_root=run_root
                    )
                except QualificationError as error:
                    record = self._failure_record(
                        experiment_id=f"{batch_id}-{index:02d}",
                        session_id=session,
                        error=error,
                        run_root=run_root,
                    )
                finally:
                    shutdown = self.stop_stack(handle)
                records.append(
                    self._finalize_record(
                        record,
                        lifecycle=lifecycle,
                        shutdown=shutdown,
                        launch_log=handle.log_path,
                    )
                )
                if record["status"] == RunStatus.INVALID.value:
                    break
        else:
            stack_root = self.evidence_root / "shared-stack"
            stack_root.mkdir(parents=True, exist_ok=False)
            session = f"{batch_id}-reset"
            try:
                handle = self.start_stack(
                    session_id=session,
                    domain_id=base_domain_id,
                    port=base_port,
                    run_root=stack_root,
                )
            except StackStartupError as error:
                records.append(
                    self._finalize_startup_failure(
                        error,
                        experiment_id=f"{batch_id}-01",
                        session_id=session,
                        lifecycle=lifecycle,
                        run_root=stack_root,
                    )
                )
            else:
                pending: list[tuple[dict[str, Any], Path]] = []
                try:
                    for index in range(1, count + 1):
                        run_root = self.evidence_root / f"run-{index:02d}"
                        run_root.mkdir(parents=True, exist_ok=False)
                        try:
                            record = self.execute_workflow(
                                handle,
                                experiment_id=f"{batch_id}-{index:02d}",
                                run_root=run_root,
                            )
                        except QualificationError as error:
                            record = self._failure_record(
                                experiment_id=f"{batch_id}-{index:02d}",
                                session_id=handle.session_id,
                                error=error,
                                run_root=run_root,
                            )
                        pending.append((record, run_root))
                        if record.get("status") == RunStatus.INVALID.value:
                            break
                finally:
                    shutdown = self.stop_stack(handle)
                for record, _run_root in pending:
                    records.append(
                        self._finalize_record(
                            record,
                            lifecycle=lifecycle,
                            shutdown=shutdown,
                            launch_log=handle.log_path,
                        )
                    )
        summary = summarize_records(
            records,
            lifecycle=lifecycle,
            fingerprint=self.fingerprint,
            target_count=count,
        )
        manifest = {
            "schema_version": 1,
            "batch_id": batch_id,
            "lifecycle": lifecycle.value,
            "fingerprint": self.fingerprint,
            "records": records,
            "summary": summary,
        }
        manifest_path = self.evidence_root / "qualification-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        manifest["manifest_path"] = str(manifest_path)
        manifest["manifest_sha256"] = sha256_file(manifest_path)
        return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_qualification")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--lifecycle", choices=[item.value for item in Lifecycle], required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--fingerprint", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--base-domain-id", type=int, required=True)
    parser.add_argument("--base-port", type=int, required=True)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    fingerprint = json.loads(options.fingerprint.read_text())
    runner = ProductionQualificationRunner(
        evidence_root=options.evidence_root,
        fingerprint=fingerprint,
        headless=options.headless,
    )
    manifest = runner.run_batch(
        batch_id=options.batch_id,
        lifecycle=Lifecycle(options.lifecycle),
        count=options.count,
        base_domain_id=options.base_domain_id,
        base_port=options.base_port,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["summary"]["qualified"] else 1
