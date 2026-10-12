"""Plan prefix, consumer readiness, the dynamic manifest outcome and numeric evidence."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

from so101_demo.parallel_batch.contracts.common import AttemptStatus
from so101_demo.runtime.container_campaign.ros_namespace import container_ros_init_options
from so101_demo.parallel_batch.start_guard_probe import read_process_identity
from so101_demo.runtime.parallel_worker_parts.plan_prefix import RosDynamicPlanPrefixAdapter
from so101_demo.runtime.parallel_worker_parts.receipts import (
    ExecutionCompletionReceipt,
    NumericEvidenceReceipt,
    RuntimeDecision,
)


class ExecutionPorts:
    def _planning_adapter(self):
        if self._planner is not None:
            return self._planner
        call = self.dependencies.get("planning_adapter")
        if call is not None:
            self._planner = call()
            return self._planner
        from ament_index_python.packages import get_package_share_directory
        import rclpy
        from rclpy.parameter import Parameter

        from so101_demo.control.planning_scene.task_scene import RosTaskScenePort
        from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant

        context = rclpy.context.Context()
        rclpy.init(context=context,**container_ros_init_options())
        node = rclpy.create_node(
            "so101_parallel_planner",
            context=context,
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        try:
            loaded = load_dynamic_policy_variant(
                Path(get_package_share_directory("so101_demo_py")), backend="mujoco"
            )
            scene = RosTaskScenePort(
                node, "mujoco", loaded.template.planning_timeout_s
            )
            self._planner = RosDynamicPlanPrefixAdapter(
                node, loaded.template, scene, owned_context=context
            )
        except Exception:
            node.destroy_node()
            context.shutdown()
            raise
        return self._planner

    def plan_prefix(self, lease, admitted, states):
        return self._planning_adapter()(lease, admitted, states)

    @staticmethod
    def _command_option(command, name):
        try:
            index = command.index(name)
            return command[index + 1]
        except (AttributeError, IndexError, ValueError) as error:
            raise RuntimeError("DYNAMIC_READY_COMMAND_IDENTITY") from error

    def _consumer_ready_fence(self, child):
        command = tuple(getattr(child, "cmdline", ()))
        values = {
            name: self._command_option(command, f"--{name.replace('_', '-')}")
            for name in (
                "batch_id",
                "coordinator_epoch",
                "worker_id",
                "worker_generation",
                "point_id",
                "attempt_id",
                "lease_generation",
                "session_id",
                "expected_reset_epoch",
                "ready_receipt",
            )
        }
        expected_path = (
            Path(self.resources.worker_root)
            / "attempts"
            / values["point_id"]
            / values["attempt_id"]
            / "working/dynamic/consumer-ready.json"
        )
        path = Path(values["ready_receipt"])
        if path != expected_path:
            raise RuntimeError("DYNAMIC_READY_RECEIPT_PATH")
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > 8192
            ):
                raise RuntimeError("DYNAMIC_READY_RECEIPT_FILE_IDENTITY")
            payload = os.read(descriptor, 8193)
        finally:
            os.close(descriptor)
        if not payload.strip():
            return None     # created and not yet written: not ready yet (the Teacher publishes it atomically now)
        try:
            document = json.loads(payload)
        except (UnicodeError, json.JSONDecodeError) as error:
            if not payload.endswith(b"\n"):
                return None   # a receipt is one line with a final newline: a cut-off one is still being written
            raise RuntimeError("DYNAMIC_READY_RECEIPT_JSON") from error
        integer_fields = (
            "coordinator_epoch",
            "worker_generation",
            "lease_generation",
        )
        lease_identity = {
            name: int(values[name]) if name in integer_fields else values[name]
            for name in (
                "batch_id",
                "coordinator_epoch",
                "worker_id",
                "worker_generation",
                "point_id",
                "attempt_id",
                "lease_generation",
            )
        }
        expected = {
            "schema_version": 1,
            "kind": "dynamic_consumer_ready",
            "session_id": values["session_id"],
            "reset_epoch": int(values["expected_reset_epoch"]),
            "parallel_lease_identity": lease_identity,
        }
        if any(document.get(name) != value for name, value in expected.items()):
            raise RuntimeError("DYNAMIC_READY_RECEIPT_IDENTITY")
        if set(document) != {
            *expected,
            "ready_ros_ns",
            "ready_monotonic_s",
        }:
            raise RuntimeError("DYNAMIC_READY_RECEIPT_SCHEMA")
        ready_ros_ns = document["ready_ros_ns"]
        ready_monotonic_s = document["ready_monotonic_s"]
        if type(ready_ros_ns) is not int or ready_ros_ns <= 0:
            raise RuntimeError("DYNAMIC_READY_RECEIPT_ROS_TIME")
        if (
            isinstance(ready_monotonic_s, bool)
            or not isinstance(ready_monotonic_s, (int, float))
            or not math.isfinite(ready_monotonic_s)
            or ready_monotonic_s <= 0.0
            or ready_monotonic_s > time.monotonic()
        ):
            raise RuntimeError("DYNAMIC_READY_RECEIPT_MONOTONIC_TIME")
        return ready_ros_ns

    def consumer_ready(self, child):
        call = self.dependencies.get("consumer_ready")
        if call is not None:
            return call(child)

        deadline = time.monotonic() + 20.0
        # the container consumer runs under the stack namespace: its graph name is `<namespace>/so101_dynamic_cup_pick_place`
        consumer_name = (self.worker_ros_namespace() or "") + "/so101_dynamic_cup_pick_place"
        try:
            owner, publisher = self._prime_pose_publisher()
        except Exception:
            self._close_pose_publisher()
            return False
        while time.monotonic() < deadline:
            if read_process_identity(child.pid) is None:
                self._close_pose_publisher()
                return False
            try:
                owner.spin_once(timeout_sec=0.02)
                consumer_nodes = tuple(
                    f"{namespace.rstrip('/')}/{name}"
                    for name, namespace in owner.node.get_node_names_and_namespaces()
                    if name == "so101_dynamic_cup_pick_place"
                )
                if (
                    consumer_nodes == (consumer_name,)
                    and publisher.get_subscription_count() == 1
                    and owner.node.get_clock().now().nanoseconds > 0
                ):
                    ready_ros_ns = self._consumer_ready_fence(child)
                    if ready_ros_ns is not None:
                        self._minimum_inference_stamp_ns = ready_ros_ns
                        return True
            except Exception:
                self._close_pose_publisher()
                return False
        self._close_pose_publisher()
        return False

    def _dynamic_policy_identity(self):
        supplied = self.dependencies.get("dynamic_policy_identity")
        if supplied is not None:
            path, sha256 = supplied()
            return str(path), sha256
        from ament_index_python.packages import get_package_share_directory

        from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant

        loaded = load_dynamic_policy_variant(
            Path(get_package_share_directory("so101_demo_py")), backend="mujoco"
        )
        return str(loaded.path), loaded.sha256

    def _trusted_final_cup_pose(self, policy_path, policy_sha256):
        supplied = self.dependencies.get("expected_final_cup_pose_world")
        if supplied is not None:
            return list(supplied())
        path = Path(policy_path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != policy_sha256:
            raise ValueError("DYNAMIC_POLICY_CHANGED")
        from so101_demo.core.dynamic_pick import compose_pose, inverse_pose
        from so101_demo.core.dynamic_pick_policy import load_dynamic_pick_template

        template = load_dynamic_pick_template(
            path,
            expected_backend="mujoco",
            expected_execution_allowed=True,
        )
        return list(compose_pose(
            template.place_tcp_world,
            inverse_pose(template.cup_to_tcp_grasp),
        ).values)

    def _dynamic_manifest_outcome(self, manifest, lease, admitted, exit_code):
        """Verify one immutable terminal consumer document before classification."""
        descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_size <= 0
                or before.st_size > 8 * 1024 * 1024
            ):
                raise ValueError("DYNAMIC_MANIFEST_FILE")
            payload = os.read(descriptor, before.st_size + 1)
            after = os.fstat(descriptor)
            if (
                len(payload) != before.st_size
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            ):
                raise ValueError("DYNAMIC_MANIFEST_CHANGED")
        finally:
            os.close(descriptor)
        document = json.loads(payload)
        required = {
            "schema", "parallel_lease_identity", "status", "current_state",
            "failure", "simulation_session_id", "expected_reset_epoch",
            "policy_path", "policy_sha256", "state_trace", "transition_count",
            "state_events", "planning_attempts", "final_samples",
            "planning_scene_readback", "release_marker_sequence",
        }
        if type(document) is not dict or not required.issubset(document):
            raise ValueError("DYNAMIC_MANIFEST_SCHEMA")
        # Exactly two manifests are known, the general one and the Teacher one (minimal runtime gates); both carry the Teacher result.
        # Anything else is rejected rather than silently read with another meaning.
        from so101_demo.application.e2e_acceptance import (
            SCHEMA_GENERAL,
            SCHEMA_TEACHER,
            is_manifest_of,
        )

        if not is_manifest_of(document, SCHEMA_GENERAL, SCHEMA_TEACHER):
            raise ValueError("DYNAMIC_MANIFEST_SCHEMA")
        if not {
                "teacher_execution_status", "teacher_task_result", "act_data_status", "process_diagnostics",
                "teacher_start_observation", "teacher_end_observation"}.issubset(document):
            raise ValueError("DYNAMIC_MANIFEST_SCHEMA")
        expected_identity = {
            name: getattr(lease, name)
            for name in (
                "batch_id", "coordinator_epoch", "worker_id",
                "worker_generation", "point_id", "attempt_id",
                "lease_generation",
            )
        }
        if document["parallel_lease_identity"] != expected_identity:
            raise ValueError("DYNAMIC_MANIFEST_LEASE_IDENTITY")
        reset_epoch = getattr(admitted, "reset_epoch", None)
        if (
            not isinstance(reset_epoch, str)
            or not reset_epoch.startswith("reset-")
            or not reset_epoch[6:].isascii()
            or not reset_epoch[6:].isdecimal()
            or document["expected_reset_epoch"] != int(reset_epoch[6:])
            or document["simulation_session_id"] != self.resources.session_id
        ):
            raise ValueError("DYNAMIC_MANIFEST_RUNTIME_IDENTITY")
        policy_path, policy_sha256 = self._dynamic_policy_identity()
        # Content identity: a frozen run's Teacher loads the policy from the frozen snapshot, so its recorded path is
        # that copy's, not this worker's installed one. What must match is the content: the recorded sha256 is the
        # worker's own trusted policy's, and the trusted final pose is computed from the worker's file.
        if (
            not isinstance(document["policy_path"], str)
            or document["policy_sha256"] != policy_sha256
            or re.fullmatch(r"[0-9a-f]{64}", policy_sha256) is None
        ):
            raise ValueError("DYNAMIC_MANIFEST_POLICY_IDENTITY")
        status = document["status"]
        failure = document["failure"]
        if status == "DONE":
            # The Teacher child exits 0 when it COMPLETED and 1 otherwise; the data verdict is the Recorder's and is
            # never part of this exit code (Phase A4c).
            if exit_code != 0:
                raise ValueError("DYNAMIC_MANIFEST_DONE")
        elif status == "ERROR":
            # Exit 0 never ends an ERROR manifest.
            if exit_code == 0:
                raise ValueError("DYNAMIC_MANIFEST_ERROR")
        else:
            raise ValueError("DYNAMIC_MANIFEST_STATUS")
        from so101_demo.parallel_batch.dynamic_manifest import validate_dynamic_manifest_semantics

        outcome = validate_dynamic_manifest_semantics(
            document,
            expected_status=status,
            expected_reset_epoch=int(reset_epoch[6:]),
            expected_final_cup_pose_world=self._trusted_final_cup_pose(
                policy_path, policy_sha256
            ),
            frozen_execution_policy=self.dependencies.get("teacher_execution_policy"),
        )
        task = document["teacher_task_result"]
        # The Teacher manifest carries no data verdict (constant DISABLED); the Recorder's replaces it afterwards.
        data_status = document["act_data_status"]
        fields = dict(teacher_execution_status=document["teacher_execution_status"],
                      teacher_task_result=task["result"], act_data_status=data_status, act_data_reason=None)
        if outcome is AttemptStatus.PASSED:
            return outcome, "OK", fields
        if document["teacher_execution_status"] == "COMPLETED":
            first = task["reasons"][0].split(":", 1)[0] if task["reasons"] else task["result"]
            prefix = "TEACHER_TASK_FAIL" if outcome is AttemptStatus.FAILED else "TEACHER_TASK_UNCONFIRMED"
            return outcome, f"{prefix}:{first}", fields
        if outcome is AttemptStatus.FAILED:
            return outcome, failure, fields
        return outcome, f"{failure}:CONTROLLER_OUTCOME_UNCONFIRMED", fields

    def execute_result(self, lease, admitted, child):
        call = self.dependencies.get("execute_result")
        if call is not None:
            return call(lease, admitted, child)
        from so101_demo.parallel_batch.contracts.linux_cuda import teacher_execution_bound_s

        timeout_s = teacher_execution_bound_s(self.config)
        deadline = time.monotonic() + timeout_s
        status = None
        while time.monotonic() < deadline:
            waited, observed = os.waitpid(child.pid, os.WNOHANG)
            if waited == child.pid:
                status = os.waitstatus_to_exitcode(observed)
                break
            time.sleep(0.05)
        manifest = (
            self.resources.worker_root
            / f"attempts/{lease.point_id}/{lease.attempt_id}/working/dynamic/"
            "dynamic-execute-manifest.json"
        )
        from so101_demo.parallel_batch.contracts.common import AttemptStatus

        try:
            outcome, reason, teacher = self._dynamic_manifest_outcome(
                manifest, lease, admitted, status
            )
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            outcome = AttemptStatus.INDETERMINATE
            reason = "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"
            teacher = dict(teacher_execution_status="INDETERMINATE", teacher_task_result="UNCONFIRMED",
                           act_data_status="INVALID", act_data_reason="DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE")
        # The decision carries the Teacher's own result and the data verdict of its child side by side: the attempt
        # status is derived from the Teacher fields alone, and the result store grades the data separately.
        decision = RuntimeDecision(
            outcome,
            reason,
            physical_action_proven_absent=False,
            **teacher,
        )
        return ExecutionCompletionReceipt(decision, time.monotonic(), teacher_child_exited=status is not None)

    def capture_numeric_evidence(self, lease, localized, root, boundary):
        root.mkdir(parents=True, exist_ok=False)
        value, depth, localized_object = self._localized[lease.attempt_id]
        if value is not localized:
            raise RuntimeError("NUMERIC_LOCALIZATION_IDENTITY")
        physical = self._running_evidence(localized.request.image_timestamp_s)
        documents = {
            "depth.json": {
                "source_stamp_ns": localized.request.image_timestamp_s * 1_000_000_000,
                "sha256": localized.depth_sha256,
                "byte_count": len(depth.data),
            },
            "tf.json": {
                "source_frame": localized.source_frame,
                "target_frame": localized.target_frame,
                "source_stamp_s": localized.tf_timestamp_s,
                "center_world_xyz": list(localized.position_xyz),
            },
            "physical.json": asdict(physical),
        }
        paths = []
        for name, document in documents.items():
            path = root / name
            path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
            paths.append(path)
        observed = time.monotonic()
        if observed <= boundary:
            raise RuntimeError("NUMERIC_EVIDENCE_STALE")
        del localized_object
        try:
            return NumericEvidenceReceipt(*paths, observed)
        finally:
            stamp = round(localized.request.image_timestamp_s * 1_000_000_000)
            retained = self._rgbd.pop(stamp, None)
            if retained is not None:
                close = getattr(retained[0], "close", None)
                if callable(close):
                    close()

    def _running_evidence(self, minimum_simulation_time_s):
        call = self.dependencies.get("running_evidence")
        if call is not None:
            return call(self.resources.session_id, minimum_simulation_time_s)
        sources = [source for source, *_rest in self._rgbd.values()]
        if len(sources) != 1 or getattr(sources[0], "_node", None) is None:
            raise RuntimeError("RUNNING_EVIDENCE_SOURCE_CONTEXT")
        import rclpy

        from so101_demo.backends.mujoco.observer import EvidenceStale, MujocoWorldObserver

        node = sources[0]._node
        observer = MujocoWorldObserver(
            node, self.resources.session_id, max_age_s=1.0
        )
        deadline = time.monotonic() + self.RUNNING_EVIDENCE_TIMEOUT_S
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
            try:
                evidence = observer.snapshot()
            except EvidenceStale:
                continue
            if (
                evidence.simulation_session_id == self.resources.session_id
                and evidence.paused is False
                and evidence.simulation_time_s >= minimum_simulation_time_s
            ):
                return evidence
        # The failure names what the observer saw, so the next occurrence says whether the world was paused, behind the image
        # stamp, silent, or being rejected (the first one, S2 6b6efca6, left only the bare code).
        try:
            seen = {"minimum_simulation_time_s": minimum_simulation_time_s, "publishers": observer.publisher_count,
                    "callbacks": observer.callback_count, "rejected": observer.rejected_count,
                    "last_rejection": observer.last_rejection[:120], "latest": observer.latest_summary()}
        except Exception as error:   # noqa: BLE001  (an observation can never replace the failure it explains)
            seen = {"observation_failed": type(error).__name__}
        raise RuntimeError("RUNNING_EVIDENCE_UNAVAILABLE: " + json.dumps(seen, sort_keys=True, default=str))
