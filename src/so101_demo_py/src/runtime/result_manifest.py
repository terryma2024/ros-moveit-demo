"""Rich execution and qualification result classification."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..core.domain import ExecutionRunStatus, FailureCategory, QualificationStatus

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RunResultManifest:
    run_status: ExecutionRunStatus
    qualification_status: QualificationStatus
    backend: str
    session_id: str
    reset_epoch: int
    policy_sha256: str
    bundle_sha256: str
    first_failed_phase: str | None
    failure_category: FailureCategory | None
    error_code: str | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.backend or not self.session_id or self.reset_epoch < 0:
            raise ValueError("run identity is invalid")
        if not _SHA256.fullmatch(self.policy_sha256) or not _SHA256.fullmatch(
            self.bundle_sha256
        ):
            raise ValueError("result provenance hashes must be complete SHA-256 values")


def classify_run(
    *,
    backend: str,
    session_id: str,
    reset_epoch: int,
    policy_sha256: str,
    bundle_sha256: str,
    error_code: str | None,
    evidence_valid: bool,
    first_failed_phase: str | None = None,
    failure_category: FailureCategory | None = None,
    evidence_refs: tuple[str, ...] = (),
    rejected: bool = False,
    qualified: bool = False,
) -> RunResultManifest:
    if not evidence_valid:
        run_status = ExecutionRunStatus.INVALID
    elif rejected:
        run_status = ExecutionRunStatus.REJECTED
    elif error_code is not None:
        run_status = ExecutionRunStatus.FAILED
    else:
        run_status = ExecutionRunStatus.SUCCEEDED
    qualification_status = (
        QualificationStatus.QUALIFIED
        if run_status is ExecutionRunStatus.SUCCEEDED and qualified
        else QualificationStatus.NOT_QUALIFIED
    )
    return RunResultManifest(
        run_status,
        qualification_status,
        backend,
        session_id,
        reset_epoch,
        policy_sha256,
        bundle_sha256,
        first_failed_phase,
        failure_category,
        error_code,
        evidence_refs,
    )


def write_run_result(path: Path, result: RunResultManifest) -> Path:
    """Atomically persist the stable, backend-neutral result wire schema."""

    document = {
        "backend": result.backend,
        "bundle_sha256": result.bundle_sha256,
        "error_code": result.error_code,
        "evidence_refs": list(result.evidence_refs),
        "failure_category": (
            None if result.failure_category is None else result.failure_category.value
        ),
        "first_failed_phase": result.first_failed_phase,
        "policy_sha256": result.policy_sha256,
        "qualification_status": result.qualification_status.value,
        "reset_epoch": result.reset_epoch,
        "run_status": result.run_status.value,
        "schema": "so101-run-result-v1",
        "session_id": result.session_id,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return path
