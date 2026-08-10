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


def test_physical_outcome_implementation_and_headers_are_manifested() -> None:
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    for source in (
        'final_placement_evaluator.cpp',
        'final_placement_evidence_store.cpp',
        'release_settle_executor.cpp',
        'support_pose.cpp',
    ):
        assert f'src/pick_place/{source}' in cmake
    assert re.search(r'install\s*\(\s*DIRECTORY[^)]*\binclude/', cmake, re.DOTALL)
