"""Image-byte freeze and installed-runtime readback for both campaign images."""

import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import stat
import sys

from so101_demo.runtime.container_campaign.process_identity import container_key_from_inspect
from so101_demo.runtime.inference.config import _open_regular
from so101_demo.runtime.parallel_ipc.frames import _pairs, canonical_json


INFERENCE_PACKAGES = ("so101_demo_py",)
#: the shard's ament packages whose resolved prefix is read back; the lossless queued-state overlay
#: (joint_trajectory_controller, joint_state_broadcaster, so101_queued_state_publisher) must resolve inside
#: /act/install, so an apt fallback to /opt/ros/jazzy is refused
SHARD_PACKAGES = INFERENCE_PACKAGES + ("so101_teleop", "so101_quik", "so101_mujoco_support",
    "controller_manager", "joint_trajectory_controller", "joint_state_broadcaster",
    "so101_queued_state_publisher", "mujoco_ros2_control", "mujoco_ros2_control_msgs",
    "mujoco_ros2_control_plugins")


def _require(condition):
    if not condition:
        raise ValueError("IMAGE_PROVENANCE_INVALID")


def _sha(value, length=64):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{"+str(length)+r"}", value) is not None


def _json(payload):
    if type(payload) is bytes:
        payload = payload.decode("utf-8", errors="strict")
    _require(type(payload) is str)
    return json.loads(payload, object_pairs_hook=_pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")))


def _tree(root):
    root = Path(root)
    _require(root.is_absolute() and root.resolve(strict=True) == root and root.is_dir())
    files = {}
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(metadata.st_mode):
            target = path.readlink()
            _require(not target.is_absolute() and path.resolve(strict=True).is_relative_to(root))
            files[relative] = dict(kind="symlink", target=str(target))
        elif stat.S_ISREG(metadata.st_mode):
            digest = hashlib.sha256()
            with _open_regular(path) as stream:
                while chunk := stream.read(1024*1024):
                    digest.update(chunk)
            files[relative] = dict(kind="file", sha256=digest.hexdigest(), size=metadata.st_size,
                                   mode=stat.S_IMODE(metadata.st_mode))
        else:
            _require(stat.S_ISDIR(metadata.st_mode))
    _require(bool(files))
    return dict(files=files, sha256=hashlib.sha256(canonical_json(files)).hexdigest())


def _git(commit, submodules):
    _require(_sha(commit, 40) and type(submodules) is dict)
    for path, value in submodules.items():
        _require(type(path) is str and path and not Path(path).is_absolute()
                 and ".." not in Path(path).parts and str(Path(path)) == path and _sha(value, 40))


def _git_readback(source_root, commit, submodules):
    with _open_regular(Path(source_root) / ".image-git.json") as stream:
        metadata = _json(stream.read())
    _require(metadata == dict(git_commit=commit, submodules=submodules))


def _runtime_contract(runtime):
    _require(type(runtime) is dict and set(runtime) == {
        "interpreter", "dependencies", "module_origins", "package_prefixes"})
    _require(runtime["interpreter"] == "/act/venv/bin/python")
    for group in ("dependencies", "module_origins", "package_prefixes"):
        _require(type(runtime[group]) is dict and bool(runtime[group]))
        for name, value in runtime[group].items():
            _require(type(name) is str and bool(name) and type(value) is str and bool(value))
            if group != "dependencies":
                path = Path(value)
                _require(path.is_absolute() and ".." not in path.parts
                         and path.is_relative_to("/act/install") and str(path) == value)


def freeze_image(*, source_root, install_root, git_commit, submodules, runtime):
    try:
        _git(git_commit, submodules)
        _git_readback(source_root, git_commit, submodules)
        _runtime_contract(runtime)
        return dict(schema_version=1, kind="ACT_CONTAINER_IMAGE_FREEZE",
            source=_tree(source_root) | dict(git_commit=git_commit, submodules=submodules.copy()),
            install=_tree(install_root), runtime=json.loads(canonical_json(runtime)))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        raise ValueError("IMAGE_PROVENANCE_INVALID") from error


def verify_image_freeze(manifest, *, source_root, install_root, runtime):
    try:
        _require(type(manifest) is dict and set(manifest) == {"schema_version", "kind", "source", "install", "runtime"})
        _require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1
                 and manifest["kind"] == "ACT_CONTAINER_IMAGE_FREEZE")
        _require(type(manifest["source"]) is dict and set(manifest["source"]) == {
            "git_commit", "submodules", "files", "sha256"})
        _require(type(manifest["install"]) is dict and set(manifest["install"]) == {"files", "sha256"})
        source = manifest["source"]
        _git(source["git_commit"], source["submodules"])
        _git_readback(source_root, source["git_commit"], source["submodules"])
        _runtime_contract(manifest["runtime"])
        _runtime_contract(runtime)
        _require(manifest["runtime"] == runtime)
        _require({name: source[name] for name in ("files", "sha256")} == _tree(source_root))
        _require(manifest["install"] == _tree(install_root))
        return dict(schema_version=1, kind="ACT_CONTAINER_IMAGE_READBACK",
            package_source_sha256=source["sha256"], install_sha256=manifest["install"]["sha256"],
            git_commit=source["git_commit"], submodules=source["submodules"].copy(),
            runtime=json.loads(canonical_json(runtime)))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        raise ValueError("IMAGE_PROVENANCE_INVALID") from error


def runtime_readback(contract):
    """Import the requested installed modules and query actual dependency metadata."""
    from ament_index_python.packages import get_package_prefix

    _runtime_contract(contract)
    modules = {name: str(Path(importlib.import_module(name).__file__).resolve(strict=True))
               for name in contract["module_origins"]}
    runtime = dict(interpreter=sys.executable,
        dependencies={name: importlib.metadata.version(name) for name in contract["dependencies"]},
        module_origins=modules,
        package_prefixes={name: str(Path(get_package_prefix(name)).resolve(strict=True))
                          for name in contract["package_prefixes"]})
    _runtime_contract(runtime)
    return runtime


def _report(report):
    _require(type(report) is dict and set(report) == {"schema_version", "kind",
        "package_source_sha256", "install_sha256", "git_commit", "submodules", "runtime"})
    _require(type(report["schema_version"]) is int and report["schema_version"] == 1
             and report["kind"] == "ACT_CONTAINER_IMAGE_READBACK")
    _require(_sha(report["package_source_sha256"]) and _sha(report["install_sha256"]))
    _git(report["git_commit"], report["submodules"])
    _runtime_contract(report["runtime"])


def read_container_provenance(container_id, *, docker_runner):
    try:
        _require(_sha(container_id))
        def inspect():
            result = docker_runner(["docker", "inspect", container_id])
            _require(result.returncode == 0)
            documents = _json(result.stdout)
            _require(type(documents) is list and len(documents) == 1)
            document = documents[0]
            key = container_key_from_inspect(document, launch_generation=1)
            state = document["State"]
            _require(key.container_id == container_id and state["Running"] is True
                     and state["Restarting"] is False and type(state["Pid"]) is int and state["Pid"] > 0)
            return key
        before = inspect()
        result = docker_runner(["docker", "exec", container_id, "/act/venv/bin/python", "-I", "-m",
                               "so101_demo.runtime.container_campaign.provenance"])
        _require(result.returncode == 0)
        report = _json(result.stdout)
        _report(report)
        _require(inspect() == before)
        return dict(container_id=before.container_id, docker_started_at=before.docker_started_at,
                    image_digest=before.image_digest, provenance=report)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, AttributeError) as error:
        raise ValueError("IMAGE_PROVENANCE_INVALID") from error


def read_installed_image():
    with _open_regular("/act/provenance.json") as stream:
        manifest = _json(stream.read())
    runtime = runtime_readback(manifest["runtime"])
    return verify_image_freeze(manifest, source_root="/act/source", install_root="/act/install", runtime=runtime)


def write_build_freeze(role):
    """Build-only producer; bootstrap never calls it or repairs a frozen image."""
    import subprocess

    _require(role in ("inference", "shard"))
    modules = ["so101_demo"] + (["so101_teleop", "so101_quik"] if role == "shard" else [])
    packages = list(SHARD_PACKAGES if role == "shard" else INFERENCE_PACKAGES)
    versions = {distribution.metadata["Name"]: importlib.metadata.version(distribution.metadata["Name"])
                for distribution in importlib.metadata.distributions() if distribution.metadata.get("Name")}
    runtime = runtime_readback(dict(interpreter="/act/venv/bin/python", dependencies=versions,
        module_origins={name: "/act/install" for name in modules},
        package_prefixes={name: "/act/install" for name in packages}))
    if role == "inference":
        pins = {"torch": "2.13.0+cu130", "torchvision": "0.28.0+cu130", "ultralytics": "8.4.115",
                "numpy": "1.26.4", "PyYAML": "6.0.2", "Pillow": "12.3.0"}
        _require(all(importlib.metadata.version(name) == value for name, value in pins.items()))
    dependencies = Path("/act/install/share/act-image-dependencies.json")
    with dependencies.open("xb") as stream:
        stream.write(canonical_json(dict(python=versions, apt=subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Package}=${Version}\\n"], text=True).splitlines())))
    os.chmod(dependencies, 0o444)
    with _open_regular("/act/source/.image-git.json") as stream:
        metadata = _json(stream.read())
    manifest = freeze_image(source_root="/act/source", install_root="/act/install", runtime=runtime, **metadata)
    with Path("/act/provenance.json").open("xb") as stream:
        stream.write(canonical_json(manifest)+b"\n")
    print(canonical_json(verify_image_freeze(manifest, source_root="/act/source",
        install_root="/act/install", runtime=runtime)).decode())


def main():
    try:
        report = read_installed_image()
        print(canonical_json(report).decode())
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, ImportError) as error:
        print(f"IMAGE_PROVENANCE_INVALID: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
