"""ACT-local capture/request association, independent of transport file identity."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from so101_demo.parallel_batch.contracts.common import (
    ExecutionKind, _require_finite, _require_id, _require_positive_int,
)
from so101_demo.parallel_batch.contracts.identity import _validate_execution_identity
from so101_demo.parallel_batch.perception import LocalizedPose, PerceptionError, PoseAdmissionLatch


@dataclass(frozen=True, slots=True)
class ActInferenceFrame:
    rgb8: np.ndarray
    source_stamp_monotonic_s: float
    source_stamp_ns: int
    source_frame_id: str
    simulation_session_id: str
    source_clock: str
    sequence: int

    def __post_init__(self):
        if (not isinstance(self.rgb8, np.ndarray) or self.rgb8.dtype != np.uint8
                or self.rgb8.ndim != 3 or self.rgb8.shape[2] != 3 or min(self.rgb8.shape) <= 0
                or not self.rgb8.flags.c_contiguous or self.source_clock != "ros_sim"):
            raise ValueError("ACT_INFERENCE_FRAME_INVALID")
        _require_finite("source_stamp_monotonic_s", self.source_stamp_monotonic_s)
        _require_positive_int("source_stamp_ns", self.source_stamp_ns)
        _require_positive_int("sequence", self.sequence)
        for value in (self.source_frame_id, self.simulation_session_id):
            if type(value) is not str or not value or any(character.isspace() for character in value):
                raise ValueError("ACT_INFERENCE_FRAME_INVALID")
        owned = np.array(self.rgb8, copy=True, order="C")
        owned.setflags(write=False)
        object.__setattr__(self, "rgb8", owned)

    @property
    def shape(self):
        return self.rgb8.shape


@dataclass(frozen=True, slots=True)
class ActInferenceRequest:
    request_id: str
    model_id: str
    image_timestamp_s: float
    execution_kind: ExecutionKind
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    lease_generation: int
    reset_epoch: str
    source_stamp_ns: int
    source_frame_id: str
    image_shape: tuple[int, int, int]
    simulation_session_id: str
    frame_sequence: int
    service_generation: str
    deadline_monotonic_ns: int
    attempt_id: str | None = None
    validation_id: str | None = None

    def __post_init__(self):
        try:
            for name in ("request_id", "model_id", "batch_id", "worker_id", "point_id", "reset_epoch",
                         "simulation_session_id", "service_generation"):
                _require_id(name, getattr(self, name))
            for name in ("coordinator_epoch", "worker_generation", "lease_generation", "source_stamp_ns",
                         "frame_sequence", "deadline_monotonic_ns"):
                _require_positive_int(name, getattr(self, name))
            _validate_execution_identity(execution_kind=self.execution_kind, attempt_id=self.attempt_id,
                                         validation_id=self.validation_id)
            _require_finite("image_timestamp_s", self.image_timestamp_s)
            if (self.image_timestamp_s <= 0 or round(self.image_timestamp_s * 1e9) != self.source_stamp_ns
                    or type(self.source_frame_id) is not str or not self.source_frame_id
                    or any(character.isspace() for character in self.source_frame_id)
                    or type(self.image_shape) is not tuple or len(self.image_shape) != 3
                    or self.image_shape[2] != 3
                    or any(type(value) is not int or value <= 0 for value in self.image_shape)):
                raise ValueError("image identity")
        except (ValueError, TypeError) as error:
            raise ValueError("ACT_INFERENCE_REQUEST_INVALID") from error


@dataclass(frozen=True)
class ActLocalizedPose(LocalizedPose):
    _request_type = ActInferenceRequest


class ActPoseAdmissionLatch(PoseAdmissionLatch):
    """Same durable/freshness/adjudication guards, one ACT memory identity type.

    The generic latch still accepts only InferenceRequest and its file input.
    This class cannot accept a generic request as an ACT compatibility format.
    """

    _request_type = ActInferenceRequest
    _localized_type = ActLocalizedPose

    def _validate_input_identity(self, request):
        if (request.simulation_session_id != self.context.session_id
                or request.source_frame_id != self.context.source_frame):
            raise PerceptionError("INPUT_SOURCE_IDENTITY_MISMATCH")


@dataclass(frozen=True)
class ActInferenceResult:
    request: ActInferenceRequest
    broker_generation: int
    response: dict
    started_monotonic_ns: int
    completed_monotonic_ns: int
    cancelled: bool = False

    def __post_init__(self):
        from so101_demo.runtime.inference.contract import validate_inference_response

        if type(self.request) is not ActInferenceRequest:
            raise ValueError("ACT_INFERENCE_RESULT_INVALID")
        _require_positive_int("broker_generation", self.broker_generation)
        _require_positive_int("started_monotonic_ns", self.started_monotonic_ns)
        _require_positive_int("completed_monotonic_ns", self.completed_monotonic_ns)
        if type(self.cancelled) is not bool:
            raise ValueError("ACT_INFERENCE_RESULT_INVALID")
        document = validate_inference_response(self.response)
        request = self.request
        if (self.completed_monotonic_ns < self.started_monotonic_ns
                or self.completed_monotonic_ns >= request.deadline_monotonic_ns
                or (document["request_id"], document["service_generation"],
                    document["source_stamp_ns"], document["source_frame_id"]) != (
                    request.request_id, request.service_generation,
                    request.source_stamp_ns, request.source_frame_id)):
            raise ValueError("ACT_INFERENCE_RESULT_IDENTITY_MISMATCH")
        batch = document["batch"]
        if batch is not None and (batch["model_id"] != request.model_id
                                  or tuple(batch["shape"]) != request.image_shape):
            raise ValueError("ACT_INFERENCE_RESULT_IDENTITY_MISMATCH")
        object.__setattr__(self, "response", document)

    @property
    def outcome(self):
        if self.cancelled:
            from so101_demo.parallel_batch.contracts.common import ModelOutcome
            return ModelOutcome.CANCELLED
        from so101_demo.parallel_batch.act_perception import map_inference_outcome
        return map_inference_outcome(self.response)

    @property
    def candidate(self):
        return self.response["batch"]

    @property
    def reason(self):
        return self.response["reason"]
