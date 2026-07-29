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
