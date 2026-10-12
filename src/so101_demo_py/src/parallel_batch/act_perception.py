"""ACT's single YOLO stage; existing local pose/safety admission still owns motion."""

from __future__ import annotations

import threading

from so101_demo.parallel_batch.contracts.common import AttemptStatus, ModelOutcome, _require_id
from so101_demo.parallel_batch.perception import (
    PerceptionDecision, PerceptionError, PerceptionPolicy, PoseAdmissionLatch,
)
from so101_demo.runtime.inference.contract import validate_inference_response


_WIRE_OUTCOMES = {
    "DETECTED": ModelOutcome.QUALIFIED,
    "NOT_DETECTED": ModelOutcome.NORMAL_REJECTION,
    "INPUT_INVALID": ModelOutcome.INFRA_ERROR,
    "QUEUE_FULL": ModelOutcome.INFRA_ERROR,
    "QUEUE_TIMEOUT": ModelOutcome.QUEUE_TIMEOUT,
    "INFERENCE_TIMEOUT": ModelOutcome.INFERENCE_TIMEOUT,
    "MODEL_ERROR": ModelOutcome.MODEL_ERROR,
    "INFRA_ERROR": ModelOutcome.INFRA_ERROR,
}


def map_inference_outcome(response):
    """QUALIFIED here means readable candidates, never physical task success."""
    document = validate_inference_response(response)
    return _WIRE_OUTCOMES[document["outcome"]]


class ActTeacherPerceptionPolicy(PerceptionPolicy):
    """A separate business policy sharing the unchanged guarded latch methods.

    Initialization and decisions never construct a Grounded stage. Inherited
    request/result/admit methods preserve the checks around local authorization,
    freshness, R6/geometry/quality, durable write and adjudication readback.
    The generic PerceptionPolicy retains its own fallback behavior.
    """

    def __init__(self, latch, *, yolo_model_id):
        _require_id("yolo_model_id", yolo_model_id)
        if not isinstance(latch, PoseAdmissionLatch):
            raise PerceptionError("LOCAL_ADMISSION_LATCH_REQUIRED")
        self.latch = latch
        self._models = {"yolo": yolo_model_id}
        self._outcomes = {"yolo": None}
        self._pending = None
        self._awaiting_admission = False
        self._lock = threading.RLock()

    def _stage(self, request):
        if request.model_id != self._models["yolo"]:
            raise PerceptionError("MODEL_SEQUENCE")
        return "yolo"

    @property
    def decision(self):
        with self._lock:
            if self.latch.requires_adjudication:
                return PerceptionDecision("INVALID", reason="PERCEPTION_INFRA_ERROR",
                                          attempt_status=AttemptStatus.INVALID)
            if self._pending is not None and not self._awaiting_admission:
                return PerceptionDecision("WAIT_RESULT")
            if self.latch.accepted:
                return PerceptionDecision("CONTINUE")
            outcome = self._outcomes["yolo"]
            if outcome is None:
                return PerceptionDecision("REQUEST_MODEL", self._models["yolo"])
            if outcome is ModelOutcome.QUALIFIED:
                return PerceptionDecision("ADMIT_POSE")
            if outcome is ModelOutcome.CANCELLED:
                return PerceptionDecision("CANCELLED", reason="PERCEPTION_CANCELLED")
            if outcome in (ModelOutcome.INFRA_ERROR, ModelOutcome.QUEUE_TIMEOUT, ModelOutcome.INFERENCE_TIMEOUT):
                return PerceptionDecision("INVALID", reason=f"PERCEPTION_{outcome.value}",
                                          attempt_status=AttemptStatus.INVALID)
            return PerceptionDecision("FAILED", reason=("PERCEPTION_MODEL_ERROR"
                if outcome is ModelOutcome.MODEL_ERROR else "PERCEPTION_NO_POSE"),
                attempt_status=AttemptStatus.FAILED)
