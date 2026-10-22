"""CLI: the host's ACT policy service for parallel closed-loop rollouts. Runs in the training interpreter (lerobot, torch).

Design: docs/superpowers/specs/2026-10-22-so101-act-parallel-rollout-design.md (P2). It loads ONE policy bundle on the GPU,
warms the model up and serves `policy_request`s from rollout shards over a Unix socket (`so101_demo.runtime.act_policy`): FIFO, one
inference at a time, at most `--max-inflight` requests in the system (more are answered `QUEUE_FULL`), every reply carrying the
bundle identity, the sequence, the observation stamp and the request's own timing.

Evidence, in the new `--record-dir` (nothing is overwritten):

    process-record.json   written before the model is loaded: pid, process group, start ticks, argv hash; the host identifies this
                          process by it before it signals it
    ready.json            written when the socket serves: the readiness reply (bundle and policy hashes, cameras, warm-up latencies)
    requests.jsonl        one row per answered request (request id, client, sequence, outcome, timing)
    stop-proof.json       written at SIGTERM/SIGINT after the accept loop, the worker and every connection thread have ended

Exit code: 0 stopped with a confirmed proof; 1 a fault after start, or a stop that could not be proven; 2 refused before start.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import threading
import time

from so101_demo.runtime.act_policy.service import (
    PolicyService, PolicyUnixServer, process_record, write_json)

DEFAULT_LEGACY_CAMERAS = ("head", "wrist")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="act_policy_service", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle-dir", type=Path, required=True, help="the policy bundle: bundle.json and policy.safetensors")
    parser.add_argument("--socket", type=Path, required=True, help="absolute path of the Unix socket (its directory is private)")
    parser.add_argument("--record-dir", type=Path, required=True, help="a NEW directory for the service's evidence")
    parser.add_argument("--generation", required=True, help="the service generation every reply names")
    parser.add_argument("--gpu-uuid", required=True)
    parser.add_argument("--max-inflight", type=int, default=8)
    parser.add_argument("--queue-timeout-s", type=float, default=1.0)
    parser.add_argument("--inference-timeout-s", type=float, default=0.5)
    parser.add_argument("--receive-budget-s", type=float, default=1.0)
    parser.add_argument("--max-frame-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--warm-up-calls", type=int, default=3)
    parser.add_argument("--undeclared-cameras", default=",".join(DEFAULT_LEGACY_CAMERAS),
                        help="the camera set of a bundle that declares none (the rollout config's undeclared_bundle_cameras)")
    return parser


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _refuse(message):
    print(f"POLICY_SERVICE_REFUSED: {message}", file=sys.stderr)
    return 2


def _check_arguments(args):
    for name in ("socket", "record_dir", "bundle_dir"):
        path = getattr(args, name)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{name} must be an absolute path")
    if args.record_dir.exists() or args.record_dir.is_symlink():
        raise ValueError("record dir exists")
    if not args.bundle_dir.is_dir() or not (args.bundle_dir / "bundle.json").is_file():
        raise ValueError("bundle dir holds no bundle.json")
    if not args.socket.parent.is_dir():
        raise ValueError("socket directory is missing")
    for name in ("max_inflight", "max_frame_bytes", "warm_up_calls"):
        if getattr(args, name) < 1:
            raise ValueError(f"{name} must be positive")
    for name in ("queue_timeout_s", "inference_timeout_s", "receive_budget_s"):
        if not 0 < getattr(args, name) < float("inf"):
            raise ValueError(f"{name} must be positive")


def bundle_identity(args) -> dict:
    """What every reply binds: the bundle file and policy hashes, the cameras, the state width, the image shape, the chunk size."""
    from so101_demo.act.bundle import load_bundle
    from so101_demo.act.policy import observation_spec

    bundle = load_bundle(args.bundle_dir / "bundle.json")
    spec = observation_spec(bundle, legacy_cameras=tuple(args.undeclared_cameras.split(",")))
    shape = bundle["normalization"].get("image_shape")
    if not isinstance(shape, list) or len(shape) != 3 or shape[0] != 3:
        raise ValueError("POLICY_BUNDLE_IMAGE_SHAPE_INVALID")
    return bundle, {"bundle_sha256": sha256_file(args.bundle_dir / "bundle.json"), "policy_sha256": bundle["policy_sha256"],
                    "cameras": list(spec["cameras"]), "state_dim": spec["state_dim"], "image_shape": [shape[1], shape[2], 3],
                    "chunk_size": bundle["action"]["chunk_size"], "device": "cuda"}


def default_policy_factory(bundle_dir, bundle, gpu_uuid):
    """The trained policy on CUDA, refused when the visible device is not the selected GPU."""
    import torch

    from so101_demo.adapters.act.lerobot import build_policy_from_bundle

    if not torch.cuda.is_available():
        raise RuntimeError("POLICY_SERVICE_CUDA_UNAVAILABLE")
    visible = str(torch.cuda.get_device_properties(0).uuid)
    if visible.removeprefix("GPU-") != gpu_uuid.removeprefix("GPU-"):
        raise RuntimeError(f"POLICY_SERVICE_GPU_MISMATCH: visible {visible}, selected {gpu_uuid}")
    return build_policy_from_bundle(bundle_dir, "cuda", bundle=bundle)


def serve(args, *, policy_factory=default_policy_factory, stop=None, install_signals=True, clock=time.monotonic_ns) -> int:
    from so101_demo.act.rollout_shared import warm_up_policy

    try:
        _check_arguments(args)
    except ValueError as error:
        return _refuse(error)
    stop = threading.Event() if stop is None else stop
    args.record_dir.mkdir(mode=0o700)
    record = process_record()
    write_json(args.record_dir / "process-record.json", {
        "schema_version": 1, "kind": "ACT_POLICY_SERVICE_PROCESS", **record, "socket": str(args.socket),
        "record_dir": str(args.record_dir), "bundle_dir": str(args.bundle_dir), "generation": args.generation,
        "gpu_uuid": args.gpu_uuid, "started_wall_ns": time.time_ns()})
    audit_handle = (args.record_dir / "requests.jsonl").open("x")
    audit_lock = threading.Lock()

    def audit(row):
        with audit_lock:
            audit_handle.write(json.dumps(row, sort_keys=True) + "\n")
            audit_handle.flush()

    previous = {}
    if install_signals:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
    service = server = None
    code = 1
    fault = None
    try:
        bundle, identity = bundle_identity(args)
        policy = policy_factory(args.bundle_dir, bundle, args.gpu_uuid)
        warm = warm_up_policy(policy, {"cameras": identity["cameras"], "state_dim": identity["state_dim"],
                                       "image_shape": identity["image_shape"]}, calls=args.warm_up_calls)
        identity["warm_up_s"] = warm
        service = PolicyService(infer=policy.infer, identity=identity, generation=args.generation, gpu_uuid=args.gpu_uuid,
                                max_inflight=args.max_inflight, queue_timeout_s=args.queue_timeout_s,
                                inference_timeout_s=args.inference_timeout_s, max_frame_bytes=args.max_frame_bytes,
                                monotonic_ns=clock, audit=audit)
        server = PolicyUnixServer(service=service, socket_path=args.socket, receive_budget_s=args.receive_budget_s)
        service.start()
        server.start()
        ready = service.query({"schema_version": 1, "kind": "policy_ready_query", "request_id": "startup"})
        write_json(args.record_dir / "ready.json", dict(ready, socket=str(args.socket), socket_inode=server.socket_inode))
        stop.wait()
        code = 0
    except Exception as error:      # noqa: BLE001 - reported in the stop proof; the service is stopped below either way
        fault = f"{type(error).__name__}: {error}"
        print(f"POLICY_SERVICE_FAILED: {fault}", file=sys.stderr)
    finally:
        server_stop = server.close() if server is not None else {"terminated": True}
        service_stop = service.close() if service is not None else {"terminated": True}
        audit_handle.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        terminated = server_stop["terminated"] is True and service_stop["terminated"] is True
        write_json(args.record_dir / "stop-proof.json", {
            "schema_version": 1, "kind": "ACT_POLICY_SERVICE_STOP_PROOF", "terminated": terminated, "fault": fault,
            "server": server_stop, "service": service_stop, "pid": record["pid"], "socket": str(args.socket),
            "socket_inode": None if server is None else server.socket_inode, "generation": args.generation})
    return code if terminated else 1


def main(argv=None, **kwargs) -> int:
    return serve(build_parser().parse_args(argv), **kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
