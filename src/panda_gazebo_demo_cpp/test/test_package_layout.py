from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_package_identity_and_cpp_api_boundary() -> None:
    package = ET.parse(PACKAGE_ROOT / 'package.xml').getroot()
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')

    assert PACKAGE_ROOT.name == 'panda_gazebo_demo_cpp'
    assert package.findtext('name') == 'panda_gazebo_demo_cpp'
    assert 'project(panda_gazebo_demo_cpp)' in cmake
    assert (PACKAGE_ROOT / 'include' / 'panda_gazebo_demo').is_dir()
    assert not (PACKAGE_ROOT / 'include' / 'panda_gazebo_demo_cpp').exists()
