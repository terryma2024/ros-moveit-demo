"""Spawned model owners; the parent never imports Torch or creates CUDA state."""

from __future__ import annotations

import json
import multiprocessing
import os
import threading
import time
from types import SimpleNamespace

from so101_demo.adapters.perception.errors import (
    DeterministicModelResultError, ModelRuntimeInfrastructureError,
)
from so101_demo.runtime.inference.codec import decode_inference_frame, encode_inference_frame, unpack_rgb
from so101_demo.runtime.parallel_ipc.frames import _decode_payload, canonical_json


class _CudaModel:
    def __init__(self, detector, config):
        self.detector, self.config = detector, config
        self.runtime_device = detector.runtime_device

    def infer(self, request, payload):
        from so101_demo.core.detection import DetectionFrame, DetectionQuery
        from so101_demo.runtime.parallel_perception_runtime import normalize_batch

        rgb = unpack_rgb(request["image"], payload, limits=self.config)
        frame = DetectionFrame(rgb, request["image"]["source_stamp_ns"], request["image"]["source_frame_id"])
        batch = self.detector.detect(frame, DetectionQuery(request["query_class_id"]))
        if not batch.candidates:
            return None
        return normalize_batch(batch, frame)


def _load_cuda_model(config, gpu_uuid, head_descriptor):
    """Called only in the spawned child, after immutable config readback."""
    import subprocess
    from so101_demo.runtime.inference.config import _service, verify_head_configuration

    _service(config, "head" if head_descriptor is not None else "teacher", readback=True)
    import torch
    import ultralytics
    from so101_demo.adapters.perception.detector_factory import DetectorFactoryOptions, build_detector

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("CUDA_REQUIRED: exactly one selected device")
    observed = subprocess.run(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"],
        check=True, text=True, capture_output=True, timeout=5).stdout.strip().splitlines()
    if observed != [gpu_uuid]:
        raise RuntimeError("CUDA_GPU_UUID_MISMATCH")
    versions = {"torch_version": torch.__version__, "ultralytics_version": ultralytics.__version__}
    if head_descriptor is not None:
        verify_head_configuration(config, binding=SimpleNamespace(detector=head_descriptor), runtime_versions=versions)
    torch.set_num_threads(config["torch_threads"])
    torch.set_num_interop_threads(config["torch_interop_threads"])
    if (torch.get_num_threads() != config["torch_threads"]
            or torch.get_num_interop_threads() != config["torch_interop_threads"]):
        raise RuntimeError("HEAD_SEARCH_THREAD_DRIFT" if head_descriptor is not None else "INFERENCE_THREAD_DRIFT")
    from pathlib import Path
    model = config["model"]
    built = build_detector(DetectorFactoryOptions(backend="yolo_seg", requested_device="cuda",
        allow_cpu_fallback=False, yolo_weights_path=Path(model["weights"]["path"]),
        yolo_weights_sha256=model["weights"]["sha256"], yolo_model_id=model["model_id"],
        yolo_imgsz=640, yolo_score_threshold=model["score_threshold"]))
    actual_classes = {str(index): name for index, name in built.detector._class_names.items()}
    if actual_classes != model["classes"]:
        raise RuntimeError("INFERENCE_MODEL_CLASS_MAP_MISMATCH")
    return _CudaModel(built.detector, config), {"runtime_device": built.detector.runtime_device,
        "gpu_uuid": gpu_uuid, "pid": os.getpid(), **versions,
        "torch_threads": torch.get_num_threads(), "torch_interop_threads": torch.get_num_interop_threads()}


def _executor_main(pipe, index, config, gpu_uuid, head_descriptor, loader):
    try:
        model, ready = loader(config, gpu_uuid, head_descriptor)
        if model.runtime_device != "cuda" or ready["runtime_device"] != "cuda":
            raise RuntimeError("CUDA_REQUIRED")
        if ready["gpu_uuid"] != gpu_uuid:
            raise RuntimeError("CUDA_GPU_UUID_MISMATCH")
        pipe.send_bytes(canonical_json({"ready": ready, "error": None}))
    except BaseException as error:
        pipe.send_bytes(canonical_json({"ready": None, "error": f"EXECUTOR_START_FAILED: {type(error).__name__}: {error}"}))
        pipe.close()
        return
    try:
        while True:
            frame = pipe.recv_bytes(maxlength=config["max_frame_bytes"] + 4)
            if not frame:
                return
            request, payload = decode_inference_frame(frame, max_frame_bytes=config["max_frame_bytes"])
            received = time.monotonic_ns()
            batch, outcome, reason = None, "DETECTED", ""
            try:
                batch = model.infer(request, payload)
                if batch is None:
                    outcome, reason = "NOT_DETECTED", "NO_CANDIDATES"
            except ModelRuntimeInfrastructureError as error:
                outcome, reason = "INFRA_ERROR", str(error)
            except (DeterministicModelResultError, ValueError, KeyError, TypeError) as error:
                outcome, reason = "MODEL_ERROR", str(error)
            except Exception as error:
                outcome, reason = "INFRA_ERROR", str(error)
            response = {"schema_version": 1, "kind": "inference_response", "request_id": request["request_id"],
                "service_generation": f"executor-{index}", "source_stamp_ns": request["image"]["source_stamp_ns"],
                "source_frame_id": request["image"]["source_frame_id"], "outcome": outcome, "reason": reason,
                "batch": batch, "timing": {"received_monotonic_ns": received, "queued_monotonic_ns": received,
                    "started_monotonic_ns": received, "completed_monotonic_ns": time.monotonic_ns()}}
            try:
                encoded = encode_inference_frame(response, b"", max_frame_bytes=config["max_frame_bytes"])
            except ValueError:
                response.update(outcome="MODEL_ERROR", reason="RESPONSE_FRAME_INVALID_OR_TOO_LARGE", batch=None)
                encoded = encode_inference_frame(response, b"", max_frame_bytes=config["max_frame_bytes"])
            pipe.send_bytes(encoded)
            if outcome == "INFRA_ERROR":
                return
    except (EOFError, OSError):
        return
    finally:
        pipe.close()


class SpawnExecutor:
    def __init__(self, *, index, config, gpu_uuid, startup_deadline_monotonic_ns,
                 head_descriptor=None, loader=_load_cuda_model):
        if type(startup_deadline_monotonic_ns) is not int or startup_deadline_monotonic_ns <= time.monotonic_ns():
            raise ValueError("EXECUTOR_START_DEADLINE_INVALID")
        self.config, self.index = config, index
        self._lock = threading.Lock()
        context = multiprocessing.get_context("spawn")
        self.start_method = context.get_start_method()
        self._pipe, child_pipe = context.Pipe(duplex=True)
        self._process = context.Process(target=_executor_main,
            args=(child_pipe, index, config, gpu_uuid, head_descriptor, loader),
            name=f"act-yolo-executor-{index}", daemon=False)
        self._process.start()
        child_pipe.close()
        try:
            while not self._pipe.poll(0.01):
                if not self.alive():
                    raise RuntimeError("EXECUTOR_START_FAILED: child exited")
                if time.monotonic_ns() >= startup_deadline_monotonic_ns:
                    raise RuntimeError("EXECUTOR_START_FAILED: deadline exceeded")
            boot = _decode_payload(self._pipe.recv_bytes(maxlength=config["max_frame_bytes"]))
            if boot["error"] is not None:
                raise RuntimeError(boot["error"])
            self.ready = boot["ready"]
        except BaseException:
            self.close()
            raise

    def alive(self):
        return self._process.is_alive()

    def infer(self, request, payload):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("EXECUTOR_REQUEST_ALREADY_RUNNING")
        try:
            if not self.alive():
                raise ModelRuntimeInfrastructureError("EXECUTOR_EXITED")
            self._pipe.send_bytes(encode_inference_frame(request, payload,
                max_frame_bytes=self.config["max_frame_bytes"]))
            # The service can publish timeout while this call remains running.
            # Do not release the model's slot merely because the caller expired.
            while not self._pipe.poll(0.01):
                if not self.alive():
                    raise ModelRuntimeInfrastructureError("EXECUTOR_EXITED")
            response, _ = decode_inference_frame(self._pipe.recv_bytes(maxlength=self.config["max_frame_bytes"] + 4),
                max_frame_bytes=self.config["max_frame_bytes"])
            if response["request_id"] != request["request_id"]:
                raise ModelRuntimeInfrastructureError("EXECUTOR_RESPONSE_IDENTITY_MISMATCH")
            if response["outcome"] == "MODEL_ERROR":
                raise DeterministicModelResultError(response["reason"])
            if response["outcome"] == "INFRA_ERROR":
                raise ModelRuntimeInfrastructureError(response["reason"])
            return response["batch"]
        except (EOFError, OSError) as error:
            raise ModelRuntimeInfrastructureError("EXECUTOR_PIPE_FAILED") from error
        finally:
            self._lock.release()

    def close(self):
        if self.alive():
            try:
                self._pipe.send_bytes(b"")
            except (OSError, EOFError):
                pass
            self._process.join(timeout=0.2)
            if self.alive():
                self._process.terminate()
                self._process.join(timeout=2)
            if self.alive():
                self._process.kill()
                self._process.join(timeout=2)
        self._pipe.close()
        return not self.alive()
