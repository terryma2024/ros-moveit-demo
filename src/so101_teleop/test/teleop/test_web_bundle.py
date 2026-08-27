from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from so101_teleop.web_bundle import WebBundleError, ensure_web_bundle, select_bun


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _source(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.tsx").write_text("export default 1\n")
    (root / "index.html").write_text('<div id="root"></div>\n')
    (root / "package.json").write_text('{"scripts":{"build":"vite build"}}\n')
    (root / "bun.lock").write_text('lockfileVersion = 1\n')
    for name in ("vite.config.ts", "tailwind.config.ts", "postcss.config.cjs", "tsconfig.json"):
        (root / name).write_text("// config\n")
    return root


def _bundle(root: Path, *, empty_asset: bool = False, missing_asset: bool = False) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text('<script type="module" src="/assets/app.js"></script><link rel="stylesheet" href="/assets/app.css">')
    if not missing_asset:
        (dist / "assets" / "app.js").write_text("" if empty_asset else "console.log(1)")
    (dist / "assets" / "app.css").write_text("body{color:white}")
    return dist


class FakeRunner:
    def __init__(self, root: Path, *, fail_build: bool = False):
        self.root = root
        self.fail_build = fail_build
        self.calls: list[list[str]] = []

    def __call__(self, command, *, cwd=None, env=None):
        command = [str(part) for part in command]
        self.calls.append(command)
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "1.3.14\n", "")
        if command[-2:] == ["run", "build"]:
            if self.fail_build:
                return subprocess.CompletedProcess(command, 2, "", "vite exploded")
            _bundle(self.root)
        return subprocess.CompletedProcess(command, 0, "ok\n", "")


def _env(tmp_path: Path) -> dict[str, str]:
    bun = tmp_path / "bun"
    bun.write_text(""); bun.chmod(0o755)
    return {"SO101_TELEOP_BUN": str(bun), "PATH": os.environ.get("PATH", "")}


def test_fresh_valid_bundle_skips_bun(tmp_path: Path, capsys):
    root = _source(tmp_path / "web")
    dist = _bundle(root)
    for path in dist.rglob("*"):
        if path.is_file():
            os.utime(path, (2_000_000_000, 2_000_000_000))
    runner = FakeRunner(root)
    assert ensure_web_bundle(root, runner=runner, env={}) == dist
    assert runner.calls == []
    assert "web bundle fresh" in capsys.readouterr().out


@pytest.mark.parametrize("stale", [False, True], ids=["missing", "stale"])
def test_missing_or_stale_bundle_builds(tmp_path: Path, stale: bool, capsys):
    root = _source(tmp_path / "web")
    if stale:
        _bundle(root)
        os.utime(root / "src" / "main.tsx", (2_000_000_000, 2_000_000_000))
    runner = FakeRunner(root)
    assert ensure_web_bundle(root, runner=runner, env=_env(tmp_path)) == root / "dist"
    assert any(call[-2:] == ["run", "build"] for call in runner.calls)
    output = capsys.readouterr().out
    assert "web bundle missing or stale; building" in output
    assert "web bundle built and validated" in output


def test_lock_change_runs_ci_but_matching_fingerprint_skips_it(tmp_path: Path):
    root = _source(tmp_path / "web")
    runner = FakeRunner(root)
    env = _env(tmp_path)
    ensure_web_bundle(root, runner=runner, env=env)
    assert any(call[-2:] == ["install", "--frozen-lockfile"] for call in runner.calls)
    (root / "src" / "main.tsx").write_text("export default 2\n")
    runner.calls.clear()
    ensure_web_bundle(root, runner=runner, env=env)
    assert not any(call[-2:] == ["install", "--frozen-lockfile"] for call in runner.calls)
    (root / "bun.lock").write_text('lockfileVersion = 2\n')
    runner.calls.clear()
    ensure_web_bundle(root, runner=runner, env=env)
    assert any(call[-2:] == ["install", "--frozen-lockfile"] for call in runner.calls)


def test_build_failure_is_typed_and_includes_safe_diagnostics(tmp_path: Path):
    root = _source(tmp_path / "web")
    with pytest.raises(WebBundleError, match=r"bun run build.*vite exploded"):
        ensure_web_bundle(root, runner=FakeRunner(root, fail_build=True), env=_env(tmp_path))


@pytest.mark.parametrize("kwargs", [{"missing_asset": True}, {"empty_asset": True}])
def test_invalid_asset_reference_is_rejected_when_build_is_disabled(tmp_path: Path, kwargs):
    root = _source(tmp_path / "web")
    _bundle(root, **kwargs)
    with pytest.raises(WebBundleError, match="asset"):
        ensure_web_bundle(root, build_if_needed=False, runner=FakeRunner(root), env={})


def test_bun_selection_prefers_override_then_pinned_then_path(tmp_path: Path):
    override = tmp_path / "override-bun"
    pinned = tmp_path / "pinned-bun"
    path_bin = tmp_path / "path"; path_bin.mkdir()
    path_bun = path_bin / "bun"
    for executable in (override, pinned, path_bun):
        executable.write_text(""); executable.chmod(0o755)
    runner = FakeRunner(tmp_path)
    assert select_bun({"SO101_TELEOP_BUN": str(override)}, runner=runner, pinned_bun=pinned) == override
    assert select_bun({"PATH": str(path_bin)}, runner=runner, pinned_bun=pinned) == pinned
    assert select_bun({"PATH": str(path_bin)}, runner=runner, pinned_bun=tmp_path / "absent") == path_bun


def test_bun_selection_rejects_invalid_version(tmp_path: Path):
    bun = tmp_path / "bad-bun"; bun.write_text("")

    def old_runner(command, *, cwd=None, env=None):
        return subprocess.CompletedProcess(command, 0, "not-a-version\n", "")

    with pytest.raises(WebBundleError, match=r"Bun is required"):
        select_bun({"SO101_TELEOP_BUN": str(bun)}, runner=old_runner, pinned_bun=tmp_path / "absent")


def test_installed_web_source_contract_contains_task_page_and_exact_three() -> None:
    package = (PACKAGE_ROOT / "web/package.json").read_text(encoding="utf-8")
    main = (PACKAGE_ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
    task_app = (PACKAGE_ROOT / "web/src/task-app.tsx").read_text(encoding="utf-8")
    assert '"three": "0.184.0"' in package
    assert '"@types/three": "0.184.0"' in package
    assert 'location.pathname === "/tasks"' in main
    assert "LiveSensor" in task_app
    assert "EvidenceBrowser" in task_app
