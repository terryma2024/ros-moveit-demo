from configparser import ConfigParser
from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[1]
DEFAULT_TEST_ROOT = PACKAGE_ROOT / "test"
BENCHMARK_TEST_ROOT = PACKAGE_ROOT / "benchmark_test"
BENCHMARK_PATTERN = "test_perception_benchmark_*.py"


def _benchmark_test_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.rglob(BENCHMARK_PATTERN)))


def test_low_frequency_benchmark_tests_are_outside_default_package_suite() -> None:
    misplaced = _benchmark_test_files(DEFAULT_TEST_ROOT)
    benchmark_files = _benchmark_test_files(BENCHMARK_TEST_ROOT)

    assert misplaced == ()
    assert benchmark_files


def test_package_pytest_defaults_to_the_fast_test_tree() -> None:
    configuration = ConfigParser()
    configuration.read(PACKAGE_ROOT / "setup.cfg")

    configured = configuration.get("tool:pytest", "testpaths", fallback="")
    configured_paths = configured.splitlines()
    assert [path.strip() for path in configured_paths if path.strip()] == ["test"]
