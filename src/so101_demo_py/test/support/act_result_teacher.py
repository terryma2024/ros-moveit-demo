"""Teacher-result fixtures for the ACT collection result (schema 3): the Teacher's claim and its manifest on disk."""

import json
from pathlib import Path

from so101_demo.parallel_batch.dynamic_manifest import SCHEMA_GENERAL

# outcome -> (teacher_execution_status, teacher_task_result)
OUTCOMES = {
    "PASSED": ("COMPLETED", "PASS"),
    "FAILED": ("COMPLETED", "FAIL"),
    "UNCONFIRMED": ("COMPLETED", "UNCONFIRMED"),
    "FAILED_EXECUTION": ("FAILED", "UNCONFIRMED"),
    "STOPPED_SAFETY": ("STOPPED_SAFETY", "UNCONFIRMED"),
    "DEADLINE": ("DEADLINE", "UNCONFIRMED"),
    "INDETERMINATE": ("INDETERMINATE", "UNCONFIRMED"),
}


def teacher(outcome="PASSED", *, data="PENDING_QC", reason=None):
    execution, task = OUTCOMES[outcome]
    return dict(execution_status=execution, task_result=task, data_status=data, data_reason=reason)


def write_manifest(working: Path, fields: dict, *, status=None) -> Path:
    """The Teacher child's manifest, as the sealed result carries it under <result>/dynamic/."""
    directory = Path(working) / "dynamic"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "dynamic-execute-manifest.json"
    done = fields["execution_status"] == "COMPLETED"
    path.write_text(json.dumps({
        "schema": SCHEMA_GENERAL, "schema_version": 1, "status": status or ("DONE" if done else "ERROR"),
        "teacher_execution_status": fields["execution_status"],
        "teacher_task_result": {"result": fields["task_result"]},
        # the Teacher manifest holds no data verdict of its own (A4c): the data status is the independent Recorder's, so the
        # manifest carries the constant DISABLED whatever the claim says
        "act_data_status": "DISABLED"}, sort_keys=True))
    return path


def sealed_teacher(store, outcome="PASSED", *, data="PENDING_QC", reason=None):
    """Write the Teacher manifest into the store's working directory and return the claim `seal` takes."""
    fields = teacher(outcome, data=data, reason=reason)
    write_manifest(store.working, fields)
    return fields
