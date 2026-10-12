"""Head IPC retains raw masks, local tracks, original stamps and timing fences."""

import copy
import hashlib
import importlib

import numpy as np
import pytest

from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from so101_demo.core.detection import DetectionBatch, DetectionFrame, DetectionQuery
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from test_contract import response_document


class Clock:
    def __init__(self): self.now = 100_000_000
    def __call__(self): return self.now


class WireClient:
    generation = "g1"
    def __init__(self, clock):
        self.clock, self.calls, self.sequence = clock, [], 0
        self.before_return = lambda: None
        self.document = response_document()
    def new_request_id(self):
        self.sequence += 1
        return f"opaque-{self.sequence}"
    def infer(self, request, payload):
        self.calls.append((copy.deepcopy(request), payload))
        self.clock.now += 100_000_000
        self.before_return()
        document = copy.deepcopy(self.document)
        document.update(request_id=request["request_id"], source_stamp_ns=request["image"]["source_stamp_ns"],
                        source_frame_id=request["image"]["source_frame_id"])
        if document["batch"] is not None:
            document["batch"].update(source_stamp_ns=request["image"]["source_stamp_ns"],
                                    source_frame_id=request["image"]["source_frame_id"])
        return document


def make_backend(*, classes=None):
    module = importlib.import_module("so101_demo.adapters.act.head_ipc_detector")
    clock = Clock()
    context = {"session_id": "session", "attempt_id": "attempt", "reset_epoch": "reset-1",
               "lease_generation": 1, "worker_generation": 1, "sequence": 1,
               "search_deadline_ns": 2_000_000_000}
    client = WireClient(clock)
    classes = classes or {"0": "plastic_cup"}
    backend = module.HeadIpcDetector(client=client, context_probe=lambda: dict(context),
        policy=HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document()), monotonic_ns=clock,
        model_id="cup-model", weights_sha256="a" * 64, classes=classes,
        class_map_sha256=hashlib.sha256(canonical_json(classes)).hexdigest())
    return module, backend, client, clock, context


def frame():
    return DetectionFrame(np.arange(18, dtype=np.uint8).reshape(2, 3, 3), 7, "head")


def test_raw_pixels_mask_and_original_source_identity_survive_backend():
    _, backend, client, _, _ = make_backend()
    batch = backend.detect(frame(), DetectionQuery("plastic_cup"))
    assert (batch.model_id, batch.weights_sha256, batch.runtime_device) == ("cup-model", "a" * 64, "cuda")
    assert client.calls[0][1] == bytes(range(18))
    assert client.calls[0][0]["image"]["source_stamp_ns"] == 7
    assert set(client.calls[0][0]) == {"schema_version", "kind", "request_id", "image", "query_class_id", "deadline_monotonic_ns"}
    np.testing.assert_array_equal(batch.candidates[0].mask, [[True, True, False], [False, False, False]])
    assert (batch.candidates[0].source_stamp_ns, batch.candidates[0].source_frame_id) == (7, "head")


def test_serialization_is_included_in_frozen_end_to_end_budget(monkeypatch):
    module, backend, client, clock, _ = make_backend()
    original = module.pack_rgb
    def serialize(*args, **kwargs):
        clock.now += 40_000_000
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "pack_rgb", serialize)
    backend.detect(frame(), DetectionQuery("plastic_cup"))
    assert client.calls[0][0]["deadline_monotonic_ns"] == 1_100_000_000
    assert backend.last_evidence["end_to_end_wait_ns"] == 140_000_000


@pytest.mark.parametrize("field", ["attempt_id", "reset_epoch", "lease_generation", "worker_generation", "sequence"])
def test_cross_attempt_generation_and_sequence_response_never_enters_tracks(field):
    _, backend, client, _, context = make_backend()
    client.before_return = lambda: context.update({field: "changed" if type(context[field]) is str else 2})
    with pytest.raises(ValueError, match="HEAD_IPC_CONTEXT_CHANGED"):
        backend.detect(frame(), DetectionQuery("plastic_cup"))


def test_reset_fences_an_already_running_request_without_service_reset():
    _, backend, client, _, _ = make_backend()
    client.before_return = backend.reset
    with pytest.raises(ValueError, match="HEAD_IPC_CONTEXT_CHANGED"):
        backend.detect(frame(), DetectionQuery("plastic_cup"))
    assert len(client.calls) == 1


def test_valid_but_late_batch_is_rejected_by_earlier_search_deadline():
    _, backend, client, _, context = make_backend()
    context["search_deadline_ns"] = 150_000_000
    with pytest.raises(TimeoutError, match="HEAD_IPC_DEADLINE_EXCEEDED"):
        backend.detect(frame(), DetectionQuery("plastic_cup"))
    assert client.calls[0][0]["deadline_monotonic_ns"] == 150_000_000


def test_configured_cup_label_is_restored_as_a_valid_local_string_class():
    _, backend, client, _, _ = make_backend(classes={"0": "cup"})
    client.document["batch"]["candidates"][0]["class_id"] = "cup"
    batch = backend.detect(frame(), DetectionQuery("plastic_cup"))
    assert client.calls[0][0]["query_class_id"] == "cup"
    assert batch.candidates[0].class_id == "cup"


def test_foreign_class_is_not_renamed_into_a_cup():
    _, backend, client, _, _ = make_backend()
    client.document["batch"]["candidates"][0]["class_id"] = "bottle"
    with pytest.raises(ValueError, match="HEAD_IPC_CLASS_MISMATCH"):
        backend.detect(frame(), DetectionQuery("plastic_cup"))


def test_no_policy_is_not_filled_with_candidate_defaults():
    module, _, client, clock, context = make_backend()
    with pytest.raises(ValueError, match="HEAD_IPC_POLICY_REQUIRED"):
        module.HeadIpcDetector(client=client, context_probe=lambda: context, policy=None,
            monotonic_ns=clock, model_id="cup-model", weights_sha256="a" * 64,
            classes={"0": "plastic_cup"}, class_map_sha256="a" * 64)


def test_local_tracker_reset_also_fences_its_ipc_backend():
    from so101_demo.adapters.act.detector import HeadRgbDetector
    _, backend, client, _, _ = make_backend()
    local = HeadRgbDetector(backend, model_id="cup-model", weights_sha256="a" * 64,
                            tracking_iou=0.5, min_bbox_aspect=0.5)
    client.before_return = local.reset
    with pytest.raises(ValueError, match="HEAD_IPC_CONTEXT_CHANGED"):
        backend.detect(frame(), DetectionQuery("plastic_cup"))


def test_one_shard_cannot_submit_a_second_pending_head_request():
    import threading
    from concurrent.futures import ThreadPoolExecutor
    _, backend, client, _, _ = make_backend()
    entered, release = threading.Event(), threading.Event()
    def hold():
        entered.set()
        assert release.wait(2)
    client.before_return = hold
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(backend.detect, frame(), DetectionQuery("plastic_cup"))
        try:
            assert entered.wait(1)
            with pytest.raises(ValueError, match="HEAD_IPC_REQUEST_PENDING"):
                backend.detect(frame(), DetectionQuery("plastic_cup"))
            assert len(client.calls) == 1
        finally:
            release.set()
        assert len(first.result(timeout=1).candidates) == 1


def test_real_unix_head_batch_preserves_900027_dedup_and_track_continuity(tmp_path, monkeypatch):
    import time
    from dataclasses import replace
    from types import SimpleNamespace
    from paths import TEST_ROOT
    from test_act_head_detector_mask_deduplication import HIGH_BOX, LOW_BOX, candidate
    from so101_demo.adapters.act.detector import HeadRgbDetector
    from so101_demo.adapters.perception import detector_factory
    from so101_demo.runtime.inference.client import InferenceClient
    from so101_demo.runtime.inference.service import InferenceService, InferenceUnixServer
    from so101_demo.runtime.parallel_perception_runtime import normalize_batch
    from test_config_identity import campaign_fixture

    def no_local_model(*args, **kwargs):
        raise AssertionError("Worker must not construct a local detector model")
    monkeypatch.setattr(detector_factory, "build_detector", no_local_model)
    with np.load(TEST_ROOT / "data/head_900027_duplicate_masks.npz") as saved:
        original = [candidate("high", saved["high"], confidence=.9388879537582397, box=HIGH_BOX),
                    candidate("low", saved["low"], confidence=.2810225784778595, box=LOW_BOX)]
    config = campaign_fixture(tmp_path)["head_service"]
    config["model"].update(model_id="cup-model")
    config["model"]["weights"]["sha256"] = "a" * 64
    class ModelIO:
        ready = {"runtime_device": "cuda", "gpu_uuid": "GPU-selected"}
        def __init__(self): self.live = True
        def alive(self): return self.live
        def close(self): self.live = False; return True
        def infer(self, request, payload):
            image = request["image"]
            rgb = np.frombuffer(payload, np.uint8).reshape(image["shape"])
            captured = DetectionFrame(rgb, image["source_stamp_ns"], image["source_frame_id"])
            candidates = tuple(replace(item, source_stamp_ns=captured.source_stamp_ns,
                                       source_frame_id=captured.source_frame_id) for item in original)
            raw = DetectionBatch("cup-model", "a" * 64, "cuda", 1.0, 640, 480, candidates)
            return normalize_batch(raw, captured)
    service = InferenceService(config=config, executor_factory=lambda index, settings: ModelIO(),
        monotonic_ns=time.monotonic_ns, generation="g1", gpu_uuid="GPU-selected")
    service.start()
    server = InferenceUnixServer(service=service, socket_path=tmp_path / "head.sock", receive_budget_s=0.5)
    server.start()
    context = {"session_id": "s", "attempt_id": "a", "reset_epoch": "reset-1",
               "lease_generation": 1, "worker_generation": 1, "sequence": 1,
               "search_deadline_ns": time.monotonic_ns() + 3_000_000_000}
    try:
        backend = importlib.import_module("so101_demo.adapters.act.head_ipc_detector").HeadIpcDetector(
            client=InferenceClient(socket_path=tmp_path / "head.sock", service_generation="g1", max_frame_bytes=2**20),
            context_probe=lambda: dict(context), policy=HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document()),
            monotonic_ns=time.monotonic_ns, model_id="cup-model", weights_sha256="a" * 64,
            classes={"0": "plastic_cup"}, class_map_sha256=hashlib.sha256(canonical_json({"0": "plastic_cup"})).hexdigest())
        local = HeadRgbDetector(backend, model_id="cup-model", weights_sha256="a" * 64,
                                tracking_iou=.5, min_bbox_aspect=.5)
        for stamp in (1, 2):
            context["sequence"] = stamp
            result = local.detect(np.zeros((480, 640, 3), np.uint8), session_id="s", attempt_id="a",
                                  source_stamp_ns=stamp, source_frame_id="head_camera_frame")
            assert result == [dict(xyxy=HIGH_BOX, confidence=.9388879537582397, class_id=0, track_id="head-cup-0")]
            assert len(backend.last_evidence["raw_batch"]["candidates"]) == 2
            raw_candidate = backend.last_evidence["raw_batch"]["candidates"][0]
            from so101_demo.runtime.parallel_ros_ports.observations import _decode_row_major_mask
            np.testing.assert_array_equal(_decode_row_major_mask(raw_candidate["mask_rle"]), original[0].mask)
    finally:
        service.close()
        assert server.close()["terminated"] is True
