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
