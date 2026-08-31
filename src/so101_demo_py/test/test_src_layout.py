import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import setuptools

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_python_namespace_uses_direct_mapped_src_layout() -> None:
    """Catch adding either setuptools' default nested package or a second namespace root."""

    assert (PACKAGE_ROOT / "src" / "__init__.py").is_file()
    assert not (PACKAGE_ROOT / "so101_demo_py").exists()
    assert not (PACKAGE_ROOT / "src" / "so101_demo_py").exists()


def test_setup_maps_so101_demo_namespace_to_src(monkeypatch) -> None:
    """Catch an import/package-name mapping that makes installed imports resolve elsewhere."""

    captured: dict[str, object] = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured.update(kwargs))
    monkeypatch.chdir(PACKAGE_ROOT)
    runpy.run_path(str(PACKAGE_ROOT / "setup.py"), run_name="__main__")

    assert captured["name"] == "so101_demo_py"
    assert captured["package_dir"] == {"so101_demo": "src"}
    assert "so101_demo" in captured["packages"]
    entry_points = captured["entry_points"]
    assert isinstance(entry_points, dict)
    assert (
        "rgbd_object_pose = so101_demo.cli.rgbd_object_pose:main"
        in entry_points["console_scripts"]
    )


def test_package_declares_vision_msgs_runtime_dependency() -> None:
    root = ET.parse(PACKAGE_ROOT / "package.xml").getroot()
    dependencies = {
        element.text
        for element in root
        if element.tag in {"depend", "exec_depend"}
    }
    assert "vision_msgs" in dependencies
