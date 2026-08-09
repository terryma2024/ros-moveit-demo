from pathlib import Path
import os
import subprocess

from ament_index_python.packages import get_package_prefix, get_package_share_directory


LAUNCHES={"so101_display.launch.py","so101_controller.launch.py","so101_gazebo.launch.py","so101_moveit.launch.py","so101_move_group_headless.launch.py","so101_pick_place.launch.py"}
EXECUTABLES={"pick_place_state_machine","gazebo_attachment_state_relay","reset_so101_world","so101_moveit_scene"}


def test_installed_package_is_self_contained() -> None:
    share=Path(get_package_share_directory("so101_gazebo_demo_py")); prefix=Path(get_package_prefix("so101_gazebo_demo_py"))
    assert LAUNCHES <= {path.name for path in (share/"launch").glob("*.launch.py")}
    binaries=prefix/"lib/so101_gazebo_demo_py"
    assert EXECUTABLES <= {path.name for path in binaries.iterdir()}
    forbidden=("get_package_share_directory(\"so101_gazebo_demo\")","ros2 run so101_gazebo_demo ","libso101_attachment_collision_system.so","package://so101_gazebo_demo/")
    for root in (share,prefix/"lib/python3.12/site-packages/so101_gazebo_demo_py"):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix not in (".pyc",".stl",".dae") and "provenance.json" not in path.name:
                text=path.read_text(errors="ignore")
                assert not any(value in text for value in forbidden), path


def test_console_scripts_do_not_resolve_old_package() -> None:
    environment={**os.environ,"PYTHONNOUSERSITE":"1"}
    for executable in EXECUTABLES - {"gazebo_attachment_state_relay"}:
        completed=subprocess.run(["ros2","run","so101_gazebo_demo_py",executable,"--help"],env=environment,text=True,capture_output=True,timeout=10)
        assert completed.returncode == 0, (executable,completed.stderr)
