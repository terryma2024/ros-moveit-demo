import json

from .run_behavior_matrix import run_behavior


def test_single_step_checkpoint_preserves_schema_and_resume_bindings(tmp_path) -> None:
    path=tmp_path/"checkpoint.json"
    result=run_behavior(["--mode","dry_run","--step","--checkpoint",str(path),"--session-id","session"])
    assert result["status"] == "CHECKPOINT_COMPLETE"
    document=json.loads(path.read_text())
    assert document["schema_version"] == 3
    assert document["simulation_session_id"] == "session"
    assert document["source_mode"] == "dry_run"
    assert document["last_completed_state"] == "PREPARE_OPEN_GRIPPER"
    assert document["next_state"] == "MOVE_ABOVE_OBJECT"


def test_max_transition_exhaustion_is_stable() -> None:
    result=run_behavior(["--mode","dry_run","--max-state-transitions","1"])
    assert result["exit_code"] == 1
    assert result["failure_code"] == "MAX_STATE_TRANSITIONS_EXCEEDED"
