from pathlib import Path
import re


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / 'src' / 'pick_place'
ALLOWLIST: dict[str, str] = {}


def _manifest_sources() -> set[str]:
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    cmake = '\n'.join(line.split('#', 1)[0] for line in cmake.splitlines())
    return set(re.findall(r'src/pick_place/[A-Za-z0-9_]+\.cpp', cmake))


def test_every_pick_place_implementation_is_in_the_build_manifest() -> None:
    tracked = {f'src/pick_place/{path.name}' for path in SOURCE_ROOT.glob('*.cpp')}
    unaccounted = sorted(tracked - _manifest_sources() - set(ALLOWLIST))

    assert not unaccounted, 'Unaccounted pick-place implementations:\n' + '\n'.join(
        unaccounted
    )
    assert all(ALLOWLIST.values()), 'Every allowlist entry must explain why it is not built'


def test_no_state_machine_bypass_executable_is_built_or_installed() -> None:
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'attach_and_lift_demo' not in cmake
    assert not (PACKAGE_ROOT / 'src' / 'attach_and_lift_demo.cpp').exists()
    assert not (PACKAGE_ROOT / 'include' / 'panda_gazebo_demo' / 'pick_place' /
                'headless_fault_fixture.hpp').exists()
