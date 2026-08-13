"""Task-owned Gazebo transport commands used only by the simulator adapter."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from typing import Any

from ...core.task_geometry import Pose7
from ...ports.reset import ResetStepReceipt


class GazeboCommandAdapter:
    def __init__(
        self,
        *,
        runner: Callable[..., Any] = subprocess.run,
        process_timeout_s: float = 5.0,
        service_timeout_ms: int = 3000,
    ) -> None:
        self._runner = runner
        self._process_timeout_s = process_timeout_s
        self._service_timeout_ms = service_timeout_ms

    def _run(self, argv: list[str], *, require_ack: bool) -> ResetStepReceipt:
        evidence: dict[str, object] = {"argv": argv}
        try:
            result = self._runner(
                argv,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=self._process_timeout_s,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as error:
            return ResetStepReceipt(
                False,
                "RESET_GAZEBO_COMMAND_TIMEOUT",
                {**evidence, "message": str(error)},
            )
        except OSError as error:
            return ResetStepReceipt(
                False,
                "RESET_GAZEBO_COMMAND_UNAVAILABLE",
                {**evidence, "message": str(error)},
            )
        evidence.update(
            {
                "returncode": int(result.returncode),
                "stdout": str(result.stdout),
                "stderr": str(result.stderr),
            }
        )
        if result.returncode != 0:
            return ResetStepReceipt(
                False, "RESET_GAZEBO_COMMAND_FAILED", evidence
            )
        if require_ack:
            match = re.search(r"\bdata:\s*(true|false)\b", str(result.stdout).lower())
            if match is None:
                return ResetStepReceipt(False, "RESET_GAZEBO_ACK_INVALID", evidence)
            evidence["acknowledged"] = match.group(1) == "true"
            if not evidence["acknowledged"]:
                return ResetStepReceipt(False, "RESET_GAZEBO_ACK_REJECTED", evidence)
        return ResetStepReceipt(True, None, evidence)

    def request_detach(self) -> ResetStepReceipt:
        return self._run(
            [
                "gz",
                "topic",
                "-t",
                "/so101/detach_object",
                "-m",
                "gz.msgs.Empty",
                "-p",
                "",
            ],
            require_ack=False,
        )

    def request_attach(self) -> ResetStepReceipt:
        return self._run(
            [
                "gz",
                "topic",
                "-t",
                "/so101/attach_object",
                "-m",
                "gz.msgs.Empty",
                "-p",
                "",
            ],
            require_ack=False,
        )

    def observe_attachment(
        self,
        *,
        parent_entity_id: int,
        child_entity_id: int,
    ) -> ResetStepReceipt:
        receipt = self._run(
            [
                "gz",
                "service",
                "-s",
                "/world/so101_pick_place/state",
                "--reqtype",
                "gz.msgs.Empty",
                "--reptype",
                "gz.msgs.SerializedStepMap",
                "--timeout",
                str(self._service_timeout_ms),
                "--req",
                "",
            ],
            require_ack=False,
        )
        if not receipt.success:
            return receipt
        joint = f'component: "{parent_entity_id} {child_entity_id} fixed"'
        return ResetStepReceipt(
            True,
            None,
            {
                **receipt.evidence,
                "parent_entity_id": parent_entity_id,
                "child_entity_id": child_entity_id,
                "joint_component": joint,
                "attached": joint in str(receipt.evidence["stdout"]),
            },
        )

    def set_task_object_pose(self, pose: Pose7) -> ResetStepReceipt:
        x, y, z, qx, qy, qz, qw = pose.values
        request = (
            'name: "plastic_cup" '
            f"position: {{x: {x}, y: {y}, z: {z}}} "
            f"orientation: {{x: {qx}, y: {qy}, z: {qz}, w: {qw}}}"
        )
        return self._run(
            [
                "gz",
                "service",
                "-s",
                "/world/so101_pick_place/set_pose",
                "--reqtype",
                "gz.msgs.Pose",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                str(self._service_timeout_ms),
                "--req",
                request,
            ],
            require_ack=True,
        )
