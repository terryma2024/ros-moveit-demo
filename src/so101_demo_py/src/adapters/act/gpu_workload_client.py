"""Task 11A: the closed GPU workload contract.

The campaign is CUDA-only by policy, so this client has no CPU path to fall back to: if the device
cannot be used, or a worker answers from a device other than the one requested, the submission is
refused rather than quietly downgraded. The model source is echoed back and compared, because a result
produced by a different model than the one requested is not evidence for this campaign.
"""

from __future__ import annotations

REQUEST_KEYS = frozenset({"schema_version", "kind", "workload", "model_source", "scene_id",
                          "payload_sha256", "allow_cpu_fallback"})
RESPONSE_KEYS = frozenset({"schema_version", "status", "device", "model_source", "result_sha256"})
_KINDS = ("act_teacher_inference", "act_expert_action")
_STATUSES = ("PASSED", "FAILED")


def _sha256(value) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("GPU_WORKLOAD_DIGEST_INVALID")
    return value


class GpuWorkloadClient:
    """Submits one closed workload request and validates the answer it gets back."""

    def __init__(self, *, device_port, runner) -> None:
        self.device_port = device_port
        self.runner = runner

    def submit(self, request: dict) -> dict:
        if not isinstance(request, dict) or set(request) != REQUEST_KEYS:
            raise ValueError("GPU_WORKLOAD_REQUEST_INVALID")
        if request["schema_version"] != 1 or request["kind"] not in _KINDS:
            raise ValueError("GPU_WORKLOAD_REQUEST_INVALID")
        if not isinstance(request["workload"], str) or not request["workload"]:
            raise ValueError("GPU_WORKLOAD_REQUEST_INVALID")
        if not isinstance(request["scene_id"], str) or not request["scene_id"]:
            raise ValueError("GPU_WORKLOAD_REQUEST_INVALID")
        _sha256(request["payload_sha256"])
        if request["allow_cpu_fallback"] is not False:
            raise ValueError("GPU_CPU_FALLBACK_FORBIDDEN")
        model_source = request["model_source"]
        if (not isinstance(model_source, dict)
                or set(model_source) != {"name", "sha256"}
                or not isinstance(model_source["name"], str) or not model_source["name"]):
            raise ValueError("GPU_WORKLOAD_REQUEST_INVALID")
        _sha256(model_source["sha256"])

        availability = self.device_port.available()
        if not isinstance(availability, dict) or availability.get("cuda") is not True:
            # no CPU path exists to fall back to, by policy
            raise ValueError("GPU_UNAVAILABLE_NO_CPU_FALLBACK")

        response = self.runner.run(dict(request))
        if not isinstance(response, dict) or set(response) != RESPONSE_KEYS:
            raise ValueError("GPU_WORKLOAD_RESPONSE_INVALID")
        if response["schema_version"] != 1 or response["status"] not in _STATUSES:
            raise ValueError("GPU_WORKLOAD_RESPONSE_INVALID")
        if response["device"] != "cuda":
            raise ValueError("GPU_DEVICE_MISMATCH")
        if response["model_source"] != model_source:
            raise ValueError("GPU_MODEL_SOURCE_MISMATCH")
        _sha256(response["result_sha256"])
        return response
