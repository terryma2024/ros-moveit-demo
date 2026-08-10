from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE = Path(__file__).parents[1]


def test_package_name_and_build_type() -> None:
    root = ET.parse(PACKAGE / "package.xml").getroot()
    assert root.findtext("name") == "so101_gazebo_demo_py"
    assert root.find("./export/build_type").text == "ament_python"


def test_python_package_uses_flat_src_layout_and_public_import_name() -> None:
    assert (PACKAGE / "src" / "__init__.py").is_file()
    assert not (PACKAGE / "so101_gazebo_demo_py").exists()

    setup_text = (PACKAGE / "setup.py").read_text()
    assert 'package_name = "so101_gazebo_demo_py"' in setup_text
    assert 'python_package = "so101_gazebo_demo"' in setup_text
    assert 'package_dir={python_package: "src"}' in setup_text


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
