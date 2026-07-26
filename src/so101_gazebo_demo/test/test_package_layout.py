from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE_DIR = Path(__file__).resolve().parents[1]


def test_single_package_has_expected_identity():
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    assert package.findtext('name') == 'so101_gazebo_demo'
    assert not list(PACKAGE_DIR.glob('*/package.xml'))


def test_package_records_verified_source_provenance():
    readme = (PACKAGE_DIR / 'README.md').read_text()
    assert '/data/work/so101_lerobot_ws' in readme
    assert '65c371e' in readme


def test_installed_tool_dependencies_are_declared_directly():
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    dependencies = {
        element.text
        for tag in ('depend', 'exec_depend')
        for element in package.findall(tag)
    }

    assert {'ament_index_python', 'python3-numpy', 'libx11'} <= dependencies


def test_attachment_bridge_message_dependency_is_declared_directly():
    """Catch a package that launches std_msgs bridges without declaring them."""
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    dependencies = {
        element.text
        for tag in ('depend', 'exec_depend')
        for element in package.findall(tag)
    }

    assert 'std_msgs' in dependencies
