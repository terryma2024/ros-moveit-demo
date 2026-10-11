"""Admission, the served admission split, the parser, the inventory and the model factories."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from so101_demo.cli.macos_campaign.journal import IMPLEMENTED_OPERATIONS, _declared_digest
from so101_demo.parallel_batch.macos_two_worker_campaign import (
    read_inventory,
)
from so101_demo.runtime.unix_address import PRIVATE_TMP


def admission_decision(*, operation: str, request_id: str, serialized_request: object,
                       consumed_ids, bound_digest: str, cancelled_ids=()) -> dict | None:
    """The campaign's admission rule, as a pure function so it can be tested without a socket.

    Returns a refusal mapping the v4 server turns into a non-OK response, or `None` to serve. The
    order matters: an unimplemented operation is refused before anything else, and a repeated id is
    refused before it can consume the table a second time.
    """

    if operation not in IMPLEMENTED_OPERATIONS:
        return {"error": {"code": "UNKNOWN_OPERATION", "detail": operation}}
    if request_id in cancelled_ids:
        # A cancelled request's result is forfeit: it is refused whether or not it was ever consumed,
        # which is the safety-cancel property the Coordinator owns in the design.
        return {"error": {"code": "CANCELLED", "detail": request_id}}
    if request_id in consumed_ids:
        return {"error": {"code": "DUPLICATE_REQUEST", "detail": request_id}}
    if operation == "broker.infer":
        declared = _declared_digest(serialized_request)
        if declared != bound_digest:
            return {"error": {"code": "SNAPSHOT_MISMATCH", "detail": f"{request_id}: {declared!r}"}}
    return None


def serve_and_admit(campaign, *, request_id: str, candidates: int, device: str,
                    served: list, broker_pid: int, broker_birth_identity: int) -> dict | None:
    """Record one served response and consult the one-time table for it *now*.

    The table is the admission gate for every response, and it is also a bounded table of
    *outstanding* requests. Deferring every admission to the end of a campaign drains that bound:
    the drain issues one lease per point, and the registry refuses a new binding once its pending
    set is full (`REGISTRY_CAPACITY`), which is how the first seven-point drain stopped after five
    spawns. Admitting each response as it is served keeps the table's semantics exactly - nothing is
    served that the table will not admit - while keeping its pending set bounded.
    """

    decision = campaign.admit_response(
        request_id, broker_pid=broker_pid, broker_birth_identity=broker_birth_identity)
    entry = {"request_id": request_id, "candidates": candidates, "device": device,
             "admitted": bool(decision.accepted), "admission_reason": decision.reason}
    served.append(entry)
    if not decision.accepted:
        return {"error": {"code": "RESULT_NOT_ADMITTED", "detail": decision.reason}}
    return None


def served_admission_split(served) -> tuple[list[dict], list[dict]]:
    """The admitted and refused responses of one campaign, from the decisions made while serving."""

    admitted = [{"request_id": entry["request_id"], "reason": entry.get("admission_reason")}
                for entry in served if entry.get("admitted")]
    refused = [{"request_id": entry["request_id"], "reason": entry.get("admission_reason")}
               for entry in served if not entry.get("admitted")]
    return admitted, refused


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="so101_macos_two_worker_campaign",
        description="Run one exact-W2 macOS MPS campaign with the published model set.",
    )
    parser.add_argument("--config", type=Path, required=True,
                        help="the schema-v4 macOS MPS document")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--point-id", action="append", default=[],
                        help="repeatable; exact W2 keeps two slots regardless")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=None,
                        help="the immutable point catalog the selection is frozen from; the "
                             "installed document is used when this is omitted")
    parser.add_argument("--catalog-sha256", default=None,
                        help="the catalog digest the selection must match; drift is refused")
    parser.add_argument("--retry-root", type=Path, default=None,
                        help="v5 only: the prior campaign evidence root whose committed business "
                             "FAILED point this retry is bound to")
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--duplicate-probe", action="store_true",
                        help="have each Worker repeat one request id, so the one-time table's refusal "
                             "is exercised; off by default, because a refused request makes the "
                             "campaign verdict INCOMPLETE by construction")
    parser.add_argument("--cancel-second-worker-after-served", type=int, default=0,
                        help="fault injection: after this many served requests, cancel every "
                             "remaining request of the second Worker, whose results are then forfeit")
    parser.add_argument("--tamper-snapshot-sha", action="store_true",
                        help="fault injection: tell the Workers to declare a wrong snapshot digest, "
                             "so the bound-digest check must refuse them")
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

    from so101_demo.adapters.perception.detector_factory import (
        DetectorFactoryOptions,
        build_detector,
    )
    from so101_demo.adapters.perception.grounded_sam import GroundedSamThresholds
    from so101_demo.core.detection import DetectionQuery
    from so101_demo.parallel_batch.contracts.macos_two_worker import (
        ParallelRuntimeConfigMacosMpsTwoWorker,
    )

    def build(model_id: str):
        def factory():
            if model_id == "yolo":
                options = DetectorFactoryOptions(
                    backend="yolo_seg", requested_device="mps", allow_cpu_fallback=False,
                    yolo_weights_path=yolo_weights,
                    yolo_weights_sha256=ParallelRuntimeConfigMacosMpsTwoWorker.FROZEN_YOLO_WEIGHTS_SHA256,
                    yolo_model_id="plastic-cup-yolo11n-seg-v1", yolo_imgsz=640)
            else:
                options = DetectorFactoryOptions(
                    backend="grounded_sam", requested_device="mps", allow_cpu_fallback=False,
                    grounded_model_root=grounded_root,
                    grounded_manifest_sha256=(
                        ParallelRuntimeConfigMacosMpsTwoWorker.FROZEN_GROUNDED_SAM_MANIFEST_SHA256),
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
                        from so101_demo.core.detection import DetectionFrame as _Frame

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
