"""The web bundle must track every real build input, not only TypeScript sources."""

from __future__ import annotations

from pathlib import Path

CMAKE = Path(__file__).parents[1] / "CMakeLists.txt"
WEB_ROOT = Path(__file__).parents[1] / "web"


def test_web_build_tracks_css_components_and_local_font_assets():
    cmake = CMAKE.read_text()
    assert "${SO101_TELEOP_WEB_ROOT}/src/*.css" in cmake
    assert "${SO101_TELEOP_WEB_ROOT}/public/*" in cmake
    assert "components.json" in cmake
    assert "design-system.lock.json" in cmake


def test_every_declared_web_dependency_exists_in_the_source_tree():
    """A DEPENDS entry that does not exist would break the configure step."""
    for name in ("package.json", "bun.lock", "vite.config.ts", "tailwind.config.ts",
                 "postcss.config.cjs", "index.html", "components.json", "design-system.lock.json"):
        assert (WEB_ROOT / name).is_file(), name
    assert any(WEB_ROOT.glob("src/**/*.css")), "at least one stylesheet must be tracked"


def test_the_bundle_is_built_by_bun_with_the_frozen_lockfile():
    cmake = CMAKE.read_text()
    assert "install --frozen-lockfile" in cmake
    assert "run build" in cmake
    assert "BUN_EXECUTABLE" in cmake
