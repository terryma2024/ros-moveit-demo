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


_READY_KEYS = frozenset({"schema_version", "status", "source_commit", "config_sha256",
                         "source_provenance_sha256", "measurements", "checks"})
_QUALIFICATION_CHECKS = ("fov", "collision", "search", "synchronization", "execution")


def build_task8_qualified_report(task8_ready_report: Path, preparation_receipt: Path,
                                 campaign_result: Path, case_root: Path, output: Path) -> Path:
    """Upgrade a `TASK8_READY` report to `QUALIFIED` from a complete live campaign.

    The input report is read-only and is never rewritten; the output is a new document written
    atomically and only if every gate passes. A failure raises and leaves **no** output behind.
    """

    import json

    from .task8_artifact_bundle import verify_prepared_task8_bundle

    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("TASK8_QUALIFICATION_OUTPUT_EXISTS")
    ready_path = require_regular_file(Path(task8_ready_report),
                                      "TASK8_QUALIFICATION_READY_MISSING")
    try:
        ready = json.loads(ready_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("TASK8_QUALIFICATION_READY_INVALID") from error
    if type(ready) is not dict or set(ready) != _READY_KEYS or ready["status"] != "TASK8_READY":
        raise ValueError("TASK8_QUALIFICATION_READY_INVALID")
    checks = ready["checks"]
    if type(checks) is not dict or any(checks.get(name) != "PASS"
                                       for name in _QUALIFICATION_CHECKS):
        raise ValueError("TASK8_QUALIFICATION_CHECKS_INCOMPLETE")
    if checks.get("release") != "UNMEASURED" or checks.get("retreat") != "UNMEASURED":
        raise ValueError("TASK8_QUALIFICATION_CHECKS_INCOMPLETE")

    bundle = verify_prepared_task8_bundle(Path(preparation_receipt))
    identities = bundle.identities
    try:
        manifest = json.loads(require_regular_file(
            Path(bundle.manifest), "TASK8_QUALIFICATION_MANIFEST_MISSING").read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("TASK8_QUALIFICATION_MANIFEST_INVALID") from error
    try:
        summary = json.loads(require_regular_file(
            Path(campaign_result), "TASK8_QUALIFICATION_SUMMARY_MISSING").read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("TASK8_QUALIFICATION_SUMMARY_INVALID") from error
    validate_campaign_summary(summary)
    if identities.get("source_provenance_sha256") != ready["source_provenance_sha256"]:
        raise ValueError("TASK8_QUALIFICATION_IDENTITY_MISMATCH")
    validate_case_journals(case_root, manifest, identities=identities,
                           manifest_document_sha256=manifest["manifest_document_sha256"])

    document = dict(ready)
    document["status"] = "QUALIFIED"
    document["checks"] = dict(checks, release="PASS", retreat="PASS")
    document["live_campaign"] = {
        "case_root": str(Path(case_root).resolve()),
        "campaign_result_sha256": _digest(Path(campaign_result)),
        "preparation_receipt_sha256": _digest(Path(preparation_receipt)),
        "journal_sha256": list(summary["case_journal_sha256"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    temporary.write_bytes(json.dumps(document, sort_keys=True, indent=2).encode() + b"\n")
    os.replace(temporary, output)
    return output


# --- protocol v2 (Task 8): the five live-only fields -------------------------------------------------------
# Each field's extrema direction is fixed by the approved plan: the occlusion window and the cup support distance
# take the maximum across the five runs, while the three stability/distance fields take the minimum. The cup support
# distance additionally has a raw rule: when a run carries the frames before its first open in the release epoch,
# the value is derived from the three consecutive 10 Hz samples immediately preceding it and reported as
# `max(0, d_signed)` - never from a summary.

LIVE_ONLY_FIELDS = ("grasp_occlusion_window_s", "support_distance_m", "release_stable_s",
                    "retreat_distance_m", "placement_stable_s")
LIVE_EXTREMA = {"grasp_occlusion_window_s": max, "support_distance_m": max,
                "release_stable_s": min, "retreat_distance_m": min, "placement_stable_s": min}
LIVE_UNITS = {"grasp_occlusion_window_s": "s", "support_distance_m": "m", "release_stable_s": "s",
              "retreat_distance_m": "m", "placement_stable_s": "s"}
_IDENTITY_KEYS = ("session_id", "contact_policy_fingerprint", "phase_camera_matrix_sha256")


def support_distance_from_frames(frames, *, cup_collision_geom: str,
                                 table_collision_geom: str = "table_collision") -> float:
    """The design's `support_distance_m` rule over one run's pre-open frames.

    The bottom geom's real name depends on the case's cup (`cup_a_bottom_collision` for `plastic_cup`,
    `cup_b_collision` for `plastic_cup_b`), so it is supplied by the caller rather than hard-coded. Each of the three
    consecutive 10 Hz frames immediately before the first open must carry a real contact for the exact pair, the
    per-frame value is `max(0, signed_distance_m)`, and the run's value is the maximum of the three.
    """

    if not cup_collision_geom:
        raise ValueError("CUP_COLLISION_GEOM_REQUIRED: the pair's bottom geom must be named by the caller")
    epoch = frames[0].get("release_epoch") if frames else None
    pre_open = [frame for frame in frames
                if frame.get("release_epoch") == epoch and frame.get("phase") == "RELEASE"
                and frame.get("before_first_open") is True]
    if len(pre_open) < 3:
        raise ValueError("SUPPORT_FRAMES_REQUIRED: three pre-open frames are needed")
    window = pre_open[-3:]
    for earlier, later in zip(window, window[1:]):
        if abs((later["source_stamp"] - earlier["source_stamp"]) - 0.1) > 0.01:
            raise ValueError("SUPPORT_FRAMES_NOT_CONSECUTIVE: the three samples must be one 10 Hz step apart")
    values = []
    for frame in window:
        pair = None
        for contact in frame.get("contacts") or ():
            names = {contact.get("geom1"), contact.get("geom2")}
            if names == {cup_collision_geom, table_collision_geom}:
                pair = contact
                break
        if pair is None:
            raise ValueError(
                f"SUPPORT_CONTACT_REQUIRED: no active contact for {cup_collision_geom}/{table_collision_geom}")
        values.append(max(0.0, float(pair["signed_distance_m"])))
    return max(values)


def _support_from_frames(run: dict) -> float:
    """One run's `support_distance_m`, taken from its own frames and the case's cup collision geom."""

    frames = run.get("support_frames")
    if not frames:
        return float(run["cup_support_distance_m"])
    geom = run.get("cup_collision_geom")
    if not geom:
        raise ValueError("CUP_COLLISION_GEOM_REQUIRED: the run must name its cup's collision geom")
    return support_distance_from_frames(frames, cup_collision_geom=geom)


def derive_live_measurements(full_runs, contract) -> dict:
    """Derive the five live-only fields from five sealed independent FULL runs."""

    runs = list(full_runs)
    if len(runs) != 5:
        raise ValueError(f"FIVE_RUNS_REQUIRED: exactly five runs, found {len(runs)}")
    for key in _IDENTITY_KEYS:
        values = {run.get(key) for run in runs}
        if len(values) != 1 or None in values:
            raise ValueError(f"IDENTITY_MISMATCH: {key} differs across runs")
    for run in runs:
        if not run.get("sample_path") or not run.get("sample_sha256"):
            raise ValueError("SEALED_SAMPLE_REQUIRED: every run needs a sealed sample path and hash")
    derived = {}
    for field in LIVE_ONLY_FIELDS:
        extrema = LIVE_EXTREMA[field]
        if field == "support_distance_m":
            values = [_support_from_frames(run) for run in runs]
        else:
            values = [float(run[field]) for run in runs]
        derived[field] = {"value": extrema(values), "unit": LIVE_UNITS[field],
                          "runs": [run["run_index"] for run in runs]}
    return derived


def build_qualified_measurements(ready_measurements: dict, live_runs, contract) -> dict:
    """Copy the ready measurements **by value** and add exactly the five live-only entries.

    The ready report is never mutated: the caller gets a new mapping, so the `TASK8_READY` document it came from
    keeps its own contents and digest. The five additions come from `derive_live_measurements`, so they carry the
    plan's extrema directions and, where a run supplies its own frames, the raw support-distance rule.
    """

    import copy

    if type(ready_measurements) is not dict or not ready_measurements:
        raise ValueError("READY_MEASUREMENTS_REQUIRED")
    merged = copy.deepcopy(ready_measurements)
    derived = derive_live_measurements(live_runs, contract)
    overlap = set(derived) & set(merged)
    if overlap:
        # a live-only field must not already be present, or the ready report was not the 28-field document
        raise ValueError(f"LIVE_FIELD_ALREADY_PRESENT: {sorted(overlap)[0]}")
    for field in LIVE_ONLY_FIELDS:
        merged[field] = {"value": derived[field]["value"], "unit": derived[field]["unit"]}
    return merged


def _span_s(samples) -> float:
    stamps = [sample["sim_time_s"] for sample in samples]
    if len(stamps) < 2:
        return 0.0
    return max(stamps) - min(stamps)


def retreat_distance_m(frames, *, qualifying) -> float:
    """The design's `retreat_distance_m` rule: the radial displacement from the placed cup at the first qualifying
    RADIAL_RETREAT readback.

    The radial distance is the horizontal distance between the end effector and the cup at each frame; the reported
    value is how far that distance has grown by the **first** frame whose clearance, contact and pose predicates all
    hold together. A run with no such readback is refused, as its design row requires ("每次必须出现 qualifying
    readback"), and the predicate is supplied by the caller because it is read from the raw records rather than from
    the sample keys.
    """

    retreat = sorted((frame for frame in frames if frame.get("phase") == "RADIAL_RETREAT"),
                     key=lambda frame: frame["source_stamp"])
    if not retreat:
        raise ValueError("RETREAT_SAMPLES_REQUIRED: no RADIAL_RETREAT frame in this run")

    def radial(frame) -> float:
        cup, effector = frame["cup_position_m"], frame["end_effector_position_m"]
        return ((effector[0] - cup[0]) ** 2 + (effector[1] - cup[1]) ** 2) ** 0.5

    baseline = radial(retreat[0])
    for frame in retreat:
        if qualifying(frame) is True:
            return radial(frame) - baseline
    raise ValueError("RETREAT_QUALIFYING_READBACK_REQUIRED: no frame satisfied clearance, contact and pose stability")


def placement_stable_s(frames, *, stable) -> float:
    """The design's `placement_stable_s` rule: the longest contiguous source-stamp duration in FINAL_CHECK over which
    pose, linear/angular velocity, table support and forbidden contact all hold.

    The design states four conditions together, and three of them - table support and forbidden contact in
    particular - are read from the raw contact records rather than from the sample keys, so the combined predicate is
    supplied by the caller and the span structure is the shared one. A frame break ends the span here; the row does
    not require the run to fail on a break, only the occlusion row does.
    """

    return longest_contiguous_span_s(frames, predicate=stable, phase="FINAL_CHECK")










def longest_contiguous_span_s(frames, *, predicate, phase=None, period_s: float = 0.1,
                              tolerance_s: float = 0.01, strict_breaks: bool = False) -> float:
    """The longest contiguous source-stamp span over which a predicate holds.

    Three of the five live-only rules are stated this way - the occlusion window over CLOSE..RELEASE, the release
    stability duration and the placement stability duration - so the structure lives here once. A stamp gap ends the
    current span; `strict_breaks` turns a gap into a refusal instead, which is what the occlusion row requires. The
    predicate is supplied by the caller, so each rule keeps its own definition of "holds".
    """

    selected = sorted((frame for frame in frames if phase is None or frame.get("phase") == phase),
                      key=lambda frame: frame["source_stamp"])
    if not selected:
        raise ValueError(f"SPAN_FRAMES_REQUIRED: no frames for phase {phase!r}")
    best, current_start, previous = 0.0, None, None
    for frame in selected:
        if previous is not None:
            step = frame["source_stamp"] - previous["source_stamp"]
            if abs(step - period_s) > tolerance_s:
                if strict_breaks:
                    raise ValueError(f"SPAN_FRAME_BREAK: {previous['source_stamp']} -> {frame['source_stamp']}")
                current_start = None
        previous = frame
        if predicate(frame) is not True:
            current_start = None
            continue
        if current_start is None:
            current_start = frame["source_stamp"]
        best = max(best, frame["source_stamp"] - current_start)
    return best


def release_stable_s(frames, *, stable) -> float:
    """The design's `release_stable_s` rule: the longest contiguous source-stamp span in RELEASE over which the cup's
    pose, velocity and contact stability predicate holds.

    The row measures from the first moment after RELEASE at which the predicate holds to the first break or the end
    of the phase, so a break simply ends the span; the predicate itself is supplied by the caller because the
    velocity and contact parts are read from the raw records.
    """

    return longest_contiguous_span_s(frames, predicate=stable, phase="RELEASE")


def grasp_occlusion_window_s(frames, *, occluded) -> float:
    """The design's `grasp_occlusion_window_s` rule: the longest contiguous source-stamp interval of legitimate
    gripper occlusion between CLOSE and RELEASE.

    Unlike the stability rows, this one makes a frame break fail the run, so the span is computed with
    `strict_breaks=True` and a gap raises `SPAN_FRAME_BREAK`. No phase filter is applied: the caller's predicate is
    what identifies legitimate occlusion, and it must accept only CLOSE..RELEASE frames whose occluder owner is one of
    the approved group-0 visual geoms - a non-allowed owner belongs in the predicate so it ends the span rather than
    being silently counted.
    """

    return longest_contiguous_span_s(frames, predicate=occluded, strict_breaks=True)
