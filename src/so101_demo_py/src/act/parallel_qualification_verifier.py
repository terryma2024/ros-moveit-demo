"""The container-collection qualification report: its builder and its independent verifier.

`build_collection_qualification_report` recomputes a finished exact-eight qualification run from its originals and writes the
report; `verify_collection_qualification` recomputes the same run again, from the report's own location, and accepts the report
only when the recomputation reproduces its bytes. The recomputation they share is `collection_qualification_recompute`. Formal
collection admission (`so101_teleop/unified/admission.py`) calls the verifier. Neither function trusts a number a report, a
memo or an in-memory verdict claims, and neither reads a pick-place live document: that shape fails the closed form check.
"""

import hashlib
import os
from pathlib import Path


# ---- the container-collection qualification report ---------------------------------------------------------------------

REPORT_RELATIVE = Path("host") / "qualification-report.json"
_REPORT_KEYS = frozenset({"schema_version", "kind", "status", "qualification_run_id", "worker_count", "controlled_identity",
                          "contract", "campaign_index", "waves", "quality", "resource_logs", "reasons"})
_QUALITY_NAMES = frozenset({"recorder_lossless", "frame_continuity", "qc_valid_rate", "teacher_physical_success_rate"})


def build_collection_qualification_report(run_root, *, contract) -> Path:
    """Recompute the run from its originals and write `<run>/host/qualification-report.json`, once and never over an old one.

    `contract` is the gate contract file the campaign config names. A run that does not qualify still gets a report: status
    `NOT_QUALIFIED` and a sorted list of closed reason codes. A run or contract that cannot be read raises and writes nothing.
    """

    from .collection_qualification_recompute import canonical, recompute, run_layout

    run, _ = run_layout(run_root)
    target = run / REPORT_RELATIVE
    if target.exists() or target.is_symlink():
        raise ValueError("QUALIFICATION_REPORT_EXISTS")
    payload = canonical(recompute(run, contract))
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as error:
        raise ValueError("QUALIFICATION_REPORT_EXISTS") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return target


def _qualification_run(report_path, registered_root) -> Path:
    """The run directory a report belongs to: the registered root's direct child, with its own layout file and the fixed report path.

    Composes `_open_regular` (no symlink in any component), the canonical-path rule of the campaign paths and the run layout
    document. Whether the run is the current one is the caller's question: admission knows the current root."""

    from .collection_qualification_recompute import run_layout

    report, registered = Path(report_path), Path(registered_root)
    try:
        for path in (report, registered):
            if not path.is_absolute() or ".." in path.parts or path.resolve(strict=True) != path:
                raise ValueError("path is not canonical")
        run = report.parent.parent
        if not registered.is_dir() or run.parent != registered or report != run / REPORT_RELATIVE:
            raise ValueError("report is not at the fixed location of a run of the registered root")
        _, layout = run_layout(run)
        if layout["root"] != str(registered) or layout["run_id"] != run.name:
            raise ValueError("layout names another root")
    except (OSError, ValueError) as error:
        raise ValueError("COLLECTION_QUALIFICATION_PATH_INVALID") from error
    return run


def _closed_report(document):
    from .collection_qualification_recompute import KIND

    if (type(document) is not dict or set(document) != _REPORT_KEYS or document["kind"] != KIND
            or type(document["schema_version"]) is not int or document["schema_version"] != 1
            or document["status"] not in ("QUALIFIED", "NOT_QUALIFIED")
            or type(document["worker_count"]) is not int or document["worker_count"] != 8
            or type(document["qualification_run_id"]) is not str or type(document["reasons"]) is not list
            or type(document["quality"]) is not dict or set(document["quality"]) != _QUALITY_NAMES):
        raise ValueError("COLLECTION_QUALIFICATION_REPORT_INVALID")


def verify_collection_qualification(report_path, *, registered_root, expected_identity) -> dict:
    """Recompute the whole run behind a report and return the in-memory proof; nothing is written, nothing the report says is used.

    A legacy `PASSED` receipt or a pick-place live document fails the closed kind and field check before anything else is read.
    The recomputed document must equal the report byte for byte and be `QUALIFIED`. `expected_identity=None` skips only the
    comparison with an externally supplied controlled identity.
    """

    from .collection_qualification_recompute import (
        _bytes, _parse, campaign_contract_path, canonical, contract_documents, recompute,
    )

    report = Path(report_path)
    try:
        run = _qualification_run(report, registered_root)
        raw = _bytes(report)
        document = _parse(raw)
        _closed_report(document)
    except ValueError as error:
        if str(error).startswith("COLLECTION_QUALIFICATION_"):
            raise
        raise ValueError("COLLECTION_QUALIFICATION_REPORT_INVALID") from error
    except OSError as error:
        raise ValueError("COLLECTION_QUALIFICATION_REPORT_INVALID") from error
    if document["status"] != "QUALIFIED":
        raise ValueError("COLLECTION_QUALIFICATION_NOT_QUALIFIED")
    try:
        contract_path = campaign_contract_path(run)
        recomputed = recompute(run, contract_path)
        _, contract = contract_documents(contract_path)
    except ValueError as error:
        raise ValueError("COLLECTION_QUALIFICATION_RECOMPUTE_INVALID") from error
    if recomputed["status"] != "QUALIFIED" or canonical(recomputed) != raw:
        raise ValueError("COLLECTION_QUALIFICATION_RECOMPUTE_MISMATCH")
    if expected_identity is not None and recomputed["controlled_identity"] != expected_identity:
        raise ValueError("COLLECTION_QUALIFICATION_IDENTITY_MISMATCH")
    return dict(kind="ACT_COLLECTION_QUALIFICATION_READBACK", schema_version=1, status="PASS",
                report_sha256=hashlib.sha256(raw).hexdigest(), qualification_run_id=recomputed["qualification_run_id"],
                run_root=str(run), controlled_identity=recomputed["controlled_identity"],
                contract_sha256=recomputed["contract"]["sha256"],
                scene_manifest_sha256=contract["scene_manifest"]["sha256"],
                functional_manifest_sha256=contract["functional_manifest"]["sha256"],
                formal_split_manifest_sha256=contract["formal_split_manifest"]["sha256"], task_count=40)
