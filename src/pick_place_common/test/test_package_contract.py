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
