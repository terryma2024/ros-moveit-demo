"""Layout-aware, fail-closed resolution of one batch's fixed-coordinator journal root.

One batch root can carry two different journal layouts:

* ``<batch_root>/coordinator`` - the Linux fixed coordinator (``mujoco_parallel_batch``) and the
  canonical layout the service was written against;
* ``<batch_root>/journal`` - the macOS campaign compositions (``macos_w2_campaign`` and the W1/N1
  entry points), which reuse the same ``CoordinatorJournal`` under the campaign name.

The service used to read ``<batch_root>/coordinator`` and treat a missing epoch document as "no
journal yet". On the macOS layout that silently projected nothing forever, so a campaign that had
committed a full terminal journal never reached a verdict. This resolver decides the layout once,
from the filesystem, and refuses to guess:

* exactly one candidate directory present and carrying an epoch document -> that layout;
* both candidate directories present -> ``JOURNAL_LAYOUT_AMBIGUOUS``, or
  ``JOURNAL_EPOCH_MISMATCH`` when both epoch documents are readable and disagree;
* a candidate that is a symlink, or that exists but is not a directory -> ``JOURNAL_LAYOUT_INVALID``;
* neither candidate present, or the only candidate present has not published its epoch document
  yet -> ``JOURNAL_NOT_PRESENT``;
* an epoch document that is a symlink, is not a regular file, is unreadable, is not exactly
  ``{"batch_id", "coordinator_epoch"}``, names another batch, or carries a non-positive/non-integer
  epoch -> ``OWNER_EPOCH_INVALID``, byte for byte the checks the canonical layout already had.

``JOURNAL_NOT_PRESENT`` is the one outcome that describes a batch whose journal has not been
published yet (the coordinator creates its directory before it writes the epoch document, so the
window is real). Callers that used to read a missing epoch document as ``None`` translate exactly
this code into their previous transient behaviour; every other code is a refusal and is never
caught into a silent "still starting".
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from .coordinator_events import CoordinatorProjectionError


COORDINATOR_LAYOUT: Literal["COORDINATOR"] = "COORDINATOR"
CAMPAIGN_LAYOUT: Literal["CAMPAIGN"] = "CAMPAIGN"

#: The directory each layout keeps its journal in, in resolution order. The order is only a
#: reading order: a batch that carries both is refused rather than resolved.
_LAYOUT_DIRECTORIES = (
    (COORDINATOR_LAYOUT, "coordinator"),
    (CAMPAIGN_LAYOUT, "journal"),
)

_EPOCH_KEYS = frozenset({"batch_id", "coordinator_epoch"})


@dataclass(frozen=True, slots=True)
class FixedJournalLayout:
    """The one journal layout this batch publishes, with its verified epoch."""

    layout: Literal["COORDINATOR", "CAMPAIGN"]
    batch_root: Path
    journal_root: Path
    batch_id: str
    epoch: int


def _read_epoch_document(journal_root: Path, batch_id: str) -> int | None:
    """Read and verify one epoch document, or return ``None`` when it is not published yet.

    Every refusal here is the canonical layout's own ``OWNER_EPOCH_INVALID`` contract, unchanged.
    """

    epoch_path = journal_root / "coordinator_epoch.json"
    if epoch_path.is_symlink():
        raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
    if not epoch_path.exists():
        return None
    if not epoch_path.is_file():
        raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
    try:
        epoch_document = json.loads(epoch_path.read_text(encoding="utf-8"))
        epoch = epoch_document["coordinator_epoch"]
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise CoordinatorProjectionError("OWNER_EPOCH_INVALID") from error
    if (
        set(epoch_document) != _EPOCH_KEYS
        or epoch_document["batch_id"] != batch_id
        or isinstance(epoch, bool)
        or not isinstance(epoch, int)
        or epoch <= 0
    ):
        raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
    return epoch


def _present_candidates(batch_root: Path) -> tuple[tuple[str, Path], ...]:
    """Return the candidate layout directories that exist, refusing anything unusable."""

    present: list[tuple[str, Path]] = []
    for layout, name in _LAYOUT_DIRECTORIES:
        candidate = batch_root / name
        if candidate.is_symlink():
            # A symlinked journal root is never the batch's own directory, whatever it points at.
            raise CoordinatorProjectionError("JOURNAL_LAYOUT_INVALID")
        if candidate.exists():
            if not candidate.is_dir():
                raise CoordinatorProjectionError("JOURNAL_LAYOUT_INVALID")
            present.append((layout, candidate))
    return tuple(present)


def resolve_fixed_journal_layout(batch_root, batch_id: str) -> FixedJournalLayout:
    """Resolve the single journal layout under one batch root, or fail closed."""

    root = Path(batch_root)
    if not isinstance(batch_id, str) or not batch_id:
        raise CoordinatorProjectionError("JOURNAL_BATCH_ID_REQUIRED")
    present = _present_candidates(root)
    if not present:
        raise CoordinatorProjectionError("JOURNAL_NOT_PRESENT")
    if len(present) > 1:
        # Both layouts are on disk. Never pick one: compare the two epoch documents so the refusal
        # names the stronger fact when the two journals disagree about the epoch they describe.
        epochs = []
        for _layout, candidate in present:
            try:
                epochs.append(_read_epoch_document(candidate, batch_id))
            except CoordinatorProjectionError:
                epochs.append(None)
        if len(set(epochs)) == 2 and all(epoch is not None for epoch in epochs):
            raise CoordinatorProjectionError("JOURNAL_EPOCH_MISMATCH")
        raise CoordinatorProjectionError("JOURNAL_LAYOUT_AMBIGUOUS")
    layout, journal_root = present[0]
    epoch = _read_epoch_document(journal_root, batch_id)
    if epoch is None:
        # The directory exists but this layout has not published its epoch document yet.
        raise CoordinatorProjectionError("JOURNAL_NOT_PRESENT")
    return FixedJournalLayout(
        layout=layout,
        batch_root=root,
        journal_root=journal_root,
        batch_id=batch_id,
        epoch=epoch,
    )
