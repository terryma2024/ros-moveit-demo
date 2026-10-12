"""Private entry for one immutable head or Teacher inference container.

The Host extracts this role's closed service block into the read-only config
file. The service does not read the campaign index, leases, registered ROOT or
qualification report. This entry does not authorize a campaign or any motion.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import signal
import sys
import threading
import time
from types import SimpleNamespace

from so101_demo.runtime.inference.config import _open_regular, _service, verify_head_configuration
from so101_demo.runtime.inference.executor import SpawnExecutor
from so101_demo.runtime.inference.service import InferenceService, InferenceUnixServer
from so101_demo.runtime.parallel_ipc.frames import _decode_payload, canonical_json


def _document(path):
    with _open_regular(path) as stream:
        payload = stream.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise ValueError("INFERENCE_SERVICE_INPUT_INVALID: config size")
    return _decode_payload(payload), payload


def _inputs(arguments):
    config, _ = _document(arguments.config)
    try:
        _service(config, arguments.role, readback=True)
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("INFERENCE_SERVICE_INPUT_INVALID") from error
    if (arguments.startup_deadline_monotonic_ns <= time.monotonic_ns()
            or not arguments.gpu_uuid.startswith("GPU-")):
        raise ValueError("INFERENCE_SERVICE_INPUT_INVALID: startup identity/deadline")
    descriptor = None
    if arguments.role == "head":
        if arguments.head_descriptor is None or arguments.head_descriptor_sha256 is None:
            raise ValueError("HEAD_DESCRIPTOR_REQUIRED")
        descriptor, payload = _document(arguments.head_descriptor)
        if hashlib.sha256(payload).hexdigest() != arguments.head_descriptor_sha256:
            raise ValueError("HEAD_DESCRIPTOR_HASH_MISMATCH")
        expected = {"backend", "weights_path", "weights_sha256", "model_id", "image_size_px",
            "requested_device", "allow_cpu_fallback", "torch_threads", "torch_interop_threads",
            "torch_version", "ultralytics_version"}
        if (set(descriptor) != expected or descriptor["backend"] != "yolo_seg"
                or type(descriptor["image_size_px"]) is not int or descriptor["image_size_px"] != 640
                or any(type(descriptor[name]) is not str or not descriptor[name]
                       for name in ("torch_version", "ultralytics_version"))):
            raise ValueError("HEAD_DESCRIPTOR_INVALID")
        verify_head_configuration(config, binding=SimpleNamespace(detector=descriptor),
            runtime_versions={name: descriptor[name] for name in ("torch_version", "ultralytics_version")})
    elif arguments.head_descriptor is not None or arguments.head_descriptor_sha256 is not None:
        raise ValueError("INFERENCE_SERVICE_INPUT_INVALID: head/Teacher config mixed")
    return config, descriptor


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--role", choices=("head", "teacher"), required=True)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--gpu-uuid", required=True)
    parser.add_argument("--startup-deadline-monotonic-ns", type=int, required=True)
    parser.add_argument("--receive-budget-s", type=float, required=True)
    parser.add_argument("--head-descriptor", type=Path)
    parser.add_argument("--head-descriptor-sha256")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    try:
        config, descriptor = _inputs(arguments)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print(f"INFERENCE_SERVICE_INPUT_INVALID: {error}", file=sys.stderr)
        return 2
    stopping = threading.Event()
    previous_handlers = {}
    service, server = None, None
    result = 0
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda signum, frame: stopping.set())
        def factory(index, settings):
            if stopping.is_set():
                raise RuntimeError("INFERENCE_SERVICE_START_INTERRUPTED")
            return SpawnExecutor(index=index, config=settings, gpu_uuid=arguments.gpu_uuid,
                head_descriptor=descriptor, startup_deadline_monotonic_ns=arguments.startup_deadline_monotonic_ns)
        service = InferenceService(config=config, executor_factory=factory, monotonic_ns=time.monotonic_ns,
            generation=arguments.generation, gpu_uuid=arguments.gpu_uuid)
        service.start()
        server = InferenceUnixServer(service=service, socket_path=arguments.socket,
            receive_budget_s=arguments.receive_budget_s,
            audit=lambda event: print(canonical_json(event).decode(), flush=True))
        server.start()
        print(canonical_json(service.query({"schema_version": 1, "kind": "service_ready",
            "request_id": "startup"})).decode(), flush=True)
        while not stopping.wait(0.05):
            health = service.query({"schema_version": 1, "kind": "service_health", "request_id": "health"})
            if not health["available"]:
                raise RuntimeError(health["reason"])
    except (ValueError, RuntimeError, OSError) as error:
        print(f"INFERENCE_SERVICE_FAILED: {error}", file=sys.stderr)
        result = 1
    finally:
        # Mark unavailable/wake pending replies, stop all owned model processes,
        # then join socket handlers. No controller or other session is touched.
        if service is not None and not service.close()["terminated"]:
            print("INFERENCE_SERVICE_TERMINATION_UNCONFIRMED", file=sys.stderr)
            result = 1
        if server is not None and not server.close()["terminated"]:
            print("INFERENCE_SOCKET_TERMINATION_UNCONFIRMED", file=sys.stderr)
            result = 1
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
