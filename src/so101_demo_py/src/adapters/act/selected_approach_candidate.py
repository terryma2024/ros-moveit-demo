"""Prepare an exact, noncollecting approach candidate from selected SEARCH."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import time

import mujoco

from so101_demo.act.contracts import finite, validate_action_prefix, vector
from so101_demo.act.visible_approach_candidate import (
    _prefix_rows, build_candidate_manifest,
)
from so101_demo.act.visible_approach_diagnostic import build_route_manifest
from .physics import model_sha256
from .selected_search_source import freeze_selected_search_source


class SelectedApproachCandidate:
    """Prevalidate the route before SEARCH; prepare one source-bound first prefix."""

    def __init__(
        self, *, scene_path: Path, plugin_path: Path,
        source_profile_path: Path, candidate_profile_path: Path,
        session_id: str, attempt_id: str, max_skew_s: float,
        max_source_age_s: float, joint_tolerance_rad: float,
        cup_tolerance_m: float, stop_velocity_rad_s: float,
        monotonic=time.monotonic,
    ):
        if not callable(monotonic):
            raise ValueError("SELECTED_APPROACH_CONFIG_INVALID")
        limits = tuple(finite(value) for value in (
            max_skew_s, max_source_age_s, joint_tolerance_rad,
            cup_tolerance_m, stop_velocity_rad_s,
        ))
        if min(limits) <= 0:
            raise ValueError("SELECTED_APPROACH_CONFIG_INVALID")
        self.max_skew, self.max_age, self.joint_tolerance = limits[:3]
        self.cup_tolerance, self.stop_velocity = limits[3:]
        self.monotonic = monotonic
        route = build_route_manifest(
            scene_path=scene_path, plugin_path=plugin_path,
            profile_path=source_profile_path,
            session_id=session_id, attempt_id=attempt_id,
        )
        candidate = build_candidate_manifest(
            scene_path=scene_path, plugin_path=plugin_path,
            source_profile_path=source_profile_path,
            candidate_profile_path=candidate_profile_path,
            session_id=session_id, attempt_id=attempt_id,
        )
        if (candidate["source_route_sha256"] != route["manifest_sha256"]
                or candidate["eligible_for_collection"] is not False
                or len(candidate["segments"]) < 1):
            raise ValueError("SELECTED_APPROACH_ROUTE_INVALID")
        model = mujoco.MjModel.from_xml_path(str(Path(scene_path).resolve()))
        if model_sha256(model) != candidate["model_sha256"]:
            raise ValueError("SELECTED_APPROACH_MODEL_INVALID")
        self._route, self._manifest = route, candidate
        self.model = model
        self.joints = []
        self.dofs = []
        for name in ("1", "2", "3", "4", "5", "6"):
            joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint < 0 or model.jnt_type[joint] != mujoco.mjtJoint.mjJNT_HINGE:
                raise ValueError("SELECTED_APPROACH_MODEL_INVALID")
            self.joints.append(int(model.jnt_qposadr[joint]))
            self.dofs.append(int(model.jnt_dofadr[joint]))
        cup = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT,
                                "cup_free_joint")
        if cup < 0 or model.jnt_type[cup] != mujoco.mjtJoint.mjJNT_FREE:
            raise ValueError("SELECTED_APPROACH_MODEL_INVALID")
        self.cup_address = int(model.jnt_qposadr[cup])

    @property
    def manifest(self) -> dict:
        return copy.deepcopy(self._manifest)

    def prepare(self, observed, *, selected_source: dict) -> dict:
        """Freeze the first candidate only; never issue a receipt or permit."""
        source = freeze_selected_search_source(observed, max_skew_s=self.max_skew)
        if type(selected_source) is not dict or source != selected_source:
            raise ValueError("SELECTED_APPROACH_SOURCE_CHANGED")
        route = self._route
        if (source["session_id"] != route["session_id"]
                or source["attempt_id"] != route["attempt_id"]
                or source["phase"] != "SEARCH"
                or source["physics_step"] < 1):
            raise ValueError("SELECTED_APPROACH_SOURCE_INVALID")
        now = finite(self.monotonic(), nonnegative=True)
        receipts = source["source_received_wall_s"]
        if (any(value > now for value in receipts.values())
                or not now - min(receipts.values()) < self.max_age):
            raise ValueError("SELECTED_APPROACH_SOURCE_STALE")
        raw = observed.physical_readback
        world, scene = raw["world"], raw["scene"]
        if (world.reset_epoch != source["reset_epoch"]
                or world.object_state.body != "plastic_cup"
                or world.left_fingertip_contacts
                or world.right_fingertip_contacts
                or scene["model_sha256"] != self._manifest["model_sha256"]):
            raise ValueError("SELECTED_APPROACH_SOURCE_INVALID")
        qpos = vector(scene["qpos"], self.model.nq)
        qvel = vector(scene["qvel"], self.model.nv)
        expected = self._manifest["segments"][0]["prior"]
        actual = tuple(qpos[index] for index in self.joints)
        if (any(abs(value - target) > self.joint_tolerance
                for value, target in zip(actual, expected, strict=True))
                or any(abs(qvel[index]) > self.stop_velocity
                       for index in self.dofs)
                or any(abs(value - actual[index]) > self.joint_tolerance
                       for index, value in enumerate(raw["observation"]["state"][:6]))
                or math.dist(qpos[self.cup_address:self.cup_address + 3],
                             route["cup_start_m"]) > self.cup_tolerance
                or math.dist(world.object_state.position_world,
                             route["cup_start_m"]) > self.cup_tolerance
                or abs(abs(qpos[self.cup_address + 3]) - 1.) > .01
                or any(abs(value) > .01 for value in
                       qpos[self.cup_address + 4:self.cup_address + 7])):
            raise ValueError("SELECTED_APPROACH_START_INVALID")
        rows = _prefix_rows(expected, self._manifest["segments"][0]["goal"])
        row_hash = hashlib.sha256(json.dumps(
            rows, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if row_hash != self._manifest["segments"][0]["rows_sha256"]:
            raise ValueError("SELECTED_APPROACH_ROWS_INVALID")
        origin = source["simulation_time_s"]
        prefix = dict(
            session_id=source["session_id"], attempt_id=source["attempt_id"],
            sequence=0, observation_time_s=origin,
            first_target_delay_s=.1, target_interval_s=.002,
            target_times_s=[origin + .1 + .002 * index
                            for index in range(1, 601)],
            positions=rows,
        )
        validate_action_prefix(prefix)
        return dict(
            selected_source=copy.deepcopy(source), prefix=prefix,
            candidate_manifest_sha256=self._manifest["manifest_sha256"],
            eligible_for_collection=False, command_authority=False,
        )
