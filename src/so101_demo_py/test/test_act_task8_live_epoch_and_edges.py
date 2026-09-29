"""P1-4 (rereview4): the release epoch must come from the phase, and the seal from the terminal identity.

The verdict's finding, verified in CP-1678: `PickPlaceSearchPhasePort._grid_sample` builds every sample's identity with
`"release_epoch": 0` **hardcoded**, while the port's own `_release_epoch_for(phase)` returns 1 for
RELEASE / RADIAL_RETREAT / FINAL_CHECK (`_RELEASE_EPOCH_AFTER`). So the port states one rule and stamps another. And
`seal_live_evidence` takes its identity from `_release_epoch_for("FINAL_CHECK")` - the computed terminal epoch - while
a completed chain *returns the artifact that already exists* instead of comparing it against that identity, so the
disagreement between the entries (0) and the seal (1) is never surfaced.

This file requires, at the port level and on the repo's own nine-phase fixture:
  1. each sample carries the epoch the port's OWN rule computes for its phase - a cross-epoch case, not a constant;
  2. sealing and reading back uses the ACTUAL terminal identity, and a sealed artifact whose entries disagree with it
     is refused by name rather than returned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_task8_sealed_raw_sources import _sealed  # noqa: E402

PRE_RELEASE = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN")
POST_RELEASE = ("RELEASE", "RADIAL_RETREAT", "FINAL_CHECK")


def test_each_sample_carries_the_epoch_the_ports_own_rule_gives_its_phase(tmp_path):
    """The port has `_release_epoch_for`; the samples must agree with it instead of a hardcoded 0."""

    index, _artifact = _sealed(tmp_path)
    seen = {entry["phase"]: entry["release_epoch"] for entry in index["samples"]}
    expected_after = 1
    for phase in POST_RELEASE:
        if phase in seen:
            assert seen[phase] == expected_after, (
                f"{phase} carries release_epoch={seen[phase]} while the port's own rule "
                f"(_RELEASE_EPOCH_AFTER) gives it {expected_after}")
    for phase in PRE_RELEASE:
        if phase in seen:
            assert seen[phase] == 0, f"{phase} precedes the release and carries {seen[phase]}"
    assert set(seen.values()) == {0, 1}, (
        f"a case that spans the release has samples in BOTH epochs; this one carries {sorted(set(seen.values()))}")


def test_the_sealed_identity_is_the_epoch_the_case_actually_ended_in(tmp_path):
    """Claim 2: the seal's identity must be the TERMINAL epoch the entries end in - not an initial 0.

    The port computes `_release_epoch_for("FINAL_CHECK")` for its seal while its samples carry 0, so the two only agree
    because both are wrong together. The rule CP-1612 chose is "non-decreasing, and the last entry is the identity", so
    this requires the identity to be the epoch the case really ended in - 1, once the case has passed its release.
    """

    index, _artifact = _sealed(tmp_path)
    terminal = index["samples"][-1]["release_epoch"]
    assert index["identity"]["release_epoch"] == terminal, (
        f"the seal says {index['identity']['release_epoch']} while the case ended in {terminal}")
    assert terminal == 1, (
        f"a case that has run RELEASE, RADIAL_RETREAT and FINAL_CHECK ended in epoch {terminal}, not 1")

    # The other side of the same rule - a recorder refusing an identity its entries do not end in - is already pinned
    # by test_act_task8_release_epoch_boundary (CP-1648), and asserting it here with an EMPTY recorder would raise
    # TASK8_LIVE_EVIDENCE_EMPTY first, i.e. pass or fail for a reason that is not this one.


def _bound_port(tmp_path):
    """A real port with a real window attached - the layer the verdict calls the source-acquisition layer."""

    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow, Task8LiveEvidenceRecorder
    from test_act_task8_search_port import SESSION, ATTEMPT, bind, fixture, request

    port, _events = fixture()
    # the case the fixture's request() describes: `scenario_id` is "prefix-01" in this suite, and a recorder
    # refuses a sample belonging to another case - correctly
    recorder = Task8LiveEvidenceRecorder(case_id="prefix-01", evidence_root=tmp_path,
                                         session_id=SESSION, attempt_id=ATTEMPT)
    window = LiveEvidenceWindow(recorder,
                                identity={"case_id": "prefix-01", "session_id": SESSION, "attempt_id": ATTEMPT,
                                          "reset_epoch": 2, "release_epoch": 0},
                                period_s=0.1, tolerance_s=0.01)
    # the boundary must be able to DERIVE the canonical fields, which is what the search-port suite's own
    # "records a canonical sample" test does; without it the phase refuses by name and never reaches the edge
    stamps = {name: 2.0 for name in ("world", "scene", "contact", "head", "wrist", "arm", "neck")}

    def canonical(captured, *, support_distance_max_m, raw_records):
        del captured, support_distance_max_m, raw_records
        return {"physics_step": 12, "sim_time_s": 2.0,
                # the phase's OWN sampled instants: three search iterations, which is what makes the frozen grid
                # more than one point inside a phase (P1-4's third finding)
                "search_result": {"found": True, "iterations": [{"index": index} for index in range(3)]},
                "source_stamps_s": dict(stamps),
                "source_received_monotonic_s": dict(stamps),
                "holding_state": "EMPTY", "cup_supported": True, "released": False,
                "placement_stable": False, "bilateral_contact": False, "no_fingertip_contact": True,
                "wrist_frame_valid": True, "wrist_target_visible": True,
                "cup_support_distance_m": 0.01, "end_effector_position_m": [0.0, 0.0, 0.1],
                "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
                "contact_observation_valid": True}

    port.boundary.canonical_evidence = canonical
    port.bind_live_evidence(window, support_distance_max_m=0.02, raw_records_root=tmp_path)
    bind(port)
    port.begin(request())
    # the phase's own instants, asked of the SAME boundary the port reads: the rule is "as many grid points as the
    # phase reports instants", not a number this test picks
    observed = port.boundary.search(request())
    iterations = (observed or {}).get("iterations") if isinstance(observed, dict) else None
    expected = len(iterations) if isinstance(iterations, list) and iterations else 1
    return port, window, request, expected


def _release_shaped_contact():
    """The same canonical fields with the CONTACT observation flipped - a contact edge, not a new grid point."""

    stamps = {name: 2.0 for name in ("world", "scene", "contact", "head", "wrist", "arm", "neck")}

    def canonical(captured, *, support_distance_max_m, raw_records):
        del captured, support_distance_max_m, raw_records
        return {"physics_step": 13, "sim_time_s": 2.1, "source_stamps_s": dict(stamps),
                "source_received_monotonic_s": dict(stamps),
                "holding_state": "EMPTY", "cup_supported": True, "released": False,
                "placement_stable": False, "bilateral_contact": True, "no_fingertip_contact": False,
                "wrist_frame_valid": True, "wrist_target_visible": True,
                "cup_support_distance_m": 0.01, "end_effector_position_m": [0.0, 0.0, 0.1],
                "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
                "contact_observation_valid": True}

    return canonical


def test_the_port_feeds_EDGE_events_beside_the_frozen_grid(tmp_path):
    """P1-4 claim 3: the port fed ONLY grid points, one per phase, and never called `add_event`.

    The verdict's words: *"implement frozen grid plus command/release/contact edge sampling at the source-acquisition
    layer"*. A single SEARCH is enough to see both halves of that: the run's own search iterations are the phase's
    sampled instants, so the grid carries more than one point, and the start of a phase is a COMMAND edge - recorded
    as an ADDITION, because the window's own rule says an event "can never stand in for a grid point". A case runs
    SEARCH once, so the contact and release edges are exercised by the nine-phase fixture instead.
    """

    port, window, request, expected = _bound_port(tmp_path)
    port.run_phase("SEARCH", request())

    assert window.grid_count == expected, (
        "the grid samples the phase at the frozen period, one point per instant the phase's own readback reports: "
        f"expected {expected}, got {window.grid_count}")
    assert window.event_count >= 1, (
        f"the phase's start is a COMMAND edge; the port fed only grid points, so event_count is {window.event_count}")
    assert "command" in window.event_reasons, (
        f"an edge says WHY it was recorded: {window.event_reasons}")
