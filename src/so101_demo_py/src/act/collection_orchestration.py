"""The collection request of one run and the verdict type of the offline data path (Phase A4c, cleanup step 2).

`CollectionOptions` is the validated `--collection` / `--collection-fault` pair a run carries; `RecorderOutcome` is the verdict on the
data that `act/offline/orchestration.py` returns. The live Recorder process and its orchestrator are gone.

Direction of dependence: the Teacher never waits for, reads from or is stopped by anything here after its own start. Every
defect on this side is a verdict on the data (INVALID) and never an input to the Teacher. Nothing in this module imports
ROS or the Teacher's modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

FAULT_SANDBOX_COMPONENT = "fault-sandbox"
COLLECTION_MODES = ("on", "off")
#: `recorder_absent` and `recorder_late` are orchestrator faults; the other three are bag faults (`act/offline/orchestration.py`).
COLLECTION_FAULTS = ("none", "recorder_absent", "recorder_late", "queue_overflow", "source_gap", "output_write_failure")
DIAGNOSTIC_MODE = "preselected_target_diagnostic"
#: The Teacher states at which a diagnostic run may inject an execution failure (one: the cup is held and the arm has moved)
INJECTABLE_STATES = ("LIFT",)


class CollectionRefused(ValueError):
    """The collection request is refused before any Teacher starts."""


@dataclass(frozen=True)
class CollectionOptions:
    """The validated `--collection` / `--collection-fault` pair of one run."""

    mode: str = "on"
    fault: str = "none"
    #: `<run>/fault-sandbox`; present only when a fault was requested
    sandbox_root: Path | None = None
    #: Diagnostic mode only: the Teacher state at whose execute boundary one execution failure is injected (default: none)
    inject_failure_at: str | None = None

    @property
    def enabled(self) -> bool:
        return self.mode == "on"

    @property
    def raw_pilot(self) -> bool:
        """The record-only bag is the only data path, so it is on exactly when the collection is."""
        return self.enabled

    def document(self) -> dict:
        """The form a Worker specification carries; `collection_from_document` re-validates it."""
        document = {"mode": self.mode, "fault": self.fault,
                    "sandbox_root": None if self.sandbox_root is None else str(self.sandbox_root),
                    "raw_pilot": self.enabled}
        if self.inject_failure_at is not None:
            document["inject_failure_at"] = self.inject_failure_at
        return document


def validate_collection_request(collection: str, fault: str, *, run_mode: str, run_root,
                                raw_pilot: bool | None = None, inject_failure_at: str | None = None) -> CollectionOptions:
    """Refuse an unknown value, and refuse a fault outside the diagnostic mode, before any Teacher start.

    `raw_pilot` is the retired `--raw-pilot` switch: the bag recorder is the data path, so `True` is a no-op with the collection on and
    `False` with the collection on is refused (there is no other data path)."""

    if collection not in COLLECTION_MODES:
        raise CollectionRefused(f"COLLECTION_MODE_UNKNOWN: {collection}")
    if fault not in COLLECTION_FAULTS:
        raise CollectionRefused(f"COLLECTION_FAULT_UNKNOWN: {fault}")
    if raw_pilot is not None and type(raw_pilot) is not bool:
        raise CollectionRefused("COLLECTION_RAW_PILOT_UNKNOWN")
    if raw_pilot is True and collection != "on":
        raise CollectionRefused("COLLECTION_RAW_PILOT_REQUIRES_COLLECTION_ON")
    if raw_pilot is False and collection == "on":
        raise CollectionRefused("COLLECTION_RAW_RECORDER_IS_THE_ONLY_DATA_PATH")
    if inject_failure_at is not None:
        # Refused by name, never ignored
        if run_mode != DIAGNOSTIC_MODE:
            raise CollectionRefused("TEACHER_INJECTION_REQUIRES_DIAGNOSTIC_MODE")
        if collection != "on":
            raise CollectionRefused("TEACHER_INJECTION_REQUIRES_COLLECTION_ON")
        if inject_failure_at not in INJECTABLE_STATES:
            raise CollectionRefused(f"TEACHER_INJECTION_STATE_UNSUPPORTED: {inject_failure_at}")
    if fault == "none":
        return CollectionOptions(collection, "none", None, inject_failure_at)
    if run_mode != DIAGNOSTIC_MODE:
        raise CollectionRefused("COLLECTION_FAULT_REQUIRES_DIAGNOSTIC_MODE")
    if collection != "on":
        raise CollectionRefused("COLLECTION_FAULT_REQUIRES_COLLECTION_ON")
    return CollectionOptions(collection, fault, Path(run_root) / FAULT_SANDBOX_COMPONENT, inject_failure_at)


def collection_from_document(document) -> CollectionOptions:
    """Rebuild and re-validate the options a Worker specification carries; any defect refuses the Worker."""

    if (type(document) is not dict or set(document) not in ({"mode", "fault", "sandbox_root"},
                                                              {"mode", "fault", "sandbox_root", "raw_pilot"},
                                                              {"mode", "fault", "sandbox_root", "raw_pilot", "inject_failure_at"})
            or document["mode"] not in COLLECTION_MODES or document["fault"] not in COLLECTION_FAULTS
            or ("raw_pilot" in document and document["raw_pilot"] is not (document["mode"] == "on"))):
        raise CollectionRefused("COLLECTION_SPEC_INVALID")
    injected = document.get("inject_failure_at")
    if "inject_failure_at" in document and (injected not in INJECTABLE_STATES or document["mode"] != "on"):
        raise CollectionRefused("COLLECTION_SPEC_INVALID")
    root = document["sandbox_root"]
    if document["fault"] == "none":
        if root is not None:
            raise CollectionRefused("COLLECTION_SPEC_INVALID")
        return CollectionOptions(document["mode"], "none", None, injected)
    if (document["mode"] != "on" or type(root) is not str or not Path(root).is_absolute()
            or Path(root).name != FAULT_SANDBOX_COMPONENT or ".." in Path(root).parts):
        raise CollectionRefused("COLLECTION_FAULT_OUTSIDE_SANDBOX")
    return CollectionOptions(document["mode"], document["fault"], Path(root), injected)


def require_under_sandbox(sandbox_root, *paths) -> None:
    """Every fault output must sit beneath `<run>/fault-sandbox/`, as written and after resolving symlinks."""

    if sandbox_root is None:
        raise CollectionRefused("COLLECTION_FAULT_SANDBOX_REQUIRED")
    root = Path(sandbox_root)
    if root.name != FAULT_SANDBOX_COMPONENT:
        raise CollectionRefused(f"COLLECTION_FAULT_OUTSIDE_SANDBOX: {root}")
    real_root = Path(os.path.realpath(root))
    for path in paths:
        path = Path(path)
        if ".." in path.parts or not path.is_relative_to(root) or not Path(os.path.realpath(path)).is_relative_to(real_root):
            raise CollectionRefused(f"COLLECTION_FAULT_OUTSIDE_SANDBOX: {path}")


@dataclass
class RecorderOutcome:
    """The Recorder's verdict on the data, recorded in full (every field is evidence)."""

    data_status: str
    reason: str | None
    facts: dict = field(default_factory=dict)
