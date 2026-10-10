"""The diagnostic-episode station: the ACT launch profile, selected by the frozen inputs.

The Worker's station for a diagnostic-episode run is the ACT task station (ACT `ros2_controllers.yaml` and `mujoco_plugins.yaml`,
the neck controller, the seven-joint reset), and it is chosen here from the frozen inputs manifest and its collection scope,
never from the process environment. The Teacher drives plain JointTrajectoryControllers: this binding owns no broker, no
reservation and no IPC socket, only the launch command and the worker environment that go with it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from so101_demo.act.collection_scope import build_collection_scope, require_valid_scope
from so101_demo.act.execution_snapshot import verify_execution_snapshot
from so101_demo.act.diagnostic_episode_inputs import validate_execution_snapshot_binding, verify_frozen_inputs
from so101_demo.application.qualification_stack import ros2_command
from .task_stack import PersistentStackConfig, StackProcessSpec

LAUNCH_FILE = "so101_mujoco_act.launch.py"


@dataclass(frozen=True)
class DiagnosticEpisodeStation:
    inputs_manifest: Path
    scope_path: Path
    inputs_sha256: str
    scope_sha256: str

    @classmethod
    def bind(cls, inputs_manifest, scope_path):
        if scope_path is None:
            raise ValueError("EPISODE_COLLECTION_SCOPE_REQUIRED")
        inputs_manifest, scope_path = Path(inputs_manifest).resolve(), Path(scope_path).resolve()
        frozen = verify_frozen_inputs(inputs_manifest)
        scope_bytes = scope_path.read_bytes()
        cls._verify_scope(scope_bytes, frozen)
        if frozen.get("mode") != "preselected_target_diagnostic":
            raise ValueError("EPISODE_DIAGNOSTIC_REQUIRED")
        if "execution_snapshot" not in frozen:
            raise ValueError("EPISODE_EXECUTION_INPUTS_REQUIRED")
        validate_execution_snapshot_binding(frozen["execution_snapshot"])
        return cls(inputs_manifest, scope_path, frozen["inputs_sha256"],
                   hashlib.sha256(scope_bytes).hexdigest())

    @staticmethod
    def _verify_scope(payload, frozen):
        try:
            scope = require_valid_scope(json.loads(payload), expected_inputs_sha256=frozen["inputs_sha256"],
                                        expected_mode="preselected_target_diagnostic")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("COLLECTION_SCOPE_INVALID") from error
        anchor = frozen["roles"]["anchor_scene"]["identity"]
        if scope != build_collection_scope(frozen["mode"], scene_id=anchor["scene_id"],
                                           seed=anchor["seed"], inputs_sha256=frozen["inputs_sha256"]):
            raise ValueError("EPISODE_COLLECTION_SCOPE_MISMATCH")

    def _frozen(self):
        frozen = verify_frozen_inputs(self.inputs_manifest)
        if frozen["inputs_sha256"] != self.inputs_sha256:
            raise ValueError("EPISODE_INPUTS_IDENTITY_CHANGED")
        payload = self.scope_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != self.scope_sha256:
            raise ValueError("EPISODE_INPUTS_IDENTITY_CHANGED")
        self._verify_scope(payload, frozen)
        return frozen

    def __call__(self, resources):
        if sys.platform != "linux":
            raise ValueError("EPISODE_AI_STATION_LINUX_REQUIRED")
        frozen = self._frozen()
        binding = frozen["execution_snapshot"]
        validate_execution_snapshot_binding(binding)
        snapshot_root = self.inputs_manifest.parent / binding["path"]
        snapshot = verify_execution_snapshot(snapshot_root, expected_sha256=binding["sha256"])
        command = ros2_command(
            "launch", "so101_demo_py", LAUNCH_FILE,
            "headless:=true", "sensor_rendering:=true", "include_teleop:=false",
            f"session_id:={resources.session_id}", f"task_evidence_root:={resources.worker_root}",
            f"mujoco_scene:={snapshot_root / snapshot['scene_path']}",
            f"mujoco_initial_keyframe:={snapshot['targets']['reset_keyframe']}",
            f"act_first_episode_inputs:={self.inputs_manifest}",
            f"act_expected_inputs_sha256:={self.inputs_sha256}")
        return PersistentStackConfig(resources.session_id, True, resources.worker_root,
                                     (StackProcessSpec("task-station", tuple(command)),))

    def environment(self, resources):
        """The worker environment: the ACT profile and the simulation session, set explicitly."""
        return {**resources.environment, "SO101_ACT_PROFILE": "1",
                "SO101_SIMULATION_SESSION_ID": resources.session_id}
