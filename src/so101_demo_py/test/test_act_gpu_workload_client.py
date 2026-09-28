"""Task 11A GPU client: CUDA only, no silent fallback, model source echoed exactly."""

import pytest

from so101_demo.adapters.act.gpu_workload_client import GpuWorkloadClient


def _request(**overrides):
    request = {"schema_version": 1, "kind": "act_teacher_inference", "workload": "teacher-v1",
               "model_source": {"name": "act-teacher", "sha256": "a" * 64}, "scene_id": "act-1",
               "payload_sha256": "b" * 64, "allow_cpu_fallback": False}
    request.update(overrides)
    return request


def _response(**overrides):
    response = {"schema_version": 1, "status": "PASSED", "device": "cuda",
                "model_source": {"name": "act-teacher", "sha256": "a" * 64},
                "result_sha256": "c" * 64}
    response.update(overrides)
    return response


class _Device:
    def __init__(self, *, cuda=True):
        self._cuda = cuda

    def available(self):
        return {"cuda": self._cuda, "device_name": "L40S" if self._cuda else None}


class _Runner:
    def __init__(self, response=None, *, error=None):
        self.calls = []
        self._response, self._error = response or _response(), error

    def run(self, request):
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return self._response


def test_a_serviceable_request_returns_a_validated_response():
    runner = _Runner()
    client = GpuWorkloadClient(device_port=_Device(), runner=runner)
    assert client.submit(_request())["status"] == "PASSED"
    assert runner.calls[0]["scene_id"] == "act-1"


def test_no_cpu_fallback_and_only_cuda_answers_are_accepted():
    runner = _Runner()
    client = GpuWorkloadClient(device_port=_Device(cuda=False), runner=runner)
    with pytest.raises(ValueError, match="GPU_UNAVAILABLE_NO_CPU_FALLBACK"):
        client.submit(_request())
    assert runner.calls == []                                  # nothing was submitted

    for device in ("cpu", "mps", None):
        bad = GpuWorkloadClient(device_port=_Device(),
                                runner=_Runner(_response(device=device)))
        with pytest.raises(ValueError, match="GPU_DEVICE_MISMATCH"):
            bad.submit(_request())
    with pytest.raises(ValueError, match="GPU_CPU_FALLBACK_FORBIDDEN"):
        GpuWorkloadClient(device_port=_Device(), runner=_Runner()).submit(
            _request(allow_cpu_fallback=True))


def test_a_result_from_a_different_model_is_refused():
    other = _response(model_source={"name": "act-teacher", "sha256": "d" * 64})
    with pytest.raises(ValueError, match="GPU_MODEL_SOURCE_MISMATCH"):
        GpuWorkloadClient(device_port=_Device(), runner=_Runner(other)).submit(_request())
    for bad in (_response(status="MAYBE"), _response(result_sha256="short"),
                {"status": "PASSED"}, _response(schema_version=2)):
        with pytest.raises(ValueError, match="GPU_WORKLOAD_RESPONSE_INVALID|GPU_WORKLOAD_DIGEST_INVALID"):
            GpuWorkloadClient(device_port=_Device(), runner=_Runner(bad)).submit(_request())
    for bad in (_request(kind="something-else"), _request(payload_sha256="zz"),
                _request(model_source={"name": "act-teacher"}),
                _request(allow_cpu_fallback=None), {"scene_id": "act-1"}):
        expected = "GPU_WORKLOAD_REQUEST_INVALID|GPU_WORKLOAD_DIGEST_INVALID|GPU_CPU_FALLBACK_FORBIDDEN"
        with pytest.raises(ValueError, match=expected):
            GpuWorkloadClient(device_port=_Device(), runner=_Runner()).submit(bad)
