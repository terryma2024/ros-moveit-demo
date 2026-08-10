import json
from pathlib import Path

from so101_gazebo_demo.grasp.evidence_store import (
    FilePhysicalGraspEvidenceStore, PhysicalGraspEvidence, RetryPhase,
)


def evidence(phase: RetryPhase = RetryPhase.IDLE) -> PhysicalGraspEvidence:
    return PhysicalGraspEvidence(
        simulation_session_id="session", policy_bundle_sha256="b" * 64,
        attempt_index=2, contact_missing_count=1,
        current_reclose_target_q6=-0.048608632840292,
        micro_lift_preload_target_q6=-0.053608632840292,
        phase=phase, before_lift=None, after_lift=None,
    )


def test_grasp_sidecar_round_trips_retry_phase(tmp_path: Path) -> None:
    store = FilePhysicalGraspEvidenceStore(tmp_path / "grasp.json", "session", "b" * 64)
    assert store.commit(evidence(RetryPhase.LIFT_PENDING)) is None
    loaded, failure = store.load()
    assert failure is None
    assert loaded == evidence(RetryPhase.LIFT_PENDING)
    assert json.loads(store.path.read_text())["schema_version"] == 2


def test_grasp_sidecar_rejects_wrong_session_and_pending_resume(tmp_path: Path) -> None:
    path = tmp_path / "grasp.json"
    writer = FilePhysicalGraspEvidenceStore(path, "session", "b" * 64)
    assert writer.commit(evidence(RetryPhase.VERIFY_PENDING)) is None
    wrong = FilePhysicalGraspEvidenceStore(path, "other", "b" * 64)
    assert wrong.load()[1].code == "PHYSICAL_GRASP_EVIDENCE_SESSION_MISMATCH"
    assert writer.resume_failure().code == "PHYSICAL_GRASP_RETRY_INTERRUPTED"


def test_grasp_sidecar_rejects_invalid_attempts(tmp_path: Path) -> None:
    store = FilePhysicalGraspEvidenceStore(tmp_path / "grasp.json", "session", "b" * 64)
    invalid = PhysicalGraspEvidence(
        "session", "b" * 64, 6, 0, -0.04, -0.05, RetryPhase.IDLE, None, None
    )
    assert store.commit(invalid).code == "PHYSICAL_GRASP_EVIDENCE_RETRY_INVALID"
