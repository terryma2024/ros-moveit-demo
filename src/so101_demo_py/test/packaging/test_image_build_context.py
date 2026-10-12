"""Contract: container images that install ``so101_demo_py`` must carry every file
its ``setup.py`` packages relative to the package directory.

``setup.py`` adds ``../../scripts/run_so101_adaptive_batch.zsh`` to ``data_files``.
Relative to the package directory inside an image (``/opt/so101_demo_py``) that path
resolves to ``/scripts/run_so101_adaptive_batch.zsh``. A Dockerfile that copies only
``src/so101_demo_py`` therefore fails while the wheel build copies data files, long
before the image can be used. The build context and the ``COPY`` instructions must
agree with ``setup.py``, so that contract is asserted here instead of being rediscovered
by a full image build.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path, PurePosixPath
from paths import REPOSITORY


REPOSITORY_ROOT = REPOSITORY
PACKAGE_SOURCE = "src/so101_demo_py"
DOCKERFILES = sorted((REPOSITORY_ROOT / "src/so101_demo_py/docker").glob("*/Dockerfile"))

_COPY_PATTERN = re.compile(r"^\s*COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)\s*$")


def _normalize(path: PurePosixPath) -> PurePosixPath:
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "/", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return PurePosixPath("/", *parts)


def _packaged_parent_paths() -> list[str]:
    """``data_files`` entries in ``setup.py`` that escape the package directory."""

    setup_py = (REPOSITORY_ROOT / "src/so101_demo_py/setup.py").read_text(encoding="utf-8")
    tree = ast.parse(setup_py)
    found = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("../")
    }
    assert found, "setup.py no longer packages any parent-relative file"
    return sorted(found)


def _context_path(relative: str) -> str:
    """Repository-relative path a ``COPY`` source must use for a packaged parent file."""

    resolved = _normalize(PurePosixPath(PACKAGE_SOURCE) / relative)
    return str(resolved).lstrip("/")


def _copy_instructions(dockerfile: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = _COPY_PATTERN.match(line)
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def _dockerignore_matches(pattern: str, path: str) -> bool:
    pattern = pattern.rstrip("/")
    if pattern in {"*", "**"}:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return path == prefix or path.startswith(prefix + "/")
    return path == pattern or path.startswith(pattern + "/")


def _context_included(relative: str, ignore_file: Path) -> bool:
    """Whether a repository-relative path survives the Dockerfile-specific ignore list."""

    if not ignore_file.is_file():
        return True
    included = True
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        pattern = raw.strip()
        if not pattern or pattern.startswith("#"):
            continue
        if _dockerignore_matches(pattern.lstrip("!"), relative):
            included = pattern.startswith("!")
    return included


def _images_installing_the_package() -> list[Path]:
    selected = [
        dockerfile
        for dockerfile in DOCKERFILES
        if any(
            source.rstrip("/") == PACKAGE_SOURCE
            for source, _ in _copy_instructions(dockerfile)
        )
    ]
    assert selected, "no Dockerfile copies the so101_demo_py package"
    return selected


def test_every_packaged_parent_file_reaches_its_image() -> None:
    required_relative = _packaged_parent_paths()

    failures: list[str] = []
    for dockerfile in _images_installing_the_package():
        copies = _copy_instructions(dockerfile)
        package_destination = _normalize(
            PurePosixPath(
                next(
                    destination
                    for source, destination in copies
                    if source.rstrip("/") == PACKAGE_SOURCE
                )
            )
        )
        ignore_file = dockerfile.with_name(dockerfile.name + ".dockerignore")

        for relative in required_relative:
            target = _normalize(package_destination / relative)
            context_path = _context_path(relative)
            for source, destination in copies:
                source_path = REPOSITORY_ROOT / source
                destination_path = _normalize(PurePosixPath(destination))
                if source_path.is_file():
                    if destination_path == target and _context_included(
                        source, ignore_file
                    ):
                        break
                elif destination_path == target or str(target).startswith(
                    str(destination_path) + "/"
                ):
                    tail = target.relative_to(destination_path)
                    if (source_path / str(tail)).is_file() and _context_included(
                        source, ignore_file
                    ):
                        break
            else:
                failures.append(
                    f"{dockerfile.relative_to(REPOSITORY_ROOT)} does not provide "
                    f"{target} (setup.py packages {relative}, build context "
                    f"{context_path})"
                )

    assert not failures, "\n".join(failures)


def test_images_installing_the_package_use_their_own_ignore_list() -> None:
    for dockerfile in _images_installing_the_package():
        ignore_file = dockerfile.with_name(dockerfile.name + ".dockerignore")
        if not ignore_file.is_file():
            continue
        required = _packaged_parent_paths()
        for relative in required:
            assert _context_included(_context_path(relative), ignore_file), (
                f"{ignore_file.relative_to(REPOSITORY_ROOT)} excludes "
                f"{_context_path(relative)}, which setup.py packages as {relative}"
            )


def test_campaign_shard_python_mujoco_pin_equals_the_setup_declaration() -> None:
    """The shard venv's Python MuJoCo must be the version setup.py requires and the vendored native one."""
    declared = set(re.findall(r'"mujoco==([0-9.]+)"', (REPOSITORY_ROOT / PACKAGE_SOURCE / "setup.py").read_text()))
    assert len(declared) == 1
    dockerfile = REPOSITORY_ROOT / PACKAGE_SOURCE / "docker/campaign-shard/Dockerfile"
    pinned = re.findall(r"\bmujoco==([0-9.]+)", dockerfile.read_text())
    assert pinned == sorted(declared)


# --- campaign-shard image layering -------------------------------------------------------------------

SHARD_DOCKERFILE = REPOSITORY_ROOT / PACKAGE_SOURCE / "docker/campaign-shard/Dockerfile"
SHARD_BASE = "so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115"
BUILD_TREE_PATHS = ("/act/build", "/act/build-source", "/act/build-log", "/act/build-tools")
# The dependency stage is cache-keyed by its text: it must stay byte-identical to the previous revision
# except for the mujoco pin that tracks setup.py.
SHARD_DEPS_STAGE = """\
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 YOLO_OFFLINE=true
RUN apt-get update && apt-get install --yes --no-install-recommends \\
    build-essential cmake python3-dev python3-venv python3-colcon-common-extensions \\
    libboost-all-dev libeigen3-dev libfmt-dev libglfw3-dev libegl1-mesa-dev libtinyxml2-dev \\
    ros-jazzy-moveit ros-jazzy-moveit-configs-utils ros-jazzy-ros2-control ros-jazzy-ros2-controllers \\
    ros-jazzy-control-toolbox ros-jazzy-mujoco-vendor ros-jazzy-backward-ros \\
    ros-jazzy-ros-gz-interfaces ros-jazzy-tf2-geometry-msgs ros-jazzy-vision-msgs
RUN apt-get install --yes --no-install-recommends \\
    ros-jazzy-ros2-control-cmake ros-jazzy-ros2-control-test-assets \\
    ros-jazzy-example-interfaces ros-jazzy-launch-testing-ros \\
    ros-jazzy-launch ros-jazzy-launch-testing ros-jazzy-launch-ros
RUN python3 -m venv --system-site-packages /act/venv \\
    && printf '%s\\n' 'import sys; sys.path[:0] = ["/act/install/lib/python3.12/site-packages", "/act/install/local/lib/python3.12/dist-packages", "/opt/ros/jazzy/lib/python3.12/site-packages", "/opt/venv/lib/python3.12/site-packages"]' \\
       > /act/venv/lib/python3.12/site-packages/act-runtime.pth \\
    && NO_PROXY="${NO_PROXY:+$NO_PROXY,}pypi.tuna.tsinghua.edu.cn" no_proxy="${no_proxy:+$no_proxy,}pypi.tuna.tsinghua.edu.cn" \\
       /act/venv/bin/python -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple pydantic==2.14.1 mujoco==3.12.0 colcon-override-check==0.0.1 pytest==7.4.4 pytest-xdist==3.8.0
"""
COLCON_COMMON = (
    "--base-paths src third_party",
    "--build-base /act/build --install-base /act/install --merge-install",
    "--allow-overriding controller_manager hardware_interface_testing mujoco_ros2_control "
    "mujoco_ros2_control_msgs mujoco_ros2_control_plugins",
    "--parallel-workers 4 --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON",
    "-DPython3_EXECUTABLE=/act/venv/bin/python -DPYTHON_EXECUTABLE=/act/venv/bin/python",
    "-DFETCHCONTENT_SOURCE_DIR_LODEPNG=/act/source/build-deps/lodepng -DFETCHCONTENT_FULLY_DISCONNECTED=ON",
)


def _shard_stages() -> dict[str, list[str]]:
    """Logical instructions (continuations joined) per stage, in order; element 0 is the ``FROM``."""

    stages: dict[str, list[str]] = {}
    current: list[str] | None = None
    pending = ""
    for line in SHARD_DOCKERFILE.read_text(encoding="utf-8").splitlines():
        if not pending and (not line.strip() or line.lstrip().startswith("#")):
            continue
        if line.endswith("\\"):
            pending += line + "\n"
            continue
        pending += line
        instruction, pending = pending, ""
        match = re.match(r"FROM\s+(\S+)\s+AS\s+(\S+)$", instruction)
        if match:
            current = stages.setdefault(match.group(2), [])
        else:
            assert current is not None, "instruction before the first FROM " + instruction
        current.append(instruction)
    return stages


def _shard_stage_text(name: str) -> str:
    return "\n".join(_shard_stages()[name][1:])


def _package_closure() -> dict[str, tuple[str, set[str]]]:
    """What ``colcon --packages-up-to so101_demo_py`` builds: name -> (directory, in-tree dependencies).

    colcon's up-to selection follows every dependency category, test dependencies included.
    """

    import xml.etree.ElementTree as ET

    found: dict[str, tuple[str, set[str]]] = {}
    for top in ("src", "third_party"):
        for path in sorted((REPOSITORY_ROOT / top).rglob("package.xml")):
            relative = path.relative_to(REPOSITORY_ROOT)
            if any(part in ("build", "install", "log", "node_modules") for part in relative.parts):
                continue
            root = ET.parse(path).getroot()
            dependencies = {
                element.text.strip()
                for tag in ("depend", "build_depend", "exec_depend", "buildtool_depend",
                            "build_export_depend", "test_depend")
                for element in root.findall(tag)
            }
            found[root.find("name").text.strip()] = (relative.parent.as_posix(), dependencies)
    selected: set[str] = set()
    pending = ["so101_demo_py"]
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        selected.add(name)
        pending.extend(dependency for dependency in found[name][1] if dependency in found)
    return {name: (found[name][0], found[name][1] & set(found)) for name in selected}


def _colcon_runs() -> list[str]:
    return [item for item in _shard_stages().get("build", []) if item.startswith("RUN") and "colcon" in item]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\\\n", " "))


def _selected(run: str) -> set[str]:
    match = re.search(r"--packages-select ([a-z0-9_ ]+?) --", _flat(run))
    assert match, "colcon invocation without --packages-select"
    return set(match.group(1).split())


def test_shard_dockerfile_has_deps_build_and_final_stages() -> None:
    stages = _shard_stages()
    assert list(stages) == ["deps", "build", "final"]
    assert stages["deps"][0] == f"FROM {SHARD_BASE} AS deps"
    assert stages["build"][0] == "FROM deps AS build"
    assert stages["final"][0] == "FROM deps AS final"


def test_shard_dependency_stage_text_is_unchanged_apart_from_the_mujoco_pin() -> None:
    assert "\n".join(_shard_stages()["deps"][1:]) + "\n" == SHARD_DEPS_STAGE


def test_shard_final_stage_carries_no_build_tree() -> None:
    final = _shard_stage_text("final")
    for path in BUILD_TREE_PATHS:
        assert path not in final, path
    for word in ("colcon", "SO101_TELEOP_BUN", "bun-cache"):
        assert word not in final, word
    assert "COPY --from=build /act/install /act/install" in final


def test_shard_final_stage_copies_the_whole_read_only_source_once() -> None:
    final = _shard_stages()["final"]
    assert [item for item in final if re.match(r"COPY\s+source\s+/act/source$", item)] == ["COPY source /act/source"]
    assert sum(1 for item in final if item.startswith("COPY") and "/act/source" in item) == 1
    assert "RUN chmod -R a+rX,a-w /act/source" in final
    assert not any(re.match(r"COPY\s+source\s", item) for item in _shard_stages()["build"])


def test_shard_final_stage_keeps_the_freeze_and_runtime_contract() -> None:
    final = _shard_stage_text("final")
    for fragment in (
        "chmod -R a+rX,a-w /act/install && chmod u+w /act/install/share",
        'write_build_freeze("shard")',
        "chmod a-w /act/install/share /act/install/share/act-image-dependencies.json /act/provenance.json /act/image-role",
        "-m so101_demo.runtime.container_campaign.provenance",
        "COPY source/src/so101_demo_py/docker/campaign-inference/bootstrap.bash /act/bootstrap.bash",
        "printf '%s\\n' shard > /act/image-role",
        "AMENT_PREFIX_PATH=/act/install:/opt/ros/jazzy",
        "/act/install/bin/ros2",
        'ENTRYPOINT ["/act/bootstrap.bash", "/act/venv/bin/python", "-I", "-m", '
        '"so101_demo.runtime.container_campaign.image_bootstrap"]',
    ):
        assert fragment in final, fragment


def test_shard_layers_build_exactly_the_colcon_closure_once() -> None:
    runs = _colcon_runs()
    assert len(runs) == 2
    early, late = (_selected(run) for run in runs)
    closure = _package_closure()
    assert early.isdisjoint(late)
    assert early | late == set(closure)
    # The early layer is dependency-closed, so it never needs a file of the later layer.
    for name in early:
        assert closure[name][1] <= early, name
    for name in late:
        assert closure[name][1] <= early | late, name
    assert all(closure[name][0].startswith("third_party/") or name == "so101_quik" for name in early)
    for run in runs:
        flat = _flat(run)
        for fragment in COLCON_COMMON:
            assert fragment in flat, fragment
        assert "--log-base /act/build-log build" in flat
        assert "pytest --version" in flat
    assert "ROS_PACKAGE_READBACK" in runs[0]
    assert "source /act/install/local_setup.bash" in _flat(runs[1]), "the later layer must see the earlier install"


def test_shard_copies_precede_the_colcon_run_that_needs_them() -> None:
    build = _shard_stages()["build"]
    runs = _colcon_runs()
    assert len(runs) == 2
    early_at, late_at = build.index(runs[0]), build.index(runs[1])
    closure = _package_closure()
    early, late = (_selected(run) for run in runs)

    def copied(before: int) -> list[str]:
        return [item.split()[2].rstrip("/") for item in build[:before] if item.startswith("COPY ")]

    for name, bound in [(n, early_at) for n in early] + [(n, late_at) for n in late]:
        directory = f"/act/build-source/{closure[name][0]}"
        assert any(
            directory == destination or directory.startswith(destination + "/") for destination in copied(bound)
        ), f"{name} ({directory}) is not copied before the colcon run that builds it"
    # Nothing that changes often may sit in front of the native layer.
    early_copies = copied(early_at)
    assert not any(destination.endswith(("/src", "/scripts")) for destination in early_copies)
    assert "/act/source/build-deps/lodepng" in early_copies
    assert "COPY source/src /act/build-source/src" in build[early_at:late_at]
