"""Protect the simulator-neutral SO-101 video-debug skill contract."""

from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def test_skill_routes_gazebo_and_mujoco_without_mixing_backends():
    """The entrypoint must keep Gazebo and MuJoCo evidence separate."""
    skill = (SKILL_ROOT / 'SKILL.md').read_text()

    assert 'backend: gazebo | mujoco' in skill
    assert 'simulator_window_recorder.py' in skill
    assert 'camera_preset --backend mujoco' in skill
    assert 'Gazebo' in skill
    assert 'MuJoCo' in skill
    assert '不得在同一轮实验中切换 backend' in skill


def test_skill_defines_the_validated_mujoco_video_only_launch_contract():
    """The skill must expose the tested visible video-only launch mode."""
    skill = (SKILL_ROOT / 'SKILL.md').read_text()

    assert 'so101_mujoco.launch.py' in skill
    assert 'sensor_rendering:=false' in skill
    assert 'GLFW' in skill
    assert '不提供 `task_camera`' in skill


def test_report_template_records_backend_specific_physics_and_clock():
    """The report must keep simulator-specific physics and clock fields."""
    template = (SKILL_ROOT / 'references' / 'report-template.md').read_text()

    assert 'backend: `gazebo | mujoco`' in template
    assert '仿真时钟' in template
    assert 'Gazebo 专属' in template
    assert 'MuJoCo 专属' in template


def test_skill_uses_the_registered_durable_root_for_video_evidence():
    """Video artifacts must use the repository's durable evidence root."""
    skill = (SKILL_ROOT / 'SKILL.md').read_text()
    template = (SKILL_ROOT / 'references' / 'report-template.md').read_text()

    assert '/data/work/so101-evidence/' in skill
    assert '/data/work/so101-evidence/' in template
