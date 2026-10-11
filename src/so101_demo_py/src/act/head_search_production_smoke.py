"""The production smoke - the flight, its sealed journal, and the aggregator that reads it.

The plan's Step 3 is one sentence of requirements and one sentence of refusals:

    *"Read back production smoke and 40-scene evidence. The smoke must prove producer -> sealed journal ->
    actual aggregator, correct ``TARGET_LOCKED``, 10 Hz continuity, bounded commands, three-sample stop
    proof and exact runtime identity. A mock/fixture-only result does not pass."*

The installed ``so101_head_search_smoke`` proved something else: planning coverage of the bounded stop plan
against the geometry seal, with no stack, no detector, no journal and its ``--scenario`` flag accepted but
never read (HS-179, HS-315 row 5). That proof is still produced - the plan's coverage gate cites it - but it
is **not** what this phase's success stands on. This module is the smoke the plan asks for:

* **The producer owns the stack.** It takes the exclusive-ownership receipt, refuses unless
  that receipt guards exactly this run root, and then starts the one production composition through
  ``head_search_restarts.run_anchor_restart`` - the same start/stop discipline, the same graph probe, the
  same teardown proof, one anchor of the seal's ``in_frame_matrix``, and the cup placed at the seal's own
  point through the simulator's ``set_free_joint_state`` service. Nothing here re-implements the transport.
* **The flight is the production path.** ``RosSearchAdapter`` + the production ``HeadSearchController``
  over the real ``/head_camera/color``, ``/head_camera/camera_info``, ``/joint_states`` and TF, with the
  neck commanded through the admission-wrapped neck controller. The in-process MuJoCo harness the forty
  scenarios use is a different, ROS-free path; this phase does not use it.
* **The producer writes a sealed journal; the aggregator reads it back.** The raw record - frames, the
  commanded targets, the held stop samples, the graph, the teardown - is written to
  ``sealed-journal.json`` with its own body digest, and :func:`aggregate_production_smoke` then reads that
  **file** and re-derives every gate from it. The document the qualification aggregate's gate consumes,
  ``production-smoke-journal.json``, is the aggregator's output, not the flight's narration.
* **The terminal is classified by the scenario module's own rule.** ``classify_terminal`` builds the entry
  the forty-scenario producer builds and hands it to ``head_search_scenarios.classify_scenario``; the
  smoke's declared class is ``nominal``, so a lock is the only passing terminal and a lock on any other
  class is the wrong-lock failure the plan names. The cadence check and the stop proof are that module's
  too (``check_frame_cadence`` / ``stop_proof``), never a second implementation.

The refusal vocabulary is ``SMOKE_*``. A stack that will not start, a cup that is not locked, a cadence
outside the declared contract, an unbounded command, an unproven stop, a teardown that cannot be proven or
a GPU that was not released each refuse **by name**, and a refused run leaves its sealed journal and its
journal on disk so the reason is readable rather than inferred. A flight that itself refused
(``RESTART_*``) is mapped onto the smoke's own code and the original code is kept verbatim in the detail.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_qualification import _require_new_root
from so101_demo.act.head_search_restarts import (
    RESTART_OWNERSHIP_MISMATCH,
    RESTART_OWNERSHIP_REFUSED,
    RESTART_RUNTIME_UNVERIFIED,
    anchor_declarations,
    read_ownership_receipt,
    require_runtime_of_record,
)
from so101_demo.act.head_search_scenarios.plan import check_frame_cadence, expected_terminals
from so101_demo.act.head_search_scenarios.scenario_run import classify_scenario
from so101_demo.act.head_search_scenarios.stop_proof import stop_proof
from so101_demo.act.head_search_timing_measurement.contracts import (
    DEFAULT_MAX_SETTLE_S,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1

#: the aggregate's own declaration of this artefact (``head_search_aggregate.SMOKE_KIND`` / ``PHASE``);
#: the two must not drift, and :func:`validate_smoke_journal` is what makes that a run-time invariant
KIND = "head_search_production_smoke_journal"
SEALED_KIND = "head_search_production_smoke_sealed_journal"
RECEIPT_KIND = "head_search_production_smoke_receipt"
OPERATION = "QUALIFICATION_RUN"
PHASE = "production_smoke"

JOURNAL_ARTIFACT = "production-smoke-journal.json"
SEALED_ARTIFACT = "sealed-journal.json"
RECEIPT_ARTIFACT = "measurement-receipt.json"
COVERAGE_PROOF_ARTIFACT = "coverage-proof.json"
PLAN_ARTIFACT = "head-search-plan-{anchor}.json"
STDOUT_LOG = "stdout.log"
STDERR_LOG = "stderr.log"

#: the plan's own smoke anchors are the three the seal declares; one phase runs exactly one of them
ANCHORS = ("default", "left", "forward")
#: the plan's Step 3 sentence: "Legal single cup ends TARGET_LOCKED" - one legal cup is the nominal class
CONDITION_CLASS = "nominal"
#: a lock is three consecutive centred frames, so a sequence that produced a lock cannot be shorter
MINIMUM_CADENCE_FRAMES = 3

PRODUCER_ENTRY = "so101_head_search_smoke"
AGGREGATOR_ENTRY = "so101_demo.act.head_search_production_smoke.aggregate_production_smoke"

SMOKE_INPUTS_INCOMPLETE = "SMOKE_INPUTS_INCOMPLETE"
SMOKE_RUN_ROOT_EXISTS = "SMOKE_RUN_ROOT_EXISTS"
SMOKE_OWNERSHIP_REFUSED = "SMOKE_OWNERSHIP_REFUSED"
SMOKE_OWNERSHIP_MISMATCH = "SMOKE_OWNERSHIP_MISMATCH"
SMOKE_RUNTIME_UNVERIFIED = "SMOKE_RUNTIME_UNVERIFIED"
SMOKE_CLASS_UNDECLARED = "SMOKE_CLASS_UNDECLARED"
SMOKE_ANCHOR_UNDECLARED = "SMOKE_ANCHOR_UNDECLARED"
SMOKE_STACK_START_FAILED = "SMOKE_STACK_START_FAILED"
SMOKE_CUP_NOT_PLACED = "SMOKE_CUP_NOT_PLACED"
SMOKE_DETECTOR_FAILED = "SMOKE_DETECTOR_FAILED"
SMOKE_LOCK_UNPROVEN = "SMOKE_LOCK_UNPROVEN"
SMOKE_CADENCE_BROKEN = "SMOKE_CADENCE_BROKEN"
SMOKE_COMMANDS_UNBOUNDED = "SMOKE_COMMANDS_UNBOUNDED"
SMOKE_STOP_UNPROVEN = "SMOKE_STOP_UNPROVEN"
SMOKE_TEARDOWN_UNPROVEN = "SMOKE_TEARDOWN_UNPROVEN"
SMOKE_GPU_NOT_RELEASED = "SMOKE_GPU_NOT_RELEASED"
SMOKE_PROBE_FAILED = "SMOKE_PROBE_FAILED"
SMOKE_COVERAGE_UNPROVEN = "SMOKE_COVERAGE_UNPROVEN"
SMOKE_JOURNAL_UNREADABLE = "SMOKE_JOURNAL_UNREADABLE"
SMOKE_SEAL_MISMATCH = "SMOKE_SEAL_MISMATCH"
SMOKE_JOURNAL_INVALID = "SMOKE_JOURNAL_INVALID"

#: a flight that refused keeps its own code in the detail; this is the smoke's name for the same refusal
RESTART_CODE_MAP = {
    "RESTART_STACK_START_FAILED": SMOKE_STACK_START_FAILED,
    "RESTART_PROBE_FAILED": SMOKE_PROBE_FAILED,
    "RESTART_ADAPTER_SILENT": SMOKE_PROBE_FAILED,
    "RESTART_NODE_MISSING": SMOKE_STACK_START_FAILED,
    "RESTART_FOREIGN_OWNER_ACTIVE": SMOKE_OWNERSHIP_REFUSED,
    "RESTART_SCENE_CONTRADICTORY": SMOKE_CUP_NOT_PLACED,
    "RESTART_DEVICE_UNAVAILABLE": SMOKE_DETECTOR_FAILED,
    "RESTART_DETECTOR_FAILED": SMOKE_DETECTOR_FAILED,
    "RESTART_SEARCH_UNPROVEN": SMOKE_LOCK_UNPROVEN,
    "RESTART_LOCK_UNPROVEN": SMOKE_LOCK_UNPROVEN,
    "RESTART_CADENCE_BROKEN": SMOKE_CADENCE_BROKEN,
    "RESTART_TIMING_THRESHOLDS": SMOKE_CADENCE_BROKEN,
    "RESTART_FRAME_RATE_MISMATCH": SMOKE_CADENCE_BROKEN,
    "RESTART_SIM_CLOCK_STALLED": SMOKE_CADENCE_BROKEN,
    "RESTART_STOP_UNPROVEN": SMOKE_STOP_UNPROVEN,
    "RESTART_TEARDOWN_UNPROVEN": SMOKE_TEARDOWN_UNPROVEN,
    "RESTART_GPU_NOT_RELEASED": SMOKE_GPU_NOT_RELEASED,
    "RESTART_OWNERSHIP_REFUSED": SMOKE_OWNERSHIP_REFUSED,
    "RESTART_OWNERSHIP_MISMATCH": SMOKE_OWNERSHIP_MISMATCH,
    "RESTART_RUNTIME_UNVERIFIED": SMOKE_RUNTIME_UNVERIFIED,
    "RESTART_ANCHOR_UNDECLARED": SMOKE_ANCHOR_UNDECLARED,
}

FIT_WARNING = (
    "the smoke is one bounded flight of one anchor through the production path: it is evidence that the "
    "production composition locks the cup it was pointed at, not a measurement of the search's accuracy "
    "over the ten condition classes - that is the forty-scenario phase's job"
)

CONDITION_CLASS_DEFINITION = (
    "the plan's Step 3 rule is the forty-scenario producer's own rule: a legal single cup ends "
    "TARGET_LOCKED, two cups end TARGET_AMBIGUOUS, no cup ends TARGET_NOT_FOUND only with complete "
    "coverage. The smoke declares exactly one legal cup, so `nominal` is its condition class and a lock "
    "is the only passing terminal"
)


class SmokeRefused(CalibrationInputsRefused):
    """A smoke refusal, carrying the exact ``SMOKE_*`` code the journal records and the CLI returns."""


def _refuse(code: str, detail: str) -> SmokeRefused:
    return SmokeRefused(code, detail)


def _finite(value) -> bool:
    return (
        type(value) in (int, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _utc_now(now=time.gmtime) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", now())


def _read_json(path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError(f"{path} is not a JSON object")
    return document


def _write(root: Path, name: str, document: Mapping) -> Path:
    """One document, written atomically: a half-written journal is never a journal."""

    target = root / name
    pending = root / f".{name}.pending"
    pending.write_text(
        json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(pending, target)
    return target


# --- the three re-derived readings (the scenario module's own rules) ----------------------------------


def smoke_cadence(
    frames, *, frame_period_s: float = FRAME_PERIOD_S, max_settle_s: float = DEFAULT_MAX_SETTLE_S
) -> dict:
    """The 10 Hz contract over the frames the controller really consumed, or the numbers that say why not.

    ``head_search_scenarios.check_frame_cadence`` is the rule and this is a thin naming of it plus one
    declaration of its own: a sequence of fewer than :data:`MINIMUM_CADENCE_FRAMES` frames is **not** a
    continuous cadence. An empty list has no intervals at all, and "no interval violated the contract" is
    not the same statement as "the loop produced the frames the contract describes".
    """

    cadence = check_frame_cadence(frames, frame_period_s=frame_period_s, max_settle_s=max_settle_s)
    enough = cadence["frame_count"] >= MINIMUM_CADENCE_FRAMES
    cadence["declared_rate_hz"] = FRAME_RATE_HZ
    cadence["measured_rate_hz"] = cadence["achieved_rate_hz"]
    cadence["minimum_frames"] = MINIMUM_CADENCE_FRAMES
    cadence["frames_short"] = not enough
    cadence["continuous"] = bool(cadence["continuous"]) and enough
    cadence["definition"] = (
        cadence["definition"]
        + f"; a locked smoke consumed at least {MINIMUM_CADENCE_FRAMES} frames (the lock itself is three "
        "consecutive centred frames), so a shorter sequence is not a continuous cadence"
    )
    return cadence


def smoke_commands(commands) -> dict:
    """Every neck target the controller commanded, against the interval the seal declares.

    ``commands`` is the production adapter's own record: the declared corridor, the declared required
    search domain, and the distinct targets with the ticks that repeated them. A target is inside the
    corridor when it is within the seal's ``lock_valid_neck_rad`` plus one float ulp of allowance; the
    required search domain is reported beside it because the seal's own anchor start is outside that
    domain (HS-316's recorded inference), and an anchor start is not an unbounded command.
    """

    if not isinstance(commands, Mapping):
        return {
            "bounded": False,
            "outside_corridor_count": 0,
            "corridor_rad": None,
            "required_search_domain_rad": None,
            "outside_required_domain_count": 0,
            "outside_corridor_indices": [],
            "targets_rad": [],
            "max_abs_neck_rad": None,
            "command_count": 0,
            "commands": [],
            "definition": "no commanded-target record was presented, so no command is shown to be bounded",
        }
    corridor = commands.get("corridor_rad")
    if (
        isinstance(corridor, (str, bytes))
        or not isinstance(corridor, Sequence)
        or len(corridor) != 2
        or not all(_finite(bound) for bound in corridor)
        or float(corridor[0]) >= float(corridor[1])
    ):
        raise _refuse(
            SMOKE_COMMANDS_UNBOUNDED,
            f"the commanded targets are presented without a finite ordered corridor: {corridor!r}",
        )
    low, high = float(corridor[0]), float(corridor[1])
    required = commands.get("required_search_domain_rad")
    required = (
        [float(bound) for bound in required]
        if isinstance(required, Sequence)
        and not isinstance(required, (str, bytes))
        and len(required) == 2
        else None
    )
    records: list[dict] = []
    outside: list[int] = []
    outside_required: list[int] = []
    targets: list[float] = []
    for position, entry in enumerate(commands.get("targets") or ()):
        if not isinstance(entry, Mapping) or not _finite(entry.get("target_rad")):
            raise _refuse(
                SMOKE_COMMANDS_UNBOUNDED,
                f"commanded target {position} carries no finite target_rad: {dict(entry or {})}",
            )
        target = float(entry["target_rad"])
        index = entry.get("index")
        index = position if type(index) is not int or isinstance(index, bool) else int(index)
        inside = low - 1e-12 <= target <= high + 1e-12
        in_required = (
            None if required is None else (required[0] - 1e-12 <= target <= required[1] + 1e-12)
        )
        if not inside:
            outside.append(index)
        if in_required is False:
            outside_required.append(index)
        targets.append(target)
        records.append(
            {
                "index": index,
                "target_rad": target,
                "statuses": list(entry.get("statuses") or ()),
                "ticks": int(entry.get("ticks") or 0),
                "first_frame_sim_s": entry.get("first_frame_sim_s"),
                "kind": entry.get("kind"),
                "inside_corridor": inside,
                "inside_required_domain": in_required,
            }
        )
    return {
        "bounded": bool(records) and not outside,
        "outside_corridor_count": len(outside),
        "corridor_rad": [low, high],
        "required_search_domain_rad": required,
        "outside_required_domain_count": len(outside_required),
        "outside_corridor_indices": outside,
        "targets_rad": targets,
        "max_abs_neck_rad": max((abs(target) for target in targets), default=None),
        "command_count": len(records),
        "commands": records,
        "corridor_definition": (
            "the corridor is the seal's own lock_valid_neck_rad, the interval a lock is valid in, which "
            "is the interval the seal's anchor start and a fine correction both lie in; the required "
            "search domain is reported beside it because the seal's own `default` anchor starts outside "
            "it (HS-316), and the anchor's declared start is not an unbounded command"
        ),
        "definition": (
            "a command is bounded when the neck target the controller really commanded lies inside the "
            "declared corridor; the count of targets outside it must be zero"
        ),
    }


def classify_terminal(
    terminal_status,
    *,
    condition_class: str = CONDITION_CLASS,
    coverage=None,
    seed=None,
) -> dict:
    """One smoke flight's terminal, judged by ``head_search_scenarios.classify_scenario`` itself.

    The entry built here is the entry the forty-scenario producer builds, so the smoke cannot pass on a
    rule of its own: ``nominal`` declares ``TARGET_LOCKED``, and a terminal the class does not declare is
    the scenario module's own failure (a wrong lock for a class that must not lock, a missed cup for one
    that must) with the scenario module's own code.
    """

    try:
        terminals = expected_terminals(condition_class)
    except CalibrationInputsRefused as error:
        raise _refuse(
            SMOKE_CLASS_UNDECLARED,
            f"the smoke declares the condition class {condition_class!r}, which the plan's scenario rule does "
            f"not name, so its terminal cannot be judged: {error}",
        ) from error
    entry = {
        "seed": seed if seed is not None else f"{PHASE}-{condition_class}",
        "condition_class": condition_class,
        "terminal_status": terminal_status,
        "coverage": dict(coverage or {}),
        "attempts": [],
    }
    classification = classify_scenario(entry)
    classification["declared_terminals"] = list(terminals)
    classification["condition_class_definition"] = CONDITION_CLASS_DEFINITION
    return classification


# --- the sealed journal -------------------------------------------------------------------------------


def sealed_journal_document(
    *,
    run_root,
    anchor: str,
    condition_class: str,
    declared: Mapping,
    runtime: Mapping,
    ownership: Mapping,
    approved_bundle_sha256: str,
    seal: Mapping,
    producer: Mapping,
    corridors: Mapping,
    values: Mapping | None = None,
    coverage: Mapping | None = None,
    evidence: Mapping | None = None,
    flight_refusal: Mapping | None = None,
    started_at_utc: str,
    finished_at_utc: str,
    elapsed_s: float,
    now=time.gmtime,
) -> dict:
    """The producer's raw record: everything the flight observed, and nothing it concluded.

    The gates are **not** here. What the flight saw - the frames the controller consumed, the targets it
    commanded, the feedback samples it held, the nodes that were up, the teardown probe - is sealed with
    this document's own body digest, and the aggregator derives the gates by reading the file back.
    """

    flight = dict(evidence or {})
    search = flight.get("search") if isinstance(flight.get("search"), Mapping) else {}
    camera = flight.get("camera") if isinstance(flight.get("camera"), Mapping) else {}
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": SEALED_KIND,
        "operation": OPERATION,
        "phase": PHASE,
        "run_root": str(run_root),
        "anchor": anchor,
        "condition_class": condition_class,
        "declared_anchor": dict(declared),
        "producer": {**dict(producer), "stack_owned": True},
        "ownership": dict(ownership),
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
        "seal_sha256": seal.get("seal_sha256"),
        "corridors": dict(corridors),
        "control_thresholds": {
            key: (values or {}).get(key)
            for key in (
                "stop_velocity_rad_s",
                "settle_velocity_rad_s",
                "goal_tolerance_rad",
                "search_timeout_s",
                "max_age_s",
                "max_skew_s",
            )
        },
        "values": dict(values or {}),
        "coverage_proof": (
            None
            if coverage is None
            else {
                "document": dict(coverage),
                "path": str(Path(run_root) / COVERAGE_PROOF_ARTIFACT),
                "sha256": _digest(Path(run_root) / COVERAGE_PROOF_ARTIFACT),
                "role": (
                    "the planning-coverage proof of the bounded plan this flight walks; it is a "
                    "precondition, not this phase's success condition - the qualification gate reads "
                    f"{JOURNAL_ARTIFACT}"
                ),
            }
        ),
        "stack": dict(flight.get("stack") or {}),
        "camera": dict(camera),
        "clock": dict(flight.get("clock") or {}),
        "scene": dict(flight.get("scene") or {}),
        "detector": dict(flight.get("detector") or {}),
        "admission": dict(flight.get("admission") or {}),
        "adapter_liveness": dict(flight.get("adapter_liveness") or {}),
        "neck_port": dict(flight.get("neck_port") or {}),
        "frames": list(flight.get("frames") or ()),
        "terminal": dict(search.get("terminal") or {}),
        "terminal_status": search.get("terminal_status"),
        "coverage": dict(search.get("coverage") or {}),
        "lock": dict(flight.get("lock") or {}),
        "commands": search.get("commands"),
        "stop": dict(flight.get("stop") or {}),
        "teardown": dict(flight.get("teardown") or {}),
        "reconstruction": dict(flight.get("reconstruction") or {}),
        "flight_refusal": None if flight_refusal is None else dict(flight_refusal),
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "elapsed_s": None if elapsed_s is None else float(elapsed_s),
        "producer_elapsed_s": None if elapsed_s is None else float(elapsed_s),
        "fit_warning": FIT_WARNING,
    }
    # the flight's own elapsed time is the one the plan reads; the producer's wall time around the call is
    # recorded beside it so a reader can tell a fast refusal from a fast flight
    flight_elapsed = flight.get("elapsed_s")
    if _finite(flight_elapsed):
        document["elapsed_s"] = float(flight_elapsed)
    document["sealed"] = {
        "at_utc": _utc_now(now),
        "body_sha256": canonical_sha256(document),
        "definition": (
            "the sha256 of this document's canonical body without this block; the aggregator recomputes "
            "it from the file it reads, so a hand-edited journal is refused rather than judged"
        ),
    }
    return document


# --- the aggregator -----------------------------------------------------------------------------------


def _gate(name: str, holds: bool, detail: str) -> dict:
    return {"gate": name, "status": "PASS" if holds else "FAIL", "detail": detail}


def aggregate_production_smoke(
    sealed_journal_path,
    *,
    run_root=None,
    producer: Mapping | None = None,
    entry: str = AGGREGATOR_ENTRY,
    now=time.gmtime,
) -> dict:
    """Read a sealed journal back off disk and write the document the qualification gate consumes.

    This is the middle link of the plan's "producer -> sealed journal -> actual aggregator" chain, and it
    is deliberately a **reader**: it opens the file, refuses a body whose digest is not the one the seal
    declares, and then re-derives the cadence, the commands, the stop proof and the terminal from the raw
    records. It never consults the flight's own summary, and it writes ``production-smoke-journal.json``.
    """

    path = Path(sealed_journal_path)
    try:
        sealed = _read_json(path)
    except (OSError, ValueError) as error:
        raise _refuse(
            SMOKE_JOURNAL_UNREADABLE,
            f"the sealed journal {path} cannot be read as one document ({error}); an aggregator with no "
            f"sealed journal has nothing to aggregate",
        ) from error
    if sealed.get("kind") != SEALED_KIND:
        raise _refuse(
            SMOKE_JOURNAL_UNREADABLE,
            f"{path} carries kind {sealed.get('kind')!r}, not {SEALED_KIND!r}",
        )
    declared_digest = (sealed.get("sealed") or {}).get("body_sha256")
    body = {key: value for key, value in sealed.items() if key != "sealed"}
    computed = canonical_sha256(body)
    if declared_digest != computed:
        raise _refuse(
            SMOKE_SEAL_MISMATCH,
            f"the sealed journal's body digest is {computed}, not the declared {declared_digest!r}: the "
            f"file was edited after it was sealed",
        )

    root = Path(run_root) if run_root is not None else Path(str(sealed.get("run_root")))
    runtime = dict(sealed.get("runtime") or {})
    thresholds = (
        sealed.get("control_thresholds")
        if isinstance(sealed.get("control_thresholds"), Mapping)
        else {}
    )
    stop = sealed.get("stop") if isinstance(sealed.get("stop"), Mapping) else {}
    velocity_limit = thresholds.get("stop_velocity_rad_s")
    if velocity_limit is None:
        velocity_limit = stop.get("velocity_limit_rad_s")
    if not _finite(velocity_limit) or float(velocity_limit) <= 0.0:
        raise _refuse(
            SMOKE_JOURNAL_UNREADABLE,
            f"the sealed journal records no positive stop velocity limit ({velocity_limit!r}), so the held "
            f"samples cannot be judged against the promoted stop_velocity_rad_s",
        )
    corridor = (sealed.get("corridors") or {}).get("lock_valid_neck_rad")
    commands_record = sealed.get("commands")
    if isinstance(commands_record, Mapping):
        commands_record = {**dict(commands_record), "corridor_rad": corridor}
    cadence = smoke_cadence(list(sealed.get("frames") or ()))
    commands = smoke_commands(commands_record)
    proof = stop_proof(
        list(stop.get("samples") or ()),
        velocity_limit_rad_s=float(velocity_limit),
        required_samples=3,
    )
    proof["held_at_rad"] = stop.get("held_at_rad")
    proof["source"] = stop.get("source")
    proof["controller_stop_confirmed"] = stop.get("controller_stop_confirmed")
    proof["criterion"] = stop.get("criterion")
    classification = (
        classify_terminal(
            sealed.get("terminal_status"),
            condition_class=str(sealed.get("condition_class") or CONDITION_CLASS),
            coverage=sealed.get("coverage"),
            seed=f"{PHASE}-{sealed.get('anchor')}",
        )
        if not sealed.get("flight_refusal")
        else None
    )
    detector = sealed.get("detector") if isinstance(sealed.get("detector"), Mapping) else {}
    teardown = sealed.get("teardown") if isinstance(sealed.get("teardown"), Mapping) else {}
    stack = sealed.get("stack") if isinstance(sealed.get("stack"), Mapping) else {}
    lock = sealed.get("lock") if isinstance(sealed.get("lock"), Mapping) else {}
    scene = sealed.get("scene") if isinstance(sealed.get("scene"), Mapping) else {}
    camera = sealed.get("camera") if isinstance(sealed.get("camera"), Mapping) else {}
    reconstruction = (
        sealed.get("reconstruction") if isinstance(sealed.get("reconstruction"), Mapping) else {}
    )

    teardown_fields = (
        "previous_stack_stopped",
        "controller_owner_stopped",
        "children_exited",
        "graph_clear",
    )
    gates = {
        "stack": _gate(
            "stack",
            bool(stack.get("nodes"))
            and reconstruction.get("stack_started") is True
            and reconstruction.get("one_mujoco_instance") is True,
            f"nodes={list(stack.get('nodes') or ())}, reconstruction={dict(reconstruction)}",
        ),
        "detector": _gate(
            "detector",
            int(detector.get("count", 0)) == 1
            and str(detector.get("device", "")) == "cuda"
            and detector.get("allow_cpu_fallback") is False
            and detector.get("weights_sha256") == runtime.get("weight_sha256_declared"),
            f"detector={dict(detector)}",
        ),
        "scene": _gate(
            "scene",
            bool(scene.get("point_m")) and bool(scene.get("service")),
            f"the anchor's cup placement: {dict(scene)}",
        ),
        "search": _gate(
            "search",
            bool(classification) and classification["outcome"] == "PASSED",
            (
                "no terminal was recorded"
                if not classification
                else f"terminal {sealed.get('terminal_status')!r}: "
                f"{classification['outcome']} {classification['outcome_code'] or ''} "
                f"{classification['outcome_detail'] or ''}".strip()
            ),
        ),
        "lock": _gate(
            "lock",
            int(lock.get("consecutive_frames", 0)) >= 3,
            f"lock={dict(lock)}",
        ),
        "cadence": _gate(
            "cadence", cadence["continuous"] is True, f"cadence={_cadence_summary(cadence)}"
        ),
        "commands": _gate(
            "commands",
            commands["bounded"] is True and int(commands["outside_corridor_count"]) == 0,
            f"commands={_commands_summary(commands)}",
        ),
        "stop": _gate(
            "stop",
            proof["proven"] is True and int(proof["qualifying_samples"]) >= 3,
            f"stop_proof={_stop_summary(proof)}",
        ),
        "teardown": _gate(
            "teardown",
            all(teardown.get(field) is True for field in teardown_fields),
            f"teardown={ {field: teardown.get(field) for field in teardown_fields} }",
        ),
        "gpu": _gate(
            "gpu",
            teardown.get("gpu_released") is True,
            f"gpu_compute_apps={list(teardown.get('gpu_compute_apps') or ())}",
        ),
    }

    refuse_on = {
        "stack": SMOKE_STACK_START_FAILED,
        "detector": SMOKE_DETECTOR_FAILED,
        "scene": SMOKE_CUP_NOT_PLACED,
        "search": SMOKE_LOCK_UNPROVEN,
        "lock": SMOKE_LOCK_UNPROVEN,
        "cadence": SMOKE_CADENCE_BROKEN,
        "commands": SMOKE_COMMANDS_UNBOUNDED,
        "stop": SMOKE_STOP_UNPROVEN,
        "teardown": SMOKE_TEARDOWN_UNPROVEN,
        "gpu": SMOKE_GPU_NOT_RELEASED,
    }
    refusals: list[dict] = []
    flight_refusal = sealed.get("flight_refusal")
    if isinstance(flight_refusal, Mapping) and flight_refusal:
        original = str(flight_refusal.get("code") or "")
        refusals.append(
            {
                "code": RESTART_CODE_MAP.get(original, SMOKE_PROBE_FAILED),
                "detail": f"the flight refused with {original}: {flight_refusal.get('detail')}",
                "flight_code": original,
            }
        )
    for name in (
        "stack",
        "detector",
        "scene",
        "search",
        "lock",
        "cadence",
        "commands",
        "stop",
        "teardown",
        "gpu",
    ):
        if gates[name]["status"] != "PASS":
            refusals.append({"code": refuse_on[name], "detail": gates[name]["detail"]})

    sealed_digest = _digest(path)
    measured_rate = camera.get("measured_rate_hz")
    document: dict = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "operation": OPERATION,
        "phase": PHASE,
        "run_root": str(root),
        "anchor": sealed.get("anchor"),
        "condition_class": sealed.get("condition_class"),
        "condition_class_definition": CONDITION_CLASS_DEFINITION,
        "producer": dict(sealed.get("producer") or {}),
        "aggregator": {
            "entry": entry,
            "journal_sha256": sealed_digest,
            "status": "SUCCEEDED",
            "body_sha256": computed,
            "at_utc": _utc_now(now),
            "definition": (
                "the aggregator read the sealed journal back from disk, re-derived every reading below "
                "from its raw records, and wrote this document; SUCCEEDED means the read and the "
                "re-derivation both happened, not that the gates passed"
            ),
        },
        "journal": {
            "path": str(path),
            "sha256": sealed_digest,
            "kind": SEALED_KIND,
            "body_sha256": computed,
            "frames": cadence["frame_count"],
            "command_count": commands["command_count"],
            "stop_sample_count": proof["sample_count"],
        },
        "ownership": dict(sealed.get("ownership") or {}),
        "runtime": runtime,
        "coverage_proof": sealed.get("coverage_proof"),
        "approved_bundle_sha256": sealed.get("approved_bundle_sha256"),
        "seal_sha256": sealed.get("seal_sha256"),
        "terminal_status": sealed.get("terminal_status"),
        "terminal": dict(sealed.get("terminal") or {}),
        "outcome": None if not classification else classification["outcome"],
        "outcome_code": None if not classification else classification["outcome_code"],
        "outcome_detail": None if not classification else classification["outcome_detail"],
        "zero_wrong_locks": bool(
            classification is not None
            and classification["outcome"] == "PASSED"
            and int(lock.get("consecutive_frames", 0)) >= 3
        ),
        "frame_cadence": cadence,
        "commands": commands,
        "stop_proof": proof,
        "lock": dict(lock),
        "detector": dict(detector),
        "stack": dict(stack),
        "camera": dict(camera),
        "clock": dict(sealed.get("clock") or {}),
        "scene": dict(scene),
        "admission": dict(sealed.get("admission") or {}),
        "adapter_liveness": dict(sealed.get("adapter_liveness") or {}),
        "neck_port": dict(sealed.get("neck_port") or {}),
        "reconstruction": dict(reconstruction),
        "teardown": dict(teardown),
        "corridors": dict(sealed.get("corridors") or {}),
        "provenance": {
            "run_root": str(root),
            "final_run": runtime.get("final_run"),
            "source_commit": runtime.get("source_commit"),
            "production_config": runtime.get("production_config"),
            "production_config_sha256": runtime.get("production_config_sha256"),
            "values_sha256": runtime.get("values_sha256"),
            "weight_path": runtime.get("weight_path"),
            "weight_sha256": runtime.get("weight_sha256_observed"),
            "approved_bundle_sha256": sealed.get("approved_bundle_sha256"),
            "seal_sha256": sealed.get("seal_sha256"),
            "anchor": sealed.get("anchor"),
            "condition_class": sealed.get("condition_class"),
            "nodes": list(stack.get("nodes") or ()),
            "node_count": len(stack.get("nodes") or ()),
            "device": detector.get("device"),
            "model_id": detector.get("model_id"),
            "published_frame_id": camera.get("published_frame_id"),
            "declared_rate_hz": FRAME_RATE_HZ,
            "measured_rate_hz": measured_rate,
            "consumed_frame_rate_hz": cadence["achieved_rate_hz"],
            "elapsed_s": sealed.get("elapsed_s"),
            "producer_elapsed_s": sealed.get("producer_elapsed_s"),
            "started_at_utc": sealed.get("started_at_utc"),
            "finished_at_utc": sealed.get("finished_at_utc"),
            "teardown_proof": {field: teardown.get(field) for field in teardown_fields}
            | {"gpu_released": teardown.get("gpu_released")},
        },
        "frames": list(sealed.get("frames") or ()),
        "gates": {name: gates[name]["status"] for name in gates},
        "gate_details": gates,
        "refusals": refusals,
        "status": "REFUSED" if refusals else "PASS",
        "flight_refusal": None if flight_refusal is None else dict(flight_refusal),
        "started_at_utc": sealed.get("started_at_utc"),
        "finished_at_utc": sealed.get("finished_at_utc"),
        "elapsed_s": sealed.get("elapsed_s"),
        "fit_warning": FIT_WARNING,
    }
    if producer is not None:
        document["producer"] = {**dict(producer), "stack_owned": True}
    # the artefact's own digest covers everything except itself and the aggregation instant, so reading
    # the same sealed journal twice reproduces the same digest
    digest_body = {key: value for key, value in document.items() if key != "sha256"}
    digest_body["aggregator"] = {
        key: value for key, value in digest_body["aggregator"].items() if key != "at_utc"
    }
    document["sha256"] = canonical_sha256(digest_body)

    problems = validate_smoke_journal(document)
    if problems:
        raise _refuse(
            SMOKE_JOURNAL_INVALID,
            f"the aggregated journal does not carry the shape the qualification gate reads: {problems}",
        )
    root.mkdir(parents=True, exist_ok=True)
    _write(root, JOURNAL_ARTIFACT, document)
    _write(
        root,
        RECEIPT_ARTIFACT,
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RECEIPT_KIND,
            "operation": OPERATION,
            "phase": PHASE,
            "run_root": str(root),
            "anchor": document["anchor"],
            "journal": str(root / JOURNAL_ARTIFACT),
            "journal_sha256": _digest(root / JOURNAL_ARTIFACT),
            "sealed_journal": str(path),
            "sealed_journal_sha256": sealed_digest,
            "gates": document["gates"],
            "refusals": refusals,
            "status": document["status"],
            "sha256": document["sha256"],
        },
    )
    return document


# --- the planning coverage proof, kept beside the journal ---------------------------------------------


def coverage_proof_document(seal, anchor: str, *, anchor_rad: float, plan) -> dict:
    """The planning-coverage proof the bounded plan produces: the document the coverage gate cites.

    This is the document ``so101_head_search_smoke`` has always written (one construction, so the
    coverage path and the production smoke cannot drift), and it is deliberately **not** the smoke's
    success condition: covering the required domain with bounded stops says the plan is complete, not
    that the production loop found the cup.
    """

    from so101_demo.act.head_search_domain import (
        TARGET_NOT_FOUND,
        TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL,
    )

    return {
        "schema_version": 1,
        "anchor": anchor,
        "anchor_rad": float(anchor_rad),
        "targets_rad": list(plan.targets_rad),
        "stop_count": len(plan.targets_rad),
        "coverage_complete": plan.coverage_complete,
        "required_domain_rad": list(plan.required_domain_rad),
        "safe_interval_rad": list(plan.safe_interval_rad),
        "horizontal_fov_rad": plan.horizontal_fov_rad,
        "coarse_step_rad": plan.coarse_step_rad,
        "statuses": [TARGET_NOT_FOUND, TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL],
        "seal_sha256": seal.get("seal_sha256"),
    }


def write_coverage_proof(root, seal: Mapping, anchor: str, *, anchor_rad: float) -> dict:
    """Prove the bounded plan covers the required domain before the smoke commands anything.

    The step is never invented: it is the sealed contract's, and a seal that declares none refuses.
    """

    from so101_demo.act.head_search_domain import HeadSearchDomainError, bounded_search_stops

    step_source = (seal.get("camera") or {}).get("coarse_step_rad") or seal.get(
        "coarse_step_candidate_rad"
    )
    if step_source is None:
        raise _refuse(
            SMOKE_COVERAGE_UNPROVEN,
            "the sealed geometry declares no coarse step, so the coverage of the bounded plan cannot be "
            "proven and no search may be commanded from it",
        )
    try:
        plan = bounded_search_stops(
            anchor_rad=float(anchor_rad),
            required_domain_rad=seal["required_search_domain_rad"],
            safe_interval_rad=seal["lock_valid_neck_rad"],
            horizontal_fov_rad=float(seal["horizontal_fov_rad"]),
            coarse_step_rad=float(step_source),
        )
    except (HeadSearchDomainError, KeyError, TypeError, ValueError) as error:
        raise _refuse(
            SMOKE_COVERAGE_UNPROVEN, f"the bounded plan could not be built: {error}"
        ) from error
    if not plan.coverage_complete:
        raise _refuse(
            SMOKE_COVERAGE_UNPROVEN,
            f"the bounded plan for the anchor {anchor!r} does not cover the required domain "
            f"{list(plan.required_domain_rad)} with stops inside {list(plan.safe_interval_rad)}",
        )
    document = coverage_proof_document(seal, anchor, anchor_rad=float(anchor_rad), plan=plan)
    root = Path(root)
    _write(root, f"head-search-plan-{anchor}.json", document)
    _write(root, COVERAGE_PROOF_ARTIFACT, document)
    return document


# --- the shape the qualification gate reads -----------------------------------------------------------


def validate_smoke_journal(document) -> list[str]:
    """Every field ``head_search_aggregate._gate_smoke`` reads, named when it is not there.

    This is the run-time half of the contract in ``aggregate.DECLARED_CONTRACTS``: the producer refuses to
    declare a run finished with a journal the gate could not read, so a drift between this module and the
    gate is a refusal at the producer rather than a mystery in the verdict.
    """

    problems: list[str] = []
    if not isinstance(document, Mapping):
        return ["the journal is not a mapping"]
    if document.get("kind") != KIND:
        problems.append(f"kind is {document.get('kind')!r}, not {KIND!r}")
    if document.get("phase") != PHASE:
        problems.append(f"phase is {document.get('phase')!r}, not {PHASE!r}")
    producer = document.get("producer")
    producer = producer if isinstance(producer, Mapping) else {}
    if not producer.get("entry"):
        problems.append("producer.entry is empty")
    if producer.get("stack_owned") is not True:
        problems.append(f"producer.stack_owned is {producer.get('stack_owned')!r}, not True")
    journal = document.get("journal")
    journal = journal if isinstance(journal, Mapping) else {}
    if not journal.get("path"):
        problems.append("journal.path names no sealed journal")
    if not journal.get("sha256"):
        problems.append("journal.sha256 is empty")
    aggregator = document.get("aggregator")
    aggregator = aggregator if isinstance(aggregator, Mapping) else {}
    if not aggregator.get("entry"):
        problems.append("aggregator.entry is empty")
    if not aggregator.get("journal_sha256"):
        problems.append("aggregator.journal_sha256 is empty")
    if aggregator.get("status") != "SUCCEEDED":
        problems.append(f"aggregator.status is {aggregator.get('status')!r}, not 'SUCCEEDED'")
    runtime = document.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    for key in ("source_commit", "production_config_sha256", "values_sha256"):
        if not runtime.get(key):
            problems.append(f"runtime.{key} is empty")
    # a refused journal is the honest record of a run that did not pass, so the readings a refusal is
    # allowed to be missing are only required of a journal that claims to have passed
    if document.get("status") != "PASS":
        return problems
    if document.get("zero_wrong_locks") is not True:
        problems.append("zero_wrong_locks is not True on a passing journal")
    cadence = document.get("frame_cadence")
    cadence = cadence if isinstance(cadence, Mapping) else {}
    for key in ("continuous", "duplicate_count", "backward_count", "undeclared_gap_count"):
        if key not in cadence:
            problems.append(f"frame_cadence.{key} is missing")
    commands = document.get("commands")
    commands = commands if isinstance(commands, Mapping) else {}
    for key in ("bounded", "outside_corridor_count"):
        if key not in commands:
            problems.append(f"commands.{key} is missing")
    proof = document.get("stop_proof")
    proof = proof if isinstance(proof, Mapping) else {}
    for key in ("proven", "qualifying_samples"):
        if key not in proof:
            problems.append(f"stop_proof.{key} is missing")
    detector = document.get("detector")
    detector = detector if isinstance(detector, Mapping) else {}
    for key in ("count", "device", "allow_cpu_fallback"):
        if key not in detector:
            problems.append(f"detector.{key} is missing")
    provenance = document.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    for key in ("nodes", "measured_rate_hz", "elapsed_s", "teardown_proof"):
        if provenance.get(key) in (None, [], {}):
            problems.append(f"provenance.{key} is empty")
    return problems


def _cadence_summary(cadence: Mapping) -> dict:
    return {
        key: cadence.get(key)
        for key in (
            "frame_count",
            "continuous",
            "achieved_rate_hz",
            "min_interval_s",
            "max_interval_s",
            "duplicate_count",
            "backward_count",
            "too_fast_count",
            "gap_count",
            "undeclared_gap_count",
            "frames_short",
        )
    }


def _commands_summary(commands: Mapping) -> dict:
    return {
        key: commands.get(key)
        for key in (
            "bounded",
            "outside_corridor_count",
            "corridor_rad",
            "outside_required_domain_count",
            "targets_rad",
            "max_abs_neck_rad",
        )
    }


def _stop_summary(proof: Mapping) -> dict:
    return {
        key: proof.get(key)
        for key in ("proven", "required_samples", "qualifying_samples", "longest_consecutive_run")
    }


# --- the producer -------------------------------------------------------------------------------------


def write_head_search_production_smoke(
    *,
    run_root,
    ownership_receipt,
    runtime: Mapping,
    seal: Mapping,
    workdir,
    run_flight,
    producer: Mapping,
    approved_bundle_sha256: str,
    anchor: str = "default",
    condition_class: str = CONDITION_CLASS,
    values: Mapping | None = None,
    now=time.gmtime,
) -> dict:
    """Claim a brand-new run root, fly one anchor through the production path, seal it and aggregate it.

    The order is fixed and it is the plan's: the class is judged against the plan's own vocabulary, the
    runtime is the CUDA-only runtime of record, the Step 1 receipt must guard exactly this run root, the
    seal must declare this anchor, and only then is the root claimed and the stack started. A flight that
    refuses leaves its sealed journal and its journal behind: a run that did not pass is still readable.
    """

    root = Path(run_root)
    if root.exists():
        raise _refuse(
            SMOKE_RUN_ROOT_EXISTS,
            f"{root} exists; a qualification phase is never resumed, continued or overwritten",
        )
    classify_terminal(None, condition_class=condition_class)
    if anchor not in ANCHORS:
        raise _refuse(
            SMOKE_ANCHOR_UNDECLARED,
            f"the smoke anchor {anchor!r} is not one of the plan's anchors {list(ANCHORS)}",
        )
    try:
        runtime = require_runtime_of_record(runtime)
    except CalibrationInputsRefused as error:
        raise _refuse(SMOKE_RUNTIME_UNVERIFIED, f"{error.code}: {error.detail}") from error
    try:
        ownership = read_ownership_receipt(ownership_receipt, run_root=root)
    except CalibrationInputsRefused as error:
        code = {
            RESTART_OWNERSHIP_REFUSED: SMOKE_OWNERSHIP_REFUSED,
            RESTART_OWNERSHIP_MISMATCH: SMOKE_OWNERSHIP_MISMATCH,
            RESTART_RUNTIME_UNVERIFIED: SMOKE_RUNTIME_UNVERIFIED,
        }.get(error.code, SMOKE_OWNERSHIP_MISMATCH)
        raise _refuse(code, f"{error.code}: {error.detail}") from error
    try:
        declared = anchor_declarations(seal, [anchor])
    except CalibrationInputsRefused as error:
        raise _refuse(SMOKE_ANCHOR_UNDECLARED, f"{error.code}: {error.detail}") from error
    if len(declared) != 1:
        raise _refuse(
            SMOKE_ANCHOR_UNDECLARED,
            f"the seal resolves the anchor {anchor!r} to {len(declared)} declarations, not one",
        )
    declared = declared[0]
    from so101_demo.act.head_search_deadband_measurement.lock_trial import motion_corridor_rad
    from so101_demo.act.head_search_fine_correction_episodes.episode import fine_corridor_rad

    corridors = {
        "lock_valid_neck_rad": list(fine_corridor_rad(geometry_seal=seal)),
        "required_search_domain_rad": [
            float(bound) for bound in seal["required_search_domain_rad"]
        ],
        "sweep_corridor_rad": list(motion_corridor_rad(geometry_seal=seal)),
        "lock_valid_definition": (
            "the seal's own lock_valid_neck_rad: the interval a lock is valid in, the interval the "
            "controller's plan clamps its stops to, and the corridor every commanded target is judged "
            "against (HS-316: the seal's `default` anchor starts outside the required search domain, so "
            "that domain cannot bound the anchor start without refusing the plan's own anchor)"
        ),
    }

    _require_new_root(root)
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    # the plan the flight walks is proven before anything is commanded, and the proof stays in the run
    # root: the plan's coverage gate cites this artefact, while the smoke's own success is the journal
    coverage = write_coverage_proof(
        root, seal, anchor, anchor_rad=float(declared["neck_start_rad"])
    )
    anchor_root = root / anchor
    anchor_root.mkdir()
    started = time.time()
    started_at = _utc_now(now)
    evidence: dict = {}
    flight_refusal: dict | None = None
    stdout = (anchor_root / STDOUT_LOG).open("a", encoding="utf-8")
    stderr = (anchor_root / STDERR_LOG).open("a", encoding="utf-8")
    try:
        evidence = dict(
            run_flight(
                anchor=anchor,
                root=root,
                anchor_root=anchor_root,
                declared=declared,
                runtime=runtime,
                ownership=ownership,
                run_root=root,
                approved_bundle_sha256=approved_bundle_sha256,
                producer={**dict(producer), "stack_owned": True},
                values=dict(values or {}),
                seal=seal,
                stdout=stdout,
                stderr=stderr,
            )
            or {}
        )
    except CalibrationInputsRefused as error:
        flight_refusal = {"code": error.code, "detail": error.detail}
        print(f"the flight refused: {error}", file=stderr)
    finally:
        stdout.close()
        stderr.close()
    elapsed = time.time() - started

    sealed_document = sealed_journal_document(
        run_root=root,
        anchor=anchor,
        condition_class=condition_class,
        declared=declared,
        runtime=runtime,
        ownership=ownership,
        approved_bundle_sha256=approved_bundle_sha256,
        seal=seal,
        producer=producer,
        corridors=corridors,
        values=values,
        coverage=coverage,
        evidence=evidence,
        flight_refusal=flight_refusal,
        started_at_utc=started_at,
        finished_at_utc=_utc_now(now),
        elapsed_s=elapsed,
        now=now,
    )
    sealed_path = _write(root, SEALED_ARTIFACT, sealed_document)
    journal = aggregate_production_smoke(sealed_path, run_root=root, producer=producer, now=now)
    return {
        "run_root": str(root),
        "anchor_root": str(anchor_root),
        "sealed_journal": str(sealed_path),
        "sealed_journal_sha256": _digest(sealed_path),
        "journal": str(root / JOURNAL_ARTIFACT),
        "receipt": str(root / RECEIPT_ARTIFACT),
        "evidence": evidence,
        "document": journal,
        "gates": dict(journal["gates"]),
        "refusals": list(journal["refusals"]),
        "status": journal["status"],
        "elapsed_s": elapsed,
    }


def run_smoke_flight(**kwargs) -> dict:
    """Run development through the formal entry; legacy execution requires migration."""

    if 'execution_inputs' in kwargs:
        if set(kwargs) != {'execution_inputs'}:
            raise _refuse('SMOKE_EXECUTION_INPUTS_MIXED',
                          'development inputs cannot be mixed with qualification anchor arguments')
        from so101_demo.act.head_execution_inputs import HeadExecutionInputs
        from so101_demo.cli.head_execution_run import main

        inputs = HeadExecutionInputs.parse(kwargs['execution_inputs'])
        code = main(['--execution-inputs', str(inputs.document_path)])
        return dict(operation=inputs.document['operation'],
                    execution_scope=inputs.execution_scope,
                    qualification_status='NOT_QUALIFIED',
                    business_return_code=code, run_root=str(inputs.run_root),
                    execution_inputs_sha256=inputs.document_sha256)

    raise _refuse('HEAD_LEGACY_EXECUTION_REMOVED',
                  'use run --execution-inputs; legacy qualification execution is not migrated')


def read_runtime_of_record(final_run, production_config=None) -> dict:
    """The frozen runtime's own identity, read off disk through the Step 1 reader."""

    from so101_demo.act.head_search_restarts import read_runtime_of_record as read

    return read(final_run, production_config)
