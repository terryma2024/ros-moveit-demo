"""The Teacher's process telemetry as the data side sees it (policy v3, design 2026-10-10 sections 7 to 9).

The Teacher manifest of policy v3 carries a `teacher_process_summary_v1`. The data side copies it, with the Teacher policy version, the
cup-pose source and the verdict source, into a metadata document beside the sealed episode (the sealed episode itself is never
rewritten). The same manifest decides whether the episode is training-eligible: an oracle flag or an incomplete summary excludes it.
Collision, contact and force data never enter a training sample (`bundle.TRAINING_FIELDS`)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..core.process_summary import SCHEMA as SUMMARY_SCHEMA, oracle_exclusion, validate_summary

METADATA_SCHEMA = "teacher_process_metadata_v1"
METADATA_FILE = "teacher-process-metadata.json"
TEACHER_MANIFEST_SCHEMA_V3 = "so101-dynamic-mujoco-execute-v3"
EXCLUDED_CODE = "EXPORT_EPISODE_ORACLE_EXCLUDED"


def metadata_document(manifest_bytes: bytes) -> dict | None:
    """The episode metadata of a v3 Teacher manifest (its raw bytes), or None for any other schema. Raises ValueError for a v3
    manifest whose summary or provenance is unreadable: the metadata would then be a claim nothing supports."""
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, ValueError) as error:
        raise ValueError("TEACHER_PROCESS: manifest unreadable") from error
    if type(manifest) is not dict or manifest.get("schema") != TEACHER_MANIFEST_SCHEMA_V3:
        return None
    summary = manifest.get("teacher_process_summary")
    validate_summary(summary)
    policy = summary.get("policy")
    if type(policy) is not dict:
        raise ValueError("TEACHER_PROCESS: summary policy")
    return {
        "schema": METADATA_SCHEMA,
        "teacher_execution_policy_version": policy.get("execution_policy_schema"),
        "teacher_execution_policy_sha256": policy.get("execution_policy_sha256"),
        "cup_pose_source": policy.get("cup_pose_source"),
        "verdict_source": policy.get("verdict_source"),
        "teacher_process_summary_schema": summary.get("schema"),
        "teacher_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "teacher_process_summary": summary,
    }


def write_metadata(manifest_path, output_dir) -> dict | None:
    """Write `teacher-process-metadata.json` into `output_dir` for a v3 Teacher manifest and return the document (None otherwise).
    The file is written once, atomically; an existing identical file is accepted, a different one is refused."""
    document = metadata_document(Path(manifest_path).read_bytes())
    if document is None:
        return None
    payload = (json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    target = Path(output_dir) / METADATA_FILE
    if target.exists():
        if target.read_bytes() != payload:
            raise ValueError("TEACHER_PROCESS: metadata exists and differs")
        return document
    staging = target.with_name(f".{METADATA_FILE}.pending")
    staging.write_bytes(payload)
    staging.replace(target)
    return document


def exclusion_of_manifest(manifest_bytes: bytes) -> tuple[str, str] | None:
    """(flag, phase) when the episode of this Teacher manifest is not training-eligible, else None. A manifest of another schema
    carries no summary and is not judged here; an unreadable v3 summary is itself an exclusion (``INCOMPLETE``)."""
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, ValueError):
        return ("INCOMPLETE", "teacher manifest unreadable")
    if type(manifest) is not dict or manifest.get("schema") != TEACHER_MANIFEST_SCHEMA_V3:
        return None
    return oracle_exclusion(manifest.get("teacher_process_summary"))


__all__ = ["EXCLUDED_CODE", "METADATA_FILE", "METADATA_SCHEMA", "SUMMARY_SCHEMA", "exclusion_of_manifest", "metadata_document",
           "validate_summary", "write_metadata"]
