import runpy
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
    runpy.run_path(str(PACKAGE_ROOT / "setup.py"), run_name="__main__")

    assert captured["name"] == "so101_demo_py"
    assert captured["package_dir"] == {"so101_demo": "src"}
    assert "so101_demo" in captured["packages"]
