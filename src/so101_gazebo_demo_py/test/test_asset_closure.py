from pathlib import Path


PACKAGE = Path(__file__).parents[1]
REQUIRED = (
    "config/initial_positions.yaml", "config/joint_limits.yaml",
    "config/kinematics.yaml", "config/moveit_controllers.yaml",
    "config/ompl_planning.yaml", "config/so101_controllers.yaml",
    "config/so101.srdf", "config/motion_policies/light_cup_wall_pick.yaml",
    "config/task_objects/light_plastic_cup.yaml",
    "config/validation_policies/light_cup_wall_pick.yaml",
    "urdf/so101.urdf.xacro", "urdf/so101_base.xacro",
    "urdf/so101_gazebo.xacro", "urdf/so101_ros2_control.xacro",
    "worlds/so101_pick_place.sdf", "rviz/display.rviz",
    "models/so101_prepared.sdf",
    "meshes/so101/base_so101_v2.stl",
    "meshes/so101/generated/fixed/fingertip_pad.stl",
    "meshes/so101/generated/fixed/fingertip_pad_collision_006.stl",
    "meshes/so101/generated/moving/fingertip_pad.stl",
    "meshes/so101/generated/moving/fingertip_pad_collision_005.stl",
)


def test_required_runtime_assets_are_package_local() -> None:
    missing = [relative for relative in REQUIRED if not (PACKAGE / relative).is_file()]
    assert missing == []


def test_text_assets_have_no_forbidden_runtime_reference() -> None:
    forbidden = (
        "package://so101_gazebo_demo_cpp/",
        "libso101_attachment_collision_system.so",
        "/data/work",
    )
    candidates = [
        path for folder in ("config", "urdf", "models", "worlds", "rviz")
        for path in (PACKAGE / folder).rglob("*") if path.is_file()
    ]
    violations = {
        str(path.relative_to(PACKAGE)): token
        for path in candidates
        for token in forbidden
        if token in path.read_text(errors="ignore")
    }
    assert violations == {}
