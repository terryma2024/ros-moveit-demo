"""Closed ACT workload port for the existing fixed ParallelWorker lifecycle."""

from __future__ import annotations


class ActCollectionWorkload:
    """Delegate one authorized scenario while retaining Worker lease boundaries."""

    kind = "act_collection"

    def run_authorized(self, lease, *, runtime, broker, boundary,
                       start_event_id, start_event_type, reset_epoch):
        collect = getattr(runtime, "collect_authorized_scenario", None)
        if not callable(collect):
            raise RuntimeError("ACT_COLLECTION_RUNTIME_UNAVAILABLE")
        return boundary(lambda current: collect(
            current, broker=broker, boundary=boundary,
            start_event_id=start_event_id, start_event_type=start_event_type,
            reset_epoch=reset_epoch,
        ))


def training_eligible(record: dict) -> bool:
    """A record enters training only when it is a committed, clean, complete success.

    A business failure is retained as evidence but never exported, and a record whose coordinator has
    not committed is not yet a result — it is a run in progress.
    """

    # fail closed on a missing or malformed field: the plan's own boundary case passes a record that
    # carries neither `status` nor `coordinator_committed` and expects it to be ineligible, so an
    # incomplete record is refused rather than raising out of a gate on training data
    if not isinstance(record, dict):
        return False
    return (record.get("status") == "PASSED" and record.get("qc") == "PASS"
            and record.get("done") is True and record.get("interventions") == 0
            and record.get("coordinator_committed") is True)


SCENARIO_KEYS = frozenset({"scene_id", "split", "xy", "arm_q", "search_start_rad", "seed",
                           "config_sha256"})

# the plan's collection order: search through QC. The second half is deliberately not given a reset
# port, so a mid-scenario reset is impossible by construction rather than by a runtime check.
COLLECTION_PHASES = ("SEARCH", "LOCK", "STABLE", "RECORD", "TEACHER_INFERENCE", "EXPERT", "RELEASE",
                     "RETREAT", "FINAL_CHECK", "QC")


def prepare_scenario(scenario: dict, *, reset_port, joints_port) -> dict:
    """One reset, a seven-joint readback and a readiness proof, for a frozen scenario.

    The caller passes the result to `collect_authorized_scenario`; nothing else may reset.
    """

    if not isinstance(scenario, dict) or set(scenario) != SCENARIO_KEYS:
        raise ValueError("SCENARIO_INVALID")
    reset = reset_port.reset(scenario)
    if (not isinstance(reset, dict) or type(reset.get("reset_epoch")) is not int
            or reset["reset_epoch"] < 1 or reset.get("ready") is not True
            or not isinstance(reset.get("proof"), dict) or not reset["proof"]):
        raise ValueError("SCENARIO_RESET_UNPROVED")
    joints = joints_port.read()
    if (not isinstance(joints, (list, tuple)) or len(joints) != 7
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in joints)):
        raise ValueError("SEVEN_JOINT_READBACK_INVALID")
    return {"scene_id": scenario["scene_id"], "split": scenario["split"],
            "reset_epoch": reset["reset_epoch"], "joints": [float(value) for value in joints],
            "proof": dict(reset["proof"]),
            "scene_sha256": reset.get("scene_sha256")}


def collect_authorized_scenario(prepared: dict, scenario: dict, *, phase_port, recorder,
                                qc_port) -> dict:
    """Search through QC for an already-prepared scenario, with no second reset.

    A business failure is sealed as an immutable FAILED record; an infrastructure fault (recorder or
    persistence) is raised instead, because it must not be sealed as a business outcome.
    """

    if (not isinstance(prepared, dict) or prepared.get("scene_id") != scenario.get("scene_id")
            or prepared.get("split") != scenario.get("split")):
        raise ValueError("SCENARIO_NOT_PREPARED")
    observed = []
    for phase in COLLECTION_PHASES:
        if phase == "QC":
            break
        evidence = phase_port.run(phase, dict(prepared))
        if not isinstance(evidence, dict) or evidence.get("phase") != phase:
            raise ValueError("COLLECTION_PHASE_EVIDENCE_INVALID")
        if evidence.get("infra_fault"):
            raise RuntimeError("COLLECTION_INFRA_FAULT")
        observed.append(phase)
        recorder.append({"scene_id": scenario["scene_id"], "phase": phase,
                         "reset_epoch": prepared["reset_epoch"], "evidence": evidence})
    verdict = qc_port.verdict(dict(prepared), tuple(observed))
    if verdict not in ("PASS", "FAIL"):
        raise ValueError("QC_VERDICT_INVALID")
    return {"scene_id": scenario["scene_id"], "split": scenario["split"],
            "status": "PASSED" if verdict == "PASS" else "FAILED", "qc": verdict,
            "done": True, "interventions": 0, "coordinator_committed": True,
            "reset_epoch": prepared["reset_epoch"], "phases": list(observed)}
