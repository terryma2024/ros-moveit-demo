"""Every test module name is unique inside its package.

Test directories carry no ``__init__.py``, so pytest's default import mode imports a test file by its bare
file name. Two files with one name would collide in ``sys.modules``, and the shared helpers on ``pythonpath``
are imported by bare name too. The guard also keeps the test layout free to move files between directories
without a collision surfacing late.
"""

import pytest
import style_inventory as inventory
from paths import REPOSITORY

TESTED_PACKAGES = ("so101_demo_py", "so101_teleop", "so101_quik")


def test_a_repeated_basename_in_two_directories_is_reported(tmp_path):
    (tmp_path / "test" / "one").mkdir(parents=True)
    (tmp_path / "test" / "two").mkdir(parents=True)
    (tmp_path / "test" / "one" / "test_same.py").write_text("")
    (tmp_path / "test" / "two" / "test_same.py").write_text("")
    (tmp_path / "test" / "two" / "test_other.py").write_text("")

    assert inventory.duplicate_basenames(tmp_path) == {
        "test_same.py": ["test/one/test_same.py", "test/two/test_same.py"]
    }


def test_conftest_and_package_markers_may_repeat(tmp_path):
    for directory in ("one", "two"):
        (tmp_path / "test" / directory).mkdir(parents=True)
        (tmp_path / "test" / directory / "conftest.py").write_text("")
        (tmp_path / "test" / directory / "__init__.py").write_text("")

    assert inventory.duplicate_basenames(tmp_path) == {}


def test_helpers_and_benchmark_tests_share_one_namespace_with_the_tests(tmp_path):
    (tmp_path / "test" / "support").mkdir(parents=True)
    (tmp_path / "benchmark_test").mkdir()
    (tmp_path / "test" / "test_alpha.py").write_text("")
    (tmp_path / "test" / "support" / "helper.py").write_text("")
    (tmp_path / "benchmark_test" / "helper.py").write_text("")

    assert inventory.duplicate_basenames(tmp_path) == {
        "helper.py": ["benchmark_test/helper.py", "test/support/helper.py"]
    }


@pytest.mark.parametrize("package", TESTED_PACKAGES)
def test_test_basenames_are_unique_in_the_package(package):
    duplicates = inventory.duplicate_basenames(REPOSITORY / "src" / package)

    assert duplicates == {}, f"{package}: test file names must be unique; rename one of each pair: {duplicates}"
