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


def prepare_scenario(scenario: dict, *, reset_port, joints_port, ledger=None,
                     attempt_id=None) -> dict:
    """One reset, a seven-joint readback and a readiness proof, for a frozen scenario.

    The caller passes the result to `collect_authorized_scenario`; nothing else may reset.
    """

    if not isinstance(scenario, dict) or set(scenario) != SCENARIO_KEYS:
        raise ValueError("SCENARIO_INVALID")
    if ledger is not None:
        if ledger.terminal(scenario["scene_id"]) is not None:
            raise ValueError("SCENE_TERMINAL_STATE_IMMUTABLE")
        # noted BEFORE the port is asked, so a retry after a failed reset is refused too
        ledger.note_reset(attempt_id if attempt_id is not None else scenario["scene_id"])
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
                                qc_port, ledger=None) -> dict:
    """Search through QC for an already-prepared scenario, with no second reset.

    A business failure is sealed as an immutable FAILED record; an infrastructure fault (recorder or
    persistence) is raised instead, because it must not be sealed as a business outcome.
    """

    if (not isinstance(prepared, dict) or prepared.get("scene_id") != scenario.get("scene_id")
            or prepared.get("split") != scenario.get("split")):
        raise ValueError("SCENARIO_NOT_PREPARED")
    if ledger is not None and ledger.terminal(scenario["scene_id"]) is not None:
        raise ValueError("SCENE_TERMINAL_STATE_IMMUTABLE")
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
    record = {"scene_id": scenario["scene_id"], "split": scenario["split"],
              "status": "PASSED" if verdict == "PASS" else "FAILED", "qc": verdict,
              "done": True, "interventions": 0, "coordinator_committed": True,
              "reset_epoch": prepared["reset_epoch"], "phases": list(observed)}
    if ledger is not None:
        ledger.seal(scenario["scene_id"], record)
    return record


COLLECTION_PAYLOAD_KEYS = frozenset({
    "campaign_id", "backend", "manifest_path", "manifest_sha256", "calibration_report_path",
    "calibration_report_sha256", "policy_path", "policy_sha256", "activation_receipt_path",
    "activation_receipt_sha256", "evidence_root", "qualification_mode", "limit",
})

# the two Rollout sets never receive expert labels, and qualification scenes never enter training
_TRAINING_SPLITS = ("train", "validation", "offline_test")
_QUALIFICATION_SETS = ("functional", "load")


def _file_digest(path) -> str:
    import hashlib
    from pathlib import Path as _Path

    target = _Path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError("COLLECTION_INPUT_UNREADABLE")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def build_collection_payload(*, campaign_id: str, manifest_path, calibration_report, policy,
                             activation_receipt, evidence_root, qualification_mode: bool,
                             limit: int) -> dict:
    """The closed payload the W1 CLI hands to the unified service.

    Every referenced artifact is digested here, so the spec carries evidence rather than paths alone;
    nothing about the service's own epoch or binding is invented.
    """

    from pathlib import Path as _Path

    if type(qualification_mode) is not bool:
        raise ValueError("COLLECTION_QUALIFICATION_MODE_INVALID")
    if type(limit) is not int or limit < 1:
        raise ValueError("COLLECTION_LIMIT_INVALID")
    if not isinstance(campaign_id, str) or not campaign_id:
        raise ValueError("COLLECTION_CAMPAIGN_INVALID")
    root = _Path(evidence_root)
    if not root.is_absolute() or ".." in root.parts or not root.is_dir() or root.is_symlink():
        raise ValueError("COLLECTION_EVIDENCE_ROOT_INVALID")
    return {"campaign_id": campaign_id, "backend": "mujoco",
            "manifest_path": str(manifest_path), "manifest_sha256": _file_digest(manifest_path),
            "calibration_report_path": str(calibration_report),
            "calibration_report_sha256": _file_digest(calibration_report),
            "policy_path": str(policy), "policy_sha256": _file_digest(policy),
            "activation_receipt_path": str(activation_receipt),
            "activation_receipt_sha256": _file_digest(activation_receipt),
            "evidence_root": str(root), "qualification_mode": qualification_mode, "limit": limit}


def require_collection_selection(manifest: dict, *, qualification_mode: bool) -> list:
    """The scene ids a run may collect, refusing the sets the plan excludes.

    Formal mode collects Train/Validation/Offline Test only; qualification mode accepts the 8 functional
    and 40 sustained-load scenes only. Neither mode accepts a Rollout set, because those must never
    receive expert labels, and qualification scenes must never enter the training manifest.
    """

    if type(qualification_mode) is not bool:
        raise ValueError("COLLECTION_QUALIFICATION_MODE_INVALID")
    scenarios = manifest.get("scenarios") if isinstance(manifest, dict) else None
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("COLLECTION_MANIFEST_INVALID")
    allowed = _QUALIFICATION_SETS if qualification_mode else _TRAINING_SPLITS
    selected, seen_splits = [], set()
    for row in scenarios:
        if not isinstance(row, dict) or not isinstance(row.get("split"), str):
            raise ValueError("COLLECTION_MANIFEST_INVALID")
        split = row["split"]
        if split in ("rollout_validation", "rollout_test"):
            # the Rollout sets legitimately live in the split manifest but never receive expert labels,
            # so they are excluded from the selection rather than making the manifest unusable
            continue
        seen_splits.add(split)
        if split in allowed:
            selected.append(row["scene_id"])
    if not selected:
        raise ValueError("COLLECTION_SELECTION_EMPTY")
    return selected


class AttemptLedger:
    """One reset per attempt, and a terminal scene result nothing may overwrite.

    The ledger is bookkeeping the caller owns across a run: it is what turns "the plan says a scenario
    resets once" into something a second caller cannot violate.
    """

    def __init__(self) -> None:
        self._resets: dict = {}
        self._terminal: dict = {}

    def note_reset(self, attempt_id: str) -> None:
        if attempt_id in self._resets:
            raise ValueError("SCENARIO_RESET_ALREADY_PERFORMED")
        self._resets[attempt_id] = True

    def seal(self, scene_id: str, record: dict) -> None:
        if scene_id in self._terminal:
            raise ValueError("SCENE_TERMINAL_STATE_IMMUTABLE")
        self._terminal[scene_id] = dict(record)

    def terminal(self, scene_id: str):
        return self._terminal.get(scene_id)
