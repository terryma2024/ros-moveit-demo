from pathlib import Path
import xml.etree.ElementTree as ET


def test_common_package_exports_quality_gate_and_both_consumers_depend_on_it():
    root = Path(__file__).parents[1]
    cmake = (root / "CMakeLists.txt").read_text()
    package = ET.parse(root / "package.xml").getroot()
    assert package.findtext("name") == "pick_place_common"
    assert 'CONFIG_EXTRAS "cmake/pick_place_common-extras.cmake"' in cmake
    for consumer in (root.parent / "panda_gazebo_demo", root.parent / "so101_gazebo_demo"):
        assert "<depend>pick_place_common</depend>" in (consumer / "package.xml").read_text()
        assert "pick_place_common_add_cpp_quality_gate(" in (consumer / "CMakeLists.txt").read_text()


def test_robot_consumers_compile_only_the_shared_common_algorithms():
    root = Path(__file__).parents[1]
    consumers = (root.parent / "panda_gazebo_demo", root.parent / "so101_gazebo_demo")
    forbidden_sources = (
        "src/pick_place/runner.cpp",
        "src/pick_place/domain_types.cpp",
        "src/pick_place/state_action.cpp",
        "src/pick_place/gazebo_attachment_executor.cpp",
        "src/pick_place/moveit_scene_executor.cpp",
    )
    for consumer in consumers:
        cmake = (consumer / "CMakeLists.txt").read_text()
        for source in forbidden_sources:
            assert source not in cmake
        assert "pick_place_common::core" in cmake
        assert "pick_place_common::ros_adapters" in cmake
