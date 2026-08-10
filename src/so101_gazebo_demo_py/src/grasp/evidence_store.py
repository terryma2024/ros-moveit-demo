"""Durable physical-grasp retry sidecar."""

from dataclasses import dataclass
from enum import StrEnum
import json
import math
from pathlib import Path
from typing import Any, Mapping

from ..checkpoint import _atomic_write
from ..domain import Failure, FailureCategory


class RetryPhase(StrEnum):
    IDLE = "IDLE"
    OPEN_PENDING = "OPEN_PENDING"
    DESCEND_PENDING = "DESCEND_PENDING"
    CLOSE_PENDING = "CLOSE_PENDING"
    LIFT_PENDING = "LIFT_PENDING"
    VERIFY_PENDING = "VERIFY_PENDING"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True, slots=True)
class PhysicalGraspEvidence:
    simulation_session_id: str
    policy_bundle_sha256: str
    attempt_index: int
    contact_missing_count: int
    current_reclose_target_q6: float
    micro_lift_preload_target_q6: float
    phase: RetryPhase
    before_lift: Mapping[str, Any] | None
    after_lift: Mapping[str, Any] | None
    schema_version: int = 2


def _failure(code: str, message: str) -> Failure:
    return Failure(FailureCategory.OBSERVATION, code, message)


class FilePhysicalGraspEvidenceStore:
    def __init__(self, path: Path, simulation_session_id: str, policy_bundle_sha256: str) -> None:
        self.path = Path(path)
        self.simulation_session_id = simulation_session_id
        self.policy_bundle_sha256 = policy_bundle_sha256

    @staticmethod
    def _valid(value: PhysicalGraspEvidence) -> bool:
        return (
            value.schema_version == 2 and 1 <= value.attempt_index <= 5
            and 0 <= value.contact_missing_count < value.attempt_index
            and math.isfinite(value.current_reclose_target_q6)
            and math.isfinite(value.micro_lift_preload_target_q6)
        )

    def commit(self, evidence: PhysicalGraspEvidence) -> Failure | None:
        if not self._valid(evidence):
            return _failure("PHYSICAL_GRASP_EVIDENCE_RETRY_INVALID", "retry evidence is invalid")
        document = {
            "schema_version": 2,
            "simulation_session_id": evidence.simulation_session_id,
            "configuration_fingerprint": evidence.policy_bundle_sha256,
            "retry": {
                "attempt_index": evidence.attempt_index,
                "contact_missing_count": evidence.contact_missing_count,
                "current_reclose_target_q6": evidence.current_reclose_target_q6,
                "micro_lift_preload_target_q6": evidence.micro_lift_preload_target_q6,
                "phase": evidence.phase.value,
            },
            "before_lift": evidence.before_lift,
            "after_lift": evidence.after_lift,
        }
        failure = _atomic_write(
            self.path,
            json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
            "PHYSICAL_GRASP_EVIDENCE",
        )
        if failure is None:
            return None
        return _failure(failure.code, failure.message)

    def load(self) -> tuple[PhysicalGraspEvidence | None, Failure | None]:
        try:
            document = json.loads(self.path.read_text())
            retry = document["retry"]
            value = PhysicalGraspEvidence(
                simulation_session_id=str(document["simulation_session_id"]),
                policy_bundle_sha256=str(document["configuration_fingerprint"]),
                attempt_index=int(retry["attempt_index"]),
                contact_missing_count=int(retry["contact_missing_count"]),
                current_reclose_target_q6=float(retry["current_reclose_target_q6"]),
                micro_lift_preload_target_q6=float(retry["micro_lift_preload_target_q6"]),
                phase=RetryPhase(retry["phase"]), before_lift=document["before_lift"],
                after_lift=document["after_lift"], schema_version=int(document["schema_version"]),
            )
        except FileNotFoundError:
            return None, _failure("PHYSICAL_GRASP_EVIDENCE_MISSING", "sidecar is missing")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return None, _failure("PHYSICAL_GRASP_EVIDENCE_CORRUPT", str(error))
        if value.simulation_session_id != self.simulation_session_id:
            return None, _failure("PHYSICAL_GRASP_EVIDENCE_SESSION_MISMATCH", "session differs")
        if value.policy_bundle_sha256 != self.policy_bundle_sha256:
            return None, _failure("PHYSICAL_GRASP_EVIDENCE_FINGERPRINT_MISMATCH", "fingerprint differs")
        if not self._valid(value):
            return None, _failure("PHYSICAL_GRASP_EVIDENCE_RETRY_INVALID", "retry evidence is invalid")
        return value, None

    def resume_failure(self) -> Failure | None:
        value, failure = self.load()
        if failure is not None:
            return failure
        if value is not None and value.phase not in (RetryPhase.IDLE, RetryPhase.COMPLETE):
            return _failure("PHYSICAL_GRASP_RETRY_INTERRUPTED", f"retry stopped at {value.phase.value}")
        return None

    def reset_for_fresh_run(self) -> Failure | None:
        try:
            self.path.unlink(missing_ok=True)
            return None
        except OSError as error:
            return _failure("PHYSICAL_GRASP_EVIDENCE_RESET_FAILED", str(error))
