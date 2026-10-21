"""Contract: the campaign shard image builds the so101_teleop web bundle in its own Docker stage.

The bundle used to be built inside the colcon step, where Bun missed its copied cache (the cache is keyed by registry host)
and downloaded the packages from the network, and where any Python edit repeated the build. These tests pin the
pieces that keep it fast: the separate stage, the offline cache with the mirror registry, the CMake switch, and the
snapshot that feeds the stage. They use fixtures only.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from paths import REPOSITORY

from test_image_build_context import _flat, _shard_stages

SHARD_DIR = REPOSITORY / "src/so101_demo_py/docker/campaign-shard"
WRAPPER = SHARD_DIR / "build-bun.bash"
TELEOP_CMAKE = REPOSITORY / "src/so101_teleop/CMakeLists.txt"
PREPARE = REPOSITORY / "scripts/images/prepare-image-build.py"
WEB = "/act/build-source/src/so101_teleop/web"


def _copies(instructions: list[str]) -> list[tuple[str, list[str], str]]:
    result = []
    for item in instructions:
        if not item.startswith("COPY "):
            continue
        words = [word for word in item.split()[1:] if not word.startswith("--")]
        result.append((item, words[:-1], words[-1]))
    return result


def test_web_stage_installs_from_the_manifests_before_it_sees_any_other_web_file() -> None:
    web = _shard_stages()["web"]
    web_copies = [entry for entry in _copies(web) if entry[2].rstrip("/").startswith(WEB)]
    assert [entry[1] for entry in web_copies[:1]] == [
        ["source/src/so101_teleop/web/package.json", "source/src/so101_teleop/web/bun.lock"]
    ]
    first_install = next(i for i, item in enumerate(web) if item.startswith("RUN") and "build-tools/bun install" in item)
    full_copy = next(i for i, item in enumerate(web) if item == f"COPY source/src/so101_teleop/web {WEB}")
    build_run = next(i for i, item in enumerate(web) if item.startswith("RUN") and "bun run build" in item)
    assert web.index(web_copies[0][0]) < first_install < full_copy < build_run
    # Everything the install needs is copied before it, so the install layer is keyed by manifests, toolchain and cache.
    needed = {"/act/build-tools/bun", "/act/source/build-deps/bun", "/act/source/build-deps/node",
              "/act/build-source/build-deps/bun-cache"}
    assert needed <= {entry[2].rstrip("/") for entry in _copies(web[:first_install])}
    assert "node/bin" in next(item for item in web if item.startswith("ENV PATH="))


def test_build_stage_takes_the_bundle_from_the_web_stage_and_never_runs_bun() -> None:
    build = _shard_stages()["build"]
    source_copy = build.index("COPY source/src /act/build-source/src")
    bundle = f"COPY --from=web {WEB}/dist {WEB}/dist"
    assert bundle in build
    assert build.index(bundle) > source_copy
    colcon = [item for item in build if item.startswith("RUN") and "colcon" in item]
    assert "-DSO101_TELEOP_PREBUILT_WEB_DIST=ON" not in colcon[0]
    assert "-DSO101_TELEOP_PREBUILT_WEB_DIST=ON" in colcon[1]
    assert build.index(bundle) < build.index(colcon[1])
    text = "\n".join(build)
    for word in ("build-deps/bun", "build-deps/node", "SO101_TELEOP_BUN", "build-tools"):
        assert word not in text, word


def test_the_web_stage_is_selected_only_by_files_under_the_web_directory() -> None:
    for item in _shard_stages()["web"][1:]:
        if item.startswith("COPY "):
            sources = _copies([item])[0][1]
            assert all(
                source.startswith(("source/src/so101_teleop/web", "source/build-deps/",
                                   "source/src/so101_demo_py/docker/campaign-shard/build-bun.bash"))
                for source in sources
            ), item


def test_the_snapshot_places_the_web_inputs_where_the_stage_copies_them() -> None:
    """prepare-image-build.py copies git-tracked files under src/ into source/ and the Bun toolchain into source/build-deps."""
    text = PREPARE.read_text(encoding="utf-8")
    assert 'name.startswith(("src/", "scripts/", "third_party/"))' in text
    assert "deps=source/'build-deps'" in text
    assert "deps/'bun-cache'" in text
    tracked = subprocess.run(["git", "ls-files", "src/so101_teleop/web"], cwd=REPOSITORY, capture_output=True,
                             text=True, check=True).stdout.split()
    assert "src/so101_teleop/web/package.json" in tracked and "src/so101_teleop/web/bun.lock" in tracked
    assert not [name for name in tracked if "/node_modules/" in name or "/dist/" in name]
    # The source hash list and the dependency hash list are still written.
    assert "source-files.json" in text and "build-dependency-files.json" in text
    # The copied cache is proved complete for the web lockfile before the build starts.
    assert "--offline" in text and "BUN_CACHE_INCOMPLETE_FOR_WEB_LOCKFILE" in text


# --- build-bun.bash ---------------------------------------------------------------------------------------------------

def _fake_bun(directory: Path, *, offline_ok: bool) -> tuple[Path, Path]:
    log = directory / "bun.log"
    script = directory / "bun"
    script.write_text(
        "#!/usr/bin/bash\n"
        f'printf "%s|%s\\n" "$BUN_CONFIG_REGISTRY" "$*" >> {log}\n'
        + ("" if offline_ok else 'case " $* " in *" --offline "*) exit 1;; esac\n')
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script, log


def _run_wrapper(tmp_path: Path, *args: str, offline_ok: bool, env_registry: str | None = None):
    bun, log = _fake_bun(tmp_path, offline_ok=offline_ok)
    env = {k: v for k, v in os.environ.items() if k != "BUN_CONFIG_REGISTRY"}
    env.update(SO101_BUN_BIN=str(bun), SO101_BUN_CACHE_DIR=str(tmp_path / "cache"))
    if env_registry:
        env["BUN_CONFIG_REGISTRY"] = env_registry
    result = subprocess.run(["bash", str(WRAPPER), *args], env=env, capture_output=True, text=True)
    calls = log.read_text().splitlines() if log.exists() else []
    return result, calls


def test_wrapper_installs_offline_from_the_cache_against_the_mirror_registry(tmp_path: Path) -> None:
    result, calls = _run_wrapper(tmp_path, "install", offline_ok=True)
    assert result.returncode == 0, result.stderr
    assert calls == [f"https://registry.npmmirror.com|install --frozen-lockfile --backend=copyfile --cache-dir {tmp_path}/cache --offline"]


def test_wrapper_falls_back_to_the_mirror_when_the_cache_is_incomplete(tmp_path: Path) -> None:
    result, calls = _run_wrapper(tmp_path, "install", offline_ok=False)
    assert result.returncode == 0, result.stderr
    assert "cache is incomplete" in result.stderr
    assert calls == [
        f"https://registry.npmmirror.com|install --frozen-lockfile --backend=copyfile --cache-dir {tmp_path}/cache --offline",
        f"https://registry.npmmirror.com|install --frozen-lockfile --backend=copyfile --cache-dir {tmp_path}/cache",
    ]
    assert all("--no-frozen-lockfile" not in call for call in calls)


def test_wrapper_keeps_an_explicit_registry_and_passes_other_commands_through(tmp_path: Path) -> None:
    _, calls = _run_wrapper(tmp_path, "install", offline_ok=True, env_registry="https://example.invalid/")
    assert calls[0].startswith("https://example.invalid/|install")
    result, calls = _run_wrapper(tmp_path, "run", "build", offline_ok=True)
    assert result.returncode == 0
    assert calls[-1] == "https://registry.npmmirror.com|run build"


def test_wrapper_defaults_point_at_the_image_paths() -> None:
    text = WRAPPER.read_text()
    assert "/act/source/build-deps/bun" in text and "/act/build-source/build-deps/bun-cache" in text
    assert "--frozen-lockfile" in text and "--offline" in text and "--backend=copyfile" in text and "registry.npmmirror.com" in text


# --- so101_teleop CMake option ------------------------------------------------------------------------------------------

cmake = shutil.which("cmake")


def _stub_project(root: Path, *, with_dist: bool) -> Path:
    """A copy of the package's CMakeLists.txt with stand-ins for the ament macros."""

    project = root / "so101_teleop"
    (project / "web/src").mkdir(parents=True)
    (project / "web/package.json").write_text("{}")
    (project / "web/bun.lock").write_text("")
    for name in ("config", "docs", "launch"):
        (project / name).mkdir()
    if with_dist:
        (project / "web/dist").mkdir()
        (project / "web/dist/index.html").write_text("<html></html>")
    shutil.copy2(TELEOP_CMAKE, project / "CMakeLists.txt")
    stubs = root / "stubs"
    stubs.mkdir()
    for package in ("ament_cmake", "ament_cmake_python"):
        (stubs / f"Find{package}.cmake").write_text(f"set({package}_FOUND TRUE)\n")
    (stubs / "Findament_cmake.cmake").write_text(
        "set(ament_cmake_FOUND TRUE)\n"
        "macro(ament_python_install_package)\nendmacro()\nmacro(ament_package)\nendmacro()\n")
    return project


def _configure(tmp_path: Path, *options: str, with_dist: bool, bun: str | None):
    project = _stub_project(tmp_path, with_dist=with_dist)
    build = tmp_path / "build"
    env = {k: v for k, v in os.environ.items() if k != "SO101_TELEOP_BUN"}
    if bun:
        env["SO101_TELEOP_BUN"] = bun
    result = subprocess.run(
        [cmake, "-S", str(project), "-B", str(build), "-G", "Unix Makefiles",
         f"-DCMAKE_MODULE_PATH={tmp_path / 'stubs'}", *options],
        env=env, capture_output=True, text=True)
    return result, build


@pytest.mark.skipif(cmake is None, reason="cmake is not installed")
def test_prebuilt_web_dist_without_a_bundle_is_a_configure_error(tmp_path: Path) -> None:
    result, _ = _configure(tmp_path, "-DSO101_TELEOP_PREBUILT_WEB_DIST=ON", with_dist=False, bun=None)
    assert result.returncode != 0
    assert "SO101_TELEOP_PREBUILT_WEB_DIST is ON" in result.stderr
    assert "web/dist/index.html" in result.stderr


@pytest.mark.skipif(cmake is None, reason="cmake is not installed")
def test_prebuilt_web_dist_configures_without_bun_and_runs_no_bun_command(tmp_path: Path) -> None:
    result, build = _configure(tmp_path, "-DSO101_TELEOP_PREBUILT_WEB_DIST=ON", with_dist=True, bun=None)
    assert result.returncode == 0, result.stderr
    generated = "\n".join(path.read_text() for path in build.rglob("*.make"))
    assert "so101_teleop_web" in generated
    assert "frozen-lockfile" not in generated and "run build" not in generated


@pytest.mark.skipif(cmake is None, reason="cmake is not installed")
def test_default_keeps_the_bun_install_and_build_commands(tmp_path: Path) -> None:
    result, build = _configure(tmp_path, with_dist=False, bun="/bin/true")
    assert result.returncode == 0, result.stderr
    generated = _flat("\n".join(path.read_text() for path in build.rglob("*.make")))
    assert re.search(r"/bin/true install --frozen-lockfile", generated)
    assert re.search(r"/bin/true run build", generated)
    assert (build / "CMakeCache.txt").read_text().count("SO101_TELEOP_PREBUILT_WEB_DIST:BOOL=OFF") == 1
