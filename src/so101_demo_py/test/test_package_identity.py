import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import setuptools

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_ament_and_python_package_identities_are_distinct() -> None:
    """Catch publishing the Python namespace as the ament package identity or vice versa."""

    package_root = ET.parse(PACKAGE_ROOT / "package.xml").getroot()
    assert package_root.findtext("name") == "so101_demo_py"
    assert (PACKAGE_ROOT / "resource" / "so101_demo_py").is_file()
    assert (PACKAGE_ROOT / "src" / "__init__.py").is_file()


def test_setup_installs_the_mapped_namespace(monkeypatch) -> None:
    """Catch omitting package discovery for modules below the mapped namespace root."""

    captured: dict[str, object] = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured.update(kwargs))
    monkeypatch.chdir(PACKAGE_ROOT)
    runpy.run_path(str(PACKAGE_ROOT / "setup.py"), run_name="__main__")

    packages = set(captured["packages"])
    assert {
        "so101_demo",
        "so101_demo.application",
        "so101_demo.backends.mujoco",
        "so101_demo.control.moveit",
    } <= packages
    assert all(package == "so101_demo" or package.startswith("so101_demo.") for package in packages)
    assert captured["package_dir"] == {"so101_demo": "src"}


def test_setup_publishes_unified_runtime_commands(monkeypatch) -> None:
    """Catch an installed package that cannot run its migrated workflow or qualification CLI."""

    captured: dict[str, object] = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured.update(kwargs))
    monkeypatch.chdir(PACKAGE_ROOT)
    runpy.run_path(str(PACKAGE_ROOT / "setup.py"), run_name="__main__")

    assert set(captured["entry_points"]["console_scripts"]) >= {
        "fixed_cup_pick_place = so101_demo.cli.fixed_cup_pick_place:main",
        "dynamic_cup_pick_place = so101_demo.cli.dynamic_cup_pick_place:main",
        "run_qualification = so101_demo.cli.qualification:main",
    }
