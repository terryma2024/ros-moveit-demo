"""Fixture-only checks of the image build inputs: the Dockerfiles, the pinned apt and pip sets, and scripts/images/prepare-image-build.py.

The prepare script runs here in a throw-away git repository with a fake `docker`, so nothing touches a real image or the network.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "scripts" / "images"
DOCKER = ROOT / "src" / "so101_demo_py" / "docker"
DEPS = DOCKER / "campaign-shard-deps"
PREPARE = IMAGES / "prepare-image-build.py"
PINS = json.loads((IMAGES / "base-image-ids.json").read_text())
DOCKERFILES = {"inference": DOCKER / "campaign-inference" / "Dockerfile", "shard": DOCKER / "campaign-shard" / "Dockerfile",
               "shard-deps": DEPS / "Dockerfile"}


def instructions(path):
    """The Dockerfile text without comment lines."""
    return "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("#"))


def from_tag(path):
    return re.search(r"^FROM (\S+)", instructions(path), re.M).group(1)


# --- the Dockerfiles --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["inference", "shard-deps", "shard"])
def test_every_base_is_the_tag_that_base_image_ids_pins(role):
    assert from_tag(DOCKERFILES[role]) == PINS[role]["tag"]


@pytest.mark.parametrize("role", ["inference", "shard-deps"])
def test_the_pinned_ids_are_full_image_ids(role):
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", PINS[role]["id"])


def test_the_shard_base_is_the_deps_image_and_the_shard_build_has_no_network_step():
    text = instructions(DOCKERFILES["shard"])
    assert PINS["shard"]["tag"].startswith("so101-campaign-shard-deps:")
    for forbidden in ("apt-get", "apt ", "pip install", "pip download", "curl", "wget", "git clone", "index-url"):
        assert forbidden not in text, forbidden


def test_the_networked_steps_are_in_the_deps_image_only():
    text = instructions(DOCKERFILES["shard-deps"])
    assert "apt-get install" in text and "--require-hashes" in text and "--no-deps" in text
    assert "apt-packages.txt" in text and "pip-requirements.lock" in text
    assert "apt-get install --yes --no-install-recommends $(grep -v '^#' /tmp/shard-deps/apt-packages.txt)" in text


@pytest.mark.parametrize("role", ["inference", "shard-deps", "shard"])
def test_no_bytecode_is_generated_by_a_build(role):
    text = instructions(DOCKERFILES[role]).replace("\\\n", " ")
    assert "compileall" not in text and "py_compile" not in text
    if role != "shard":     # the shard inherits both settings from the deps base
        assert "PIP_NO_COMPILE=1" in text and "PYTHONDONTWRITEBYTECODE=1" in text
    for pip_line in re.findall(r"pip install[^\n]*", text):
        assert "--no-compile" in pip_line, pip_line


def test_the_deps_image_removes_the_bytecode_apt_compiles_in_the_same_layer():
    text = instructions(DOCKERFILES["shard-deps"]).replace("\\\n", " ")
    layer = re.search(r"RUN find / -xdev -name '\*\.pyc'[^\n]*", text).group(0)
    assert layer.index("pyc.before") < layer.index("apt-get install") < layer.index("comm -13") < layer.index("rm -f")


def test_the_cpp_build_maps_build_paths_and_uses_no_ccache():
    text = instructions(DOCKERFILES["shard"]).replace("\\\n", " ")
    colcon_builds = re.findall(r"colcon --log-base[^\n]*?FETCHCONTENT_FULLY_DISCONNECTED=ON", text)
    assert len(colcon_builds) == 2
    for build in colcon_builds:
        assert "-ffile-prefix-map=" in build and "-fdebug-prefix-map=" in build
        assert "CMAKE_C_COMPILER_LAUNCHER=" in build and "CMAKE_CXX_COMPILER_LAUNCHER=" in build
    assert "CCACHE_DISABLE=1" in text and "ccache" not in text.replace("CCACHE_DISABLE", "")


# --- the pinned sets --------------------------------------------------------------------------------------------------

def test_apt_packages_are_exact_sorted_pkg_equals_version_lines():
    lines = [line for line in (DEPS / "apt-packages.txt").read_text().splitlines() if line and not line.startswith("#")]
    assert len(lines) > 400 and lines == sorted(set(lines))
    for line in lines:
        assert re.fullmatch(r"[a-z0-9][a-z0-9+.\-]*=[0-9][^\s=*?]*", line), line


def test_pip_lock_pins_every_requirement_with_a_sha256():
    text = (DEPS / "pip-requirements.lock").read_text()
    requirements = [block for block in re.split(r"\n(?=[A-Za-z0-9])", "\n".join(l for l in text.splitlines() if not l.startswith("#")).strip())]
    assert len(requirements) >= 8
    for block in requirements:
        assert re.match(r"[A-Za-z0-9][A-Za-z0-9.\-]*==[0-9][^\s]* \\", block), block
        assert re.findall(r"--hash=sha256:[0-9a-f]{64}\b", block), block
    names = [re.match(r"[^=]+", block).group(0) for block in requirements]
    assert names == sorted(names) and len(set(names)) == len(names)


# --- prepare-image-build.py -------------------------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    tree = tmp_path / "repo"
    for name, content in {"src/so101_demo_py/docker/campaign-shard-deps/Dockerfile": "FROM x\n",
                          "src/so101_demo_py/docker/campaign-shard-deps/apt-packages.txt": "a=1\n",
                          "src/so101_demo_py/docker/campaign-shard-deps/pip-requirements.lock": "b==1 \\\n    --hash=sha256:" + "0" * 64 + "\n",
                          "src/so101_demo_py/docker/campaign-shard/Dockerfile": "FROM y\n",
                          "src/so101_demo_py/docker/campaign-inference/Dockerfile": "FROM z\n",
                          "src/so101_demo_py/src/module.py": "x = 1\n", "scripts/tool.sh": "true\n", "README.md": "not copied\n"}.items():
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@localhost"]
    subprocess.run(git + ["init", "-q"], cwd=tree, check=True)
    subprocess.run(git + ["add", "-A"], cwd=tree, check=True)
    subprocess.run(git + ["commit", "-q", "-m", "fixture"], cwd=tree, check=True)
    return tree


@pytest.fixture
def host(tmp_path):
    """Fake docker (answers `image inspect` with the ID in FAKE_DOCKER_ID) and fake build dependencies."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text('#!/bin/sh\nprintf \'[{"Id": "%s"}]\\n\' "$FAKE_DOCKER_ID"\n')
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    deps = tmp_path / "deps"
    (deps / "node/node-v24.18.1-linux-x64/bin").mkdir(parents=True)
    (deps / "node/node-v24.18.1-linux-x64/bin/node").write_text("node")
    (deps / "bun").write_text("bun")
    (deps / "bun-cache").mkdir()
    (deps / "bun-cache/package").write_text("p")
    (deps / "lodepng").mkdir()
    (deps / "lodepng/lodepng.cpp").write_text("l")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    return dict(bin=bin_dir, deps=deps, evidence=evidence)


def prepare(repo, host, role, image_id, *extra, build_deps=True):
    arguments = [sys.executable, str(PREPARE), "--role", role, "--evidence-root", str(host["evidence"]), *extra]
    if build_deps:
        arguments += ["--native-build-deps", str(host["deps"]), "--bun", str(host["deps"] / "bun"),
                      "--bun-cache", str(host["deps"] / "bun-cache"), "--lodepng", str(host["deps"] / "lodepng")]
    environment = {**os.environ, "PATH": f"{host['bin']}:{os.environ['PATH']}", "FAKE_DOCKER_ID": image_id}
    for name in ("EVIDENCE_R", "NATIVE_BUILD_DEPS", "BUN_BIN", "BUN_CACHE", "DEPS_FREEZE"):
        environment.pop(name, None)
    return subprocess.run(arguments, cwd=repo, env=environment, capture_output=True, text=True)


def built(host):
    return Path((host["evidence"] / "current-image-build-path.txt").read_text().strip())


def test_shard_deps_context_is_its_own_directory_and_it_alone_may_use_the_network(repo, host):
    done = prepare(repo, host, "shard-deps", PINS["shard-deps"]["id"], build_deps=False)
    assert done.returncode == 0, done.stderr
    build = built(host)
    argv = json.loads((build / "argv.json").read_text())
    assert argv[argv.index("--network") + 1] == "default"
    assert argv[argv.index("-t") + 1] == "so101-campaign-shard-deps:ros-jazzy-yolo11n-v1"
    context = Path(argv[-1])
    assert sorted(path.name for path in context.iterdir()) == ["Dockerfile", "apt-packages.txt", "pip-requirements.lock"]
    assert Path(argv[argv.index("-f") + 1]) == context / "Dockerfile"
    assert not (build / "context/source/build-deps").exists()
    assert sorted(json.loads((build / "source-files.json").read_text())) == [
        "src/so101_demo_py/docker/campaign-shard-deps/" + name for name in ("Dockerfile", "apt-packages.txt", "pip-requirements.lock")]


def test_a_changed_base_image_id_is_refused(repo, host):
    done = prepare(repo, host, "shard-deps", "sha256:" + "1" * 64, build_deps=False)
    assert done.returncode != 0 and "DEPENDENCY_BASE_IDENTITY_CHANGED" in done.stderr


def test_the_shard_build_refuses_a_base_that_is_not_pinned_yet(repo, host):
    done = prepare(repo, host, "shard", "sha256:" + "2" * 64)
    assert done.returncode != 0 and "DEPENDENCY_BASE_NOT_PINNED" in done.stderr


def test_the_shard_build_takes_the_supplied_pin_and_runs_without_network(repo, host):
    pin = "sha256:" + "2" * 64
    done = prepare(repo, host, "shard", pin, "--pin-shard-deps", pin)
    assert done.returncode == 0, done.stderr
    argv = json.loads((built(host) / "argv.json").read_text())
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("-t") + 1].startswith("so101-campaign-shard:dispatch-")
    assert (built(host) / "context/source/build-deps/node/bin/node").is_file()


def test_the_shard_build_refuses_a_base_whose_id_differs_from_the_supplied_pin(repo, host):
    done = prepare(repo, host, "shard", "sha256:" + "3" * 64, "--pin-shard-deps", "sha256:" + "2" * 64)
    assert done.returncode != 0 and "DEPENDENCY_BASE_IDENTITY_CHANGED" in done.stderr


def test_the_inference_build_is_unchanged_offline_with_the_full_snapshot(repo, host):
    done = prepare(repo, host, "inference", PINS["inference"]["id"])
    assert done.returncode == 0, done.stderr
    argv = json.loads((built(host) / "argv.json").read_text())
    assert argv[argv.index("--network") + 1] == "none"
    assert "README.md" not in json.loads((built(host) / "source-files.json").read_text())
    assert (built(host) / "context/source/src/so101_demo_py/src/module.py").is_file()
