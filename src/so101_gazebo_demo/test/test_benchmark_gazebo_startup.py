"""Unit tests for deterministic SO101 Gazebo startup measurements."""

import importlib.util
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE_DIR / 'scripts' / 'benchmark_gazebo_startup.py'


def load_module():
    assert SCRIPT.exists(), 'startup benchmark utility is missing'
    spec = importlib.util.spec_from_file_location('benchmark_gazebo_startup', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_active_controller_evidence_requires_all_three():
    module = load_module()
    text = (
        'joint_state_broadcaster joint_state_broadcaster/JointStateBroadcaster active\n'
        'arm_controller joint_trajectory_controller/JointTrajectoryController active\n'
        'gripper_controller joint_trajectory_controller/JointTrajectoryController active\n'
    )

    assert module.controllers_ready(text)
    assert not module.controllers_ready('arm_controller active\n')


def test_summary_uses_median_and_records_piece_count():
    module = load_module()

    result = module.summarize([12.0, 9.0, 10.0], piece_count=64)

    assert result == {
        'durations_seconds': [12.0, 9.0, 10.0],
        'median_seconds': 10.0,
        'piece_count': 64,
        'success': True,
    }
