"""The restart gates, refusals and receipt validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os

from so101_demo.act.head_search.restarts.contracts import (
    ANCHORS,
    CAMERA_IMAGE_TOPIC,
    CLOCK_TOPIC,
    DECLARED_FRAME_RATE_HZ,
    FRAME_PERIOD,
    KIND,
    LIFECYCLE,
    OPERATION,
    PHASE_BY_ANCHOR,
    RESTART_CADENCE_BROKEN,
    RESTART_DEVICE_UNAVAILABLE,
    RESTART_FOREIGN_OWNER_ACTIVE,
    RESTART_FRAME_RATE_MISMATCH,
    RESTART_GPU_NOT_RELEASED,
    RESTART_LOCK_UNPROVEN,
    RESTART_NODE_MISSING,
    RESTART_SEARCH_UNPROVEN,
    RESTART_SIM_CLOCK_STALLED,
    RESTART_STOP_UNPROVEN,
    RESTART_TEARDOWN_UNPROVEN,
    RESTART_TIMING_THRESHOLDS,
    _finite,
)
from so101_demo.act.head_search.restarts.observation import (
    classify_nodes,
    frame_thresholds,
    owner_process_counts,
)
from so101_demo.act.head_search.scenarios.plan import check_frame_cadence
from so101_demo.act.head_search.timing_measurement.contracts import (
    DEFAULT_MAX_SETTLE_S,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def _owner_counts(stack: Mapping) -> dict:
    declared = stack.get("owner_processes")
    if isinstance(declared, Mapping) and declared:
        return dict(declared)
    return owner_process_counts(stack.get("processes") or ())


def _detector_gate(anchor_run: Mapping) -> str:
    detector = anchor_run.get("detector") or {}
    ok = (
        detector.get("loaded") is True
        and int(detector.get("count", 0)) == 1
        and str(detector.get("device")) == "cuda"
        and detector.get("allow_cpu_fallback") is False
        and str(detector.get("runtime_device", "")).startswith("cuda")
        and bool(detector.get("weights_sha256"))
    )
    return "PASS" if ok else "FAIL"


def _graph_gate(anchor_run: Mapping) -> str:
    stack = anchor_run.get("stack") or {}
    graph = classify_nodes(stack.get("nodes") or ())
    if graph["missing"] or graph["foreign"]:
        return "FAIL"
    owners = _owner_counts(stack)
    if int(owners.get("mujoco_instances", 0)) != 1 or int(owners.get("controller_owners", 0)) != 1:
        return "FAIL"
    return "PASS"


def _search_gate(anchor_run: Mapping) -> str:
    search = anchor_run.get("search") or {}
    ok = (
        search.get("terminal_status") == "TARGET_LOCKED"
        and search.get("coverage_complete") is True
        and int(search.get("wrong_locks", 0)) == 0
    )
    return "PASS" if ok else "FAIL"


def _lock_gate(anchor_run: Mapping) -> str:
    lock = anchor_run.get("lock") or {}
    consecutive = lock.get("consecutive_frames")
    ok = type(consecutive) is int and not isinstance(consecutive, bool) and consecutive >= 3
    return "PASS" if ok else "FAIL"


def _timing_gate(anchor_run: Mapping) -> str:
    timing = anchor_run.get("timing") or {}
    ok = (
        timing.get("cadence_continuous") is True
        and timing.get("within_thresholds") is True
        and _finite(timing.get("frame_rate_hz"))
        and abs(float(timing["frame_rate_hz"]) - DECLARED_FRAME_RATE_HZ) <= 1e-9
    )
    return "PASS" if ok else "FAIL"


def _stop_gate(anchor_run: Mapping) -> str:
    proof = anchor_run.get("stop") or {}
    ok = proof.get("proven") is True and int(proof.get("qualifying_samples", 0)) >= 3
    return "PASS" if ok else "FAIL"


def restart_gates(anchor_run: Mapping) -> dict:
    """The plan's six gates, each re-derived from the evidence rather than read from a claim."""

    return {
        "graph": _graph_gate(anchor_run),
        "detector": _detector_gate(anchor_run),
        "search": _search_gate(anchor_run),
        "lock": _lock_gate(anchor_run),
        "timing": _timing_gate(anchor_run),
        "stop": _stop_gate(anchor_run),
    }


def restart_refusals(document: Mapping) -> list[dict]:
    """Every refusal this document's own evidence fires, in the order a reader should fix them."""

    refusals: list[dict] = []
    stack = document.get("stack") or {}
    graph = classify_nodes(stack.get("nodes") or ())
    owners = _owner_counts(stack)
    if graph["missing"]:
        refusals.append(
            {
                "code": RESTART_NODE_MISSING,
                "item": "graph",
                "detail": f"the reconstructed stack published no {', '.join(graph['missing'])} node",
            }
        )
    if graph["foreign"]:
        refusals.append(
            {
                "code": RESTART_FOREIGN_OWNER_ACTIVE,
                "item": "graph",
                "detail": f"the graph carried nodes this phase does not own: {graph['foreign']}",
            }
        )
    for name in ("mujoco_instances", "controller_owners"):
        if int(owners.get(name, 0)) != 1:
            refusals.append(
                {
                    "code": RESTART_FOREIGN_OWNER_ACTIVE,
                    "item": "processes",
                    "detail": f"the process table carried {owners.get(name)} {name}, not exactly one",
                }
            )
    camera = document.get("camera") or {}
    if camera.get("matches_declared") is not True:
        refusals.append(
            {
                "code": RESTART_FRAME_RATE_MISMATCH,
                "item": "camera",
                "detail": (
                    f"{CAMERA_IMAGE_TOPIC} published at {camera.get('measured_rate_hz')!r} Hz over "
                    f"{camera.get('frames')} frames, and the production config declares "
                    f"{camera.get('declared_rate_hz')!r} Hz"
                ),
            }
        )
    clock = document.get("clock") or {}
    if clock.get("advancing") is not True:
        refusals.append(
            {
                "code": RESTART_SIM_CLOCK_STALLED,
                "item": "clock",
                "detail": f"{CLOCK_TOPIC} advanced {clock.get('delta_s')!r} s while the phase watched it",
            }
        )
    if _detector_gate(document) != "PASS":
        detector = document.get("detector") or {}
        refusals.append(
            {
                "code": RESTART_DEVICE_UNAVAILABLE,
                "item": "detector",
                "detail": (
                    f"the restart did not run exactly one CUDA detector without CPU fallback: "
                    f"count={detector.get('count')!r} device={detector.get('device')!r} "
                    f"runtime_device={detector.get('runtime_device')!r} "
                    f"allow_cpu_fallback={detector.get('allow_cpu_fallback')!r}"
                ),
            }
        )
    if _search_gate(document) != "PASS":
        refusals.append(
            {
                "code": RESTART_SEARCH_UNPROVEN,
                "item": "search",
                "detail": f"the bounded anchor search ended on {dict(document.get('search') or {})}",
            }
        )
    if _lock_gate(document) != "PASS":
        refusals.append(
            {
                "code": RESTART_LOCK_UNPROVEN,
                "item": "lock",
                "detail": (
                    f"the lock carried "
                    f"{(document.get('lock') or {}).get('consecutive_frames')!r} consecutive frames"
                ),
            }
        )
    timing = document.get("timing") or {}
    if (
        timing.get("cadence_continuous") is not True
        or abs(float(timing.get("frame_rate_hz", 0.0)) - DECLARED_FRAME_RATE_HZ) > 1e-9
    ):
        refusals.append(
            {
                "code": RESTART_CADENCE_BROKEN,
                "item": "timing",
                "detail": (
                    f"the accepted frames are not a continuous {DECLARED_FRAME_RATE_HZ} Hz sequence: "
                    f"duplicate={(timing.get('duplicate_count'))!r} "
                    f"backward={(timing.get('backward_count'))!r} "
                    f"too_fast={(timing.get('too_fast_count'))!r} "
                    f"undeclared_gap={(timing.get('undeclared_gap_count'))!r}"
                ),
            }
        )
    if timing.get("within_thresholds") is not True:
        refusals.append(
            {
                "code": RESTART_TIMING_THRESHOLDS,
                "item": "timing",
                "detail": (
                    f"the frozen per-frame thresholds were exceeded: "
                    f"{timing.get('exceeded_thresholds')!r}"
                ),
            }
        )
    if _stop_gate(document) != "PASS":
        refusals.append(
            {
                "code": RESTART_STOP_UNPROVEN,
                "item": "stop",
                "detail": f"the held stop proof is unproven: {dict(document.get('stop') or {})}",
            }
        )
    teardown = document.get("teardown") or {}
    unproven = [
        field
        for field in (
            "previous_stack_stopped",
            "controller_owner_stopped",
            "children_exited",
            "graph_clear",
        )
        if teardown.get(field) is not True
    ]
    if unproven:
        refusals.append(
            {
                "code": RESTART_TEARDOWN_UNPROVEN,
                "item": "teardown",
                "detail": f"the teardown did not prove {', '.join(unproven)}",
            }
        )
    if teardown.get("gpu_released") is not True:
        refusals.append(
            {
                "code": RESTART_GPU_NOT_RELEASED,
                "item": "teardown",
                "detail": "a compute process still held the GPU after the stack was stopped",
            }
        )
    return refusals


def timing_document(
    frames: Sequence[Mapping],
    values: Mapping,
    *,
    frame_period_s: float = FRAME_PERIOD,
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
) -> dict:
    """The production 10 Hz cadence over the accepted frames, plus the frozen per-frame thresholds."""

    cadence = check_frame_cadence(frames, frame_period_s=frame_period_s, max_settle_s=max_settle_s)
    thresholds = frame_thresholds(frames, values, frame_period_s=frame_period_s)
    return {
        **cadence,
        **thresholds,
        "frame_rate_hz": DECLARED_FRAME_RATE_HZ,
        "cadence_continuous": cadence["continuous"],
        "within_thresholds": thresholds["within_thresholds"],
        "values_sha256": canonical_sha256(dict(values)) if values else None,
    }


def validate_restart_receipt(document: Mapping) -> list[str]:
    """Every field the aggregate's restart gate re-derives, checked in one place.

    The aggregate does not read this function; it re-derives the same facts from the document. This is the
    producer-side check, so a receipt is never written that the gate would silently drop.
    """

    problems: list[str] = []
    if not isinstance(document, Mapping):
        return ["not a document"]
    if document.get("kind") != KIND:
        problems.append(f"kind: {document.get('kind')!r} is not {KIND!r}")
    if document.get("lifecycle") != LIFECYCLE:
        problems.append(f"lifecycle: {document.get('lifecycle')!r} is not {LIFECYCLE!r}")
    if document.get("operation") != OPERATION:
        problems.append(f"operation: {document.get('operation')!r} is not {OPERATION!r}")
    anchor = document.get("anchor")
    if anchor not in PHASE_BY_ANCHOR:
        problems.append(f"anchor: {anchor!r} is not one of {ANCHORS}")
    elif document.get("phase") != PHASE_BY_ANCHOR[anchor]:
        problems.append(f"phase: {document.get('phase')!r} is not {PHASE_BY_ANCHOR[anchor]!r}")
    runtime = document.get("runtime")
    if not isinstance(runtime, Mapping):
        problems.append("runtime: missing")
    else:
        for key in (
            "source_commit",
            "production_config_sha256",
            "values_sha256",
            "weight_sha256_declared",
            "weight_sha256_observed",
        ):
            if not runtime.get(key):
                problems.append(f"runtime.{key}: missing")
    ownership = document.get("ownership_receipt")
    if not isinstance(ownership, Mapping) or not ownership.get("path"):
        problems.append("ownership_receipt: missing")
    producer = document.get("producer")
    if not isinstance(producer, Mapping) or not producer.get("entry"):
        problems.append("producer: missing")
    if (
        producer is not None
        and isinstance(producer, Mapping)
        and producer.get("stack_owned") is not True
    ):
        problems.append("producer.stack_owned: the phase did not declare it owned the stack")
    teardown = document.get("teardown")
    if not isinstance(teardown, Mapping):
        problems.append("teardown: missing")
    else:
        for field in (
            "previous_stack_stopped",
            "controller_owner_stopped",
            "children_exited",
            "graph_clear",
            "gpu_released",
        ):
            if teardown.get(field) is not True:
                problems.append(f"teardown.{field}: not proven")
    reconstruction = document.get("reconstruction")
    if not isinstance(reconstruction, Mapping):
        problems.append("reconstruction: missing")
    else:
        for field in ("stack_started", "one_mujoco_instance", "one_controller_owner"):
            if reconstruction.get(field) is not True:
                problems.append(f"reconstruction.{field}: not proven")
    detector = document.get("detector")
    if not isinstance(detector, Mapping):
        problems.append("detector: missing")
    else:
        if int(detector.get("count", 0)) != 1:
            problems.append(f"detector.count: {detector.get('count')!r} is not one")
        if str(detector.get("device")) != "cuda" or not str(
            detector.get("runtime_device", "")
        ).startswith("cuda"):
            problems.append(
                f"detector.device: {detector.get('device')!r}/{detector.get('runtime_device')!r}"
            )
        if detector.get("allow_cpu_fallback") is not False:
            problems.append("detector.allow_cpu_fallback: not false")
        if not detector.get("weights_sha256"):
            problems.append("detector.weights_sha256: missing")
    search = document.get("search")
    if not isinstance(search, Mapping):
        problems.append("search: missing")
    else:
        if search.get("terminal_status") != "TARGET_LOCKED":
            problems.append(f"search.terminal_status: {search.get('terminal_status')!r}")
        if search.get("coverage_complete") is not True:
            problems.append("search.coverage_complete: not proven")
        if int(search.get("wrong_locks", 0)) != 0:
            problems.append(f"search.wrong_locks: {search.get('wrong_locks')!r}")
    lock = document.get("lock")
    if not isinstance(lock, Mapping):
        problems.append("lock: missing")
    elif type(lock.get("consecutive_frames")) is not int or lock["consecutive_frames"] < 3:
        problems.append(
            f"lock.consecutive_frames: {lock.get('consecutive_frames')!r} is below three"
        )
    timing = document.get("timing")
    if not isinstance(timing, Mapping):
        problems.append("timing: missing")
    else:
        if timing.get("cadence_continuous") is not True:
            problems.append("timing.cadence_continuous: not proven")
        if timing.get("within_thresholds") is not True:
            problems.append("timing.within_thresholds: not proven")
        if (
            not _finite(timing.get("frame_rate_hz"))
            or abs(float(timing["frame_rate_hz"]) - DECLARED_FRAME_RATE_HZ) > 1e-9
        ):
            problems.append(f"timing.frame_rate_hz: {timing.get('frame_rate_hz')!r}")
    proof = document.get("stop")
    if not isinstance(proof, Mapping):
        problems.append("stop: missing")
    elif proof.get("proven") is not True or int(proof.get("qualifying_samples", 0)) < 3:
        problems.append(f"stop: unproven ({dict(proof)})")
    gates = document.get("gates")
    if not isinstance(gates, Mapping):
        problems.append("gates: missing")
    else:
        for name in ("graph", "detector", "search", "lock", "timing", "stop"):
            if gates.get(name) != "PASS":
                problems.append(f"gates.{name}: {gates.get(name)!r}")
    if document.get("refusals"):
        problems.append(f"refusals: {document['refusals']}")
    body = {key: value for key, value in document.items() if key != "sha256"}
    if document.get("sha256") != canonical_sha256(body):
        problems.append("sha256: not the canonical digest of this document's own body")
    return problems


def stack_environment(session_id: str, base: Mapping | None = None) -> dict:
    """The environment the production stack starts under: the base plus this phase's session identity."""

    environment = dict(os.environ if base is None else base)
    environment["SO101_SIMULATION_SESSION_ID"] = str(session_id)
    return environment
