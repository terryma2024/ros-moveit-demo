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
HOSTS_DIR = ROOT / "scripts/gate/hosts"
IMAGES = ROOT / "scripts" / "images"
DOCKER = ROOT / "src" / "so101_demo_py" / "docker"
PREPARE = IMAGES / "prepare-image-build.py"
PINS = json.loads((IMAGES / "base-image-ids.json").read_text())


def instructions(path):
    """The Dockerfile text without comment lines."""
    return "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("#"))


def from_tag(path):
    return re.search(r"^FROM (\S+)", instructions(path), re.M).group(1)


# --- the Dockerfiles --------------------------------------------------------------------------------------------------

# --- the pinned sets --------------------------------------------------------------------------------------------------

def test_apt_packages_are_sorted_package_names_without_versions():
    lines = [line for line in (DOCKER / "mount-base" / "apt-packages.txt").read_text().splitlines() if line and not line.startswith("#")]
    assert len(lines) > 400 and lines == sorted(set(lines))
    for line in lines:
        assert re.fullmatch(r"[a-z0-9][a-z0-9+.\-]*", line), line


def test_pip_lock_pins_every_requirement_with_a_sha256():
    text = (DOCKER / "mount-base" / "pip-requirements.lock").read_text()
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
    for name, content in {"src/so101_demo_py/docker/mount-base/Dockerfile": "FROM m\n",
                          "src/so101_demo_py/docker/mount-base/bootstrap.bash": "true\n",
                          "src/so101_demo_py/docker/mount-base/check-mount-commit.bash": "true\n",
                          "src/so101_demo_py/docker/mount-base/apt-pins.txt": "a=1\n",
                          "src/so101_demo_py/docker/mount-base/apt-packages.txt": "a\n",
                          "src/so101_demo_py/docker/mount-base/pip-requirements.lock": "b==1 \\\n    --hash=sha256:" + "0" * 64 + "\n",
                          "src/so101_demo_py/config/perception/inference-requirements.lock": "numpy==1\n",
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


def prepare(repo, host, role, image_id, *extra, build_deps=True, env=None):
    arguments = [sys.executable, str(PREPARE), "--role", role, "--evidence-root", str(host["evidence"]), *extra]
    if build_deps:
        arguments += ["--native-build-deps", str(host["deps"]), "--bun", str(host["deps"] / "bun"),
                      "--bun-cache", str(host["deps"] / "bun-cache"), "--lodepng", str(host["deps"] / "lodepng")]
    environment = {**os.environ, "PATH": f"{host['bin']}:{os.environ['PATH']}", "FAKE_DOCKER_ID": image_id}
    for name in ("EVIDENCE_R", "BUN_BIN", "DEPS_FREEZE", "BUILD_PROXY", "BUILD_NO_PROXY"):
        environment.pop(name, None)
    environment.update(env or {})
    return subprocess.run(arguments, cwd=repo, env=environment, capture_output=True, text=True)


def built(host):
    return Path((host["evidence"] / "current-image-build-path.txt").read_text().strip())


def test_no_cache_is_passed_to_docker_build_only_when_asked(repo, host):
    for flag, expected in (((), False), (("--no-cache",), True)):
        evidence = host["evidence"] / ("cached" if not flag else "fresh")     # one build directory name per second: separate roots
        evidence.mkdir()
        done = prepare(repo, {**host, "evidence": evidence}, "mount-base", "", *flag, build_deps=False)
        assert done.returncode == 0, done.stderr
        argv = json.loads((built({"evidence": evidence})/ "argv.json").read_text())
        assert ("--no-cache" in argv) is expected and argv[:2] == ["docker", "build"]


# --- mount-base: dependency-only image for the host-built, mounted install tree --------------------------------------

MOUNT = DOCKER / "mount-base"


def test_the_mount_base_holds_dependencies_only_and_no_project_code():
    text = instructions(MOUNT / "Dockerfile").replace("\\\n", " ")
    assert re.search(r"^FROM \S+@sha256:[0-9a-f]{64}", text, re.M)
    for forbidden in ("so101_demo", "so101_teleop", "so101_mujoco", "so101_quik", "/act/install", "/act/source", "COPY source", "COPY src"):
        assert forbidden not in text, forbidden
    assert "pip install --no-compile --no-deps --require-hashes" in text.replace("-m pip", "pip")
    for fragment in ("mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu", "mirrors.tuna.tsinghua.edu.cn/ubuntu", "PYTHONDONTWRITEBYTECODE=1", "PIP_NO_COMPILE=1",
                     "10_nvidia.json", "COPY bootstrap.bash /act/bootstrap.bash", "SO101_MOUNT_INSTALL"):
        assert fragment in text, fragment
    for pip_line in re.findall(r"pip install[^&\n]*", text):
        assert "--no-compile" in pip_line, pip_line
    layer = re.search(r"RUN find / -xdev -name '\*\.pyc'[^\n]*", text).group(0)
    assert layer.index("pyc.before") < layer.index("apt-get install") < layer.index("comm -13")


def test_the_mount_base_bootstrap_sources_ros_then_the_mounted_tree_with_its_prefix():
    text = (MOUNT / "bootstrap.bash").read_text()
    assert text.index("/opt/ros/jazzy/setup.bash") < text.index('source "$SO101_MOUNT_INSTALL/setup.bash"')
    assert "COLCON_CURRENT_PREFIX=$SO101_MOUNT_INSTALL" in text and text.rstrip().endswith('exec "$@"')


def test_the_mount_base_context_is_flat_and_may_use_the_network(repo, host):
    done = prepare(repo, host, "mount-base", "", build_deps=False)
    assert done.returncode == 0, done.stderr
    build = built(host)
    argv = json.loads((build / "argv.json").read_text())
    assert argv[argv.index("--network") + 1] == "default"
    assert argv[argv.index("-t") + 1] == "so101-mount-base:ros-jazzy-torch2.13.0-cu130-v1"
    context = Path(argv[-1])
    assert sorted(path.name for path in context.iterdir()) == [
        "Dockerfile", "apt-packages.txt", "apt-pins.txt", "bootstrap.bash", "check-mount-commit.bash", "inference-requirements.lock", "pip-requirements.lock"]
    assert Path(argv[argv.index("-f") + 1]) == context / "Dockerfile"
    assert not (build / "context/source/build-deps").exists()


# --- start_mounted.zsh: the container flags of a mounted run ------------------------------------------------------------

START = IMAGES / "start_mounted.zsh"


def run_start(tmp_path, *extra, install=None):
    install = install or (tmp_path / "mount" / "abc123def456" / "install")
    install.mkdir(parents=True, exist_ok=True)
    source = install.parent / "source"
    source.mkdir(exist_ok=True)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$FAKE_DOCKER_ARGV"\n')
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    argv_file = tmp_path / "argv.txt"
    done = subprocess.run(["zsh", str(START), "--image", "sha256:" + "a" * 64, "--install", str(install), "--source", str(source),
                           "--out-dir", str(out), "--gpu", "GPU-1111", "--commit", COMMIT, "--name", "t-mounted", "--domain-id", "181", *extra],
                          capture_output=True, text=True,
                          env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_DOCKER_ARGV": str(argv_file)})
    return done, (argv_file.read_text().splitlines() if argv_file.exists() else []), install, source, out


def test_a_mounted_run_keeps_every_container_restriction_and_mounts_the_trees_read_only_at_their_own_path(tmp_path):
    done, argv, install, source, out = run_start(tmp_path)
    assert done.returncode == 0, done.stderr
    assert argv[:2] == ["run", "--detach"]
    for pair in (("--user", "1000:1000"), ("--cap-drop", "ALL"), ("--security-opt", "no-new-privileges"), ("--network", "none"),
                 ("--ipc", "private"), ("--restart", "no"), ("--gpus", "device=GPU-1111"), ("--entrypoint", "/act/bootstrap.bash")):
        assert pair[0] in argv and argv[argv.index(pair[0]) + 1] == pair[1], pair
    assert "--read-only" in argv and "--privileged" not in argv
    mounts = [argv[i + 1] for i, item in enumerate(argv) if item == "--mount"]
    assert f"type=bind,src={install},dst={install},readonly" in mounts
    assert f"type=bind,src={source},dst={source},readonly" in mounts
    assert f"type=bind,src={out},dst={out}" in mounts                # the only writable mount
    assert sum(1 for mount in mounts if not mount.endswith(",readonly")) == 1
    environment = [argv[i + 1] for i, item in enumerate(argv) if item == "--env"]
    assert f"SO101_MOUNT_INSTALL={install}" in environment and "ROS_DOMAIN_ID=181" in environment
    assert f"SO101_MOUNT_SOURCE={source}" in environment and f"SO101_EXPECTED_COMMIT={COMMIT}" in environment
    assert "PYTHONDONTWRITEBYTECODE=1" in environment and "ROS_LOCALHOST_ONLY=1" in environment


def test_a_mounted_run_refuses_a_missing_tree_or_a_relative_path(tmp_path):
    missing = subprocess.run(["zsh", str(START), "--image", "sha256:x", "--install", "relative/install", "--source", "/tmp", "--out-dir", "/tmp",
                              "--gpu", "G", "--name", "n", "--domain-id", "1", "--commit", COMMIT], capture_output=True, text=True)
    assert missing.returncode == 2 and "MOUNT_PATH_NOT_ABSOLUTE" in missing.stderr
    gone = subprocess.run(["zsh", str(START), "--image", "sha256:x", "--install", "/nonexistent/install", "--source", "/tmp", "--out-dir", "/tmp",
                           "--gpu", "G", "--name", "n", "--domain-id", "1", "--commit", COMMIT], capture_output=True, text=True)
    assert gone.returncode == 2 and "MOUNT_TREE_MISSING" in gone.stderr


# --- mount commit records: the light consistency check (host build writes BUILD-COMMIT, the container entry compares it) -------------

BUILD_MOUNT = IMAGES / "build_mount_tree.zsh"
CHECK_COMMIT = MOUNT / "check-mount-commit.bash"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def run_check(expected, *directories):
    return subprocess.run(["bash", str(CHECK_COMMIT), *([expected] if expected is not None else []), *map(str, directories)],
                          capture_output=True, text=True)


def trees(tmp_path, install_record=COMMIT, source_record=COMMIT):
    install, source = tmp_path / "install", tmp_path / "source"
    for tree, record in ((install, install_record), (source, source_record)):
        tree.mkdir(exist_ok=True)
        if record is not None:
            (tree / "BUILD-COMMIT").write_text(record + "\n")
    return install, source


def test_the_container_entry_accepts_trees_whose_records_equal_the_expected_commit(tmp_path):
    install, source = trees(tmp_path)
    assert run_check(COMMIT, install, source).returncode == 0


def test_the_container_entry_refuses_a_missing_record_a_different_commit_and_a_malformed_record(tmp_path):
    install, source = trees(tmp_path, source_record=None)
    done = run_check(COMMIT, install, source)
    assert done.returncode == 3 and "MOUNT_COMMIT_MISSING" in done.stderr and str(source) in done.stderr
    install, source = trees(tmp_path, source_record="f" * 40)
    done = run_check(COMMIT, install, source)
    assert done.returncode == 4 and "MOUNT_COMMIT_MISMATCH" in done.stderr
    install, source = trees(tmp_path, install_record="not-a-commit")
    assert run_check(COMMIT, install, source).returncode == 4
    assert run_check(None, install, source).returncode == 2
    assert run_check("short", install, source).returncode == 2


def test_the_mount_base_entry_runs_the_commit_check_before_it_sources_anything_from_the_mounted_tree():
    text = (MOUNT / "bootstrap.bash").read_text()
    assert text.index("check-mount-commit") < text.index('source "$SO101_MOUNT_INSTALL/setup.bash"')
    assert "SO101_EXPECTED_COMMIT" in text and "SO101_MOUNT_SOURCE" in text and "MOUNT_COMMIT_NOT_GIVEN" in text
    assert "COPY check-mount-commit.bash /act/check-mount-commit.bash" in instructions(MOUNT / "Dockerfile")


@pytest.fixture
def worktree(tmp_path):
    tree = tmp_path / "wt"
    tree.mkdir()
    (tree / "a.txt").write_text("1\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@localhost"]
    subprocess.run(git + ["init", "-q"], cwd=tree, check=True)
    subprocess.run(git + ["add", "-A"], cwd=tree, check=True)
    subprocess.run(git + ["commit", "-q", "-m", "x"], cwd=tree, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tree, capture_output=True, text=True, check=True).stdout.strip()
    return tree, head


def build_mount(tree, head, tmp_path, command, commit=None):
    return subprocess.run(["zsh", str(BUILD_MOUNT), "--build-root", str(tmp_path / "br"), "--commit", commit or head],
                          cwd=tree, capture_output=True, text=True, env={**os.environ, "MOUNT_BUILD_COMMAND": command})


def test_a_clean_build_writes_the_commit_record_last_and_leaves_the_trees_read_only(tmp_path, worktree):
    tree, head = worktree
    done = build_mount(tree, head, tmp_path, 'mkdir -p "$MOUNT_INSTALL/lib" && echo built > "$MOUNT_INSTALL/lib/x"', )
    assert done.returncode == 0, done.stderr
    root = tmp_path / "br" / "mount" / head[:12]
    for part in ("install", "source"):
        assert (root / part / "BUILD-COMMIT").read_text() == head + "\n"
        assert not os.access(root / part, os.W_OK) and not os.access(root / part / "BUILD-COMMIT", os.W_OK)
        assert oct((root / part).stat().st_mode & 0o777) == "0o555"
    assert (root / "source" / "a.txt").read_text() == "1\n" and (root / "install/lib/x").exists()


def test_the_mounted_install_holds_no_bytecode_and_the_build_runs_without_writing_any(tmp_path, worktree):
    tree, head = worktree
    command = ('echo "$PYTHONDONTWRITEBYTECODE" > "$MOUNT_ROOT/env-seen" && mkdir -p "$MOUNT_INSTALL/pkg/__pycache__" "$MOUNT_INSTALL/share/launch/__pycache__" '
               '&& echo x > "$MOUNT_INSTALL/pkg/__pycache__/m.cpython-312.pyc" && echo y > "$MOUNT_INSTALL/share/launch/__pycache__/l.cpython-312.pyc" '
               '&& echo z > "$MOUNT_INSTALL/pkg/stray.pyc" && echo keep > "$MOUNT_INSTALL/pkg/m.py"')
    done = build_mount(tree, head, tmp_path, command)
    assert done.returncode == 0, done.stderr
    root = tmp_path / "br" / "mount" / head[:12]
    assert (root / "env-seen").read_text() == "1\n"
    assert not list((root / "install").rglob("*.pyc")) and not list((root / "install").rglob("__pycache__"))
    assert (root / "install/pkg/m.py").read_text() == "keep\n" and (root / "install/BUILD-COMMIT").read_text() == head + "\n"


def test_the_build_refuses_a_dirty_worktree_or_another_head_before_it_creates_anything(tmp_path, worktree):
    tree, head = worktree
    (tree / "a.txt").write_text("changed\n")
    done = build_mount(tree, head, tmp_path, "true")
    assert done.returncode == 3 and "MOUNT_BUILD_WORKTREE_DIRTY" in done.stderr and not (tmp_path / "br").exists()
    subprocess.run(["git", "checkout", "-q", "a.txt"], cwd=tree, check=True)
    done = build_mount(tree, head, tmp_path, "true", commit="f" * 40)
    assert done.returncode == 3 and "MOUNT_BUILD_HEAD_MISMATCH" in done.stderr and not (tmp_path / "br").exists()


def test_a_worktree_changed_during_the_build_leaves_no_commit_record(tmp_path, worktree):
    tree, head = worktree
    done = build_mount(tree, head, tmp_path, 'mkdir -p "$MOUNT_INSTALL" && echo edit >> a.txt')
    assert done.returncode == 3 and "MOUNT_BUILD_WORKTREE_DIRTY" in done.stderr
    root = tmp_path / "br" / "mount" / head[:12]
    assert not (root / "install" / "BUILD-COMMIT").exists() and not (root / "source" / "BUILD-COMMIT").exists()


def test_a_failed_build_command_leaves_no_commit_record(tmp_path, worktree):
    tree, head = worktree
    done = build_mount(tree, head, tmp_path, "false")
    assert done.returncode == 4 and "MOUNT_BUILD_FAILED" in done.stderr
    assert not list((tmp_path / "br").rglob("BUILD-COMMIT"))


PROXY = {"BUILD_PROXY": "http://127.0.0.1:10809", "BUILD_NO_PROXY": "mirrors.tuna.tsinghua.edu.cn,pypi.tuna.tsinghua.edu.cn,registry.npmmirror.com"}


def build_args(argv):
    return [argv[i + 1] for i, word in enumerate(argv) if word == "--build-arg"]


@pytest.mark.parametrize("role", ["mount-base"])
def test_a_networked_build_with_a_proxy_uses_the_host_network_and_the_predefined_proxy_arguments(repo, host, role):
    done = prepare(repo, host, role, "", build_deps=False, env=PROXY)
    assert done.returncode == 0, done.stderr
    argv = json.loads((built(host) / "argv.json").read_text())
    assert argv[argv.index("--network") + 1] == "host"
    given = build_args(argv)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        assert f"{name}={PROXY['BUILD_PROXY']}" in given
    for name in ("NO_PROXY", "no_proxy"):
        assert f"{name}={PROXY['BUILD_NO_PROXY']}" in given
    assert all(item.split("=")[0].lower() in ("http_proxy", "https_proxy", "no_proxy") for item in given)


@pytest.mark.parametrize("role", ["mount-base"])
def test_a_networked_build_without_a_proxy_is_as_before(repo, host, role):
    done = prepare(repo, host, role, "", build_deps=False)
    assert done.returncode == 0, done.stderr
    argv = json.loads((built(host) / "argv.json").read_text())
    assert argv[argv.index("--network") + 1] == "default" and "--build-arg" not in argv


def test_both_host_files_give_the_proxy_and_the_no_proxy_list_for_the_mirrors():
    for name in ("antzb", "ai-station"):
        values = dict(line.split("=", 1) for line in (HOSTS_DIR / f"{name}.env").read_text().splitlines() if line.startswith("BUILD_"))
        assert values["BUILD_PROXY"] == "http://127.0.0.1:10809"
        for mirror in ("mirrors.tuna.tsinghua.edu.cn", "pypi.tuna.tsinghua.edu.cn", "registry.npmmirror.com"):
            assert mirror in values["BUILD_NO_PROXY"].split(",")


def test_the_mount_base_installs_the_apt_versions_of_the_build_host_from_a_sorted_pin_list():
    pins = [line for line in (ROOT / "src/so101_demo_py/docker/mount-base/apt-pins.txt").read_text().splitlines() if line]
    assert len(pins) > 500
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9+.-]+=[^\s=]+", line) for line in pins)
    names = [line.split("=")[0] for line in pins]
    assert names == sorted(names) and len(names) == len(set(names))
    text = (ROOT / "src/so101_demo_py/docker/mount-base/Dockerfile").read_text()
    assert "--allow-downgrades" in text and "$(cat /tmp/mount-base/apt-pins.txt)" in text
    assert "COPY apt-packages.txt apt-pins.txt " in text


def test_the_pin_list_carries_the_packages_whose_host_and_mirror_versions_drifted_and_no_esm_version():
    """tzdata and zlib moved on the host (2026-10-23); an unpinned tzdata takes whatever the mirror offers and fails the must-match check,
    and a pin the mirror cannot serve (an ESM build) fails the image build."""
    pins = dict(line.split("=", 1) for line in (ROOT / "src/so101_demo_py/docker/mount-base/apt-pins.txt").read_text().splitlines() if line)
    for name in ("tzdata", "zlib1g", "zlib1g-dev", "libminizip1t64", "ca-certificates"):
        assert name in pins, name
    assert not [name for name, version in pins.items() if re.search(r"[+~]esm\d", version)]


def test_the_built_mount_base_is_pinned_by_id_under_the_tag_prepare_image_build_gives_it():
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", PINS["mount-base"]["id"])
    assert PINS["mount-base"]["tag"] in (IMAGES / "prepare-image-build.py").read_text()


def test_the_mount_base_removes_the_bytecode_ensurepip_compiled_for_each_venv():
    text = (ROOT / "src/so101_demo_py/docker/mount-base/Dockerfile").read_text()
    for venv in ("/opt/venv", "/act/venv"):
        assert f"find {venv} -type d -name __pycache__ -prune -exec rm -rf {{}} +" in text


@pytest.mark.parametrize("name", ["mount-base"])
def test_a_continued_run_line_never_follows_a_line_without_its_backslash(name):
    lines = (ROOT / f"src/so101_demo_py/docker/{name}/Dockerfile").read_text().split("\n")
    for number, line in enumerate(lines[1:], 2):
        if line.startswith("    &&") or line.startswith("      ") and lines[number - 2].rstrip().endswith("\\"):
            previous = lines[number - 2].rstrip()
            assert previous.endswith("\\") or previous.endswith("'") or previous == "", f"{name}:{number}"
