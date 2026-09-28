"""Task 8P4: derive a `QUALIFIED` calibration report from a complete live campaign.

Nothing here trusts a status: the campaign summary, every case journal, both retirement receipts
and the release/retreat samples are re-checked, and a failure leaves no `QUALIFIED` behind. The
input `TASK8_READY` report is read-only; the qualification report is a new immutable document.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SUMMARY_KEYS = frozenset({"status", "prefix_count", "consecutive_full_count",
                           "case_journal_sha256"})


def _digest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def require_regular_file(path: Path, code: str) -> Path:
    path = Path(path)
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError(code) from error
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(code)
    return path


def validate_campaign_summary(summary: dict, *, prefix_count: int = 9,
                              full_count: int = 5) -> dict:
    """A campaign summary qualifies only if it is PASSED, complete and unbroken.

    Shape follows the trusted full-restart campaign's own summary: status, prefix_count,
    consecutive_full_count and one journal digest per case.
    """

    if type(summary) is not dict or set(summary) != _SUMMARY_KEYS:
        raise ValueError("TASK8_QUALIFICATION_SUMMARY_INVALID")
    if summary["status"] != "PASSED":
        raise ValueError("TASK8_QUALIFICATION_NOT_PASSED")
    if summary["prefix_count"] != prefix_count:
        raise ValueError("TASK8_QUALIFICATION_CASE_COUNT_INVALID")
    if summary["consecutive_full_count"] != full_count:
        # fulls must be consecutive: a broken run cannot be spliced into a qualification
        raise ValueError("TASK8_QUALIFICATION_FULLS_NOT_CONSECUTIVE")
    digests = summary["case_journal_sha256"]
    if not isinstance(digests, list) or len(digests) != prefix_count + full_count:
        raise ValueError("TASK8_QUALIFICATION_CASE_COUNT_INVALID")
    if len(set(digests)) != len(digests):
        raise ValueError("TASK8_QUALIFICATION_JOURNAL_DUPLICATE")
    for digest in digests:
        if _SHA.fullmatch(str(digest)) is None:
            raise ValueError("TASK8_QUALIFICATION_JOURNAL_HASH_INVALID")
    return dict(summary)


def validate_release_sample(sample: dict) -> dict:
    """Release evidence must show support before opening, contact loss after, and stability."""

    required = {"supported_before_open", "contact_lost_after_open", "stable_window_s",
                "sample_path", "sample_sha256"}
    if type(sample) is not dict or set(sample) != required:
        raise ValueError("TASK8_QUALIFICATION_RELEASE_INVALID")
    if sample["supported_before_open"] is not True or sample["contact_lost_after_open"] is not True:
        raise ValueError("TASK8_QUALIFICATION_RELEASE_INVALID")
    window = sample["stable_window_s"]
    if not isinstance(window, (int, float)) or isinstance(window, bool) or window <= 0:
        raise ValueError("TASK8_QUALIFICATION_RELEASE_INVALID")
    sample_path = require_regular_file(Path(sample["sample_path"]),
                                       "TASK8_QUALIFICATION_SAMPLE_MISSING")
    if _SHA.fullmatch(str(sample["sample_sha256"])) is None \
            or _digest(sample_path) != sample["sample_sha256"]:
        raise ValueError("TASK8_QUALIFICATION_SAMPLE_HASH_INVALID")
    return dict(sample)


def validate_retreat_sample(sample: dict, *, deadline_s: float = 120.0) -> dict:
    """Retreat evidence must show distance, stability and completion inside the deadline."""

    required = {"retreat_distance_m", "target_stable", "completed_s",
                "sample_path", "sample_sha256"}
    if type(sample) is not dict or set(sample) != required:
        raise ValueError("TASK8_QUALIFICATION_RETREAT_INVALID")
    distance, completed = sample["retreat_distance_m"], sample["completed_s"]
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           for value in (distance, completed)):
        raise ValueError("TASK8_QUALIFICATION_RETREAT_INVALID")
    if distance <= 0 or completed <= 0 or completed > deadline_s:
        raise ValueError("TASK8_QUALIFICATION_RETREAT_INVALID")
    if sample["target_stable"] is not True:
        raise ValueError("TASK8_QUALIFICATION_RETREAT_INVALID")
    sample_path = require_regular_file(Path(sample["sample_path"]),
                                       "TASK8_QUALIFICATION_SAMPLE_MISSING")
    if _SHA.fullmatch(str(sample["sample_sha256"])) is None \
            or _digest(sample_path) != sample["sample_sha256"]:
        raise ValueError("TASK8_QUALIFICATION_SAMPLE_HASH_INVALID")
    return dict(sample)


def validate_case_journals(case_root: Path, manifest: dict, *, identities: dict,
                           manifest_document_sha256: str) -> tuple[dict, ...]:
    """Load and re-check all fourteen case journals under one case root.

    Each journal must be a complete row (evidence plus both retirement receipts), bound to this
    bundle's identity, with a prefix carrying no live-evidence artifact and a full carrying one.
    A missing, foreign or incomplete journal refuses the whole qualification.
    """

    import json

    from .task8_live_evidence import (
        require_campaign_cases, require_case_journal_row, require_case_row_matches_bundle,
    )

    case_root = Path(case_root)
    if not case_root.is_absolute() or ".." in case_root.parts or not case_root.is_dir() \
            or case_root.is_symlink():
        raise ValueError("TASK8_QUALIFICATION_CASE_ROOT_INVALID")
    rows = []
    for case_id in require_campaign_cases(manifest):
        mode = "phase_prefix" if case_id.startswith("prefix-") else "full"
        journal = case_root / "task8-live" / "cases" / f"{case_id}.json"
        journal = require_regular_file(journal, "TASK8_QUALIFICATION_JOURNAL_MISSING")
        try:
            row = json.loads(journal.read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("TASK8_QUALIFICATION_JOURNAL_INVALID") from error
        if row.get("case_id") != case_id:
            raise ValueError("TASK8_QUALIFICATION_JOURNAL_IDENTITY_MISMATCH")
        row = require_case_journal_row(row, mode=mode)
        rows.append(require_case_row_matches_bundle(
            row, identities=identities, manifest_document_sha256=manifest_document_sha256))
    return tuple(rows)
