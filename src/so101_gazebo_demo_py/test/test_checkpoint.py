import json
import os
from pathlib import Path
import stat

from so101_gazebo_demo_py.checkpoint import (
    Checkpoint, CheckpointPhase, ExpectedWorldState, FileCheckpointStore,
)
from so101_gazebo_demo_py.domain import Failure, FailureCategory, RunMode, State


def checkpoint(sequence: int = 4) -> Checkpoint:
    return Checkpoint(
        run_id="run-1", sequence=sequence, source_mode=RunMode.EXECUTE,
        phase=CheckpointPhase.FORWARD, last_completed_state=State.DESCEND,
        failed_state=None, original_failure=None, next_state=State.CLOSE_GRIPPER,
        expected=ExpectedWorldState(
            tcp_pose_world=(0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0),
            gripper_open=True, joint_positions={"1": 0.1},
            moveit_world_object_poses={"plastic_cup": (0.0, -0.28, 0.165, 0, 0, 0, 1)},
            moveit_task_object_attached=False,
            gazebo_task_object_pose_world=(0.0, -0.28, 0.165, 0, 0, 0, 1),
            gazebo_task_object_attached=False, gazebo_task_object_stationary=True,
            required_world_objects=("plastic_cup", "table", "pedestal"),
        ),
        policy_bundle_sha256="a" * 64, simulation_session_id="sim-1", resumable=True,
    )


def test_checkpoint_round_trips_schema_three_with_owner_permissions(tmp_path: Path) -> None:
    path = tmp_path / "state/checkpoint.json"
    store = FileCheckpointStore(path)
    assert store.commit(checkpoint()) is None
    loaded, failure = store.load()
    assert failure is None
    assert loaded == checkpoint()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 3
    assert payload["policy_bundle_sha256"] == "a" * 64


def test_corrupt_and_missing_checkpoint_fail_closed(tmp_path: Path) -> None:
    store = FileCheckpointStore(tmp_path / "checkpoint.json")
    assert store.load()[1].code == "CHECKPOINT_NOT_FOUND"
    store.path.write_text("{")
    assert store.load()[1].code == "CHECKPOINT_PARSE_FAILED"


def test_failed_atomic_replace_preserves_prior_file(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "checkpoint.json"
    store = FileCheckpointStore(path)
    assert store.commit(checkpoint()) is None
    before = path.read_bytes()
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("no")))
    failure = store.commit(checkpoint(5))
    assert failure.code == "CHECKPOINT_RENAME_FAILED"
    assert path.read_bytes() == before
