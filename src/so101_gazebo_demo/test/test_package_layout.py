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
        for tag in ('buildtool_depend', 'depend', 'exec_depend')
        for element in package.findall(tag)
    }

    assert {'ament_index_python', 'python3-numpy', 'libx11'} <= dependencies


def test_attachment_bridge_message_dependency_is_declared_directly():
    """Catch a package that launches std_msgs bridges without declaring them."""
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    dependencies = {
        element.text
        for tag in ('buildtool_depend', 'depend', 'exec_depend')
        for element in package.findall(tag)
    }

    assert 'std_msgs' in dependencies


def test_teleop_server_runtime_dependencies_are_declared_directly():
    """Removing a direct Teleop dependency must fail before an installed server starts."""
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    dependencies = {
        element.text
        for tag in ('buildtool_depend', 'depend', 'exec_depend')
        for element in package.findall(tag)
    }

    assert {
        'ament_cmake_python', 'rclpy', 'tf2_ros', 'controller_manager_msgs',
        'python3-fastapi', 'python3-uvicorn', 'python3-pydantic', 'python3-pil', 'python3-yaml',
    } <= dependencies


def test_teleop_has_deterministic_contract_and_launchable_lifecycle_files():
    """Dropping a public launch/config/OpenAPI entrypoint must break package acceptance."""
    expected = (
        PACKAGE_DIR / 'so101_teleop' / 'service.py',
        PACKAGE_DIR / 'so101_teleop' / 'openapi_export.py',
        PACKAGE_DIR / 'so101_teleop' / 'openapi.json',
        PACKAGE_DIR / 'so101_teleop' / 'main.py',
        PACKAGE_DIR / 'launch' / 'so101_teleop.launch.py',
        PACKAGE_DIR / 'config' / 'so101_teleop.yaml',
    )
    assert all(path.is_file() for path in expected)


def test_teleop_incremental_build_tracks_all_frontend_modules_and_installs_operator_docs():
    """Changing a split component must rebuild the bundle and ship the matching operator guide."""
    cmake = (PACKAGE_DIR / 'CMakeLists.txt').read_text()
    assert 'SO101_TELEOP_WEB_SOURCES' in cmake
    assert '${SO101_TELEOP_WEB_SOURCES}' in cmake
    assert 'DIRECTORY config docs launch meshes rviz scripts urdf worlds' in cmake


def test_teleop_web_preflight_bun_and_canonical_manual_are_packaged():
    assert (PACKAGE_DIR / 'so101_teleop' / 'web_bundle.py').is_file()
    assert (PACKAGE_DIR / 'web' / '.node-version').read_text().strip() == '24.18.1'
    assert (PACKAGE_DIR / 'docs' / 'so101-teleop-web-ui.md').is_file()
    launch = (PACKAGE_DIR / 'launch' / 'so101_teleop.launch.py').read_text()
    assert 'DeclareLaunchArgument("build_web_if_needed", default_value="true")' in launch
    assert 'DeclareLaunchArgument("web_source_dir", default_value="")' in launch
    cmake = (PACKAGE_DIR / 'CMakeLists.txt').read_text()
    assert 'SO101_TELEOP_BUN' in cmake
    assert 'install --frozen-lockfile' in cmake
    assert '${SO101_TELEOP_WEB_ROOT}/bun.lock' in cmake
