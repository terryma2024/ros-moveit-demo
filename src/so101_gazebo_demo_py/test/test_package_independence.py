from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE = Path(__file__).parents[1]


def test_package_name_and_build_type() -> None:
    root = ET.parse(PACKAGE / "package.xml").getroot()
    assert root.findtext("name") == "so101_gazebo_demo_py"
    assert root.find("./export/build_type").text == "ament_python"


def test_forbidden_runtime_dependencies_absent() -> None:
    text = "\n".join(
        path.read_text(errors="ignore")
        for path in PACKAGE.rglob("*")
        if path.is_file()
        and ".pyc" not in path.name
        and "test" not in path.relative_to(PACKAGE).parts
    )
    assert "<depend>so101_gazebo_demo_cpp</depend>" not in text
    assert "<depend>pick_place_common</depend>" not in text
    assert 'get_package_share_directory("so101_gazebo_demo_cpp")' not in text
    assert "ros2 run so101_gazebo_demo_cpp " not in text
