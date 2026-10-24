"""Point reset, workspace reservation, the initial gate and RGB capture."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
from types import SimpleNamespace

import numpy as np

from so101_demo.act.rig_profile import DEFAULT_RIG
from so101_demo.ros.rgbd_snapshot import RosRgbdSnapshotSource
from so101_demo.runtime.parallel_ros_ports.isolated_node import (
    _RESET_JOINTS,
    _mkdir_private_chain,
    _worker_node_diagnostic,
)
from so101_demo.runtime.parallel_ros_ports.observations import (
    InitialGateObservation,
    ResetBoundaryReceipt,
    observe_parallel_initial_gate,
)
from so101_demo.runtime.parallel_worker_parts.process_tree import SourceStampedCapture
from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt


RESET_EVIDENCE_WAIT_S = 3.0
RESET_EVIDENCE_RETRY_S = 0.05
#: the start pose collision checks (R3-a) by (scene file, rig): the MuJoCo model is loaded once per process
_START_POSE_CHECKERS: dict = {}


class PointGate:
    def _start_pose_checker(self, rig):
        """The collision check of a reset pose on the rig's scene: the `start_pose_check` dependency, else the model of the installed share
        directory (or `start_pose_model_root`), loaded once per process."""

        factory = self.dependencies.get("start_pose_check")
        if factory is not None:
            return factory(rig)
        from so101_demo.act.joints import act_joints_for
        from so101_demo.act.rig_files import rig_model_files
        from so101_demo.act.teacher_diversity import StartPoseCollisionCheck

        root = self.dependencies.get("start_pose_model_root")
        if root is None:
            from ament_index_python.packages import get_package_share_directory

            root = get_package_share_directory("so101_demo_py")
        scene = Path(root) / rig_model_files(rig).scene
        key = (str(scene), rig.rig)
        if key not in _START_POSE_CHECKERS:
            _START_POSE_CHECKERS[key] = StartPoseCollisionCheck.from_path(scene, cup_body="plastic_cup", joint_names=act_joints_for(rig))
        return _START_POSE_CHECKERS[key]

    def _draw_start_pose(self, lease, point):
        """R3-a: the reset joint vector of this episode, or None when the Teacher policy has no diversity block.

        The first draw of (campaign seed, scene id = point id) that keeps the simulator joint limits and passes the MuJoCo collision check
        of the reset pose on this episode's cup position; at most max_redraws + 1 draws, then the episode fails before any reset. The
        selection (draw index, rejected draws and their reasons) is written beside the task's other evidence, and the initial gate
        expects the drawn pose."""

        policy = self.dependencies.get("teacher_execution_policy")
        if not isinstance(policy, dict) or policy.get("diversity") is None:
            return None
        if self.dependencies.get("act_profile") is not True:
            raise RuntimeError("TEACHER_DIVERSITY_REQUIRES_ACT_PROFILE")
        from so101_demo.act import teacher_diversity as td
        from so101_demo.act.joints import act_joints_for

        rig = self.dependencies.get("rig") or DEFAULT_RIG
        joints = act_joints_for(rig)
        td.values_for_policy(policy, lease.point_id)            # the derived values are range-checked before anything moves
        cup = tuple(float(item) for item in point["cup_position_world_m"])
        checker = self._start_pose_checker(rig)
        # the model the check runs on must be the frozen scene: a different model would make "no collision" a claim about another world
        identity = getattr(checker, "identity", None)
        identity = identity() if callable(identity) else None
        frozen_scene = self.dependencies.get("start_pose_frozen_scene")
        if frozen_scene is not None and (identity is None or any(identity.get(key) != frozen_scene.get(key) for key in frozen_scene)):
            raise RuntimeError("TEACHER_DIVERSITY_START_POSE_MODEL_MISMATCH")

        def check(offsets):
            vector = td.reset_joint_positions(offsets, joints)
            if not td.joints_within_limits(vector[:6]):
                return False, "JOINT_LIMIT: a drawn joint is within the margin of a simulator limit"
            return checker.check(vector, cup)

        selection = td.select_start_pose(policy["diversity"], lease.point_id, check)
        vector = td.reset_joint_positions(selection["offsets_rad"], joints)
        self._write_start_pose(lease, {
            "schema_version": 1, "kind": "TEACHER_DIVERSITY_START_POSE_SELECTION", "attempt_id": lease.attempt_id,
            "scene_id": lease.point_id, "policy_sha256": policy.get("policy_sha256"),
            "campaign_seed": policy["diversity"]["campaign_seed"], "draw_index": selection["draw_index"],
            "joints": list(joints), "joints_rad": list(vector), "cup_position_world_m": list(cup),
            "rejected": selection["rejected"], "model": identity, "frozen_identity_verified": frozen_scene is not None})
        self.__dict__.setdefault("_start_poses", {})[lease.attempt_id] = tuple(vector[:6])
        return vector

    def _write_start_pose(self, lease, document):
        root = getattr(self.resources, "worker_root", None)
        attempt = str(lease.attempt_id)
        if root is None or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", attempt) is None:
            raise RuntimeError("TEACHER_DIVERSITY_RECORD_UNWRITABLE")
        payload = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        target = Path(root) / f"start-pose-{attempt}.json"
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if target.read_bytes() != payload:        # a retry of the same attempt draws the same pose
                raise RuntimeError("TEACHER_DIVERSITY_RECORD_EXISTS") from None
            return
        except OSError as error:
            raise RuntimeError("TEACHER_DIVERSITY_RECORD_UNWRITABLE") from error
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def reset_point(self, lease):
        self._reset_started.add(lease.attempt_id)   # from here a fault may have left motion state behind
        call = self.dependencies.get("reset_point")
        point = self.catalog[lease.point_id]
        act_kwargs = {"act_profile": True} if self.dependencies.get("act_profile") is True else {}
        rig = self.dependencies.get("rig")
        if act_kwargs and rig is not None and rig.rig != DEFAULT_RIG.rig:
            act_kwargs["rig"] = rig   # the default rig's reset call is the call it always was
        qualified = call is None
        if qualified:
            call = self.dependencies.get("execute_reset")
        if call is None:
            from so101_demo.cli.teleop_reset import execute_mujoco_reset

            call = execute_mujoco_reset
        if qualified:
            start = self._draw_start_pose(lease, point)
            if start is not None:
                act_kwargs["start_joint_positions"] = start
            value, scene = call(
                self.resources.session_id,
                keyframe="task_start",
                cup_position_world_m=tuple(point["cup_position_world_m"]),
                **act_kwargs,
            )
            if getattr(scene, "success", None) is not True:
                raise RuntimeError("RESET_PLANNING_SCENE_RESTORE")
        else:
            value = call(lease, point)
        observe = self.dependencies.get("current_evidence")
        if observe is None:
            from so101_demo.backends.mujoco.teleop_runtime import current_evidence

            observe = current_evidence
        # The evidence topic replays up to 256 old frames to a new observer, so the first paused frame can still
        # belong to the previous epoch. Only a strictly older epoch of the same session is waited out, for a bounded
        # time; another session, a newer epoch or an expired wait is an identity failure.
        deadline = time.monotonic() + RESET_EVIDENCE_WAIT_S
        while True:
            evidence = observe(value.simulation_session_id)
            if evidence.simulation_session_id != value.simulation_session_id:
                raise RuntimeError("RESET_WATERMARK_IDENTITY")
            if evidence.reset_epoch == value.new_epoch:
                break
            if evidence.reset_epoch > value.new_epoch or time.monotonic() >= deadline:
                raise RuntimeError("RESET_WATERMARK_IDENTITY")
            time.sleep(RESET_EVIDENCE_RETRY_S)
        joint_positions = getattr(value, "joint_positions", None)
        receipt = ResetBoundaryReceipt(
            f"reset-{value.new_epoch}",
            value.simulation_session_id,
            time.monotonic(),
            evidence.simulation_time_s,
            value.new_epoch,
            None if joint_positions is None else tuple(joint_positions),
            batch_id=lease.batch_id,
            coordinator_epoch=lease.coordinator_epoch,
            worker_id=lease.worker_id,
            worker_generation=lease.worker_generation,
            point_id=lease.point_id,
            attempt_id=lease.attempt_id,
            lease_generation=lease.lease_generation,
        )
        self._reset_receipts[lease.attempt_id] = receipt
        return receipt

    def reserve_workspace(self, lease, reset_receipt):
        call = self.dependencies.get("reserve_workspace")
        if call is None:
            raise RuntimeError("WORKSPACE_RESERVATION_PORT_REQUIRED")
        return call(lease, reset_receipt)

    def initial_gate(self, lease, reset_receipt):
        teacher_profile = self.dependencies.get("act_profile") is True
        rig = self.dependencies.get("rig")
        call = self.dependencies.get("observe_initial")
        reader = self.dependencies.get("retained_evidence")
        reader_arguments = {} if reader is None else {"read_evidence": reader}
        rig_arguments = {} if rig is None or rig.rig == DEFAULT_RIG.rig else {"rig": rig}
        value=(call(reset_receipt) if call is not None else observe_parallel_initial_gate(
            reset_receipt, teacher_profile=teacher_profile, **rig_arguments, **reader_arguments))
        if type(value) is not InitialGateObservation:
            failures = ["type"]
        else:
            predicates = (
                ("reset_epoch", value.reset_epoch == reset_receipt.reset_epoch),
                (
                    "simulation_session",
                    value.simulation_session_id == reset_receipt.simulation_session_id,
                ),
                (
                    "freshness",
                    value.source_frame_monotonic_s
                    > reset_receipt.reset_completed_monotonic_s,
                ),
                (
                    "joints",
                    all(
                        abs(actual - expected) <= 0.002
                        for actual, expected in zip(
                            # R3-a: the drawn start pose of this attempt; every other attempt resets to zero
                            value.joint_positions,
                            getattr(self, "_start_poses", {}).get(lease.attempt_id, _RESET_JOINTS),
                            strict=True,
                        )
                    ),
                ),
                ("goals", not value.active_controller_goal_ids),
                ("attachment", not value.moveit_attached_object_ids),
                ("contact", value.has_contact is False),
                ("stable_graph", value.node_graph_stable is True),
                (
                    "worker_nodes",
                    self.worker_node_inventory_matches(value.worker_node_fqns, teacher_profile=teacher_profile, rig=rig),
                ),
            )
            failures = [name for name, accepted in predicates if not accepted]
        if failures:
            message = "POINT_INITIAL_GATE_OBSERVATION_REJECTED:" + ",".join(failures)
            if type(value) is InitialGateObservation and "worker_nodes" in failures:
                # The fault reason is capped at 300 characters, which cuts off a long node list. When the task directory
                # exists the whole observation is written there and the reason names the file, after a shorter summary.
                reference = self._write_gate_observation(lease, value, failures, teacher_profile=teacher_profile, rig=rig)
                message += ";worker_nodes=" + _worker_node_diagnostic(
                    value.worker_node_fqns, self.expected_worker_nodes(),
                    max_bytes=320 if reference is None else 100,
                )
                if reference is not None:
                    message += ";observation=" + reference
            raise RuntimeError(message)
        return SimpleNamespace(
            batch_id=lease.batch_id,
            coordinator_epoch=lease.coordinator_epoch,
            worker_id=lease.worker_id,
            worker_generation=lease.worker_generation,
            point_id=lease.point_id,
            attempt_id=lease.attempt_id,
            lease_generation=lease.lease_generation,
            reset_epoch=value.reset_epoch,
            simulation_session_id=value.simulation_session_id,
            source_frame_monotonic_s=value.source_frame_monotonic_s,
            canonical_joints=True,
            no_controller_goal=True,
            no_attachment=True,
            no_contact=True,
            no_stale_node=True,
        )

    def _write_gate_observation(self, lease, value, failures, *, teacher_profile, rig=None):
        """Write the complete rejected gate observation beside the task's other evidence; the file name, or None."""
        root = getattr(self.resources, "worker_root", None)
        attempt = str(getattr(lease, "attempt_id", ""))
        if root is None or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", attempt) is None:
            return None
        name = f"gate-observation-{attempt}.json"
        document = {
            "schema_version": 1,
            "kind": "POINT_INITIAL_GATE_OBSERVATION_REJECTED",
            "attempt_id": attempt,
            "failures": list(failures),
            "reset_epoch": value.reset_epoch,
            "simulation_session_id": value.simulation_session_id,
            "node_graph_stable": value.node_graph_stable,
            "has_contact": value.has_contact,
            "active_controller_goal_ids": list(value.active_controller_goal_ids),
            "moveit_attached_object_ids": list(value.moveit_attached_object_ids),
            "joint_positions": list(value.joint_positions),
            "worker_nodes": self.worker_node_inventory_report(
                value.worker_node_fqns, teacher_profile=teacher_profile, rig=rig),
        }
        payload = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        try:
            descriptor = os.open(Path(root) / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            return None
        return name

    def _capture_aligned(self):
        factory = self.dependencies.get("rgbd_source", RosRgbdSnapshotSource)
        source = factory()
        try:
            aligned = source.capture(15.0)
        except BaseException:
            source.close()
            raise
        return source, aligned, time.monotonic()

    def capture_rgb(self, path, boundary):
        from so101_demo.cli.rgbd_point_cloud import _decode_rgb, message_stamp_ns
        from so101_demo.runtime.point_cloud_preview import write_png_rgb8

        capture_attempt = 0
        while True:
            source, (camera, color, depth), received = self._capture_aligned()
            stamp = message_stamp_ns(color)
            minimum_stamp = self._minimum_inference_stamp_ns
            if (
                path.suffix == ".npy"
                and minimum_stamp is not None
                and stamp < minimum_stamp
            ):
                source.close()
                capture_attempt += 1
                if capture_attempt >= 5:
                    raise RuntimeError("RGB_SOURCE_PREDATES_CONSUMER_READY")
                continue
            break
        try:
            if received <= boundary:
                raise RuntimeError("RGB_SOURCE_NOT_FRESH")
            rgb = np.array(_decode_rgb(color), copy=True)
            # every captured frame is offered to the episode being recorded, here where the pixels and the
            # simulation stamp are both in hand - reading the PNG back later would need a decoder and would put
            # the frame behind its own acquisition. The sink is optional: a runtime that records nothing simply
            # does not have one, and `record` reports whether it took the frame.
            _sink = getattr(self, "episode_sink", None)
            if _sink is not None:
                _sink.record(camera, stamp_s=stamp / 1_000_000_000.0, pixels=rgb)
            if path.suffix == ".npy":
                path.parent.mkdir(parents=True, exist_ok=True)
                buffer = io.BytesIO()
                np.save(buffer, rgb, allow_pickle=False)
                payload = buffer.getvalue()
                descriptor = os.open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o400,
                )
                try:
                    os.write(descriptor, payload)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                receipt = InferenceSnapshotReceipt(
                    path,
                    received,
                    stamp,
                    color.header.frame_id,
                    tuple(rgb.shape),
                    hashlib.sha256(payload).hexdigest(),
                    simulation_session_id=self.resources.session_id,
                    source_clock="ros_sim",
                )
                batch_root = self.resources.worker_root.parent.parent
                relative = path.relative_to(self.resources.worker_root.parent)
                broker_copy = batch_root / "broker-inputs" / relative
                _mkdir_private_chain(
                    batch_root / "broker-inputs", broker_copy.parent
                )
                os.link(path, broker_copy, follow_symlinks=False)
                parent_fd = os.open(
                    broker_copy.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                )
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
                self._rgbd[stamp] = (source, camera, depth, color.header.frame_id)
                source = None
                self._minimum_inference_stamp_ns = None
                return receipt
            write_png_rgb8(rgb, path)
            return SourceStampedCapture(path, received, source_stamp_ns=stamp)
        finally:
            if source is not None:
                source.close()
