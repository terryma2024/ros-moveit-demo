from pathlib import Path

PACKAGE=Path(__file__).parents[1]


def test_pick_place_launch_has_safe_defaults_and_python_executable() -> None:
    text=(PACKAGE/"launch/so101_pick_place.launch.py").read_text()
    assert 'default_value="dry_run"' in text
    assert 'default_value="false"' in text
    assert 'executable="pick_place_state_machine"' in text
    assert 'package="so101_gazebo_demo_py"' in text
    assert "so101_gazebo.launch.py" in text and "so101_move_group_headless.launch.py" in text
