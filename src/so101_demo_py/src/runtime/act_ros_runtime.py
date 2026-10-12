"""ACT shard's memory capture and YOLO-only RGB-D admission ports."""

from __future__ import annotations

from dataclasses import asdict

from so101_demo.parallel_batch.act_inference import (
    ActInferenceFrame, ActInferenceRequest, ActInferenceResult, ActLocalizedPose, ActPoseAdmissionLatch,
)
from so101_demo.parallel_batch.act_perception import ActTeacherPerceptionPolicy
from so101_demo.parallel_batch.contracts.common import ModelOutcome
from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
from so101_demo.runtime.parallel_ros_ports.observations import (
    CupCandidateLocalizer, _candidates_from_batch,
)


class ActRosRuntimePorts(ParallelRosRuntimePorts):
    REQUIRED = ParallelRosRuntimePorts.REQUIRED | {"capture_act_frame"}
    _latch_type = ActPoseAdmissionLatch
    _localized_pose_type = ActLocalizedPose

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._act_capture_sequence = 0

    def reset_point(self, lease):
        receipt = super().reset_point(lease)
        for source, *_rest in tuple(self._rgbd.values()):
            source.close()
        self._rgbd.clear()
        self._localized.clear()
        self._admitted.clear()
        self._admission_candidates.clear()
        return receipt

    def run_perception_chain(self, *args, **kwargs):
        try:
            return super().run_perception_chain(*args, **kwargs)
        finally:
            # Raw masks are only needed while the current local latch checks quality.
            self._admission_candidates.clear()

    def _candidate_list(self, response):
        self._check_perception_result(response)
        if response.outcome is not ModelOutcome.QUALIFIED:
            raise RuntimeError("ACT_DETECTED_RESPONSE_REQUIRED")
        return _candidates_from_batch(response.candidate)

    def _localize_response(self, response, **kwargs):
        return CupCandidateLocalizer().localize_candidates(self._candidate_list(response), **kwargs)

    def _depth_timestamp(self, request, depth):
        from so101_demo.cli.rgbd_point_cloud import message_stamp_ns
        return message_stamp_ns(depth) / 1e9

    def _perception_policy(self, latch):
        return ActTeacherPerceptionPolicy(latch, yolo_model_id=self.config.yolo_model_id)

    def _check_perception_input(self, lease, execution_kind, snapshot):
        if type(snapshot) is not ActInferenceFrame or snapshot.simulation_session_id != self.resources.session_id:
            raise RuntimeError("ACT_CAPTURE_IDENTITY_MISMATCH")

    def _check_perception_result(self, response):
        if type(response) is not ActInferenceResult:
            raise RuntimeError("ACT_INFERENCE_RESULT_REQUIRED")
        if response.request.simulation_session_id != self.resources.session_id:
            raise RuntimeError("ACT_INFERENCE_SESSION_CHANGED")

    def _failure_identity(self, response):
        outcome = response.response["outcome"]
        return f"ActInferenceResponse.{outcome}", response.reason or outcome

    def _has_failure_diagnostic(self, response):
        return response.outcome not in {ModelOutcome.QUALIFIED, ModelOutcome.CANCELLED}

    def _record_perception_response(self, workspace, response):
        relative = f"perception/inference/{response.request.request_id}.json"
        path = workspace.path / relative
        if path.exists() or path.is_symlink():
            raise RuntimeError("ACT_INFERENCE_AUDIT_ALREADY_EXISTS")
        workspace.write_json(relative, {"schema_version": 1, "kind": "ACT_LOCAL_INFERENCE_AUDIT",
                                        **asdict(response)})

    def _start_perception_request(self, policy, request, snapshot, **kwargs):
        if (type(request) is not ActInferenceRequest
                or (request.source_stamp_ns, request.source_frame_id, request.image_shape,
                    request.simulation_session_id, request.frame_sequence) != (
                    snapshot.source_stamp_ns, snapshot.source_frame_id, snapshot.shape,
                    snapshot.simulation_session_id, snapshot.sequence)):
            raise RuntimeError("ACT_REQUEST_CAPTURE_IDENTITY")
        super()._start_perception_request(policy, request, snapshot, **kwargs)

    def _result_is_current(self, policy, response):
        return policy.latch.check_result(response.request, response.broker_generation)

    def capture_act_frame(self, lease, boundary):
        from so101_demo.cli.rgbd_point_cloud import _decode_rgb, message_stamp_ns

        reset = self._reset_receipts.get(lease.attempt_id)
        if reset is None or reset.simulation_session_id != self.resources.session_id:
            raise RuntimeError("ACT_CAPTURE_RESET_IDENTITY")
        for _attempt in range(5):
            source, (camera, color, depth), received = self._capture_aligned()
            try:
                stamp = message_stamp_ns(color)
                if received <= boundary:
                    raise RuntimeError("RGB_SOURCE_NOT_FRESH")
                if self._minimum_inference_stamp_ns is not None and stamp < self._minimum_inference_stamp_ns:
                    continue
                if stamp / 1e9 <= reset.simulation_time_s:
                    raise RuntimeError("ACT_CAPTURE_PREDATES_RESET")
                self._act_capture_sequence += 1
                frame = ActInferenceFrame(_decode_rgb(color), received, stamp, color.header.frame_id,
                    self.resources.session_id, "ros_sim", self._act_capture_sequence)
                if stamp in self._rgbd:
                    raise RuntimeError("ACT_CAPTURE_SOURCE_ALREADY_OWNED")
                sink = getattr(self, "episode_sink", None)
                if sink is not None:
                    sink.record(camera, stamp_s=stamp / 1e9, pixels=frame.rgb8)
                self._rgbd[stamp] = (source, camera, depth, color.header.frame_id)
                source = None
                self._minimum_inference_stamp_ns = None
                return frame
            finally:
                if source is not None:
                    source.close()
        raise RuntimeError("RGB_SOURCE_PREDATES_CONSUMER_READY")
