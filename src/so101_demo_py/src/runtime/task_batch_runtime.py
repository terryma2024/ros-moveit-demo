"""ROS graph and owned-subprocess adapter for RESET_WORLD task batches."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Mapping

from ..application.qualification_stack import ros2_command
from ..application.task_batch import (
    LocalPointFailure,
    ManagedChild,
    PointExecutionReceipt,
    ResetPointReceipt,
    SafetyReceipt,
    SharedStackFailure,
)
from ..application.task_reachability import ReachabilityReport, ReachabilityStatus
from ..core.task_points import TaskPoint


class OwnedPointProcesses:
    def __init__(
        self,
        *,
        popen: Callable = subprocess.Popen,
        killpg: Callable = os.killpg,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._popen = popen
        self._killpg = killpg
        self._environment = dict(os.environ)
        if environment is not None:
            self._environment.update(environment)
        self._children: dict[str, object] = {}
        self._output_streams: dict[str, object] = {}

    def start(
        self,
        role: str,
        argv: list[str],
        *,
        environment=None,
        stdout_path: Path | None = None,
    ) -> ManagedChild:
        if role in self._children:
            raise RuntimeError(f"point child role already exists: {role}")
        child_environment = dict(self._environment)
        if environment is not None:
            child_environment.update(environment)
        output = None
        if stdout_path is not None:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            output = stdout_path.open("w", encoding="utf-8", buffering=1)
        try:
            child = self._popen(
                argv,
                start_new_session=True,
                env=child_environment,
                stdout=output if output is not None else subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except BaseException:
            if output is not None:
                output.close()
            raise
        self._children[role] = child
        if output is not None:
            self._output_streams[role] = output
        return ManagedChild(role, int(child.pid), int(child.pid))

    def poll(self, role: str):
        return self._children[role].poll()

    def stop_all(self) -> None:
        failures = []
        for role, child in reversed(tuple(self._children.items())):
            if child.poll() is not None:
                continue
            try:
                self._killpg(int(child.pid), signal.SIGINT)
                child.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                try:
                    self._killpg(int(child.pid), signal.SIGTERM)
                    child.wait(timeout=3.0)
                except BaseException as error:
                    failures.append((role, error))
            except ProcessLookupError:
                continue
            except BaseException as error:
                failures.append((role, error))
        self._children.clear()
        for output in self._output_streams.values():
            output.close()
        self._output_streams.clear()
        if failures:
            raise RuntimeError(
                "; ".join(f"{role}: {error}" for role, error in failures)
            )


class RosGraphProbe:
    def __init__(self, *, runner: Callable = subprocess.run) -> None:
        self._runner = runner

    def subscription_count(self, node_name: str, topic: str) -> int:
        try:
            completed = self._runner(
                ros2_command(
                    "node",
                    "info",
                    "--no-daemon",
                    "--spin-time",
                    "0.2",
                    node_name,
                ),
                capture_output=True,
                text=True,
                timeout=3.0,
            )
        except subprocess.TimeoutExpired:
            return 0
        if completed.returncode != 0:
            return 0
        in_subscriptions = False
        count = 0
        for line in completed.stdout.splitlines():
            stripped = line.strip()
            if stripped == "Subscribers:":
                in_subscriptions = True
                continue
            if stripped.endswith(":") and stripped != "Subscribers:":
                in_subscriptions = False
            if in_subscriptions and stripped.startswith(f"{topic}:"):
                count += 1
        return count


def _last_json(stdout: str) -> dict[str, object]:
    for line in reversed(stdout.splitlines()):
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(document, dict):
            return document
    raise RuntimeError("child command did not emit a JSON document")


class RosTaskBatchRuntime:
    def __init__(
        self,
        processes,
        ros_graph,
        *,
        session_id: str,
        points_file: Path,
        policy_file: Path,
        evidence_root: Path,
        viewer_capture,
        command_runner: Callable = subprocess.run,
        resume: Callable[[], bool],
        safety_probe: Callable[[int], SafetyReceipt] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        point_timeout_s: float = 180.0,
    ) -> None:
        self._processes = processes
        self._ros_graph = ros_graph
        self._session_id = session_id
        self._points_file = points_file
        self._policy_file = policy_file
        self._evidence_root = evidence_root.resolve(strict=True)
        self._viewer_capture = viewer_capture
        self._command_runner = command_runner
        self._resume = resume
        self._safety_probe = safety_probe
        self._monotonic = monotonic
        self._sleep = sleep
        self._point_timeout_s = point_timeout_s
        self._subscription_ready = False
        self._terminal_timestamp: float | None = None

    def _run(self, argv: list[str]):
        return self._command_runner(argv, capture_output=True, text=True)

    def check_declared(self, point: TaskPoint) -> ReachabilityReport:
        root = self._evidence_root / "declared-reachability"
        root.mkdir(parents=True, exist_ok=True)
        evidence = root / f"{point.id}.json"
        completed = self._run(
            ros2_command(
                "run",
                "so101_demo_py",
                "task_reachability",
                "--points",
                str(self._points_file),
                "--policy",
                str(self._policy_file),
                "--session-id",
                self._session_id,
                "--evidence-file",
                str(evidence),
                "--point-id",
                point.id,
            )
        )
        document = _last_json(completed.stdout)
        reports = document.get("reports")
        if not isinstance(reports, list) or len(reports) != 1:
            raise SharedStackFailure("DECLARED_REACHABILITY_INVALID")
        report = reports[0]
        status = ReachabilityStatus(str(report["status"]))
        return ReachabilityReport(
            point.id,
            status,
            (),
            report.get("first_failure_code"),
            report.get("scene_revision"),
        )

    def reset_point(self, point: TaskPoint) -> ResetPointReceipt:
        root = self._evidence_root / "resets"
        root.mkdir(parents=True, exist_ok=True)
        evidence = root / f"{point.id}-{time.time_ns()}.json"
        completed = self._run(
            ros2_command(
                "run",
                "so101_demo_py",
                "teleop_reset",
                "--backend",
                "mujoco",
                "--session-id",
                self._session_id,
                "--cup-position-world-m",
                *(str(value) for value in point.cup_position_world_m),
                "--evidence-file",
                str(evidence),
            )
        )
        document = _last_json(completed.stdout)
        if completed.returncode != 0 or not document.get("success"):
            raise SharedStackFailure("TRANSACTIONAL_RESET_FAILED")
        if not self._resume():
            raise SharedStackFailure("MUJOCO_RESUME_FAILED")
        return ResetPointReceipt(
            int(document["old_epoch"]),
            int(document["new_epoch"]),
            str(document["simulation_session_id"]),
            evidence,
        )

    def start_consumer(self, point_root: Path, epoch: int) -> ManagedChild:
        dynamic = point_root / "dynamic"
        dynamic.mkdir(parents=True, exist_ok=False)
        self._subscription_ready = False
        return self._processes.start(
            "dynamic-consumer",
            ros2_command(
                "run",
                "so101_demo_py",
                "dynamic_cup_pick_place",
                "--backend",
                "mujoco",
                "--mode",
                "execute",
                "--execute",
                "--cup-pose-timeout-s",
                "45.0",
                "--session-id",
                self._session_id,
                "--expected-reset-epoch",
                str(epoch),
                "--evidence-root",
                str(dynamic),
                "--scene-source",
                "observe_only",
            ),
            stdout_path=point_root / "dynamic-consumer.log",
        )

    def wait_consumer_subscription(self, child: ManagedChild, timeout_s: float) -> None:
        if child.role != "dynamic-consumer":
            raise RuntimeError("subscription handshake requires dynamic consumer")
        deadline = self._monotonic() + timeout_s
        while self._monotonic() <= deadline:
            if self._processes.poll("dynamic-consumer") is not None:
                raise SharedStackFailure(
                    "DYNAMIC_CONSUMER_EXITED_BEFORE_SUBSCRIPTION"
                )
            if self._ros_graph.subscription_count(
                "/so101_dynamic_cup_pick_place", "/cup_pose"
            ) == 1:
                self._subscription_ready = True
                return
            self._sleep(0.02)
        raise SharedStackFailure("DYNAMIC_CONSUMER_SUBSCRIPTION_TIMEOUT")

    def start_perception(self, point_root: Path) -> ManagedChild:
        if not self._subscription_ready:
            raise RuntimeError("consumer subscription must be ready before perception")
        return self._processes.start(
            "rgbd-perception",
            ros2_command(
                "run",
                "so101_demo_py",
                "rgbd_cup_pose",
                "--output-ply",
                str(point_root / "cup-cloud.ply"),
                "--output-full-ply",
                str(point_root / "full-cloud.ply"),
                "--output-rgb",
                str(point_root / "rgb.png"),
                "--output-preview",
                str(point_root / "point-cloud-preview.png"),
                "--evidence-json",
                str(point_root / "perception-summary.json"),
            ),
            stdout_path=point_root / "rgbd-perception.log",
        )

    def wait_point_result(
        self, point: TaskPoint, epoch: int, point_root: Path
    ) -> PointExecutionReceipt:
        del point, epoch
        deadline = self._monotonic() + self._point_timeout_s
        while self._monotonic() <= deadline:
            consumer_code = self._processes.poll("dynamic-consumer")
            perception_code = self._processes.poll("rgbd-perception")
            if consumer_code is not None:
                self._terminal_timestamp = time.time()
                return PointExecutionReceipt(
                    consumer_code == 0,
                    None if consumer_code == 0 else "DYNAMIC_WORKFLOW_FAILED",
                    point_root / "dynamic/dynamic-execute-manifest.json",
                    SafetyReceipt(True, False, None),
                )
            if perception_code is not None:
                raise LocalPointFailure("RGBD_PERCEPTION_EXITED_EARLY")
            self._sleep(0.05)
        raise LocalPointFailure("POINT_EXECUTION_TIMEOUT")

    def capture_terminal(self, point_root: Path, reason: str) -> tuple[Path, ...]:
        del reason
        viewer = point_root / "viewer.png"
        self._viewer_capture.capture(
            viewer,
            terminal_timestamp=self._terminal_timestamp,
        )
        return tuple(
            point_root / name
            for name in (
                "rgb.png",
                "full-cloud.ply",
                "cup-cloud.ply",
                "point-cloud-preview.png",
                "viewer.png",
                "dynamic-consumer.log",
                "rgbd-perception.log",
            )
            if (point_root / name).is_file()
        )

    def safe_to_continue(self, epoch: int) -> SafetyReceipt:
        if self._safety_probe is not None:
            return self._safety_probe(epoch)
        from ..backends.mujoco.teleop_runtime import current_evidence

        evidence = current_evidence(self._session_id)
        if evidence.simulation_session_id != self._session_id or evidence.reset_epoch != epoch:
            return SafetyReceipt(False, False, "SESSION_OR_EPOCH_MISMATCH")
        cup_z = float(evidence.object_state.position_world[2])
        contacts = len(evidence.left_fingertip_contacts) + len(
            evidence.right_fingertip_contacts
        )
        held = cup_z > 0.19 and contacts > 0
        return SafetyReceipt(not held, held, "PHYSICAL_GRASP_UNSUPPORTED" if held else None)

    def stop_point_children(self) -> None:
        self._processes.stop_all()
        self._subscription_ready = False

    def pause_world(self) -> None:
        if self._safety_probe is None:
            from ..backends.mujoco.teleop_runtime import current_evidence

            current_evidence(self._session_id)
