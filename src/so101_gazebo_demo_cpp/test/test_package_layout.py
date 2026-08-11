from pathlib import Path
import re
import xml.etree.ElementTree as ET


PACKAGE_DIR = Path(__file__).resolve().parents[1]

USER_FACING_TOOLS = (
    'gazebo_camera_pose.py',
    'video_extract_frame.py',
    'video_sample_frames.py',
    'video_mosaic.py',
)

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
    cmake = (PACKAGE_DIR / 'CMakeLists.txt').read_text(encoding='utf-8')

    assert PACKAGE_DIR.name == 'so101_gazebo_demo_cpp'
    assert package.findtext('name') == 'so101_gazebo_demo_cpp'
    assert 'project(so101_gazebo_demo_cpp)' in cmake
    assert not list(PACKAGE_DIR.glob('*/package.xml'))
    assert (PACKAGE_DIR / 'include' / 'so101_gazebo_demo').is_dir()
    assert not (PACKAGE_DIR / 'include' / 'so101_gazebo_demo_cpp').exists()


def test_package_records_verified_source_provenance():
    readme = (PACKAGE_DIR / 'README.md').read_text()
    assert '/data/work/so101_lerobot_ws' in readme
    assert '65c371e' in readme


def test_operator_docs_assign_physical_truth_and_keep_reset_detach_defensive():
    readme = (PACKAGE_DIR / 'README.md').read_text()
    architecture = (PACKAGE_DIR.parents[1] / 'docs' / 'pick-place-architecture.md').read_text()

    assert 'Gazebo physics owns cup motion' in readme
    assert 'normal forward workflow never calls `ATTACH_GAZEBO` or `DETACH_GAZEBO`' in readme
    assert 'defensive Gazebo detach' in readme
    assert 'planning shadow' in architecture
    assert 'five consecutive' in architecture


def test_installed_tool_dependencies_are_declared_directly():
    package = ET.parse(PACKAGE_DIR / 'package.xml').getroot()
    dependencies = {
        element.text
        for tag in ('buildtool_depend', 'depend', 'exec_depend')
        for element in package.findall(tag)
    }

    assert {'ament_index_python', 'python3-numpy', 'ffmpeg'} <= dependencies
    assert not {
        'ament_cmake_python', 'python3-fastapi', 'python3-uvicorn',
        'libx11', 'libx11-6', 'x11-utils',
    } & dependencies


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


def test_user_facing_tools_are_installed_as_executables():
    cmake_text = (PACKAGE_DIR / 'CMakeLists.txt').read_text()
    blocks = _install_blocks(cmake_text, 'PROGRAMS')
    installed = _installed_scripts(blocks)

    for tool in USER_FACING_TOOLS:
        assert tool in installed, f'{tool} missing from install(PROGRAMS ...)'

    for block in blocks:
        if _installed_scripts([block]) & set(USER_FACING_TOOLS):
            assert 'lib/${PROJECT_NAME}' in _destinations(block)
