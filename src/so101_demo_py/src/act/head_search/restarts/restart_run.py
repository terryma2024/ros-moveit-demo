"""Stack teardown helpers, the restart receipt and one anchor restart."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path
import signal
import time

from so101_demo.act.head_search.restarts.contracts import (
    FIT_WARNING,
    GRAPH_TIMEOUT_S,
    KIND,
    LIFECYCLE,
    OPERATION,
    PHASE_BY_ANCHOR,
    RESTART_ANCHOR_UNDECLARED,
    RESTART_FOREIGN_OWNER_ACTIVE,
    RESTART_GPU_NOT_RELEASED,
    RESTART_STACK_START_FAILED,
    RESTART_TEARDOWN_UNPROVEN,
    SCHEMA_VERSION,
    _refuse,
    _utc_now,
)
from so101_demo.act.head_search.restarts.gates import (
    _owner_counts,
    restart_gates,
    restart_refusals,
    stack_environment,
    timing_document,
)
from so101_demo.act.head_search.restarts.observation import (
    classify_nodes,
    owner_process_counts,
    teardown_proof,
)
from so101_demo.act.head_search.restarts.process_probes import (
    RUNNER_NODE_NAMES,
    measure_stack_processes,
    probe_owners,
)
from so101_demo.act.head_search.restarts.search_flight import measure_and_search
from so101_demo.act.head_search.timing_measurement.contracts import (
    DEFAULT_MAX_SETTLE_S,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

from so101_demo.act.head_execution_stack import RestartStack


def receipt_document(
    *,
    anchor_run: Mapping,
    runtime: Mapping,
    approved_bundle_sha256: str,
    run_root,
    anchor_root,
    ownership: Mapping,
    producer: Mapping,
    values: Mapping | None = None,
    elapsed_s: float | None = None,
    started_at_utc: str | None = None,
    finished_at_utc: str | None = None,
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
) -> dict:
    """One anchor's ``FULL_RESTART`` receipt: evidence first, gates re-derived from it, digest last."""

    anchor = str(anchor_run.get("anchor"))
    if anchor not in PHASE_BY_ANCHOR:
        raise _refuse(
            RESTART_ANCHOR_UNDECLARED,
            f"the restart evidence names the anchor {anchor!r}, which the plan does not declare",
        )
    values = dict(values or {})
    frames = list(anchor_run.get("frames") or ())
    timing = anchor_run.get("timing") or timing_document(frames, values, max_settle_s=max_settle_s)
    document: dict = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "operation": OPERATION,
        "phase": PHASE_BY_ANCHOR[anchor],
        "lifecycle": LIFECYCLE,
        "anchor": anchor,
        "run_root": str(run_root),
        "anchor_root": str(anchor_root),
        "declared_anchor": dict(anchor_run.get("declared_anchor") or {}),
        "ownership_receipt": dict(ownership),
        "producer": {**dict(producer), "stack_owned": True},
        "runtime": {
            key: runtime.get(key)
            for key in (
                "final_run",
                "source_commit",
                "production_config",
                "production_config_sha256",
                "values_sha256",
                "weight_path",
                "weight_sha256_declared",
                "weight_sha256_observed",
                "allow_cpu_fallback",
                "cuda_device",
            )
        },
        "approved_bundle_sha256": approved_bundle_sha256,
        "stack": dict(anchor_run.get("stack") or {}),
        "controllers": dict(anchor_run.get("controllers") or {}),
        "camera": dict(anchor_run.get("camera") or {}),
        "clock": dict(anchor_run.get("clock") or {}),
        "detector": dict(anchor_run.get("detector") or {}),
        "search": dict(anchor_run.get("search") or {}),
        "lock": dict(anchor_run.get("lock") or {}),
        "timing": dict(timing),
        "stop": dict(anchor_run.get("stop") or {}),
        "teardown": dict(anchor_run.get("teardown") or {}),
        "frames": frames,
        "scene": dict(anchor_run.get("scene") or {}),
        "admission": dict(anchor_run.get("admission") or {}),
        "reconstruction": dict(anchor_run.get("reconstruction") or {}),
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "elapsed_s": None if elapsed_s is None else float(elapsed_s),
        "fit_warning": FIT_WARNING,
    }
    if not document["reconstruction"]:
        document["reconstruction"] = _reconstruction(document)
    document["gates"] = restart_gates(document)
    document["refusals"] = list(anchor_run.get("refusals") or ()) + restart_refusals(document)
    document["status"] = "PASS" if not document["refusals"] else "REFUSED"
    body = {key: value for key, value in document.items() if key != "sha256"}
    document["sha256"] = canonical_sha256(body)
    return document


def run_anchor_restart(
    *,
    anchor: str,
    anchor_root,
    declared: Mapping,
    runtime: Mapping,
    run_root,
    ownership: Mapping,
    approved_bundle_sha256: str,
    producer: Mapping,
    anchors: Sequence[Mapping],
    urdf_path,
    scene_path,
    plugin_config_path,
    controller_config_path,
    production_config_path,
    weights_path,
    frozen_candidate_path,
    values: Mapping,
    seal: Mapping,
    production: Mapping,
    device: str = "cuda",
    stdout=None,
    stderr=None,
    clock=time.monotonic,
    sleep=time.sleep,
    excluded_pids: Sequence[int] = (),
    stack_factory=None,
    detector_factory=None,
    probe=None,
) -> dict:
    """One anchor's full restart: prove emptiness, reconstruct the stack, gate it, search, tear down.

    The order is the plan's and it is not negotiable: nothing starts before the pre-start probe is empty;
    nothing is claimed before it is measured; and the post-teardown probe must be empty before this
    function returns, because the caller starts the next anchor's stack the moment it does.
    """

    raise _refuse('HEAD_LEGACY_EXECUTION_REMOVED',
                  'qualification restart execution requires the migrated composition')

    def log(message: str) -> None:
        line = f"[{_utc_now()}] restart-{anchor}: {message}\n"
        if stdout is not None:
            stdout.write(line)
            stdout.flush()

    def warn(message: str) -> None:
        line = f"[{_utc_now()}] restart-{anchor}: {message}\n"
        if stderr is not None:
            stderr.write(line)
            stderr.flush()

    root = Path(anchor_root)
    root.mkdir(parents=True, exist_ok=True)
    started = clock()
    started_at = _utc_now()
    observer = probe or (lambda **kwargs: probe_owners(**kwargs))
    log("pre-start ownership probe")
    before = observer(excluded_pids=excluded_pids, excluded_nodes=RUNNER_NODE_NAMES)
    _require_empty(before, anchor=anchor, stage="pre-start")
    if before.get("excluded_runner_nodes"):
        log(
            f"this phase's own rclpy node is still in discovery: "
            f"{before['excluded_runner_nodes']} (raw graph {before.get('raw_nodes')})"
        )
    log(f"pre-start probe clean: {before['owner_processes']}")

    environment = stack_environment(module_session_id(anchor))
    evidence: dict = {
        "anchor": anchor,
        "runner_node": f"/head_search_restart_{anchor}",
        "declared_anchor": dict(declared),
        "producer": dict(producer),
        "admission": {
            "session_id": module_session_id(anchor),
            "protocol": "HeadNeckTrajectoryController owner dead-man admission",
        },
    }
    stack = None
    try:
        factory = stack_factory or _stack_factory
        stack = factory(
            urdf_path=urdf_path,
            scene_path=scene_path,
            plugin_config_path=plugin_config_path,
            controller_config_path=controller_config_path,
            workspace=root / "stack",
            session_id=module_session_id(anchor),
            environment=environment,
            logger=lambda message: log(f"stack: {message}"),
        )
        log("starting the production composition")
        stack.start()
        evidence["stack"] = _await_graph(
            observer, anchor=anchor, clock=clock, sleep=sleep, excluded_pids=excluded_pids, log=log
        )
        if not evidence["stack"].get("nodes"):
            raise _refuse(
                RESTART_STACK_START_FAILED,
                f"the {anchor} stack published no node within {GRAPH_TIMEOUT_S} s",
            )
        evidence.update(
            measure_and_search(
                anchor=anchor,
                declared=declared,
                root=root,
                runtime=runtime,
                values=values,
                device=device,
                seal=seal,
                production=production,
                camera_config=production.get("camera") or {},
                scene_path=scene_path,
                production_config_path=production_config_path,
                weights_path=weights_path,
                frozen_candidate_path=frozen_candidate_path,
                session_id=module_session_id(anchor),
                clock=clock,
                sleep=sleep,
                log=log,
                warn=warn,
                detector_factory=detector_factory,
            )
        )
    finally:
        if stack is not None:
            log("stopping the stack")
            try:
                stack.stop()
            except Exception as error:  # noqa: BLE001 - a stop failure is verified, not asserted
                warn(f"the stack stop raised {error!r}")
            _kill_stragglers(excluded_pids=excluded_pids, log=log)

    log("post-teardown ownership probe")
    after = observer(excluded_pids=excluded_pids, excluded_nodes=RUNNER_NODE_NAMES)
    evidence["teardown"] = teardown_proof(
        processes=after.get("processes") or (),
        nodes=after.get("nodes") or (),
        gpu_compute_apps=after.get("gpu_compute_apps") or (),
        sim_clock_s=after.get("sim_clock_s") or (),
        own_pid=os.getpid(),
        runner_node=evidence.get("runner_node"),
    )
    evidence["teardown"]["before"] = {
        "processes": before.get("processes"),
        "nodes": before.get("nodes"),
        "gpu_compute_apps": before.get("gpu_compute_apps"),
    }
    if not all(
        evidence["teardown"].get(field) is True
        for field in (
            "previous_stack_stopped",
            "controller_owner_stopped",
            "children_exited",
            "graph_clear",
        )
    ):
        raise _refuse(
            RESTART_TEARDOWN_UNPROVEN,
            f"the {anchor} stack could not be proven gone: {evidence['teardown']}",
        )
    if evidence["teardown"].get("gpu_released") is not True:
        raise _refuse(
            RESTART_GPU_NOT_RELEASED,
            f"a compute process still held the GPU after the {anchor} stack stopped",
        )
    evidence["reconstruction"] = _reconstruction(evidence)
    evidence["elapsed_s"] = clock() - started
    evidence["started_at_utc"] = started_at
    evidence["finished_at_utc"] = _utc_now()
    log(f"restart complete in {evidence['elapsed_s']:.1f} s; stack proven gone")
    return evidence


def module_session_id(anchor: str) -> str:
    """One session id per anchor: the stack's simulation session and the detector's identity."""

    return f"head-search-restart-{anchor}"


def _stack_factory(**kwargs) -> RestartStack:
    return RestartStack(**kwargs)


def _require_empty(observation: Mapping, *, anchor: str, stage: str) -> None:
    owners = observation.get("owner_processes") or owner_process_counts(
        observation.get("processes") or ()
    )
    if observation.get("processes") or observation.get("nodes"):
        raise _refuse(
            RESTART_FOREIGN_OWNER_ACTIVE,
            f"the {stage} probe before the {anchor} restart found a live stack: "
            f"processes={observation.get('processes')!r} nodes={observation.get('nodes')!r}",
        )
    if observation.get("gpu_compute_apps"):
        raise _refuse(
            RESTART_FOREIGN_OWNER_ACTIVE,
            f"the {stage} probe before the {anchor} restart found GPU compute processes: "
            f"{observation.get('gpu_compute_apps')!r}",
        )
    if int(owners.get("mujoco_instances", 0)) or int(owners.get("controller_owners", 0)):
        raise _refuse(
            RESTART_FOREIGN_OWNER_ACTIVE,
            f"the {stage} probe before the {anchor} restart found a second owner: {owners}",
        )


def _await_graph(observer, *, anchor, clock, sleep, excluded_pids, log) -> dict:
    """Wait for the steady state, not for the first node to appear.

    A controller spawner is a transient node whose job is to activate one controller and exit; a graph read
    while a spawner is still up says nothing about the composition the search will run in. The wait
    therefore ends only once every declared owner node is present, no spawner process is alive and no
    transient node is listed.
    """

    deadline = clock() + GRAPH_TIMEOUT_S
    last: dict = {}
    while clock() < deadline:
        last = observer(excluded_pids=excluded_pids, excluded_nodes=RUNNER_NODE_NAMES)
        graph = classify_nodes(last.get("nodes") or ())
        spawners = int((last.get("owner_processes") or {}).get("spawners", 0))
        if not graph["missing"] and not graph["transient"] and spawners == 0:
            log(f"graph at steady state: {last.get('nodes')} ({graph})")
            return last
        sleep(0.25)
    log(f"graph never reached steady state within {GRAPH_TIMEOUT_S} s: {last.get('nodes')}")
    return last


def _kill_stragglers(*, excluded_pids, log) -> None:
    """A stop that left a stack process behind is escalated once, then reported honestly."""

    stragglers = measure_stack_processes(excluded_pids=excluded_pids)
    for process in stragglers:
        log(f"escalating on straggler p{process['pid']}: {process['argv']}")
        try:
            os.killpg(os.getpgid(int(process["pid"])), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(int(process["pid"]), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                continue
    if stragglers:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and measure_stack_processes(excluded_pids=excluded_pids):
            time.sleep(0.25)


def _reconstruction(evidence: Mapping) -> dict:
    """What was reconstructed, re-read from the graph, the process table and the controller manager."""

    stack = evidence.get("stack") or {}
    controllers = evidence.get("controllers") or {}
    owners = _owner_counts(stack)
    return {
        "stack_started": bool(stack.get("nodes")),
        "one_mujoco_instance": int(owners.get("mujoco_instances", 0)) == 1,
        "one_controller_owner": int(owners.get("controller_owners", 0)) == 1,
        "nodes": list(stack.get("nodes") or ()),
        "controllers": dict(controllers.get("states") or {}),
        "all_controllers_active": controllers.get("all_active") is True,
        "owner_processes": owners,
    }
