from pathlib import Path

LEGACY_NAMES = ("so101_mujoco_demo_py", "so101_gazebo_demo_py")
TEXT_SUFFIXES = {".xml", ".sdf", ".xacro", ".urdf", ".yaml", ".json", ".md"}


def _share(request) -> Path:
    installed = request.config.getoption("--installed-share")
    return installed or Path(__file__).parents[1]


def test_assets_have_backend_entrypoints_and_resolve_locally(request) -> None:
    share = _share(request)
    required = (
        "assets/mujoco/scene.xml",
        "assets/mujoco/so101.xml",
        "assets/gazebo/world.sdf",
        "assets/gazebo/so101_prepared.sdf",
        "assets/gazebo/urdf/so101.urdf.xacro",
    )
    assert all((share / relative).is_file() for relative in required)


def test_installed_assets_do_not_reference_legacy_packages(request) -> None:
    share = _share(request)
    violations = []
    for path in (share / "assets").rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            if any(name in text for name in LEGACY_NAMES):
                violations.append(str(path.relative_to(share)))
    assert violations == []


def test_mujoco_and_gazebo_collision_trees_are_nonempty_and_distinct(request) -> None:
    share = _share(request)
    mujoco = {path.name for path in (share / "assets/mujoco/collision").rglob("*.stl")}
    gazebo = {
        str(path.relative_to(share / "assets/gazebo/collision"))
        for path in (share / "assets/gazebo/collision").rglob("*.stl")
    }
    assert len(mujoco) >= 27
    assert len(gazebo) > len(mujoco)
    assert mujoco != gazebo
