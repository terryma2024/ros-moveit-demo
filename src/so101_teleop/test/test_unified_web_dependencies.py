"""The web bundle must track every real build input, not only TypeScript sources."""

from __future__ import annotations

import os
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


def test_incremental_rebuild_changes_the_bundle_in_a_registered_fixture(tmp_path):
    """The plan's fixture-bound incremental proof.

    It runs only when ``SO101_TEST_WEB_FIXTURE`` names a registered fixture directory containing a
    built ``web`` tree, because a real rebuild must never run against the implementation source. The
    fixture is a copy of ``web/``; this test edits a token inside the *copy*, rebuilds with the
    project's Bun and asserts the emitted stylesheet changes.
    """
    import hashlib
    import os
    import shutil
    import subprocess

    import pytest

    fixture = os.environ.get("SO101_TEST_WEB_FIXTURE")
    if not fixture or not Path(fixture).is_dir():
        pytest.skip("SO101_TEST_WEB_FIXTURE does not name a registered fixture directory")
    source = Path(fixture)
    bun = shutil.which("bun")
    if bun is None:
        pytest.skip("bun is not on PATH")

    def build() -> str:
        subprocess.run([bun, "run", "build"], cwd=source, check=True, capture_output=True)
        stylesheet = next((source / "dist/assets").glob("*.css"))
        return hashlib.sha256(stylesheet.read_bytes()).hexdigest()

    before = build()
    token = source / "src/styles/theme.css"
    token.write_text(token.read_text() + "\n:root { --so101-fixture-proof: oklch(0.5 0.1 200); }\n")
    after = build()
    assert before != after, "a token edit must change the emitted stylesheet"
