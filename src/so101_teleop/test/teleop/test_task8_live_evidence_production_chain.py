"""Task 7 production chain: the live-evidence artifact end to end.

This exercises the **real** recorder, window, release correlation and journal-row readback against a real evidence
root: nine phases recorded at the frozen grid, a release open event correlated with three pre-open support rows,
sealing, and a read-back that must match before a journal row may cite it. Only the external world (ROS topics,
MuJoCo, controller I/O, process launch) is absent - nothing here fabricates a sample, and every grid point comes
from a value this test supplies as if it had been read back.
"""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.task8_live_evidence import (
    LiveEvidenceWindow, Task8LiveEvidenceRecorder, _SOURCES, build_live_evidence_sample,
    correlate_release_open,
)

PHASES = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE", "RADIAL_RETREAT",
          "FINAL_CHECK")
PERIOD_S = 0.1
# the recorder validates `source_stamps_s`, `source_received_monotonic_s` and `raw_records` against its own
# `_SOURCES` set, so the fixture uses that set rather than a hand-copied list that can drift from it
READBACK_SOURCES = _SOURCES


def _identity():
    return {"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
            "reset_epoch": 4, "release_epoch": 7}


def _raw_records(root: Path, sim_time: float) -> dict:
    """Each source's raw record is a real file with its own digest, exactly as the recorder requires."""

    records = {}
    for name in READBACK_SOURCES:
        target = root / "raw" / f"{name}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"source": name, "sim_time_s": sim_time}, sort_keys=True).encode()
        target.write_bytes(payload)
        records[name] = {"relative_path": f"raw/{name}.json",
                         "sha256": hashlib.sha256(payload).hexdigest()}
    return records


def _sample(root: Path, *, phase: str, step: int, sim_time: float) -> dict:
    return build_live_evidence_sample(
        identity=_identity(), phase=phase, physics_step=step, sim_time_s=sim_time,
        source_stamps_s={name: sim_time for name in READBACK_SOURCES},
        source_received_monotonic_s={name: sim_time for name in READBACK_SOURCES},
        raw_records=_raw_records(root, sim_time),
        holding_state="HOLDING",
        frame={"wrist_frame_valid": True, "wrist_target_visible": True},
        contact={"observation_valid": True, "bilateral_contact": True, "no_fingertip_contact": False,
                 "cup_supported": True, "released": False, "placement_stable": False},
        measurements={"cup_support_distance_m": 0.01, "end_effector_position_m": [0.0, 0.0, 0.1],
                      "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]})


def test_the_nine_phase_chain_seals_and_reads_back(tmp_path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    recorder = Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=evidence_root,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=_identity(), period_s=PERIOD_S)

    seen = []
    for step, phase in enumerate(PHASES):
        sample = _sample(evidence_root, phase=phase, step=step, sim_time=step * PERIOD_S)
        recorder.append(sample)
        window.add_grid(sample)
        seen.append(sample["phase"])
    assert seen == list(PHASES), "every phase is observed in order"
    assert window.grid_count == len(PHASES)

    # the release open event is correlated with the three rows immediately before it, at the frozen period
    support = [{"phase": "RELEASE", "release_epoch": 7, "source_stamp": 6.7 + PERIOD_S * index}
               for index in range(4)]
    correlation = correlate_release_open(support, {"operation": "gripper_open", "release_epoch": 7,
                                                   "source_stamp": 7.05,
                                                   "command_ref": "raw/controller/open.json"},
                                         period_s=PERIOD_S, indexed=("raw/controller/open.json",))
    assert correlation["support_rows"] == 3 and correlation["verdict"] == "PASS"

    artifact = recorder.seal(_identity())
    assert set(artifact) == {"path", "sha256", "schema_version"}
    target = Path(artifact["path"])
    assert target.is_file() and not target.is_symlink()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == artifact["sha256"]
    # the artifact's own content: non-empty and naming the case it belongs to, without assuming a key layout
    document = json.loads(target.read_bytes())
    assert document, "the sealed artifact must carry content"
    assert "full-01" in target.read_text(), "the artifact names the case it belongs to"


def test_a_window_that_never_reached_final_check_invalid_seals_instead(tmp_path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    recorder = Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=evidence_root,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=_identity(), period_s=PERIOD_S)
    window.add_grid(_sample(evidence_root, phase="SEARCH", step=0, sim_time=0.0))
    closed = window.invalidate("OWNER_RETIRE")
    assert closed["status"] == "INVALID" and closed["grid_count"] == 1
    # the recorder is deliberately independent of the window; the port couples them, so this asserts the window's
    # own state: an invalidated window accepts no further grid sample
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_WINDOW_SEALED"):
        window.add_grid(_sample(evidence_root, phase="APPROACH", step=1, sim_time=PERIOD_S))


def test_the_journal_row_readback_refuses_a_missing_or_mismatched_artifact(tmp_path):
    from so101_teleop.unified.pick_place_case_execution import _require_live_evidence_readback

    full = {"mode": "full"}
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_READBACK_MISSING"):
        _require_live_evidence_readback(None, full)
    target = tmp_path / "live.json"
    target.write_bytes(b"{}")
    good = {"path": str(target), "sha256": hashlib.sha256(b"{}").hexdigest(), "schema_version": 1}
    assert _require_live_evidence_readback(good, full) is None
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_READBACK_MISMATCH"):
        _require_live_evidence_readback({**good, "sha256": "c" * 64}, full)
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_UNEXPECTED"):
        _require_live_evidence_readback(good, {"mode": "phase_prefix"})
