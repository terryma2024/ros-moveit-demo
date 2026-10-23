"""Dependency resolvers must select the exact NumPy version tested for each host."""

import runpy

import pytest
import setuptools
from packaging.requirements import Requirement
from paths import PACKAGE_ROOT

LOCK_PATH = PACKAGE_ROOT / "config/ik/requirements.lock"


def _setup_metadata(monkeypatch):
    captured = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured.update(kwargs))
    monkeypatch.chdir(PACKAGE_ROOT)
    runpy.run_path(str(PACKAGE_ROOT / "setup.py"), run_name="__main__")
    return captured


@pytest.mark.parametrize("host,version,rejected", [
    ("linux", "1.26.4", ("1.26.3", "1.27.0", "2.4.6", "1.26.4rc1")),
    ("darwin", "2.4.6", ("2.4.5", "2.5.0", "1.26.4", "2.4.6rc1")),
])
def test_installer_selects_only_the_tested_platform_numpy(monkeypatch, host, version, rejected):
    metadata = _setup_metadata(monkeypatch)
    requirements = [Requirement(value) for value in metadata["install_requires"]]
    selected = [req for req in requirements if req.name == "numpy"
                and (req.marker is None or req.marker.evaluate({"sys_platform": host}))]
    assert len(selected) == 1, f"missing or ambiguous NumPy constraint on {host}"
    assert str(selected[0].specifier) == f"=={version}"
    assert selected[0].specifier.contains(version)
    assert all(not selected[0].specifier.contains(value) for value in rejected)


def test_installed_lock_and_package_metadata_share_the_same_constraints(monkeypatch):
    metadata = _setup_metadata(monkeypatch)
    installed = {(destination, source) for destination, sources in metadata["data_files"]
                 for source in sources}
    assert ("share/so101_demo_py/config/ik", "config/ik/requirements.lock") in installed
    locked = [Requirement(line) for line in LOCK_PATH.read_text().splitlines()
              if line.strip() and not line.lstrip().startswith("#")]
    declared = [Requirement(value) for value in metadata["install_requires"]
                if Requirement(value).name == "numpy"]
    assert len(locked) == 2
    assert [str(req) for req in declared] == [str(req) for req in locked]
