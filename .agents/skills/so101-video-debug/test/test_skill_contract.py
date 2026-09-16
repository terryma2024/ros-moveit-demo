from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def test_skill_routes_gazebo_and_mujoco_without_mixing_backends():
    skill = (SKILL_ROOT / "SKILL.md").read_text()

    assert "backend: gazebo | mujoco" in skill
    assert "simulator_window_recorder.py" in skill
    assert "camera_preset --backend mujoco" in skill
    assert "Gazebo" in skill
    assert "MuJoCo" in skill
    assert "不得在同一轮实验中切换 backend" in skill


def test_report_template_records_backend_specific_physics_and_clock():
    template = (SKILL_ROOT / "references" / "report-template.md").read_text()

    assert "backend: `gazebo | mujoco`" in template
    assert "仿真时钟" in template
    assert "Gazebo 专属" in template
    assert "MuJoCo 专属" in template
