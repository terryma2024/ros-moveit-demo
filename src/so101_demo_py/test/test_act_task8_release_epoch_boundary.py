"""A case's samples legitimately span the release boundary; the seal must accept that.

The recorder's seal used to require EVERY entry's `release_epoch` to EQUAL the identity's. But the epoch is created at
the release: the phases before RELEASE are captured under epoch 0 and the phases after it under epoch 1, so a case with
ten samples has entries in two epochs - truthfully. The rule therefore has to be "entries are non-decreasing in release
epoch, and the last entry equals the identity", which is what the owner chose (CP-1612).

What the rule must still refuse is unchanged: a sequence that goes BACKWARDS, and a last entry that disagrees with the
identity that seals it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_task8_live_evidence import sample  # noqa: E402

from so101_demo.act.task8_live_evidence import Task8LiveEvidenceRecorder  # noqa: E402

PRE_RELEASE = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN")
POST_RELEASE = ("RELEASE", "RADIAL_RETREAT", "FINAL_CHECK")


def _recorder(root: Path) -> Task8LiveEvidenceRecorder:
    return Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=root,
                                     session_id="session-1", attempt_id="attempt-1")


def test_entries_spanning_the_release_boundary_seal_with_the_final_epoch(tmp_path):
    """The honest shape of a real case: six samples in epoch 0, three in epoch 1, sealed as epoch 1."""

    root = tmp_path / "evidence"
    root.mkdir()
    recorder = _recorder(root)
    step = 0
    for phase in PRE_RELEASE:
        recorder.append(sample(root, step=step, phase=phase, release_epoch=0))
        step += 1
    for phase in POST_RELEASE:
        recorder.append(sample(root, step=step, phase=phase, release_epoch=1))
        step += 1
    published = recorder.seal({"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
                               "reset_epoch": 4, "release_epoch": 1})
    # `seal` hands back {"path": ...}; the index itself is the file it names, so read it and check that it kept every
    # entry in the epoch each was captured in
    assert {"path", "sha256", "schema_version"} <= set(published), published
    index = json.loads(Path(published["path"]).read_bytes())
    assert index["sample_count"] == len(index["samples"]) == 9
    assert [entry["release_epoch"] for entry in index["samples"]] == [0] * 6 + [1] * 3


def test_entries_that_go_backwards_in_the_release_epoch_are_still_refused(tmp_path):
    """The relaxation must not become an absence of the rule: a decreasing sequence is wrong however it ends."""

    root = tmp_path / "evidence"
    root.mkdir()
    recorder = _recorder(root)
    recorder.append(sample(root, step=0, phase="SEARCH", release_epoch=1))
    recorder.append(sample(root, step=1, phase="CLOSE", release_epoch=0))
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_EPOCH_MISMATCH"):
        recorder.seal({"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
                       "reset_epoch": 4, "release_epoch": 1})


def test_a_last_entry_that_disagrees_with_the_sealing_identity_is_refused(tmp_path):
    """And the identity's own epoch must still be the one the case ended in."""

    root = tmp_path / "evidence"
    root.mkdir()
    recorder = _recorder(root)
    recorder.append(sample(root, step=0, phase="SEARCH", release_epoch=0))
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_EPOCH_MISMATCH"):
        recorder.seal({"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
                       "reset_epoch": 4, "release_epoch": 3})
