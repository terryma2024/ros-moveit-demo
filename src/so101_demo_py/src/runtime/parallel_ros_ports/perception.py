"""Localisation, the perception chain and the admitted pose publisher."""

from __future__ import annotations

import hashlib
from pathlib import Path
import time

from so101_demo.application.object_pose import LocalizationError
from so101_demo.core.task_geometry import Pose7
from so101_demo.parallel_batch.contracts.common import ModelOutcome
from so101_demo.parallel_batch.perception import (
    AdmissionContext,
    LocalizedPose,
    PerceptionPolicy,
    PoseAdmissionLatch,
)
from so101_demo.runtime.parallel_ros_ports.isolated_node import (
    _EXACT_TF_DISCOVERY_TIMEOUT_S,
    _open_isolated_ros_node,
)
from so101_demo.runtime.parallel_ros_ports.observations import (
    AdmittedPose,
    CupCandidateLocalizer,
    PerceptionTerminal,
    _candidates_from_response,
)


class PerceptionPorts:
    _latch_type = PoseAdmissionLatch
    _localized_pose_type = LocalizedPose

    def _candidate_list(self, response):
        return _candidates_from_response(response)

    def _localize_response(self, response, **kwargs):
        return CupCandidateLocalizer().localize(response, **kwargs)

    def _depth_timestamp(self, request, depth):
        return request.image_timestamp_s

    def _perception_policy(self, latch):
        from so101_demo.runtime.parallel_perception_runtime import GROUNDED_ID
        return PerceptionPolicy(latch, yolo_model_id=self.config.yolo_model_id,
                                grounded_model_id=GROUNDED_ID)

    def _check_perception_input(self, lease, execution_kind, snapshot):
        pass

    def _check_perception_result(self, response):
        pass

    def _failure_identity(self, response):
        return f"BrokerResponse.{response.outcome.value}", response.reason or response.outcome.value

    def _has_failure_diagnostic(self, response):
        return response.outcome in {ModelOutcome.INFRA_ERROR, ModelOutcome.QUEUE_TIMEOUT,
                                    ModelOutcome.INFERENCE_TIMEOUT}

    def _record_perception_response(self, workspace, response):
        pass

    def _perception_terminal(self, decision, failure_type, failure_message):
        return PerceptionTerminal(decision.disposition, decision.reason or "PERCEPTION_TERMINAL",
                                  failure_type, failure_message)

    def _record_pose_rejection(self, reason):
        pass

    def _start_perception_request(self, policy, request, snapshot, *, depth_timestamp_s, depth_sha256):
        policy.start_request(request, depth_timestamp_s=depth_timestamp_s, depth_sha256=depth_sha256)

    def _result_is_current(self, policy, response):
        return True

    def localize(self, lease, broker_result):
        request = broker_result.request
        if broker_result.candidate.get("source_stamp_ns") != round(
            request.image_timestamp_s * 1_000_000_000
        ):
            raise RuntimeError("BROKER_RGB_IDENTITY_MISMATCH")
        try:
            source, camera, depth, frame_id = self._rgbd[
                round(request.image_timestamp_s * 1_000_000_000)
            ]
        except (AttributeError, KeyError) as error:
            raise RuntimeError("BROKER_RGBD_IDENTITY_MISSING") from error
        localized = self._localize_response(
            broker_result,
            camera_info=camera,
            depth_message=depth,
            lookup_exact=lambda target, frame, stamp: source.lookup_exact(
                target, frame, stamp, _EXACT_TF_DISCOVERY_TIMEOUT_S
            ),
        )
        depth_hash = hashlib.sha256(bytes(depth.data)).hexdigest()
        value = self._localized_pose_type(
            request,
            broker_result.broker_generation,
            self.resources.session_id,
            self._depth_timestamp(request, depth),
            depth_hash,
            request.image_timestamp_s,
            frame_id,
            "world",
            localized.center_world_xyz,
            (0.0, 0.0, 0.0, 1.0),
        )
        self._localized[lease.attempt_id] = (value, depth, localized)
        return value

    def _source_clock(self, reset_receipt):
        call = self.dependencies.get("source_clock")
        if call is not None:
            return call(reset_receipt)
        sources = [source for source, *_rest in self._rgbd.values()]
        if len(sources) != 1:
            raise RuntimeError("SOURCE_CLOCK_IDENTITY")
        node = getattr(sources[0], "_node", None)
        if node is None:
            raise RuntimeError("SOURCE_CLOCK_IDENTITY")
        return int(node.get_clock().now().nanoseconds) / 1_000_000_000.0

    def _dynamic_template(self):
        supplied = self.dependencies.get("dynamic_template")
        if supplied is not None:
            return supplied()
        from ament_index_python.packages import get_package_share_directory

        from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant

        return load_dynamic_policy_variant(
            Path(get_package_share_directory("so101_demo_py")), backend="mujoco"
        ).template

    def run_perception_chain(
        self, lease, execution_kind, snapshot, broker_request
    ):
        """Drive the business policy through the shared durable admission guards."""

        from so101_demo.cli.rgbd_point_cloud import message_stamp_ns
        from so101_demo.parallel_batch.contracts.common import ExecutionKind

        if execution_kind not in (ExecutionKind.ATTEMPT, ExecutionKind.VALIDATION):
            raise RuntimeError("PERCEPTION_EXECUTION_KIND")
        self._check_perception_input(lease, execution_kind, snapshot)
        if type(self.broker_generation) is not int or self.broker_generation <= 0:
            raise RuntimeError("BROKER_GENERATION_AUTHORITY")
        reset = self._reset_receipts.get(lease.attempt_id)
        if reset is None:
            raise RuntimeError("PERCEPTION_RESET_RECEIPT")
        try:
            _source, _camera, depth, _frame = self._rgbd[snapshot.source_stamp_ns]
        except KeyError as error:
            raise RuntimeError("PERCEPTION_RGBD_IDENTITY") from error
        depth_stamp_s = message_stamp_ns(depth) / 1_000_000_000.0
        depth_hash = hashlib.sha256(bytes(depth.data)).hexdigest()
        workspace_provider = self.dependencies.get("workspace_provider")
        authorize = self.dependencies.get("authorize")
        if not callable(workspace_provider) or not callable(authorize):
            raise RuntimeError("PERCEPTION_AUTHORITY_PORTS")
        template = self._dynamic_template()
        bounds = tuple(template.workspace_bounds_m)
        context = AdmissionContext(
            reset.simulation_session_id,
            reset.simulation_time_s,
            snapshot.source_frame_id,
            "world",
            self.config.max_frame_age_s,
            self.config.max_rgbd_skew_s,
            self.config.max_tf_skew_s,
        )

        def geometry_gate(request, localized):
            del request
            return all(
                bounds[index] <= localized.position_xyz[index] <= bounds[index + 3]
                for index in range(3)
            )

        def quality_gate(request, localized):
            response = self._admission_candidates.get(request.request_id)
            if (
                response is None
                or response.request != request
                or response.outcome is not ModelOutcome.QUALIFIED
                or localized.request != request
                or response.candidate.get("model_id") != request.model_id
            ):
                return False
            return any(candidate.mask.any() for candidate in self._candidate_list(response))

        latch = self._latch_type(
            workspace_provider(lease),
            context,
            broker_generation=self.broker_generation,
            clock=lambda: self._source_clock(reset),
            authorize=authorize,
            geometry_gate=geometry_gate,
            quality_gate=quality_gate,
        )
        policy = self._perception_policy(latch)
        decision = policy.decision
        source = self._rgbd[snapshot.source_stamp_ns][0]
        retain_source = False
        failure_type = None
        failure_message = None
        try:
            while decision.next_model is not None:
                response = broker_request(
                    decision.next_model,
                    before_send=lambda request: self._start_perception_request(
                        policy, request, snapshot,
                        depth_timestamp_s=depth_stamp_s,
                        depth_sha256=depth_hash,
                    ),
                )
                self._check_perception_result(response)
                self._record_perception_response(latch.workspace, response)
                if not self._result_is_current(policy, response):
                    decision = policy.record_result(response.request, ModelOutcome.CANCELLED,
                        broker_generation=response.broker_generation)
                    continue
                if response.broker_generation != self.broker_generation:
                    raise RuntimeError("BROKER_GENERATION_CHANGED")
                if self._has_failure_diagnostic(response):
                    failure_type, failure_message = self._failure_identity(response)
                if response.outcome is ModelOutcome.QUALIFIED:
                    self._admission_candidates[response.request.request_id] = response
                    try:
                        localized = self.localize(lease, response)
                    except LocalizationError as error:
                        if error.code != "GEOMETRY_REJECTED":
                            raise
                        self._record_pose_rejection(str(error))
                        decision = policy.record_result(
                            response.request,
                            ModelOutcome.NORMAL_REJECTION,
                            broker_generation=response.broker_generation,
                        )
                        continue
                    policy.record_result(
                        response.request,
                        response.outcome,
                        broker_generation=response.broker_generation,
                    )
                    decision = policy.admit_pose(response.request, localized)
                    if decision.disposition != "CONTINUE":
                        self._record_pose_rejection(latch.rejection_reason)
                    if decision.disposition == "CONTINUE":
                        admitted = self._admitted_pose(lease, localized)
                        self._admitted[lease.attempt_id] = admitted
                        retain_source = True
                        return admitted
                else:
                    decision = policy.record_result(
                        response.request,
                        response.outcome,
                        broker_generation=response.broker_generation,
                    )
            return self._perception_terminal(decision, failure_type, failure_message)
        finally:
            if not retain_source:
                close = getattr(source, "close", None)
                if callable(close):
                    close()
                self._rgbd.pop(snapshot.source_stamp_ns, None)

    @staticmethod
    def _admitted_pose(lease, localized):
        del lease
        pose = Pose7((*localized.position_xyz, *localized.orientation_xyzw))
        return AdmittedPose(
            "world",
            round(localized.request.image_timestamp_s * 1_000_000_000),
            time.monotonic(),
            pose,
            localized.request.reset_epoch,
            localized,
        )

    def admit_pose(self, lease, localized):
        if type(localized) is PerceptionTerminal:
            return localized
        if type(localized) is AdmittedPose:
            if self._admitted.get(lease.attempt_id) is not localized:
                raise RuntimeError("POSE_ADMISSION_IDENTITY")
            return localized
        if self._localized.get(lease.attempt_id, (None,))[0] is not localized:
            raise RuntimeError("POSE_LOCALIZATION_IDENTITY")
        return self._admitted_pose(lease, localized)

    def _close_pose_publisher(self):
        owner = self._pose_publisher_owner
        self._pose_publisher_owner = None
        self._pose_publisher = None
        if owner is not None:
            owner.close()

    def _prime_pose_publisher(self):
        if self._pose_publisher_owner is not None:
            if self._pose_publisher is None:
                raise RuntimeError("POSE_PUBLISHER_STATE")
            return self._pose_publisher_owner, self._pose_publisher
        if self._pose_publisher is not None:
            raise RuntimeError("POSE_PUBLISHER_STATE")

        from geometry_msgs.msg import PoseStamped
        import rclpy
        from rclpy.parameter import Parameter

        owner = _open_isolated_ros_node(
            rclpy,
            "so101_parallel_pose_publisher",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        try:
            publisher = owner.node.create_publisher(PoseStamped, "/cup_pose", 10)
            owner.start_background_spin()
        except Exception:
            owner.close()
            raise
        self._pose_publisher_owner = owner
        self._pose_publisher = publisher
        return owner, publisher

    def publish_pose(self, admitted):
        call = self.dependencies.get("publish_pose")
        if call is not None:
            return call(admitted)
        from geometry_msgs.msg import PoseStamped
        import rclpy
        from rclpy.parameter import Parameter

        retained = self._pose_publisher_owner is not None
        initialized_here = False
        if retained:
            owner, publisher = self._prime_pose_publisher()
            node = owner.node
            spin_once = lambda duration: owner.spin_once(timeout_sec=duration)
        else:
            initialized_here = not rclpy.ok()
            if initialized_here:
                rclpy.init()
            node = rclpy.create_node(
                "so101_parallel_pose_publisher",
                parameter_overrides=[Parameter("use_sim_time", value=True)],
            )
            publisher = node.create_publisher(PoseStamped, "/cup_pose", 10)
            spin_once = lambda duration: rclpy.spin_once(
                node, timeout_sec=duration
            )
        try:
            message = PoseStamped()
            message.header.frame_id = "world"
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(
                admitted.source_stamp_ns, 1_000_000_000
            )
            values = admitted.pose_world.values
            (
                message.pose.position.x,
                message.pose.position.y,
                message.pose.position.z,
                message.pose.orientation.x,
                message.pose.orientation.y,
                message.pose.orientation.z,
                message.pose.orientation.w,
            ) = values
            clock_deadline = time.monotonic() + 10.0
            while node.get_clock().now().nanoseconds < admitted.source_stamp_ns:
                remaining = clock_deadline - time.monotonic()
                if remaining <= 0.0:
                    return False
                spin_once(min(0.02, remaining))
            subscription_deadline = time.monotonic() + 2.0
            while (
                publisher.get_subscription_count() < 1
                and time.monotonic() < subscription_deadline
            ):
                spin_once(0.02)
            if publisher.get_subscription_count() < 1:
                return False
            # The consumer and this publisher receive /clock independently.
            # Under multi-stack startup load the consumer can momentarily lag
            # and reject the first source-stamped pose as future data.  Keep
            # retransmitting the identical admitted pose while its exact
            # subscription remains present; the consumer removes that
            # subscription as soon as it accepts one valid sample.
            # The consumer's absolute receive deadline is 5 seconds.  Cover
            # that whole interval at low rate so an independently delivered
            # /clock callback cannot be starved by future-stamped pose data.
            for _attempt in range(30):
                publisher.publish(message)
                for _spin in range(10):
                    spin_once(0.02)
                    if publisher.get_subscription_count() < 1:
                        break
                if publisher.get_subscription_count() < 1:
                    break
            return True
        finally:
            if not retained:
                node.destroy_node()
                if initialized_here and rclpy.ok():
                    rclpy.shutdown()
