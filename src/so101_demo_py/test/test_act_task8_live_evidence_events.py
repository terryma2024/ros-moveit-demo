"""P1-4 (rereview 5): a sealed event must say WHICH edge it was, and the evidence must describe its own grid.

The finding, read in CP-1803: `add_event(sample, reason)` validates the reason and then keeps it in
`self._event_reasons` - the live window's own state - while `_SAMPLE_KEYS` (24 keys) has no `kind` and no `reason`.
So a reader of the SEALED evidence cannot tell what a given event sample was, and `event_reasons` is a property of an
object rather than of what was published. The second check is the packet's proposal 1: the sealed document records
`sample_count` but not the grid's own edges, so a reader has to recompute them from the samples.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402

from so101_demo.act.task8_live_evidence import LiveEvidenceWindow, Task8LiveEvidenceRecorder  # noqa: E402

IDENTITY = {"case_id": "case-1", "session_id": "session-1", "attempt_id": "attempt-1",
            "reset_epoch": 0, "release_epoch": 0}
PERIOD_S = 0.1


#: the sampler's own seven sources (`task8_live_evidence._SOURCES`), so a fixture cannot quietly use one
SOURCES = ("world", "scene", "contact", "head", "wrist", "arm", "neck")


def _raw_records(root: Path, index: int) -> dict:
    """Seven real raw files with their real digests - the shape the recorder validates."""

    import hashlib

    records = {}
    for name in SOURCES:
        # the recorder resolves `relative_path` UNDER the evidence root and refuses an absolute one, so the fixture
        # writes inside the root and names the file relatively - the same rule production samples follow
        path = root / f"raw-{name}-{index}.json"
        path.write_bytes(json.dumps({"source": name, "index": index}).encode())
        records[name] = {"relative_path": path.name,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return records


def _sample(index: int, phase: str = "SEARCH", *, root: Path) -> dict:
    return {
        "case_id": "case-1", "session_id": "session-1", "attempt_id": "attempt-1",
        "reset_epoch": 0, "release_epoch": 0, "physics_step": index,
        "sim_time_s": index * PERIOD_S, "phase": phase,
        "source_stamps_s": {name: index * PERIOD_S for name in SOURCES},
        "source_received_monotonic_s": {name: index * PERIOD_S for name in SOURCES},
        "raw_records": _raw_records(root, index), "holding_state": "APPROACH",
        "wrist_frame_valid": True, "wrist_target_visible": True, "contact_observation_valid": True,
        "bilateral_contact": False, "no_fingertip_contact": True, "cup_supported": False,
        "released": False, "placement_stable": False, "cup_support_distance_m": 0.0,
        "end_effector_position_m": [0.0, 0.0, 0.0], "cup_position_m": [0.0, 0.0, 0.0],
        "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
    }


def _sealed(tmp_path) -> dict:
    recorder = Task8LiveEvidenceRecorder(case_id="case-1", evidence_root=tmp_path,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=IDENTITY, period_s=PERIOD_S)
    window.bind_reset_epoch(0)
    # every REQUIRED_PHASE, because the window refuses to seal without them - the fixture follows the production
    # contract rather than the subset that would have made the test shorter
    phases = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE",
              "RADIAL_RETREAT", "FINAL_CHECK")
    for index, phase in enumerate(phases):
        window.add_grid(_sample(index, phase, root=tmp_path))
    for offset, reason, phase in ((len(phases), "command", "CLOSE"),
                                  (len(phases) + 1, "contact", "CLOSE"),
                                  (len(phases) + 2, "release", "RELEASE")):
        window.add_event(_sample(offset, phase, root=tmp_path), reason=reason)
    window.seal()
    return json.loads((tmp_path / "case-1-live-evidence.json").read_bytes())


def test_a_sealed_event_still_says_which_edge_it_was(tmp_path):
    """The reason must travel WITH the sample, not in an object that stops existing when the run does."""

    sealed = _sealed(tmp_path)
    events = [sample for sample in sealed["samples"] if sample.get("kind") == "event"]
    assert len(events) == 3, (
        "the sealed evidence distinguishes event samples from grid samples: "
        f"{sorted({sample.get('kind') for sample in sealed['samples']})}")
    reasons = [sample.get("reason") for sample in events]
    assert reasons == ["command", "contact", "release"], (
        f"each sealed event names the reason it was appended with, in order: {reasons}")


def test_the_sealed_evidence_describes_its_own_grid(tmp_path):
    """Proposal 1: a reader should learn the grid's edges and count from the document, not by recomputing them."""

    sealed = _sealed(tmp_path)
    grid = [sample for sample in sealed["samples"] if sample.get("kind") == "grid"]
    assert len(grid) == 9, "the grid samples are identified as such (every required phase)"
    description = sealed.get("grid")
    assert isinstance(description, dict), (
        f"the sealed document describes its grid: {sorted(sealed)}")
    assert description.get("count") == len(grid)
    times = [sample["sim_time_s"] for sample in grid]
    assert description.get("first_sim_time_s") == pytest.approx(min(times))
    assert description.get("last_sim_time_s") == pytest.approx(max(times))
    assert description.get("period_s") == pytest.approx(PERIOD_S)


def test_the_grid_still_refuses_a_gap_duplicate_or_regression(tmp_path):
    """The discipline that already exists must survive the change - recorded so it cannot be traded away."""

    recorder = Task8LiveEvidenceRecorder(case_id="case-1", evidence_root=tmp_path,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=IDENTITY, period_s=PERIOD_S)
    window.bind_reset_epoch(0)
    window.add_grid(_sample(0, root=tmp_path))
    with pytest.raises(ValueError):
        window.add_grid(_sample(0, root=tmp_path))     # duplicate
    with pytest.raises(ValueError):
        window.add_grid(_sample(2, root=tmp_path))     # gap of two periods
    with pytest.raises(ValueError):
        window.add_grid(_sample(-1, root=tmp_path))    # backwards
