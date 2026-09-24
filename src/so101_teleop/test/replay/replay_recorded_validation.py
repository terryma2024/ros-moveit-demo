"""Explicit, read-only replay of the recorded production validation batches.

This is not part of the ordinary gate and deliberately not named ``test_*.py``: the ordinary pytest
walk (``src/so101_teleop/test/**/test_*.py``) and the CTest registration contract both ignore it,
and it is not registered in ``CMakeLists.txt``. Run it by hand when the recordings are available:

    python -m pytest src/so101_teleop/test/replay/replay_recorded_validation.py -q

Every case here replays bytes that a *live* macOS campaign really wrote, which is the one thing no
synthetic fixture can prove: that the installed reader accepts the raw recording, that the receipt a
recorded store carries is the frame of that batch's own committed cleanup event, and that the
per-point documents match the results the journal committed. The ordinary gate asserts the same
behaviour over deterministic bytes in
``test/teleop/test_expert_validation_campaign_layout_projection.py``; this module is the historical
counterpart, never the only test of any behaviour.

Each recording root is read from the environment, with the recorded default path as the fallback:

* ``SO101_TASK12_CLEANUP_STATE`` - the state root of the recorded W1 first pass ``bf16a``;
* ``SO101_TASK12_RETRY_STATE``   - the state root of the recorded retry closed loop;
* ``SO101_TASK12_REAL_BATCH``    - the recorded live batch root of campaign ``cand-w2-…``.

Nothing here writes into a recording. The readers are read-only by construction - no store and no
service is composed - and each case fingerprints the tree before and after its own read, so a read
path that ever writes a byte fails the case instead of going unnoticed. A root that is absent is
reported as ``not run: recording absent`` rather than silently passing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

#: The recorded macOS run this task's evidence refers to, and the state roots inside it.
RECORDED_RUN = Path(
    "/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1"
)

CLEANUP_STATE = Path(os.environ.get(
    "SO101_TASK12_CLEANUP_STATE", RECORDED_RUN / "task12/service-runs/retryafterfix/state",
))
CLEANUP_CAMPAIGN_ID = "campaign-4d9af7fca30f49939f952db367338454"
CLEANUP_BATCH_ID = "bf16a"
CLEANUP_POINT_ID = "sample_05_near_center"
#: The durable receipt the recorded store carries for ``bf16a``: the frame hash of that batch's own
#: committed ``CLEANUP_COMMITTED`` event, which is what the replay re-derives from the bytes.
CLEANUP_RECEIPT = "f43880c1f5afea5fdcf28bd8ab56218a7200df7e714134c495ebd0e11a5b0e86"
CLEANUP_SELECTION_SIZE = 20

RETRY_STATE = Path(os.environ.get(
    "SO101_TASK12_RETRY_STATE", RECORDED_RUN / "task12/service-runs/retrycl/state",
))
RETRY_CAMPAIGN_ID = "campaign-e94a4b7470644a59a3cf921ce6e64444"
RETRY_FIRST_PASS_ID = "bca3f"
RETRY_BATCH_ID = "retry-001"
RETRY_POINT_ID = "sample_05_near_center"
#: The campaign's own catalog digest; both bindings name it, each in its own vocabulary.
RETRY_CATALOG_SHA256 = "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"
RETRY_FIRST_PASS_POINTS = 15
RETRY_FIRST_PASS_RECEIPT = "9def6124ebdeaded52534b85617bc60f76db7216c51d78b8095fc3a74285a6e4"

REAL_BATCH = Path(os.environ.get(
    "SO101_TASK12_REAL_BATCH", RECORDED_RUN / "task11/after-fix/w2-20260922T011804Z/batch",
))
REAL_BATCH_ID = "w2-b001"
REAL_BATCH_CAMPAIGN_ID = "cand-w2-20260922T011804Z"
REAL_BATCH_POINT_IDS = (
    "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm", "sample_07_mid_center",
    "sample_12_far_left", "sample_16_far_right", "task_start",
)


def _recording(root: Path, *, variable: str, what: str) -> Path:
    """The recording root, or a clear refusal - a missing recording is never a passing case."""

    if not root.is_dir():
        pytest.skip(f"not run: recording absent at {root} ({what}; set {variable})")
    return root


def _tree_fingerprint(root: Path) -> tuple:
    """Every recorded file's path, size and mtime: a read path may not write one of them."""

    return tuple(sorted(
        (str(path.relative_to(root)), path.stat().st_size, path.stat().st_mtime_ns)
        for path in Path(root).rglob("*") if path.is_file()
    ))


def _batch_root(state_root: Path, campaign_id: str, batch_id: str) -> Path:
    return state_root / "campaigns" / campaign_id / batch_id


def _journal_final_frame_sha256(batch_root: Path, batch_id: str) -> str:
    """The verified frame hash of the batch's own last committed event, read independently."""

    from so101_demo.parallel_batch.journal import CoordinatorJournal

    replay = CoordinatorJournal.read_only_replay(Path(batch_root) / "journal", batch_id)
    assert replay.events, "the recorded batch published no committed event at all"
    final = replay.events[-1]
    assert final.type == "CLEANUP_COMMITTED", final.type
    return final.frame_sha256


def _upstream_binding(batch_root: Path, batch_id: str, campaign_id: str):
    from so101_teleop.expert_validation.coordinator_events import CampaignUpstreamBinding
    from so101_teleop.expert_validation.journal_layout import (
        CAMPAIGN_LAYOUT,
        resolve_fixed_journal_layout,
    )

    layout = resolve_fixed_journal_layout(Path(batch_root), batch_id)
    assert layout.layout == CAMPAIGN_LAYOUT
    return CampaignUpstreamBinding(
        campaign_id=campaign_id, batch_id=batch_id, owner_kind="COORDINATOR",
        owner_epoch_or_generation=layout.epoch, journal_root=layout.journal_root,
        batch_root=layout.batch_root,
    )


def _read_batch(batch_root: Path, batch_id: str, campaign_id: str):
    from so101_teleop.expert_validation.campaign_layout import CampaignLayoutReader
    from so101_teleop.expert_validation.coordinator_events import (
        AcceptedCoordinatorCursor,
        ReadOnlyCoordinatorJournal,
    )

    binding = _upstream_binding(batch_root, batch_id, campaign_id)
    return CampaignLayoutReader(
        ReadOnlyCoordinatorJournal(binding.journal_root, batch_id), binding
    ).read_after(AcceptedCoordinatorCursor.initial(binding))


def test_the_recorded_w1_first_pass_carries_the_receipt_its_console_retry_needed():
    """The recorded 409's first pass: terminal-clean bytes, a genuine ``FAILED`` point, one receipt.

    The recorded store carried the receipt ``f43880c1…`` for ``bf16a`` while the durable column
    was NULL, the state the console's same-page retry was refused in. The re-derived frame hash
    of the batch's own committed cleanup event is that same receipt, and the recorded evidence root
    is read-only here, which the fingerprint check at the end proves.
    """

    from so101_teleop.expert_validation.campaign_layout import read_selection_binding

    state_root = _recording(
        CLEANUP_STATE, variable="SO101_TASK12_CLEANUP_STATE",
        what="the recorded W1 first pass retryafterfix/state",
    )
    batch_root = _batch_root(state_root, CLEANUP_CAMPAIGN_ID, CLEANUP_BATCH_ID)
    _recording(batch_root, variable="SO101_TASK12_CLEANUP_STATE",
               what=f"the recorded batch {CLEANUP_BATCH_ID}")
    before = _tree_fingerprint(batch_root)

    binding = _upstream_binding(batch_root, CLEANUP_BATCH_ID, CLEANUP_CAMPAIGN_ID)
    recorded = _read_batch(batch_root, CLEANUP_BATCH_ID, CLEANUP_CAMPAIGN_ID)
    projected = recorded.projected_state
    assert projected["terminal_reason"] == "POINTS_COMPLETE"
    assert projected["batch_cleanup_complete"] is True
    assert projected["points"][CLEANUP_POINT_ID]["status"] == "FAILED"
    assert recorded.events[-1].type == "CLEANUP_COMMITTED"
    assert recorded.events[-1].frame_sha256 == CLEANUP_RECEIPT, (
        "the receipt the recorded store carries is not this batch's own cleanup frame"
    )
    assert _journal_final_frame_sha256(batch_root, CLEANUP_BATCH_ID) == CLEANUP_RECEIPT

    selection = read_selection_binding(binding)
    assert selection["kind"] == "FIRST_PASS"
    point_ids = tuple(selection["selected_point_ids"])
    assert len(point_ids) == CLEANUP_SELECTION_SIZE
    assert CLEANUP_POINT_ID in point_ids
    assert _tree_fingerprint(batch_root) == before, "the recorded batch bytes were written to"


def test_the_recorded_retry_closed_loop_is_read_in_its_own_binding_vocabulary():
    """RED: ``read_selection_binding`` refused these bytes with ``CAMPAIGN_FIELD_INVALID``.

    The retry composition writes the same selection in its own vocabulary - the catalog it was
    selected from named ``original_catalog_sha256``, the one point it executes named ``point`` - and
    the batch's own bytes show complete cleanup. The readback below is the exact call that answered
    ``409 {"code": "CAMPAIGN_FIELD_INVALID:catalog_sha256"}``.
    """

    from so101_teleop.expert_validation.campaign_layout import read_selection_binding
    from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor

    state_root = _recording(
        RETRY_STATE, variable="SO101_TASK12_RETRY_STATE",
        what="the recorded retry closed loop retrycl/state",
    )
    batch_root = _batch_root(state_root, RETRY_CAMPAIGN_ID, RETRY_BATCH_ID)
    _recording(batch_root, variable="SO101_TASK12_RETRY_STATE",
               what=f"the recorded retry batch {RETRY_BATCH_ID}")
    before = _tree_fingerprint(batch_root)

    binding = _upstream_binding(batch_root, RETRY_BATCH_ID, RETRY_CAMPAIGN_ID)
    selection = read_selection_binding(binding)
    assert selection["kind"] == "FULL_RESTART_RETRY"
    assert selection["original_catalog_sha256"] == RETRY_CATALOG_SHA256
    assert "catalog_sha256" not in selection
    assert selection["point"]["point_id"] == RETRY_POINT_ID
    assert "selected_point_ids" not in selection

    recorded = _read_batch(batch_root, RETRY_BATCH_ID, RETRY_CAMPAIGN_ID)
    state = recorded.projected_state
    assert state["terminal_reason"] == "POINTS_COMPLETE"
    assert state["batch_cleanup_complete"] is True
    assert sorted(state["points"]) == [RETRY_POINT_ID]
    assert state["points"][RETRY_POINT_ID]["status"] == "FAILED"
    assert recorded.events[-1].type == "CLEANUP_COMMITTED"

    # The receipt a successful readback commits is the batch's own committed cleanup frame.
    receipt = ExpertValidationSupervisor._verify_retry_journal(
        object.__new__(ExpertValidationSupervisor),
        type("Request", (), {"campaign_id": RETRY_CAMPAIGN_ID})(),
        RETRY_BATCH_ID, batch_root,
    )
    assert receipt == _journal_final_frame_sha256(batch_root, RETRY_BATCH_ID)
    assert _tree_fingerprint(batch_root) == before, "the recorded retry bytes were written to"


def test_the_recorded_first_pass_of_the_retry_campaign_still_reads_unchanged():
    """The first pass keeps its bytes and its vocabulary: nothing about it was renamed.

    The recorded store's own receipt for this batch is the frame this reader's independent replay
    returns, so the receipt a successful readback commits and the receipt the database already
    carries for the first pass are the same fact.
    """

    from so101_teleop.expert_validation.campaign_layout import read_selection_binding

    state_root = _recording(
        RETRY_STATE, variable="SO101_TASK12_RETRY_STATE",
        what="the recorded retry closed loop retrycl/state",
    )
    batch_root = _batch_root(state_root, RETRY_CAMPAIGN_ID, RETRY_FIRST_PASS_ID)
    _recording(batch_root, variable="SO101_TASK12_RETRY_STATE",
               what=f"the recorded first pass {RETRY_FIRST_PASS_ID}")
    before = _tree_fingerprint(batch_root)

    binding = _upstream_binding(batch_root, RETRY_FIRST_PASS_ID, RETRY_CAMPAIGN_ID)
    selection = read_selection_binding(binding)
    assert selection["kind"] == "FIRST_PASS"
    assert selection["catalog_sha256"] == RETRY_CATALOG_SHA256
    assert "original_catalog_sha256" not in selection
    point_ids = tuple(selection["selected_point_ids"])
    assert len(point_ids) == RETRY_FIRST_PASS_POINTS
    assert RETRY_POINT_ID in point_ids

    recorded = _read_batch(batch_root, RETRY_FIRST_PASS_ID, RETRY_CAMPAIGN_ID)
    state = recorded.projected_state
    assert state["terminal_reason"] == "POINTS_COMPLETE"
    assert state["batch_cleanup_complete"] is True
    assert state["points"][RETRY_POINT_ID]["status"] == "FAILED"
    assert recorded.events[-1].type == "CLEANUP_COMMITTED"
    assert _journal_final_frame_sha256(
        batch_root, RETRY_FIRST_PASS_ID
    ) == RETRY_FIRST_PASS_RECEIPT
    assert _tree_fingerprint(batch_root) == before, "the recorded first-pass bytes were written to"


def test_the_recorded_live_batch_projects_from_its_own_bytes():
    """The same reader over the raw bytes of a real macOS campaign batch, in place."""

    batch_root = _recording(
        REAL_BATCH, variable="SO101_TASK12_REAL_BATCH", what="the recorded live w2 batch",
    )
    before = _tree_fingerprint(batch_root)

    recorded = _read_batch(batch_root, REAL_BATCH_ID, REAL_BATCH_CAMPAIGN_ID)
    state = recorded.projected_state
    assert state["terminal_reason"] == "POINTS_COMPLETE"
    assert state["batch_cleanup_complete"] is True
    assert sorted(state["points"]) == list(REAL_BATCH_POINT_IDS)
    terminals = {
        event.payload["point_id"]: event.payload["result_sha256"]
        for event in recorded.events if event.type == "POINT_TERMINAL"
    }
    assert {
        point_id: point["result_sha256"] for point_id, point in state["points"].items()
    } == terminals
    assert _tree_fingerprint(batch_root) == before, "the recorded live batch bytes were written to"
