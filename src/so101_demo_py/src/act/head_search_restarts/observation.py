"""Ownership receipt, runtime of record, anchor declarations and the stack observations and proofs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import re

from so101_demo.act.head_search_ownership import (
    OPERATION as OWNERSHIP_OPERATION,
)
from so101_demo.act.head_search_ownership import (
    read_runtime_identity,
)
from so101_demo.act.head_search_restarts.contracts import (
    ANCHORS,
    CAMERA_IMAGE_TOPIC,
    CLOCK_TOPIC,
    DECLARED_FRAME_RATE_HZ,
    EXPECTED_NODES,
    FRAME_PERIOD,
    MINIMUM_RATE_FRAMES,
    OWNER_PROCESS_PATTERNS,
    PHASE_BY_ANCHOR,
    RATE_TOLERANCE_HZ,
    RESTART_ANCHOR_UNDECLARED,
    RESTART_OWNERSHIP_MISMATCH,
    RESTART_OWNERSHIP_REFUSED,
    RESTART_RUNTIME_UNVERIFIED,
    RESTART_SCENE_CONTRADICTORY,
    TRANSIENT_NODE_PREFIXES,
    _digest,
    _finite,
    _read_json,
    _refuse,
)


def read_ownership_receipt(path, *, run_root) -> dict:
    """Take the exclusive-ownership receipt and refuse unless it guards exactly this run root.

    The receipt is not re-derived here: it is the Step 1 producer's observation, taken at its own instant.
    What this phase checks is that it is the right document (operation and status), that it refused
    nothing, and that the root it guards is the root this run is about to claim.
    """

    receipt = Path(path)
    if not receipt.is_file():
        raise _refuse(
            RESTART_OWNERSHIP_MISMATCH,
            f"no exclusive-ownership receipt at {receipt}; Step 1 must pass before any stack starts",
        )
    document = _read_json(receipt)
    if document.get("operation") != OWNERSHIP_OPERATION:
        raise _refuse(
            RESTART_OWNERSHIP_MISMATCH,
            f"{receipt} carries operation {document.get('operation')!r}, not {OWNERSHIP_OPERATION!r}",
        )
    if document.get("status") != "EXCLUSIVE_OWNERSHIP_OK" or document.get("refusals"):
        codes = ",".join(str(item.get("code")) for item in document.get("refusals") or ())
        raise _refuse(
            RESTART_OWNERSHIP_REFUSED,
            f"the exclusive-ownership gate refused with {codes or 'no code'}: a phase that does not "
            f"exclusively own the machine may not start a stack",
        )
    planned = document.get("planned_run_root")
    if str(planned or "") != str(run_root):
        raise _refuse(
            RESTART_OWNERSHIP_MISMATCH,
            f"the ownership receipt guards {planned!r}, not this run root {str(run_root)!r}",
        )
    return {
        "path": str(receipt),
        "sha256": _digest(receipt),
        "operation": document.get("operation"),
        "status": document.get("status"),
        "checked_at_utc": document.get("checked_at_utc"),
        "planned_run_root": planned,
        "expected_runtime": document.get("expected_runtime"),
    }


def require_runtime_of_record(runtime: Mapping) -> dict:
    """The frozen runtime's own identity, refused unless it is the CUDA-only runtime of record."""

    if not isinstance(runtime, Mapping) or not runtime:
        raise _refuse(RESTART_RUNTIME_UNVERIFIED, "no frozen runtime identity was presented")
    if runtime.get("allow_cpu_fallback") is not False:
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            f"the runtime declares allow_cpu_fallback={runtime.get('allow_cpu_fallback')!r}; this producer "
            f"never falls back to the CPU",
        )
    if str(runtime.get("cuda_device")) != "cuda:0":
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            f"the runtime declares cuda_device={runtime.get('cuda_device')!r}, not cuda:0",
        )
    if runtime.get("setup_bash_present") is not True:
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            "the frozen root has no install/setup.bash, so the overlay is not the runtime of record",
        )
    if int(runtime.get("values_count", 0)) != 17:
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            f"the runtime carries {runtime.get('values_count')!r} values, not the approved 17",
        )
    declared = runtime.get("weight_sha256_declared")
    if not declared or runtime.get("weight_sha256_observed") != declared:
        raise _refuse(
            RESTART_RUNTIME_UNVERIFIED,
            f"the declared weights {declared!r} are not the observed weights "
            f"{runtime.get('weight_sha256_observed')!r}",
        )
    if not runtime.get("source_commit"):
        raise _refuse(RESTART_RUNTIME_UNVERIFIED, "the runtime carries no source commit")
    return dict(runtime)


def anchor_declarations(seal: Mapping, anchors: Sequence[str] | None = None) -> list[dict]:
    """Every declared anchor's own search start and cup point, read from the sealed geometry.

    ``in_frame_matrix`` fixes ``neck_start_rad`` (the anchor's declared search start) and
    ``centre_angle_rad`` (the neck angle that centres that anchor's cup). ``workspace_matrix.key_samples``
    fixes the world point the anchor was measured at. A missing piece is a contradictory seal, not a
    default: guessing either would make the anchor something other than what was sealed.
    """

    if not isinstance(seal, Mapping):
        raise _refuse(RESTART_SCENE_CONTRADICTORY, "the geometry seal is not a document")
    matrix = seal.get("in_frame_matrix")
    if not isinstance(matrix, Mapping) or not matrix:
        raise _refuse(
            RESTART_SCENE_CONTRADICTORY, "the geometry seal declares no in_frame_matrix anchors"
        )
    samples = (seal.get("workspace_matrix") or {}).get("key_samples")
    points = {
        str(sample.get("anchor")): [float(value) for value in sample.get("point_m") or ()]
        for sample in (samples or ())
        if isinstance(sample, Mapping) and sample.get("kind") == "anchor"
    }
    names = list(ANCHORS) if anchors is None else [str(name) for name in anchors]
    declared: list[dict] = []
    for name in names:
        entry = matrix.get(name)
        if not isinstance(entry, Mapping):
            raise _refuse(
                RESTART_ANCHOR_UNDECLARED,
                f"the sealed geometry declares no anchor {name!r}; the plan fixes exactly "
                f"{', '.join(ANCHORS)}",
            )
        start = entry.get("neck_start_rad")
        centre = entry.get("centre_angle_rad")
        point = points.get(name)
        if not _finite(start) or not _finite(centre):
            raise _refuse(
                RESTART_SCENE_CONTRADICTORY,
                f"the sealed anchor {name!r} declares neck_start_rad={start!r} / "
                f"centre_angle_rad={centre!r}",
            )
        if not point or len(point) != 3 or not all(_finite(value) for value in point):
            raise _refuse(
                RESTART_SCENE_CONTRADICTORY,
                f"the sealed workspace declares no world point for the anchor {name!r}, so this restart "
                f"would not know where the anchor's cup is",
            )
        declared.append(
            {
                "anchor": name,
                "phase": PHASE_BY_ANCHOR[name],
                "neck_start_rad": float(start),
                "centre_angle_rad": float(centre),
                "cup_point_m": point,
            }
        )
    return declared


def classify_nodes(nodes: Sequence[str], *, expected: Sequence[str] = EXPECTED_NODES) -> dict:
    """Which declared owner nodes are present, and which observed nodes are not ours."""

    observed = [str(node) for node in nodes]
    matched: dict[str, str] = {}
    missing: list[str] = []
    claimed: set[str] = set()
    for name in expected:
        found = next((node for node in observed if node.strip("/").split("/")[-1] == name), None)
        if found is None:
            missing.append(name)
        else:
            matched[name] = found
            claimed.add(found)
    transient = sorted(
        node
        for node in observed
        if node not in claimed
        and any(
            node.strip("/").split("/")[-1].startswith(prefix) for prefix in TRANSIENT_NODE_PREFIXES
        )
    )
    foreign = sorted(node for node in observed if node not in claimed and node not in transient)
    return {
        "nodes": observed,
        "matched": matched,
        "missing": missing,
        "transient": transient,
        "foreign": foreign,
    }


def owner_process_counts(processes: Sequence[Mapping]) -> dict:
    """How many owners of each kind the process table carries; one MuJoCo is the whole point."""

    counts = {name: 0 for name in OWNER_PROCESS_PATTERNS}
    counts["children"] = len(processes)
    for process in processes:
        argv = str(process.get("argv") or "")
        for name, pattern in OWNER_PROCESS_PATTERNS.items():
            if re.search(pattern, argv):
                counts[name] += 1
    return counts


def stack_observation(
    *,
    processes: Sequence[Mapping] = (),
    nodes: Sequence[str] = (),
    gpu_compute_apps: Sequence[Mapping] = (),
    sim_clock_s: Sequence[float] = (),
    runner_node: str | None = None,
) -> dict:
    """One read-only view of the stack: its processes, its graph, its GPU hold and its clock."""

    observed_nodes = [str(node) for node in nodes]
    graph = classify_nodes(observed_nodes)
    if runner_node:
        graph["runner_node"] = runner_node
        graph["foreign"] = [node for node in graph["foreign"] if node != runner_node]
    return {
        "processes": [dict(process) for process in processes],
        "nodes": observed_nodes,
        "gpu_compute_apps": [dict(app) for app in gpu_compute_apps],
        "sim_clock_s": [float(value) for value in sim_clock_s],
        "matched": graph["matched"],
        "missing": graph["missing"],
        "foreign": graph["foreign"],
        "runner_node": runner_node,
        "owner_processes": owner_process_counts(processes),
    }


def camera_rate(
    frames: Sequence[Mapping],
    *,
    declared_hz: float = DECLARED_FRAME_RATE_HZ,
    tolerance_hz: float = RATE_TOLERANCE_HZ,
) -> dict:
    """The measured rate of one real topic stream, against the rate the production config declares.

    The rate is the one the frames actually carried - ``(n - 1) / span`` over the stamps the producer
    published - so a stack that publishes at any other rate is refused by name rather than averaged into
    the declared one. Duplicate and backward stamps are counted separately, because a "rate" computed
    across a stall and a repeat is not a rate.
    """

    if not _finite(declared_hz) or float(declared_hz) <= 0.0:
        raise ValueError("the declared frame rate must be positive and finite")
    stamps = [float(frame["frame_sim_s"]) for frame in frames]
    duplicate = backward = 0
    for previous, current in zip(stamps, stamps[1:]):
        if current < previous:
            backward += 1
        elif current == previous:
            duplicate += 1
    span = None if len(stamps) < 2 else stamps[-1] - stamps[0]
    measured = None if not span or span <= 0.0 else (len(stamps) - 1) / span
    interval = None if measured is None else 1.0 / measured
    error = None if measured is None else abs(measured - float(declared_hz))
    return {
        "topic": CAMERA_IMAGE_TOPIC,
        "frame_rate_hz": DECLARED_FRAME_RATE_HZ,
        "declared_rate_hz": float(declared_hz),
        "tolerance_hz": float(tolerance_hz),
        "frames": len(stamps),
        "span_s": span,
        "measured_rate_hz": measured,
        "measured_interval_s": interval,
        "rate_error_hz": error,
        "duplicate_count": duplicate,
        "backward_count": backward,
        "matches_declared": bool(
            measured is not None
            and len(stamps) >= MINIMUM_RATE_FRAMES
            and error is not None
            and error <= float(tolerance_hz)
            and not duplicate
            and not backward
        ),
    }


def sim_clock_progress(readings: Sequence[float]) -> dict:
    """Whether the simulator's own time base moved while the phase watched it."""

    values = [float(value) for value in readings]
    delta = None if len(values) < 2 else values[-1] - values[0]
    return {
        "topic": CLOCK_TOPIC,
        "samples": len(values),
        "first_s": values[0] if values else None,
        "last_s": values[-1] if values else None,
        "delta_s": delta,
        "advancing": bool(delta is not None and delta > 0.0),
    }


def frame_thresholds(
    frames: Sequence[Mapping], values: Mapping, *, frame_period_s: float = FRAME_PERIOD
) -> dict:
    """The frozen per-frame thresholds, read off the frames the decision loop accepted."""

    def maximum(key: str) -> float | None:
        seen = [float(frame[key]) for frame in frames if _finite(frame.get(key))]
        return max(seen) if seen else None

    max_age = maximum("frame_age_s")
    max_skew = maximum("source_skew_s")
    max_inference = maximum("inference_s")
    thresholds = {
        "max_age_s": values.get("max_age_s"),
        "max_skew_s": values.get("max_skew_s"),
        "max_inference_s": float(frame_period_s),
    }
    exceeded = []
    if (
        max_age is not None
        and _finite(thresholds["max_age_s"])
        and max_age > float(thresholds["max_age_s"])
    ):
        exceeded.append("max_age_s")
    if (
        max_skew is not None
        and _finite(thresholds["max_skew_s"])
        and max_skew > float(thresholds["max_skew_s"])
    ):
        exceeded.append("max_skew_s")
    if max_inference is not None and max_inference > float(frame_period_s):
        exceeded.append("max_inference_s")
    return {
        "max_frame_age_s": max_age,
        "max_source_skew_s": max_skew,
        "max_inference_s": max_inference,
        "thresholds": thresholds,
        "exceeded_thresholds": exceeded,
        "within_thresholds": not exceeded and bool(frames),
        "definition": (
            "the frame's own age at the decision (the controller's freshness gate), the source skew "
            "between its stamp and the paired feedback stamp (the controller's skew gate) and the "
            "detector's inference time (one declared frame period) are each read off the frames the "
            "closed loop really consumed; any of the three over its frozen threshold fails the gate"
        ),
    }


def teardown_proof(
    *,
    processes: Sequence[Mapping],
    nodes: Sequence[str],
    gpu_compute_apps: Sequence[Mapping],
    sim_clock_s: Sequence[float] = (),
    own_pid: int | None = None,
    runner_node: str | None = None,
) -> dict:
    """The four teardown facts plus the GPU hold, each re-derived from a fresh observation.

    Two observations belong to the phase itself and are excluded by name, not ignored: the runner's own
    rclpy node (it is destroyed before this probe, and the wait for it to leave the graph is part of the
    teardown) and the runner's own pid in the GPU compute list (the phase holds one CUDA context while it
    runs; it disappears with the process). Both exclusions are recorded with the raw rows beside them.
    """

    owners = owner_process_counts(processes)
    clock = sim_clock_progress(sim_clock_s)
    graph = classify_nodes(nodes)
    foreign_nodes = [node for node in graph["nodes"] if node != runner_node]
    foreign_gpu = [
        dict(app)
        for app in gpu_compute_apps
        if own_pid is None or str(app.get("pid")) != str(own_pid)
    ]
    return {
        "previous_stack_stopped": not processes,
        "controller_owner_stopped": owners["controller_owners"] == 0,
        "children_exited": not processes,
        "graph_clear": not foreign_nodes,
        "gpu_released": not foreign_gpu,
        "excluded_runner_node": runner_node,
        "excluded_own_pid": own_pid,
        "residual_nodes": foreign_nodes,
        "residual_gpu_compute_apps": foreign_gpu,
        "process_count": len(processes),
        "node_count": len(nodes),
        "gpu_compute_app_count": len(gpu_compute_apps),
        "owner_processes": owners,
        "nodes": graph["nodes"],
        "processes": [dict(process) for process in processes],
        "gpu_compute_apps": [dict(app) for app in gpu_compute_apps],
        "sim_clock_delta_s": clock["delta_s"],
        "definition": (
            "the stack is stopped and the process table, the ROS graph and the GPU compute processes are "
            "read AGAIN; previous_stack_stopped and children_exited mean no stack process is alive, "
            "controller_owner_stopped means no ros2_control_node or spawner is alive, graph_clear means "
            "the graph lists no node at all, and gpu_released means no compute process holds the device"
        ),
    }


def read_runtime_of_record(final_run, production_config=None) -> dict:
    """The frozen runtime's own identity, read off disk through the Step 1 reader."""

    return read_runtime_identity(
        Path(final_run),
        production_config=None if production_config is None else Path(production_config),
    )
