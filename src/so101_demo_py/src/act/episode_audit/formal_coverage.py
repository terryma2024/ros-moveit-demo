"""The coverage a formal seal requires, stated from the facts the decoupled Recorder and the offline processor write.

The Recorder no longer runs the old pick-place runner: nothing writes `phase_complete` rows, `release` events or `physics.jsonl`
rows. What a Teacher episode retains instead is the Teacher's own event stream (`teacher_event`, with its sealed
`teacher_event_summary`), the collection boundaries, the raw native physics chunks, the scene alignments, the controller
reference continuity report and the Recorder queue account. Formal coverage is the requirement that those facts describe one
whole episode:

* T1 lifecycle: one sealed summary that accounts for every retained event; `reset_complete`, `teacher_start_observation`,
  well-formed `phase_begin`/`phase_finish` pairs, `normal_stop`, `teacher_end_observation`, `terminal` last. A terminal that claims
  COMPLETED must have run the registered Teacher states in order, every one of them SUCCEEDED.
* T2 boundaries: exactly the five collection boundaries, once each.
* T3 physics history: raw native chunks with no step missing from the first command through the stop and the end observation,
  and one Recorder queue account whose accepted and written counts equal the bound rows.
* T4 scene and controller records: one `initial` alignment, a `world_sync` before the first command, one controller reference
  report; a COMPLETED episode also has its MoveIt attach inside ATTACH_MOVEIT and its detach inside the release window.
* T5 release (COMPLETED only): DETACH_MOVEIT, OPEN_GRIPPER and WAIT_RELEASE_SETTLE succeeded in that order, and the MoveIt detach
  was applied before the gripper opened.
* T6 reference: at least one accepted reference with one complete raw group.

An episode whose Teacher did not complete is held to T1 (structure), T2, T3, T4 (first three records) and T6, which is what native
QC itself requires of every episode. It can be sealed; the data verdict and the export gates keep it out of training.

One predicate serves the seal (`writer.py`) and the readback (`verification.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

from so101_demo.act.collection_boundaries import COLLECTION_BOUNDARY_STAGES
from so101_demo.act.episode_audit.checks import (
    _REFERENCE_FRAME_FIELDS,
    _REFERENCE_RAW_FIELDS,
    _parse_audit_lines,
)
from so101_demo.act.qc_session import cached_lines

#: the states a Teacher run that completed went through, in order. Declared here rather than imported from the workflow so the
#: audit stays readable without it; `test_the_audit_names_the_teacher_s_states` asserts equality with the registered success
#: trace, so the two cannot drift apart silently.
TEACHER_STATES = (
    "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "DESCEND", "CLOSE_GRIPPER", "WAIT_GRASP_STABLE", "MICRO_LIFT",
    "WAIT_MICRO_LIFT_STABLE", "VERIFY_PHYSICAL_GRASP", "ATTACH_MOVEIT", "LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE",
    "DETACH_MOVEIT", "OPEN_GRIPPER", "WAIT_RELEASE_SETTLE", "VALIDATE_FINAL_PLACEMENT", "SYNC_WORLD_OBJECT", "RETREAT",
)

_FACT_ERRORS = (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError,
                IndexError)


def formal_coverage_ok(audit: Path) -> bool:
    """The coverage a formal seal requires, re-checked when the audit is read back."""

    return formal_coverage_failure(audit) is None


def formal_coverage_failure(audit: Path):
    """The first clause the audit does not cover ("T1" ... "T6", "EPOCHS"), or None when it covers all of them."""

    try:
        return _first_failure(Path(audit))
    except _FACT_ERRORS:
        return "UNREADABLE"


def _rows(audit: Path, name: str) -> list:
    return cached_lines(audit / name, _parse_audit_lines)


def _ns(seconds) -> int:
    return round(seconds * 1_000_000_000)


def _first_failure(audit: Path):
    events, references = _rows(audit, "events.jsonl"), _rows(audit, "references.jsonl")
    physics, bound = _rows(audit, "physics.jsonl"), _rows(audit, "row-bindings.jsonl")
    if not events or not references:
        return "T1"
    by_kind: dict = {}
    for row in events:
        by_kind.setdefault(row["kind"], []).append(row)
    try:
        lifecycle = _lifecycle(by_kind)
    except _FACT_ERRORS:
        lifecycle = None
    if lifecycle is None:
        return "T1"
    for clause, check, arguments in (
            ("T2", _boundaries_ok, (by_kind,)),
            ("T3", _physics_history_ok, (by_kind, lifecycle, bound)),
            ("T4", _scene_records_ok, (by_kind, lifecycle)),
            ("T5", _release_ok, (by_kind, lifecycle)),
            ("T6", _reference_ok, (references,)),
            ("EPOCHS", _epochs_ok, (audit, events, physics))):
        try:
            covered = check(*arguments)
        except _FACT_ERRORS:
            covered = False
        if not covered:
            return clause
    return None


def _boundaries_ok(by_kind: dict) -> bool:
    """T2: exactly the five collection boundaries, once each."""

    stages = sorted(row["payload"]["collection_boundary"]["stage"] for row in by_kind.get("collection_boundary", ()))
    return stages == sorted(COLLECTION_BOUNDARY_STAGES)


def _lifecycle(by_kind: dict):
    """T1: the Teacher's retained events as one whole lifecycle, or None."""

    from so101_demo.act.teacher_collection import (
        event_sequence_whole,
        first_command_clock,
        validate_event_summary,
    )

    summaries = by_kind.get("teacher_event_summary", ())
    if len(summaries) != 1:
        return None
    summary = validate_event_summary(summaries[0]["payload"]["event_summary"])
    documents = [row["payload"]["teacher_event"] for row in by_kind.get("teacher_event", ())]
    if not event_sequence_whole(summary, documents):
        return None
    types = [document["type"] for document in documents]
    if (len(types) < 7 or types[:2] != ["reset_complete", "teacher_start_observation"]
            or types[-3:] != ["normal_stop", "teacher_end_observation", "terminal"]):
        return None
    middle = documents[2:-3]
    begins, finishes = middle[0::2], middle[1::2]
    if (not begins or len(begins) != len(finishes)
            or any(document["type"] != "phase_begin" for document in begins)
            or any(document["type"] != "phase_finish" for document in finishes)):
        return None
    previous = None
    for begin, finish in zip(begins, finishes):
        if (begin["payload"]["state"] != finish["payload"]["state"]
                or finish["sim_time_ns"] < begin["sim_time_ns"]
                or (previous is not None and begin["sim_time_ns"] < previous)):
            return None
        previous = finish["sim_time_ns"]
    states = [document["payload"]["state"] for document in begins]
    terminal = documents[-1]
    completed = terminal["payload"].get("teacher_execution_status") == "COMPLETED"
    if completed and (states != list(TEACHER_STATES)
                      or any(document["payload"].get("status") != "SUCCEEDED" for document in finishes)):
        return None
    clocks = [first_command_clock(document) for document in begins]
    command = next((clock for clock in clocks if clock is not None), None)
    if command is None:
        return None
    return {"documents": documents, "begins": begins, "finishes": finishes, "states": states, "completed": completed,
            "first_command_ns": command["sim_time_ns"], "stop": documents[-3], "end": documents[-2]}


def _physics_history_ok(by_kind: dict, lifecycle: dict, bound: list) -> bool:
    """T3: no native step missing from the first command through the stop and the end observation, and a whole queue account."""

    chunks = by_kind.get("physics_chunk", ())
    queues = by_kind.get("recorder_queue", ())
    if not chunks or len(queues) != 1:
        return False
    evidence = queues[0]["payload"]["queue_evidence"]
    if evidence["accepted_samples"] != len(bound) or evidence["written_samples"] != len(bound):
        return False
    samples = [sample for row in chunks for sample in row["payload"]["raw_chunk"]["chunk"]["samples"]]
    steps = [sample["physics_step"] for sample in samples]
    if not steps or any(later != earlier + 1 for earlier, later in zip(steps, steps[1:])):
        return False
    first_ns, last_ns = _ns(samples[0]["simulation_time_s"]), _ns(samples[-1]["simulation_time_s"])
    if not first_ns <= lifecycle["first_command_ns"] <= last_ns:
        return False
    stop_step = lifecycle["stop"]["payload"]["proof"]["simulation_step"]
    if type(stop_step) is not int or not steps[0] <= stop_step <= steps[-1]:
        return False
    observation = lifecycle["end"]["payload"].get("observation")
    if isinstance(observation, dict):
        end_step = observation["simulation_step"]
        if type(end_step) is not int or not steps[0] <= end_step <= steps[-1]:
            return False
    return True


def _scene_records_ok(by_kind: dict, lifecycle: dict) -> bool:
    """T4: the alignments and the controller reference report the episode rests on."""

    associations = [(row, row["payload"]["association"]) for row in by_kind.get("source_alignment", ())]
    initial = [item for _row, item in associations if item["operation"] == "initial"]
    if len(initial) != 1 or len(by_kind.get("controller_reference", ())) != 1:
        return False
    if not any(item["operation"] == "world_sync"
               and item["query"]["record"]["response_ros_clock"]["sim_time_ns"] <= lifecycle["first_command_ns"]
               for _row, item in associations):
        return False
    if not lifecycle["completed"]:
        return True
    windows = _phase_windows(lifecycle)
    attach_begin, attach_finish = windows["ATTACH_MOVEIT"]
    detach_begin = windows["DETACH_MOVEIT"][0]
    retreat_begin = windows["RETREAT"][0]
    times = {operation: [_ns(row["sim_time_s"]) for row, item in associations if item["operation"] == operation]
             for operation in ("attach", "detach")}
    return (any(attach_begin <= time <= attach_finish for time in times["attach"])
            and any(detach_begin <= time <= retreat_begin for time in times["detach"]))


def _phase_windows(lifecycle: dict) -> dict:
    return {begin["payload"]["state"]: (begin["sim_time_ns"], finish["sim_time_ns"])
            for begin, finish in zip(lifecycle["begins"], lifecycle["finishes"])}


def _release_ok(by_kind: dict, lifecycle: dict) -> bool:
    """T5 (COMPLETED only): the release ran in order, and the MoveIt detach was applied before the gripper opened."""

    if not lifecycle["completed"]:
        return True
    order = ("DETACH_MOVEIT", "OPEN_GRIPPER", "WAIT_RELEASE_SETTLE")
    states = lifecycle["states"]
    indices = [states.index(state) for state in order]
    if indices != sorted(indices) or len(set(states)) != len(states):
        return False
    if any(lifecycle["finishes"][index]["payload"].get("status") != "SUCCEEDED" for index in indices):
        return False
    windows = _phase_windows(lifecycle)
    detach_begin, open_begin = windows["DETACH_MOVEIT"][0], windows["OPEN_GRIPPER"][0]
    return any(row["payload"]["association"]["operation"] == "detach"
               and detach_begin <= _ns(row["sim_time_s"]) <= open_begin
               for row in by_kind.get("source_alignment", ()))


def _reference_ok(references: list) -> bool:
    """T6: not merely that a reference was accepted, but that it carries one complete raw group - the legacy flat keys or the
    packed frames - so a bare projected reference is not coverage."""

    return any(row["accepted"] is True
               and (_REFERENCE_RAW_FIELDS <= set(row) or _REFERENCE_FRAME_FIELDS <= set(row))
               for row in references)


def _epochs_ok(audit: Path, events: list, physics: list) -> bool:
    """The physics rows a stream may still carry never go back an epoch, and every epoch a release entered is named by a release
    event. The declared initial epoch is exempt from transition naming. Vacuous for a Teacher stream, which has no such rows."""

    named_epochs = {row["payload"].get("release_epoch") for row in events if row["kind"] == "release"}
    epochs = [row["release_epoch"] for row in physics]
    # the declared initial epoch lives in the manifest once sealed, but at SEAL time that file does not exist yet and the
    # episode's own identity is what states it - so read whichever is present
    initial = None
    for name in ("audit-manifest.json", "episode.json"):
        try:
            document = json.loads((audit / name).read_bytes())
            # the manifest nests its identity under "identity"; episode.json IS the identity, so both shapes count
            initial = (document.get("identity") or document).get("release_epoch")
            if type(initial) is int:
                break
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
            continue
    if type(initial) is not int:
        initial = 0
    return not (any(type(epoch) is not int or (epoch > initial and epoch not in named_epochs) for epoch in epochs)
                or any(later < earlier for earlier, later in zip(epochs, epochs[1:])))
