from pathlib import Path
import re
import xml.etree.ElementTree as ET


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LEGACY_IDENTITY = re.compile(
    r'(?<![A-Za-z0-9_])panda_gazebo_demo(?![A-Za-z0-9_])'
)
RUNTIME_IDENTITY_FILES = (
    PACKAGE_ROOT / 'launch' / 'panda_gazebo.launch.py',
    PACKAGE_ROOT / 'urdf' / 'panda.gazebo.urdf.xacro',
    PACKAGE_ROOT / 'scripts' / 'reset_world.sh',
    PACKAGE_ROOT / 'test' / 'scripts' / 'test_reset_world.sh',
    PACKAGE_ROOT / 'test' / 'headless' / 'run_pick_place_e2e.sh',
    PACKAGE_ROOT / 'test' / 'headless' / 'run_recovery_scenarios.sh',
    PACKAGE_ROOT / 'test' / 'headless' / 'run_plan_only_resume_matrix.sh',
)


def test_package_identity_and_cpp_api_boundary() -> None:
    package = ET.parse(PACKAGE_ROOT / 'package.xml').getroot()
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')

    assert PACKAGE_ROOT.name == 'panda_gazebo_demo_cpp'
    assert package.findtext('name') == 'panda_gazebo_demo_cpp'
    assert 'project(panda_gazebo_demo_cpp)' in cmake
    assert (PACKAGE_ROOT / 'include' / 'panda_gazebo_demo').is_dir()
    assert not (PACKAGE_ROOT / 'include' / 'panda_gazebo_demo_cpp').exists()


def test_runtime_entry_points_use_new_package_identity() -> None:
    offenders = [
        str(path.relative_to(PACKAGE_ROOT))
        for path in RUNTIME_IDENTITY_FILES
        if LEGACY_IDENTITY.search(path.read_text(encoding='utf-8'))
    ]
    assert not offenders, 'Legacy Panda ROS package identity in:\n' + '\n'.join(
        offenders
    )
