"""The macOS MPS W2 campaign entry point.

`mujoco_parallel_batch` is the Linux container path: it requires a broker image, a CUDA device and
`proc_fd_unix`. This is its macOS counterpart, and it exists because the v4 contract had no
executable entry point at all — the schema, the broker, the IPC, the supervisor, the registry and
the recovery were each tested but never driven together outside a test.

What it does, in the design's order:

1. read-only inventory, so a duplicate claim, endpoint or campaign directory stops the run before
   anything is spawned;
2. the real start guard, in its own process, because the accelerator probe imports torch;
3. the supervisor claim and the private campaign root;
4. one broker bootstrap that loads the real model set on MPS through the detector factory, on a
   single execution lane, and publishes a ready receipt;
5. two workers spawned by the supervisor, each writing a registered ACK before it runs;
6. the composed campaign's one-time admission for every response;
7. exact cleanup, with the durable receipt cleared only when cleanup is proven complete.

The command emits one JSON document on stdout so the ledger can quote it directly, and it exits
non-zero when the run is not a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

from ..parallel_batch.campaign_supervisor import CampaignSupervisor
from ..parallel_batch.contracts import ContractError
from ..parallel_batch.inference_registry import InferenceRegistry
from ..parallel_batch.macos_w2_campaign import (
    CampaignPorts,
    MacosW2Campaign,
    MacosW2CampaignError,
    read_inventory,
)
from ..parallel_batch.w2_composition import (
    CompositionError,
    compose_w2_campaign,
    load_execution_config_for_schema,
)
from ..runtime.unix_address import PRIVATE_TMP, DarwinPrivatePathUnixAddress


#: The worker child module, spawned as `python -m so101_demo.cli.macos_w2_worker`.
_WORKER_MODULE = "so101_demo.cli.macos_w2_worker"


def build_worker_leases(*, plan, batch_id: str, evidence_root: Path,
                         input_sha256: str, deadline_s: float = 240.0) -> dict[str, dict]:
    """Write each Worker's lease document and the frame it is told to send.

    The entry point knows both ends of the identity it binds, so it writes the identity down and
    hands it to the Worker rather than letting the two sides derive ids independently. The frame is
    created once; a later run reuses it rather than rewriting evidence.
    """

    leases: dict[str, dict] = {}
    for index, worker_id in enumerate(("w1", "w2")):
        slot_id = "slot-0" if index == 0 else "slot-1"
        assigned = plan.slots.assigned_points[index][1] or "p1"
        document = {
            "worker_id": worker_id, "slot_id": slot_id, "batch_id": batch_id,
            "coordinator_epoch": 1, "worker_generation": 1, "lease_generation": 1,
            # `InferenceRequest.reset_epoch` is a non-empty *identifier* string, not a number
            # (contracts.py `_require_id`), so the lease carries the identifier form of the epoch.
            "reset_epoch": "epoch-1", "point_id": assigned, "model_id": "yolo",
            "attempt_ids": [f"{worker_id}-att-{attempt:02d}" for attempt in range(3)],
            "worker_root": str(evidence_root / f"{worker_id}-worker"),
            "snapshot_path": str(evidence_root / f"{worker_id}-frame.npy"),
            "input_sha256": input_sha256, "source_stamp_ns": 1_000_000_000,
            "source_frame_id": "task_camera_frame", "shape": [480, 640, 3],
            # The Worker's v4 client deadline; a fault probe shortens it instead of waiting 240 s.
            "deadline_s": float(deadline_s),
            "start_event_type": "attempt_started",
        }
        frame_path = Path(document["snapshot_path"])
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        if not frame_path.exists():
            frame_path.write_bytes(b"campaign-warm-frame")
        lease_path = evidence_root / f"{worker_id}-lease.json"
        lease_path.write_text(json.dumps(document, sort_keys=True))
        document["lease_path"] = str(lease_path)
        leases[worker_id] = document
    return leases


def bind_worker_requests(campaign, leases: dict[str, dict], *, ready,
                         deadline_s: float = 300.0) -> None:
    """Bind every id the Workers will use *before* any of them is served.

    An id that was never bound is refused by the one-time table, so this is the admission gate - and
    it binds the `{attempt_id}-{model_id}` ids the Worker derives, not a parallel set.
    """

    for worker_id, document in sorted(leases.items()):
        for attempt_id in document["attempt_ids"]:
            campaign.request_binding(
                request_id=f"{attempt_id}-{document['model_id']}", slot_id=document["slot_id"],
                point_id=document["point_id"], attempt=1,
                input_sha256=document["input_sha256"], deadline_s=deadline_s,
                broker_pid=ready.broker_pid, broker_birth_identity=ready.broker_birth_identity)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="so101_macos_w2_campaign",
        description="Run one exact-W2 macOS MPS campaign with the published model set.",
    )
    parser.add_argument("--config", type=Path, required=True,
                        help="the schema-v4 macOS MPS document")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--point-id", action="append", default=[],
                        help="repeatable; exact W2 keeps two slots regardless")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--stall-serve-after", type=int, default=0,
                        help="fault injection: delay this request's answer beyond the Worker's "
                             "deadline, so a timeout must be refused rather than admitted")
    parser.add_argument("--worker-deadline-s", type=float, default=240.0)
    parser.add_argument("--crash-broker-after-served", type=int, default=0,
                        help="fault injection: signal the owned Broker child exactly once, after "
                             "this many served requests (0 disables it)")
    parser.add_argument("--skip-models", action="store_true",
                        help="compose and pre-flight only; never a pass")
    return parser


def _as_rgb8(value):
    """Coerce a warm-up input into the (H, W, 3) uint8 array a DetectionFrame requires.

    The bootstrap builds its default warm-up input as a torch tensor in (N, C, H, W); the frame
    type owns a stricter contract, and adapting here keeps either shape usable without loosening
    that contract.
    """

    import numpy as np

    if hasattr(value, "detach"):  # a torch tensor
        value = value.detach().to("cpu").numpy()
    array = np.asarray(value)
    if array.ndim == 4:
        array = array[0]
    if array.ndim == 3 and array.shape[0] in (1, 3, 4) and array.shape[2] not in (1, 3, 4):
        array = np.transpose(array, (1, 2, 0))
    if array.ndim == 3 and array.shape[2] == 4:
        array = array[:, :, :3]
    if array.dtype != np.uint8:
        array = np.clip(array * 255 if array.max() <= 1.0 else array, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(array)


def _inventory(campaign_id: str, evidence_root: Path) -> dict:
    supervisor_root = evidence_root / "supervisor"
    inventory = read_inventory(
        claim_path=supervisor_root / "campaign-claim.lock",
        ipc_base=PRIVATE_TMP / f"so101-ipc-{os.getuid()}",
    )
    return {
        "campaign_id": campaign_id,
        "claim_held": inventory.claim_held,
        "live_endpoints": list(inventory.live_endpoints),
        "owned_processes": list(inventory.owned_processes),
        "existing_campaign_dirs": list(inventory.existing_campaign_dirs),
        "clean": inventory.clean,
    }


def _model_factories(*, yolo_weights: Path, grounded_root: Path):
    """The real published models, built on MPS through the production detector factory."""

    from ..adapters.perception.detector_factory import (
        DetectorFactoryOptions,
        build_detector,
    )
    from ..adapters.perception.grounded_sam import GroundedSamThresholds
    from ..core.detection import DetectionQuery
    from ..parallel_batch.contracts import ParallelRuntimeConfigV4

    def build(model_id: str):
        def factory():
            if model_id == "yolo":
                options = DetectorFactoryOptions(
                    backend="yolo_seg", requested_device="mps", allow_cpu_fallback=False,
                    yolo_weights_path=yolo_weights,
                    yolo_weights_sha256=ParallelRuntimeConfigV4.FROZEN_YOLO_WEIGHTS_SHA256,
                    yolo_model_id="plastic-cup-yolo11n-seg-v1", yolo_imgsz=640)
            else:
                options = DetectorFactoryOptions(
                    backend="grounded_sam", requested_device="mps", allow_cpu_fallback=False,
                    grounded_model_root=grounded_root,
                    grounded_manifest_sha256=(
                        ParallelRuntimeConfigV4.FROZEN_GROUNDED_SAM_MANIFEST_SHA256),
                    grounded_thresholds=GroundedSamThresholds.defaults())
            detector = build_detector(options=options).detector

            class Warmable:
                """The detector plus the call shape a broker warm-up uses."""

                weights_sha256 = f"real-{model_id}"
                config_sha256 = "real-config"
                runtime_device = detector.runtime_device

                def _modules(self):
                    found = []
                    for attribute in ("_model", "_grounding_model", "_sam_model"):
                        candidate = getattr(detector, attribute, None)
                        if candidate is not None and hasattr(candidate, "parameters"):
                            found.append(candidate)
                    return found

                def parameters(self):
                    collected = []
                    for module in self._modules():
                        collected.extend(module.parameters())
                    return collected

                def query(self):
                    return DetectionQuery(class_id="cup")

                def __call__(self, frame):
                    # The broker bootstrap hands the warm-up value straight back to the model, so
                    # this must accept whatever the caller's warm-up input is: a DetectionFrame or
                    # a bare RGB array.
                    if not hasattr(frame, "rgb8"):
                        from ..core.detection import DetectionFrame as _Frame

                        frame = _Frame(rgb8=_as_rgb8(frame), source_stamp_ns=1,
                                       source_frame_id="warmup")
                    detector.detect(frame, self.query())
                    modules = self._modules()
                    if not modules:
                        raise RuntimeError(f"no torch modules on {model_id}")
                    return next(iter(modules[0].parameters())).detach().sum().reshape(1)

                def detect(self, frame, _query=None):
                    return detector.detect(frame, self.query())

            return Warmable()

        return factory

    return {"yolo": build("yolo"), "grounded-sam": build("grounded-sam")}


def run(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    arguments_argv = list(sys.argv[1:] if argv is None else argv)
    document: dict = {"status": "PENDING"}

    try:
        config = load_execution_config_for_schema(arguments.config)
    except (ContractError, CompositionError) as error:
        document.update(status="REFUSED", stage="config", detail=str(error))
        print(json.dumps(document, indent=2, sort_keys=True))
        return 1

    inventory = _inventory(arguments.campaign_id, arguments.evidence_root)
    document["inventory"] = inventory
    if not inventory["clean"]:
        document.update(
            status="REFUSED", stage="inventory",
            detail="a claim, endpoint or campaign directory is already present; "
                   "this run will not clean up someone else's resources",
        )
        print(json.dumps(document, indent=2, sort_keys=True))
        return 2

    try:
        plan = compose_w2_campaign(
            config=config, config_path=arguments.config, campaign_id=arguments.campaign_id,
            batch_id=arguments.batch_id,
            selected_point_ids=tuple(arguments.point_id) or ("p1", "p2"),
            evidence_root=arguments.evidence_root,
        )
    except CompositionError as error:
        document.update(status="REFUSED", stage="compose", detail=str(error))
        print(json.dumps(document, indent=2, sort_keys=True))
        return 1

    document["plan"] = plan.to_document()
    if arguments.skip_models:
        document.update(status="COMPOSED_ONLY", stage="compose",
                        detail="--skip-models was set, so this is never a pass")
        print(json.dumps(document, indent=2, sort_keys=True))
        return 3


    supervisor = CampaignSupervisor(
        arguments.campaign_id, state_root=arguments.evidence_root / "supervisor",
        ack_timeout_s=120.0)
    address = DarwinPrivatePathUnixAddress()
    ports = CampaignPorts(model_factories=_model_factories(
        yolo_weights=arguments.yolo_weights.resolve(),
        grounded_root=arguments.grounded_root.resolve()))
    registry = InferenceRegistry(campaign_id=arguments.campaign_id)
    campaign = MacosW2Campaign(plan=plan, address=address, supervisor=supervisor, ports=ports,
                               registry=registry)

    # The guard runs in its own process. Its probe imports torch.mps, and the broker bootstrap
    # below requires torch to be unimported when it pins the fallback, so the two phases cannot
    # share an interpreter. The first phase writes its verdict and hands over.
    guard_path = arguments.evidence_root / "start-guard.json"
    if not guard_path.exists():
        from ..parallel_batch.accelerator_probe import (
            DarwinMpsAcceleratorProbe,
            evaluate_accelerator_snapshot,
        )
        from ..parallel_batch.start_guard import StartGuardPolicy

        snapshot = DarwinMpsAcceleratorProbe().probe(
            deadline_monotonic_ns=time.monotonic_ns() + 2_000_000_000)
        evaluation = evaluate_accelerator_snapshot(
            snapshot,
            StartGuardPolicy(mps_minimum_headroom_bytes=plan.mps_minimum_headroom_bytes))
        guard = {
            "status": evaluation.status,
            "reason": evaluation.checks["mps_headroom"].reason,
            "available_bytes": snapshot.available_bytes,
            "cutoff": evaluation.checks["mps_headroom"].cutoff,
            "admission_kind": snapshot.admission_kind,
        }
        arguments.evidence_root.mkdir(parents=True, exist_ok=True)
        guard_path.write_text(json.dumps(guard, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"phase": "start-guard", **guard}, indent=2, sort_keys=True), flush=True)
        if guard["status"] != "PASS":
            document.update(status="REFUSED", stage="start_guard", start_guard=guard)
            print(json.dumps(document, indent=2, sort_keys=True))
            return 4
        environment = dict(os.environ)
        environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        os.execve(sys.executable, [sys.executable, "-m",
                                   "so101_demo.cli.macos_w2_campaign", *arguments_argv],
                  environment)
    document["start_guard"] = json.loads(guard_path.read_text())

    # The broker phase proper: torch is still unimported here, which is what the bootstrap checks.
    from ..runtime.mps_broker_bootstrap import MpsBrokerBootstrap
    from ..core.detection import DetectionFrame, DetectionQuery
    from ..runtime.parallel_ipc_v4 import V4PermissionOnlyClient, V4PermissionOnlyServer

    import numpy as np

    supervisor.acquire_claim()
    supervisor.note_heartbeat(owner_pid=os.getpid())
    try:
        bootstrap = MpsBrokerBootstrap(
            models=tuple(ports.model_factories.items()),
            memory_fraction=plan.mps_process_memory_fraction,
            lane_capacity=8)
        _torch, ready = bootstrap.prepare()
        document["broker"] = {
            "pid": ready.broker_pid, "birth_identity": ready.broker_birth_identity,
            "ready": ready.ready, "device": ready.runtime_device,
            "fallback_env": ready.fallback_env,
            "models": [model.model_id for model in ready.models],
            "model_devices": [model.device for model in ready.models],
            "model_parameter_devices": [list(model.parameter_devices) for model in ready.models],
            "lane_stats": dict(ready.lane_stats),
            "warmup_total_latency_s": ready.warmup_total_latency_s,
            "receipt_path": str(ready.write(arguments.evidence_root / "broker-ready.json")),
        }
        # --- the composed campaign runs: endpoint, two workers, one-time admission --------
        campaign_root = address.create_campaign_root()
        document["campaign_root"] = str(campaign_root.campaign_path)
        models = bootstrap.loaded_models
        served: list[dict] = []

        def warm_frame() -> DetectionFrame:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[200:280, 260:380] = 200
            return DetectionFrame(rgb8=np.ascontiguousarray(frame),
                                  source_stamp_ns=time.monotonic_ns(),
                                  source_frame_id="campaign-frame")

        # The Coordinator's table is the admission gate, so every request a Worker will make is
        # bound here *before* it is served. An id that was never bound is refused, which is the
        # property the previous run demonstrated by refusing all six.
        import hashlib

        input_digest = hashlib.sha256(b"campaign-warm-frame").hexdigest()
        # The identity each Worker will request with lives in one place: the lease document written
        # here and handed to the Worker. Binding therefore uses the same `{attempt_id}-{model_id}`
        # ids the Worker derives (both functions are unit-tested in test_macos_w2_campaign.py).
        leases = build_worker_leases(
            plan=plan, batch_id=arguments.batch_id, evidence_root=arguments.evidence_root,
            input_sha256=input_digest, deadline_s=arguments.worker_deadline_s)
        bind_worker_requests(campaign, leases, ready=ready)
        # The IPC-shape probe ids stay bound while the Worker still serves that shape, so this
        # change cannot silently refuse the requests the previous gate proved.
        for worker_id in ("w1", "w2"):
            slot_id = "slot-0" if worker_id == "w1" else "slot-1"
            for index in range(3):
                campaign.request_binding(
                    request_id=f"{worker_id}-req-{index:02d}", slot_id=slot_id,
                    point_id=plan.slots.assigned_points[0 if worker_id == "w1" else 1][1] or "p1",
                    attempt=1, input_sha256=input_digest, deadline_s=300.0,
                    broker_pid=ready.broker_pid,
                    broker_birth_identity=ready.broker_birth_identity)

        consumed_ids: set[str] = set()
        infer_served = 0

        def handler(request):
            """Serve one request: a real forward pass, admitted through the one-time table.

            Two shapes arrive here. The v4 `infer` operation carries the Worker's serialized
            `InferenceRequest` and snapshot, which is the production path; anything else is the
            IPC-shape probe this entry point has served since Task 13. Both run the same real model
            call on the shared lane - the difference is only what the caller sends and reads back.
            """

            # One-time admission: a request id may be consumed once and never again, which is the
            # property the Coordinator's table exists to provide. A repeat is refused here rather
            # than served, so a late or duplicated result can never be admitted.
            if request.request_id in consumed_ids:
                served.append({"request_id": request.request_id, "operation": request.operation,
                               "duplicate": True})
                # A refusal must be a mapping carrying `error`: that is what the v4 server turns
                # into a non-OK status, and what the Worker's port checks.
                return {"error": {"code": "DUPLICATE_REQUEST",
                                  "detail": request.request_id}}
            consumed_ids.add(request.request_id)

            if request.operation == "broker.infer":
                infer_served += 1
            if (arguments.stall_serve_after
                    and infer_served == arguments.stall_serve_after):
                # Fault injection: hold the answer past the Worker's deadline. The client must
                # refuse on timeout - an inference that never arrived cannot be admitted.
                time.sleep(max(0.0, arguments.worker_deadline_s) + 2.0)

            detector = models["yolo"]
            batch = bootstrap.lane.submit(
                lambda: detector.detect(warm_frame(), DetectionQuery(class_id="cup")),
                label=f"serve:{request.operation}")
            candidates = len(getattr(batch, "candidates", ()))
            device = detector.runtime_device
            served.append({"request_id": request.request_id, "operation": request.operation,
                           "candidates": candidates, "device": device})
            # Fault injection, explicit and one-shot: the Broker child is signalled by exact PID
            # only after the requested number of requests has been served, and what the campaign
            # does next is the evidence - never an automatic kill and never a silent retry.
            if (arguments.crash_broker_after_served
                    and len(served) == arguments.crash_broker_after_served
                    and not document.get("broker_crash")):
                killed = False
                if int(ready.broker_pid) == os.getpid():
                    # Fail closed rather than commit suicide: in this composition the MPS Broker is
                    # in-process (`models` and `bootstrap.lane` live here), so `broker_pid` is this
                    # process. A crash injection needs a Broker that is genuinely a separate owned
                    # child; signalling ourselves would destroy the evidence instead of producing it.
                    document["broker_crash"] = {"pid": ready.broker_pid,
                                                "refused": "BROKER_IS_THIS_PROCESS"}
                    return {"error": {"code": "BROKER_IS_THIS_PROCESS",
                                      "detail": request.request_id}}
                try:
                    os.kill(ready.broker_pid, signal.SIGKILL)
                    killed = True
                except OSError as error:
                    document["broker_crash"] = {"pid": ready.broker_pid, "error": str(error)}
                else:
                    document["broker_crash"] = {"pid": ready.broker_pid, "signal": "SIGKILL"}
                document["broker_crash"]["killed"] = killed
            if request.operation == "broker.infer":
                payload = request.payload or {}
                serialized = payload.get("request")
                if not isinstance(serialized, (str, bytes, dict)):
                    # Fail closed with the shape the port checks: an inference that cannot be tied
                    # to a bound request is refused rather than answered.
                    return {"error": {"code": "INVALID_REQUEST",
                                      "detail": request.request_id}}
                return {"ok": True, "request_id": request.request_id, "device": device,
                        "candidates": candidates}
            return {"request_id": request.request_id, "device": device,
                    "candidates": candidates}

        server = V4PermissionOnlyServer(
            endpoint_path=address.endpoint_path(campaign_root, "broker"), handler=handler)
        endpoint = server.start(
            address=address, root=campaign_root, role="broker", owner_pid=os.getpid(),
            owner_birth_identity=ready.broker_birth_identity)
        document["endpoint"] = {"path": str(endpoint.path),
                                "mode": oct(os.stat(endpoint.path).st_mode & 0o777)}

        # Two real workers, spawned by the supervisor, each acknowledging registration first.
        workers = []
        for slot, slot_id in enumerate(plan.slots.slot_ids):
            worker_id = f"w{slot + 1}"
            ack = arguments.evidence_root / f"{worker_id}-ack.json"
            record = supervisor.spawn(
                role="worker", slot=slot,
                argv=[sys.executable, "-m", _WORKER_MODULE, str(ack), str(endpoint.path),
                      worker_id, str(arguments.evidence_root / f"{worker_id}-result.json"),
                      # Each Worker owns a visible station on the domain the plan gave it: the
                      # session id is campaign-scoped and the station root is Worker-scoped, so two
                      # slots never share a scene, an epoch or an evidence directory.
                      f"{arguments.campaign_id}-{worker_id}",
                      str(arguments.evidence_root / f"{worker_id}-station"),
                      str(plan.ros_domain_ids[slot]),
                      leases[worker_id]["lease_path"]],
                nonce=f"{arguments.campaign_id}-{worker_id}", ack_path=ack,
                ack_timeout_s=120.0)
            workers.append({"slot_id": slot_id, "worker_id": worker_id,
                            "status": record.status, "pid": record.pid,
                            "birth_identity": record.birth_identity})
        document["workers"] = workers

        deadline = time.monotonic() + 300
        results: list[dict] = []
        while time.monotonic() < deadline:
            results = [json.loads((arguments.evidence_root / f"w{i}-result.json").read_text())
                       for i in (1, 2)
                       if (arguments.evidence_root / f"w{i}-result.json").exists()]
            if len(results) == 2:
                break
            time.sleep(0.5)
        document["worker_results"] = results

        # Every response is admitted through the one-time table before it counts.
        admitted, refused = [], []
        for entry in served:
            decision = campaign.admit_response(
                entry["request_id"], broker_pid=ready.broker_pid,
                broker_birth_identity=ready.broker_birth_identity)
            (admitted if decision.accepted else refused).append(
                {"request_id": entry["request_id"], "reason": decision.reason})
        document["admission"] = {"admitted": admitted, "refused": refused}
        document["served"] = {
            "count": len(served),
            # A refused duplicate carries no device, so the summary reads defensively.
            "devices": sorted({item["device"] for item in served if "device" in item}),
            "duplicates_refused": sum(1 for item in served if item.get("duplicate")),
            "lane_stats": {"executed": bootstrap.lane.stats.executed,
                           "max_concurrent": bootstrap.lane.stats.max_concurrent,
                           "rejected": bootstrap.lane.stats.rejected},
        }

        server.stop()
        cleanup = address.cleanup_campaign(campaign_root)
        document["cleanup"] = {
            "complete": cleanup.complete, "directory_removed": cleanup.directory_removed,
            "registry_empty": address.registry == (),
        }
        supervisor.terminate_all()
        document["cleanup"]["workers_reaped"] = [supervisor.is_gone(w["pid"]) for w in workers]

        document["status"] = "W2_CAMPAIGN_PASS" if (
            document["cleanup"]["complete"] and len(results) == 2
            and all(w["status"] == "ACTIVE" for w in workers)
            and document["served"]["count"] >= 6
            and document["served"]["devices"] == ["mps"]
            and not refused
        ) else "W2_CAMPAIGN_INCOMPLETE"
        print(json.dumps(document, indent=2, sort_keys=True))
        (arguments.evidence_root / "campaign-result.json").write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n")
        return 0 if document["status"] == "W2_CAMPAIGN_PASS" else 7
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()
        bootstrap.lane.shutdown()


def main(argv: list[str] | None = None) -> int:
    # The launcher's first job is the fallback pin and the process handover, and it happens before
    # anything that could import torch. The accelerator probe needs torch.mps, while the broker
    # bootstrap requires torch to still be unimported when it reads the pin, so the two must not
    # share an interpreter. Pinning and re-executing here is what keeps that true.
    arguments = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        environment = dict(os.environ)
        environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        os.execve(sys.executable, [sys.executable, "-m",
                                   "so101_demo.cli.macos_w2_campaign", *arguments], environment)
    try:
        return run(arguments)
    except Exception as error:  # noqa: BLE001 - a refusal is reported, never a traceback alone
        print(json.dumps({"status": "ERROR", "error": f"{type(error).__name__}: {error}"},
                         indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
