"""Raw shared head inference; tracking/search/neck ownership stays in the shard."""

from __future__ import annotations

import copy
import hashlib
import threading

from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from so101_demo.core.detection import DetectionBatch, DetectionCandidate
from so101_demo.runtime.inference.codec import pack_rgb
from so101_demo.runtime.inference.contract import validate_inference_response
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_demo.runtime.parallel_ros_ports.observations import _decode_row_major_mask


_CONTEXT_FIELDS = {"session_id", "attempt_id", "reset_epoch", "lease_generation",
                   "worker_generation", "sequence", "search_deadline_ns"}
_CUP_CLASSES = frozenset({"plastic_cup", "cup"})


class HeadIpcDetector:
    def __init__(self, *, client, context_probe, policy, monotonic_ns, model_id,
                 weights_sha256, classes, class_map_sha256):
        if policy is None:
            raise ValueError("HEAD_IPC_POLICY_REQUIRED")
        # The admitting owner must supply its approved policy. Parsing a policy
        # here grants no approval and never fills a missing budget with defaults.
        self.policy = HeadSimulationPolicy.parse(policy.readback() if type(policy) is HeadSimulationPolicy else policy)
        if (type(classes) is not dict or not classes
                or hashlib.sha256(canonical_json(classes)).hexdigest() != class_map_sha256
                or not any(name in _CUP_CLASSES for name in classes.values())):
            raise ValueError("HEAD_IPC_CLASS_MAP_MISMATCH")
        self.client, self.context_probe, self.clock = client, context_probe, monotonic_ns
        self.model_id, self.weights_sha256 = model_id, weights_sha256
        self.classes = copy.deepcopy(classes)
        self.runtime_device = "cuda"
        self._pending = threading.Lock()
        self._state = threading.Lock()
        self._reset_generation = 0
        self.last_evidence = None

    def reset(self):
        """Fence a late local result; no reset/attempt message enters the service."""
        with self._state:
            self._reset_generation += 1
            self.last_evidence = None

    def _context(self):
        context = copy.deepcopy(self.context_probe())
        if type(context) is not dict or set(context) != _CONTEXT_FIELDS:
            raise ValueError("HEAD_IPC_CONTEXT_INVALID")
        if any(type(context[key]) is not str or not context[key]
               for key in ("session_id", "attempt_id", "reset_epoch")):
            raise ValueError("HEAD_IPC_CONTEXT_INVALID")
        if any(type(context[key]) is not int or context[key] <= 0
               for key in ("lease_generation", "worker_generation", "sequence", "search_deadline_ns")):
            raise ValueError("HEAD_IPC_CONTEXT_INVALID")
        return context

    def detect(self, frame, query):
        if not self._pending.acquire(blocking=False):
            raise ValueError("HEAD_IPC_REQUEST_PENDING")
        try:
            start = self.clock()  # Includes serialization, socket wait and local decoding.
            context = self._context()
            with self._state:
                reset_generation = self._reset_generation
            if query.class_id not in _CUP_CLASSES:
                raise ValueError("HEAD_IPC_CLASS_MISMATCH")
            accepted = set(self.classes.values()) & _CUP_CLASSES
            wire_class = query.class_id if query.class_id in accepted else sorted(accepted)[0]
            deadline = min(context["search_deadline_ns"], start + int(self.policy.perception_job_timeout_s * 1e9))
            image, payload = pack_rgb(frame.rgb8, stamp_ns=frame.source_stamp_ns, frame_id=frame.source_frame_id)
            if self.clock() >= deadline:
                raise TimeoutError("HEAD_IPC_DEADLINE_EXCEEDED")
            request = {"schema_version": 1, "kind": "inference_request", "request_id": self.client.new_request_id(),
                "image": image, "query_class_id": wire_class, "deadline_monotonic_ns": deadline}
            response = validate_inference_response(self.client.infer(request, payload))
            if (response["request_id"] != request["request_id"]
                    or response["service_generation"] != self.client.generation
                    or (response["source_stamp_ns"], response["source_frame_id"]) != (
                        frame.source_stamp_ns, frame.source_frame_id)):
                raise ValueError("HEAD_IPC_RESPONSE_IDENTITY_MISMATCH")
            raw = response["batch"]
            candidates = []
            latency = 0.0
            if response["outcome"] == "DETECTED":
                if (raw["model_id"] != self.model_id or raw["weights_sha256"] != self.weights_sha256
                        or raw["shape"] != list(frame.rgb8.shape)):
                    raise ValueError("HEAD_IPC_MODEL_OR_SOURCE_MISMATCH")
                latency = raw["inference_latency_ms"]
                for candidate in raw["candidates"]:
                    if candidate["class_id"] not in accepted:
                        raise ValueError("HEAD_IPC_CLASS_MISMATCH")
                    candidates.append(DetectionCandidate(candidate["instance_id"], candidate["class_id"],
                        candidate["confidence"], tuple(candidate["bbox_xyxy"]),
                        _decode_row_major_mask(candidate["mask_rle"]), frame.source_stamp_ns,
                        frame.source_frame_id, frame.image_width, frame.image_height, candidate["segmentation_quality"]))
            elif response["outcome"] != "NOT_DETECTED":
                raise RuntimeError(f"HEAD_IPC_{response['outcome']}: {response['reason']}")
            else:
                timing = response["timing"]
                if timing["completed_monotonic_ns"] is not None and timing["started_monotonic_ns"] is not None:
                    latency = (timing["completed_monotonic_ns"] - timing["started_monotonic_ns"]) / 1e6
            batch = DetectionBatch(self.model_id, self.weights_sha256, "cuda", latency,
                                   frame.image_width, frame.image_height, tuple(candidates))
            end = self.clock()
            evidence = {"request_id": request["request_id"], "source_stamp_ns": frame.source_stamp_ns,
                "source_frame_id": frame.source_frame_id, "context": context, "raw_batch": copy.deepcopy(raw),
                "timing": copy.deepcopy(response["timing"]), "end_to_end_wait_ns": end - start, "accepted": False}
            with self._state:
                self.last_evidence = evidence
                if reset_generation != self._reset_generation or self._context() != context:
                    raise ValueError("HEAD_IPC_CONTEXT_CHANGED")
                if end >= deadline or end < start:
                    raise TimeoutError("HEAD_IPC_DEADLINE_EXCEEDED")
                evidence["accepted"] = True
            return batch
        finally:
            self._pending.release()
