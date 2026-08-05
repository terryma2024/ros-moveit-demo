from pathlib import Path
import re
import xml.etree.ElementTree as ET


PACKAGE_DIR = Path(__file__).resolve().parents[1]

USER_FACING_TOOLS = (
    'tile_ai_station_guis.py',
    'gazebo_camera_pose.py',
    'so101_stack_inventory.py',
    'gazebo_window_recorder.py',
    'video_extract_frame.py',
    'video_sample_frames.py',
    'video_mosaic.py',
)

IMPORT_ONLY_MODULE = 'ai_station_x11.py'


def _install_blocks(cmake_text, keyword):
    """Return install(<keyword> ...) blocks as token lists."""
    blocks = []
    for match in re.finditer(r'install\s*\(([^)]*)\)', cmake_text, re.DOTALL):
        tokens = match.group(1).split()
        if tokens and tokens[0] == keyword:
            blocks.append(tokens)
    return blocks


def _installed_scripts(blocks):
    return {
        token.removeprefix('scripts/')
        for block in blocks
        for token in block
        if token.startswith('scripts/') and token.endswith('.py')
    }


def _destinations(block):
    return {
        block[index + 1]
        for index, token in enumerate(block[:-1])
        if token == 'DESTINATION'
    }


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


def test_workspace_sampler_is_installed_with_direct_moveit_dependencies():
    cmake = (PACKAGE_DIR / 'CMakeLists.txt').read_text()
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    dependencies = {
        element.text for tag in ('buildtool_depend', 'depend', 'exec_depend')
        for element in package.findall(tag)
    }
    assert 'add_executable(sample_so101_workspace' in cmake
    assert 'sample_so101_workspace' in cmake.split('install(', 1)[1]
    assert {'moveit_core', 'moveit_ros_planning'} <= dependencies
    assert (PACKAGE_DIR / 'launch' / 'so101_workspace_sample.launch.py').is_file()
    assert (PACKAGE_DIR / 'docs' / 'so101-workspace-sampler.md').is_file()
    assert 'so101-workspace-sampler.md' in (PACKAGE_DIR / 'README.md').read_text()


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


def test_user_facing_tools_are_installed_as_executables():
    cmake_text = (PACKAGE_DIR / 'CMakeLists.txt').read_text()
    blocks = _install_blocks(cmake_text, 'PROGRAMS')
    installed = _installed_scripts(blocks)

    for tool in USER_FACING_TOOLS:
        assert tool in installed, f'{tool} missing from install(PROGRAMS ...)'

    for block in blocks:
        if _installed_scripts([block]) & set(USER_FACING_TOOLS):
            assert 'lib/${PROJECT_NAME}' in _destinations(block)


def test_shared_x11_module_is_installed_as_plain_file():
    cmake_text = (PACKAGE_DIR / 'CMakeLists.txt').read_text()
    program_blocks = _install_blocks(cmake_text, 'PROGRAMS')
    file_blocks = _install_blocks(cmake_text, 'FILES')

    assert IMPORT_ONLY_MODULE not in _installed_scripts(program_blocks), (
        f'{IMPORT_ONLY_MODULE} must not be installed as an executable'
    )

    module_blocks = [
        block for block in file_blocks
        if IMPORT_ONLY_MODULE in _installed_scripts([block])
    ]
    assert module_blocks, (
        f'{IMPORT_ONLY_MODULE} missing from install(FILES ...)'
    )
    assert any(
        'lib/${PROJECT_NAME}' in _destinations(block)
        for block in module_blocks
    ), f'{IMPORT_ONLY_MODULE} must install into lib/${{PROJECT_NAME}}'
