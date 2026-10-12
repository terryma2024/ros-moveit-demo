"""Exercise real spawn/pipe lifetimes without loading a GPU in ordinary tests."""

import importlib
import os
import time

import pytest

from test_config_identity import campaign_fixture
from test_contract import request_document, response_document


class LoadedFakeModel:
    runtime_device = "cuda"
    def infer(self, request, payload):
        assert payload == bytes(range(18))
        return response_document()["batch"]


def load_fake_model(config, gpu_uuid, head_descriptor):
    return LoadedFakeModel(), {"runtime_device": "cuda", "gpu_uuid": gpu_uuid, "pid": os.getpid()}


def load_cpu_model(config, gpu_uuid, head_descriptor):
    return LoadedFakeModel(), {"runtime_device": "cpu", "gpu_uuid": gpu_uuid, "pid": os.getpid()}


def executor_class():
    return importlib.import_module("so101_demo.runtime.inference.executor").SpawnExecutor


def test_spawn_child_owns_execution_and_binary_rgb_remains_unchanged(tmp_path):
    config = campaign_fixture(tmp_path)["teacher_service"]
    executor = executor_class()(index=0, config=config, gpu_uuid="GPU-selected", loader=load_fake_model,
        startup_deadline_monotonic_ns=time.monotonic_ns() + 5_000_000_000)
    try:
        assert executor.ready["pid"] != os.getpid()
        assert executor.start_method == "spawn"
        request = request_document() | {"deadline_monotonic_ns": time.monotonic_ns() + 2_000_000_000}
        assert executor.infer(request, bytes(range(18))) == response_document()["batch"]
    finally:
        assert executor.close() is True
    assert executor.alive() is False


def test_cpu_loader_cannot_become_ready_and_child_is_retired(tmp_path):
    config = campaign_fixture(tmp_path)["teacher_service"]
    with pytest.raises(RuntimeError, match="CUDA_REQUIRED"):
        executor_class()(index=0, config=config, gpu_uuid="GPU-selected", loader=load_cpu_model,
            startup_deadline_monotonic_ns=time.monotonic_ns() + 5_000_000_000)


def test_default_loader_without_torch_fails_closed_not_cpu_fallback(tmp_path):
    # This ordinary test interpreter intentionally has no ML dependencies.
    import importlib.util
    if importlib.util.find_spec("torch") is not None:
        pytest.skip("negative requires the non-ML test interpreter")
    config = campaign_fixture(tmp_path)["teacher_service"]
    with pytest.raises(RuntimeError, match="EXECUTOR_START_FAILED"):
        executor_class()(index=0, config=config, gpu_uuid="GPU-selected",
            startup_deadline_monotonic_ns=time.monotonic_ns() + 5_000_000_000)


def test_service_readiness_waits_for_three_distinct_spawned_model_owners(tmp_path):
    service_module = importlib.import_module("so101_demo.runtime.inference.service")
    config = campaign_fixture(tmp_path)["teacher_service"]
    config["model"].update(model_id="cup-model")
    config["model"]["weights"]["sha256"] = "a" * 64
    children = []
    deadline = time.monotonic_ns() + 10_000_000_000
    def factory(index, settings):
        child = executor_class()(index=index, config=settings, gpu_uuid="GPU-selected",
            loader=load_fake_model, startup_deadline_monotonic_ns=deadline)
        children.append(child)
        return child
    service = service_module.InferenceService(config=config, executor_factory=factory,
        monotonic_ns=time.monotonic_ns, generation="g1", gpu_uuid="GPU-selected")
    try:
        service.start()
        ready = service.query({"schema_version": 1, "kind": "service_ready", "request_id": "q"})
        assert (ready["configured_instances"], ready["loaded_instances"], ready["ready"]) == (3, 3, True)
        assert len({child.ready["pid"] for child in children}) == 3
        assert all(child.ready["pid"] != os.getpid() for child in children)
    finally:
        assert service.close()["terminated"] is True
    assert all(not child.alive() for child in children)
