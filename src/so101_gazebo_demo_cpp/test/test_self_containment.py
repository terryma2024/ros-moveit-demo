from pathlib import Path
import re


PACKAGE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = ('config', 'launch', 'rviz', 'scripts', 'urdf', 'worlds')
TOP_LEVEL_RUNTIME_FILES = ('package.xml', 'CMakeLists.txt')
FORBIDDEN = (
    '/data/work/so101_lerobot_ws',
    'lerobot_description',
    'lerobot_controller',
    'lerobot_moveit',
)


def test_runtime_files_have_no_legacy_package_or_workspace_reference():
    offenders = []
    paths = [PACKAGE_DIR / name for name in TOP_LEVEL_RUNTIME_FILES]
    for root_name in RUNTIME_ROOTS:
        paths.extend(
            path
            for path in (PACKAGE_DIR / root_name).rglob('*')
            if path.is_file()
            and path.suffix
            in {'.py', '.xacro', '.urdf', '.sdf', '.yaml', '.rviz'}
        )
    for path in paths:
        text = path.read_text(errors='ignore')
        for forbidden in FORBIDDEN:
            if forbidden in text:
                offenders.append((str(path.relative_to(PACKAGE_DIR)), forbidden))
    assert not offenders, offenders


def test_readme_allows_only_the_explicit_source_workspace_provenance():
    source_workspace = '/data/work/so101_lerobot_ws'
    readme = (PACKAGE_DIR / 'README.md').read_text()

    assert readme.count(source_workspace) == 1
    readme_without_provenance = readme.replace(source_workspace, '')
    offenders = [value for value in FORBIDDEN if value in readme_without_provenance]
    assert not offenders, offenders


def test_compiled_workspace_sampler_uses_current_ros_package_identity():
    source = (PACKAGE_DIR / 'src/nodes/sample_so101_workspace.cpp').read_text()

    assert 'get_package_prefix("so101_gazebo_demo_cpp")' in source
    assert 'get_package_prefix("so101_gazebo_demo")' not in source


def test_active_python_helpers_do_not_invoke_or_resolve_the_old_ros_package():
    obsolete_patterns = (
        re.compile(
            r"/\s*['\"](?:build|lib)['\"]\s*/\s*['\"]so101_gazebo_demo['\"]\s*/"
        ),
        re.compile(
            r"['\"]ros2['\"]\s*,\s*['\"](?:run|launch)['\"]\s*,\s*"
            r"['\"]so101_gazebo_demo['\"]"
        ),
    )
    offenders = []
    for path in PACKAGE_DIR.rglob('*.py'):
        if path == Path(__file__):
            continue
        text = path.read_text(errors='ignore')
        for pattern in obsolete_patterns:
            if pattern.search(text):
                offenders.append((str(path.relative_to(PACKAGE_DIR)), pattern.pattern))

    assert not offenders, offenders
