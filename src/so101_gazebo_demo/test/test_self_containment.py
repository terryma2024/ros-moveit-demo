from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = ('config', 'launch', 'rviz', 'scripts', 'urdf', 'worlds')
FORBIDDEN = (
    '/data/work/so101_lerobot_ws',
    'lerobot_description',
    'lerobot_controller',
    'lerobot_moveit',
)


def test_runtime_files_have_no_legacy_package_or_workspace_reference():
    offenders = []
    for root_name in RUNTIME_ROOTS:
        for path in (PACKAGE_DIR / root_name).rglob('*'):
            if path.is_file() and path.suffix in {'.py', '.xacro', '.urdf', '.sdf', '.yaml', '.rviz'}:
                text = path.read_text(errors='ignore')
                for forbidden in FORBIDDEN:
                    if forbidden in text:
                        offenders.append((str(path.relative_to(PACKAGE_DIR)), forbidden))
    assert not offenders, offenders
