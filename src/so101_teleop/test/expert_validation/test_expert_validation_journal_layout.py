"""The fixed-coordinator journal resolver: one layout per batch, or a typed refusal.

Two layouts exist on disk for one batch root: the Linux/coordinator one at
``<batch_root>/coordinator`` and the macOS campaign one at ``<batch_root>/journal``. The service
must pick neither silently. These tests pin the resolver contract: exactly one layout present is
accepted, everything else (both, neither, a symlink, a non-directory, disagreeing epoch
documents, an invalid epoch document) is a typed error.
"""

import json
from pathlib import Path

import pytest

from so101_teleop.expert_validation.coordinator_events import CoordinatorProjectionError
from so101_teleop.expert_validation.journal_layout import (
    CAMPAIGN_LAYOUT,
    COORDINATOR_LAYOUT,
    resolve_fixed_journal_layout,
)


BATCH_ID = "w2-b001"


def _epoch_document(batch_id=BATCH_ID, epoch=1):
    return json.dumps({"batch_id": batch_id, "coordinator_epoch": epoch})


def _layout(root, name, *, epoch_document=None, epoch=1, directory=True, symlink=False):
    """Publish one candidate layout, optionally as a symlink or a plain file."""

    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if symlink:
        target = root / f"{name}-target"
        target.mkdir(exist_ok=True)
        (target / "coordinator_epoch.json").write_text(_epoch_document(epoch=epoch))
        path.symlink_to(target, target_is_directory=True)
        return path
    if not directory:
        path.write_text("not a directory")
        return path
    path.mkdir(exist_ok=True)
    if epoch_document is not None:
        (path / "coordinator_epoch.json").write_text(
            epoch_document if epoch_document is not True else _epoch_document(epoch=epoch)
        )
    return path


def test_coordinator_only_layout_is_resolved_to_the_canonical_root(tmp_path):
    _layout(tmp_path, "coordinator", epoch_document=True, epoch=3)

    resolved = resolve_fixed_journal_layout(tmp_path, BATCH_ID)

    assert resolved.layout == COORDINATOR_LAYOUT
    assert resolved.journal_root == (tmp_path / "coordinator").resolve()
    assert resolved.batch_root == tmp_path.resolve()
    assert resolved.batch_id == BATCH_ID
    assert resolved.epoch == 3


def test_campaign_only_layout_is_resolved_to_the_campaign_root(tmp_path):
    _layout(tmp_path, "journal", epoch_document=True, epoch=1)

    resolved = resolve_fixed_journal_layout(tmp_path, BATCH_ID)

    assert resolved.layout == CAMPAIGN_LAYOUT
    assert resolved.journal_root == (tmp_path / "journal").resolve()
    assert resolved.epoch == 1


def test_both_layouts_present_is_refused_as_ambiguous(tmp_path):
    _layout(tmp_path, "coordinator", epoch_document=True, epoch=1)
    _layout(tmp_path, "journal", epoch_document=True, epoch=1)

    with pytest.raises(CoordinatorProjectionError, match="JOURNAL_LAYOUT_AMBIGUOUS"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


def test_two_layouts_with_disagreeing_epochs_are_refused_as_a_mismatch(tmp_path):
    _layout(tmp_path, "coordinator", epoch_document=True, epoch=1)
    _layout(tmp_path, "journal", epoch_document=True, epoch=2)

    with pytest.raises(CoordinatorProjectionError, match="JOURNAL_EPOCH_MISMATCH"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


def test_neither_layout_present_is_a_typed_refusal_not_a_silent_pick(tmp_path):
    with pytest.raises(CoordinatorProjectionError, match="JOURNAL_NOT_PRESENT"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


def test_a_lone_layout_without_an_epoch_document_is_not_present(tmp_path):
    _layout(tmp_path, "coordinator", epoch_document=None)

    with pytest.raises(CoordinatorProjectionError, match="JOURNAL_NOT_PRESENT"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


@pytest.mark.parametrize("name", ["coordinator", "journal"])
def test_symlinked_layout_candidate_is_refused(tmp_path, name):
    _layout(tmp_path, name, symlink=True)

    with pytest.raises(CoordinatorProjectionError, match="JOURNAL_LAYOUT_INVALID"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


@pytest.mark.parametrize("name", ["coordinator", "journal"])
def test_non_directory_layout_candidate_is_refused(tmp_path, name):
    _layout(tmp_path, name, directory=False)

    with pytest.raises(CoordinatorProjectionError, match="JOURNAL_LAYOUT_INVALID"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


def test_symlinked_epoch_document_is_refused(tmp_path):
    root = _layout(tmp_path, "coordinator", epoch_document=None)
    target = tmp_path / "epoch-target.json"
    target.write_text(_epoch_document())
    (root / "coordinator_epoch.json").symlink_to(target)

    with pytest.raises(CoordinatorProjectionError, match="OWNER_EPOCH_INVALID"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


@pytest.mark.parametrize(
    "document",
    [
        "not json",
        json.dumps({"batch_id": BATCH_ID}),
        json.dumps({"batch_id": "other-batch", "coordinator_epoch": 1}),
        json.dumps({"batch_id": BATCH_ID, "coordinator_epoch": 0}),
        json.dumps({"batch_id": BATCH_ID, "coordinator_epoch": True}),
        json.dumps({"batch_id": BATCH_ID, "coordinator_epoch": "1"}),
        json.dumps({"batch_id": BATCH_ID, "coordinator_epoch": 1, "extra": 1}),
    ],
)
def test_coordinator_epoch_document_validation_is_unchanged(tmp_path, document):
    """The canonical layout keeps every check it had before the resolver existed."""

    _layout(tmp_path, "coordinator", epoch_document=document)

    with pytest.raises(CoordinatorProjectionError, match="OWNER_EPOCH_INVALID"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


def test_a_directory_candidate_that_is_a_symlink_to_nowhere_is_refused(tmp_path):
    (tmp_path / "journal").symlink_to(tmp_path / "gone", target_is_directory=True)

    with pytest.raises(CoordinatorProjectionError, match="JOURNAL_LAYOUT_INVALID"):
        resolve_fixed_journal_layout(tmp_path, BATCH_ID)


def test_the_resolver_never_writes_to_the_batch_root(tmp_path):
    _layout(tmp_path, "journal", epoch_document=True)
    before = sorted(path.name for path in Path(tmp_path).iterdir())

    resolve_fixed_journal_layout(tmp_path, BATCH_ID)

    assert sorted(path.name for path in Path(tmp_path).iterdir()) == before
