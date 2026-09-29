"""The sealed artifact's RAW SOURCES: unique per capture, digest-consistent, and one release epoch.

These assertions exist because an independent review found - and this worktree reproduced (CP-1600) - that every one
of the nine-phase case's ten samples referenced the SAME seven raw files (`raw/<source>.json`), because the port names
each raw record by its source and opens it with O_TRUNC. A later phase therefore overwrote an earlier phase's evidence
while the earlier sample kept the digest of what IT had written, so the sealed artifact claimed ten phases of raw
evidence and could support none of them per phase.

The properties asserted here are the ones that make the artifact mean what it says:

* every source's raw record has a DIFFERENT path in every sample;
* every sample's recorded digest equals the bytes its own path holds NOW;
* the artifact's identity carries the same release epoch the case ended with.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_task8_nine_phase_case import SCENARIO, SESSION, ATTEMPT, _full_case_port  # noqa: E402
from test_dynamic_pick import _template  # noqa: E402

from so101_demo.act.pick_place_runner import PickPlaceRunner  # noqa: E402

SOURCES = ("world", "scene", "contact", "head", "wrist", "arm", "neck")


def _sealed(tmp_path):
    port, _calls, _boundary, _prefix = _full_case_port(tmp_path)
    port.bind_case_targets(gripper_closed_rad=0.2, close_duration_s=0.4,
                           motion_template=_template(), motion_duration_s=0.4)
    runner = PickPlaceRunner(port)
    result = runner.run({"mode": "full", "stop_after": None, "lifecycle": "FULL_RESTART",
                         "scenario_id": SCENARIO, "session_id": SESSION, "attempt_id": ATTEMPT,
                         "deadline_ns": runner.clock_ns() + 600_000_000_000})
    artifact = Path(result["live_evidence_artifact"]["path"])
    return json.loads(artifact.read_bytes()), artifact


def test_every_sample_names_its_own_raw_sources(tmp_path):
    """A constant name per source means one phase overwrites another's evidence."""

    index, artifact = _sealed(tmp_path)
    per_source = {name: [] for name in SOURCES}
    for entry in index["samples"]:
        record = json.loads((artifact.parent / entry["relative_path"]).read_bytes())
        for name in SOURCES:
            per_source[name].append((record["raw_records"][name])["relative_path"])

    duplicates = {name: paths for name, paths in per_source.items() if len(set(paths)) != len(paths)}
    assert not duplicates, (
        "each capture must name its own raw record: "
        + ", ".join(f"{name} has {len(set(paths))} distinct path(s) for {len(paths)} samples"
                    for name, paths in duplicates.items()))


def test_every_samples_recorded_digest_still_matches_the_bytes_it_names(tmp_path):
    """A sample that keeps the digest of what it wrote is not evidence if the file has since changed."""

    index, artifact = _sealed(tmp_path)
    stale = []
    for entry in index["samples"]:
        record = json.loads((artifact.parent / entry["relative_path"]).read_bytes())
        for name in SOURCES:
            reference = record["raw_records"][name]
            payload = (artifact.parent / reference["relative_path"]).read_bytes()
            if hashlib.sha256(payload).hexdigest() != reference["sha256"]:
                stale.append(f"{entry['phase']}:{name}")
    assert not stale, f"raw records that no longer match the digest their sample recorded: {stale}"


def test_the_sealed_identity_carries_the_epoch_the_case_ended_with(tmp_path):
    """RELEASE and FINAL_CHECK are stamped with the incremented epoch; the artifact must not say otherwise."""

    index, _artifact = _sealed(tmp_path)
    # the owner's rule (CP-1612): entries are NON-DECREASING and the LAST equals the identity, because a case
    # legitimately captures its pre-release phases in epoch 0 and the rest in epoch 1
    epochs = [entry["release_epoch"] for entry in index["samples"]]
    assert epochs == sorted(epochs), f"the release epochs must not go backwards: {epochs}"
    assert epochs[-1] == index["identity"]["release_epoch"], (
        f"the last sample carries {epochs[-1]} while the identity says {index['identity']['release_epoch']}")
    assert set(epochs) <= {0, index["identity"]["release_epoch"]}, sorted(set(epochs))
    assert index["identity"]["release_epoch"] >= 1, (
        "a case that ends after FINAL_CHECK has passed its release, so the epoch cannot still be 0")
