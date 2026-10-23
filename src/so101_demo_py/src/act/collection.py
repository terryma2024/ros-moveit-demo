"""ACT collection eligibility rules and payload keys."""

from __future__ import annotations


# the collection modes whose episodes may enter the training manifest. The preselected-target
# diagnostic is a real, committed, physically measured episode that is still not training evidence.
TRAINABLE_COLLECTION_MODES = frozenset({"formal"})


def training_eligible(record: dict) -> bool:
    """A record enters training only when it is a committed, clean, complete success.

    A business failure is retained as evidence but never exported, and a record whose coordinator has
    not committed is not yet a result — it is a run in progress. A record that names a collection
    mode must name a trainable one, so a committed diagnostic episode is refused here as well as at
    the export boundary.
    """

    # fail closed on a missing or malformed field: the plan's own boundary case passes a record that
    # carries neither `status` nor `coordinator_committed` and expects it to be ineligible, so an
    # incomplete record is refused rather than raising out of a gate on training data
    if not isinstance(record, dict):
        return False
    if "collection_mode" in record:
        mode = record["collection_mode"]
        if not isinstance(mode, str) or mode not in TRAINABLE_COLLECTION_MODES:
            # an unknown, missing or container mode is ineligible, never a raise out of a data gate
            return False
    return (record.get("status") == "PASSED" and record.get("qc") == "PASS"
            and record.get("done") is True and record.get("interventions") == 0
            and record.get("coordinator_committed") is True)


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
