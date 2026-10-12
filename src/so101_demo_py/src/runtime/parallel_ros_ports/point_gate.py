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


class PointGate:
    def reset_point(self, lease):
        call = self.dependencies.get("reset_point")
        point = self.catalog[lease.point_id]
        act_kwargs = {"act_profile": True} if self.dependencies.get("act_profile") is True else {}
        qualified = call is None
        if qualified:
            call = self.dependencies.get("execute_reset")
        if call is None:
            from so101_demo.cli.teleop_reset import execute_mujoco_reset

            call = execute_mujoco_reset
        if qualified:
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
        evidence = observe(value.simulation_session_id)
        if (
            evidence.simulation_session_id != value.simulation_session_id
            or evidence.reset_epoch != value.new_epoch
        ):
            raise RuntimeError("RESET_WATERMARK_IDENTITY")
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
        namespace=self.worker_ros_namespace()
        call = self.dependencies.get("observe_initial")
        value=(call(reset_receipt) if call is not None else observe_parallel_initial_gate(
            reset_receipt,namespace=namespace,teacher_profile=teacher_profile))
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
                            value.joint_positions, _RESET_JOINTS, strict=True
                        )
                    ),
                ),
                ("goals", not value.active_controller_goal_ids),
                ("attachment", not value.moveit_attached_object_ids),
                ("contact", value.has_contact is False),
                ("stable_graph", value.node_graph_stable is True),
                (
                    "worker_nodes",
                    self.worker_node_inventory_matches(value.worker_node_fqns,
                                                       teacher_profile=teacher_profile,namespace=namespace),
                ),
            )
            failures = [name for name, accepted in predicates if not accepted]
        if failures:
            message = "POINT_INITIAL_GATE_OBSERVATION_REJECTED:" + ",".join(failures)
            if type(value) is InitialGateObservation and "worker_nodes" in failures:
                # The fault reason is capped at 300 characters, which cuts off a long node list. When the task directory
                # exists the whole observation is written there and the reason names the file, after a shorter summary.
                reference = self._write_gate_observation(
                    lease, value, failures, namespace=namespace, teacher_profile=teacher_profile)
                message += ";worker_nodes=" + _worker_node_diagnostic(
                    value.worker_node_fqns, tuple((namespace or '')+name for name in self.expected_worker_nodes()),
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

    def _write_gate_observation(self, lease, value, failures, *, namespace, teacher_profile):
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
                value.worker_node_fqns, teacher_profile=teacher_profile, namespace=namespace),
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
