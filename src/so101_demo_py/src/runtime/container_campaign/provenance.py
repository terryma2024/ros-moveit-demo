"""Installed-runtime readback of a mount-mode container: the records of the mounted trees and what the interpreter imports."""

import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import time

from so101_demo.runtime.container_campaign.docker_inspect import bounded_docker_inspect
from so101_demo.runtime.container_campaign.mount_build import (
    COMMIT_ENV, ENTRY_SCRIPT, INSTALL_ENV, INTERPRETER, SOURCE_ENV, read_record, record_sha256)
from so101_demo.runtime.container_campaign.process_identity import container_key_from_inspect
from so101_demo.runtime.parallel_ipc.frames import _pairs, canonical_json


INFERENCE_PACKAGES = ("so101_demo_py",)
#: the shard's ament packages whose resolved prefix is read back; the lossless queued-state overlay
#: (joint_trajectory_controller, joint_state_broadcaster, so101_queued_state_publisher) must resolve inside
#: the mounted install, so an apt fallback to /opt/ros/jazzy is refused
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


def _git(commit, submodules):
    _require(_sha(commit, 40) and type(submodules) is dict)
    for path, value in submodules.items():
        _require(type(path) is str and path and not Path(path).is_absolute()
                 and ".." not in Path(path).parts and str(Path(path)) == path and _sha(value, 40))


def _runtime_contract(runtime, install_root):
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
                         and path.is_relative_to(install_root) and str(path) == value)


def runtime_readback(contract, install_root):
    """Import the requested installed modules and query actual dependency metadata."""
    from ament_index_python.packages import get_package_prefix

    _runtime_contract(contract, install_root)
    modules = {name: str(Path(importlib.import_module(name).__file__).resolve(strict=True))
               for name in contract["module_origins"]}
    runtime = dict(interpreter=sys.executable,
        dependencies={name: importlib.metadata.version(name) for name in contract["dependencies"]},
        module_origins=modules,
        package_prefixes={name: str(Path(get_package_prefix(name)).resolve(strict=True))
                          for name in contract["package_prefixes"]})
    _runtime_contract(runtime, install_root)
    return runtime


def _report(report, install_root):
    _require(type(report) is dict and set(report) == {"schema_version", "kind",
        "package_source_sha256", "install_sha256", "git_commit", "submodules", "runtime"})
    _require(type(report["schema_version"]) is int and report["schema_version"] == 1
             and report["kind"] == "ACT_CONTAINER_IMAGE_READBACK")
    _require(_sha(report["package_source_sha256"]) and _sha(report["install_sha256"]))
    _git(report["git_commit"], report["submodules"])
    _runtime_contract(report["runtime"], install_root)


#: A container read just after `docker run` may not be up yet: the daemon's inspect fails, the container is not running yet, or the exec of
#: the probe exits non-zero. Only these three are read again, `READ_ATTEMPTS` times in all with `READ_PAUSES_S` between (3.5 s at most).
#: What was read is compared once, as before: a report that is malformed or different, another container id, and a restart between the two
#: inspects are refused at the first sight.
READ_ATTEMPTS = 4
READ_PAUSES_S = (0.5, 1.0, 2.0)
_sleep = time.sleep


class _NotReadYet(ValueError):
    pass


def read_container_provenance(container_id, *, docker_runner, mount_role, install_root):
    """Reads a mount-mode container: the entry script first (it checks the trees' records and sets the environment), and `mount_role`
    ('inference' or 'shard') says which modules the readback imports."""
    try:
        _require(_sha(container_id))
        def inspect(retryable=True):
            def refuse(condition):
                if not condition:
                    raise (_NotReadYet if retryable else ValueError)("IMAGE_PROVENANCE_INVALID")
            result = bounded_docker_inspect(docker_runner, ["docker", "inspect", container_id])
            refuse(result.returncode == 0)
            documents = _json(result.stdout)
            _require(type(documents) is list and len(documents) == 1)
            document = documents[0]
            key = container_key_from_inspect(document, launch_generation=1)
            state = document["State"]
            _require(key.container_id == container_id)
            refuse(state["Running"] is True and state["Restarting"] is False and type(state["Pid"]) is int and state["Pid"] > 0)
            return key
        module = "so101_demo.runtime.container_campaign.provenance"
        command = [ENTRY_SCRIPT, INTERPRETER, "-I", "-B", "-m", module, mount_role]
        def read():
            before = inspect()
            result = docker_runner(["docker", "exec", container_id, *command])
            if result.returncode != 0:
                raise _NotReadYet("IMAGE_PROVENANCE_INVALID")
            return before, result
        for attempt in range(READ_ATTEMPTS):
            try:
                before, result = read()
                break
            except _NotReadYet:
                if attempt == READ_ATTEMPTS - 1:
                    raise
                _sleep(READ_PAUSES_S[attempt])
        report = _json(result.stdout)
        _report(report, install_root)
        _require(inspect(retryable=False) == before)
        return dict(container_id=before.container_id, docker_started_at=before.docker_started_at,
                    image_digest=before.image_digest, provenance=report)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, AttributeError) as error:
        raise ValueError("IMAGE_PROVENANCE_INVALID") from error


def read_mounted_image(role):
    """Mount mode: the report a container gives for the trees mounted into it. The trees' records name the commit, the two hashes are
    those of the records (`mount_build`), and the runtime is read back from what is imported, as for a frozen image."""
    _require(role in ("inference", "shard"))
    install, source = Path(os.environ[INSTALL_ENV]), Path(os.environ[SOURCE_ENV])
    commit = os.environ[COMMIT_ENV]
    _require(_sha(commit, 40))
    for directory in (install, source):
        _require(read_record(directory)[1] == commit)
    modules = ["so101_demo"] + (["so101_teleop", "so101_quik"] if role == "shard" else [])
    packages = list(SHARD_PACKAGES if role == "shard" else INFERENCE_PACKAGES)
    versions = {distribution.metadata["Name"]: importlib.metadata.version(distribution.metadata["Name"])
                for distribution in importlib.metadata.distributions() if distribution.metadata.get("Name")}
    runtime = runtime_readback(dict(interpreter=INTERPRETER, dependencies=versions,
        module_origins={name: str(install) for name in modules},
        package_prefixes={name: str(install) for name in packages}), str(install))
    return dict(schema_version=1, kind="ACT_CONTAINER_IMAGE_READBACK", package_source_sha256=record_sha256(source),
                install_sha256=record_sha256(install), git_commit=commit, submodules={}, runtime=runtime)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        report = read_mounted_image(argv[0])
        print(canonical_json(report).decode())
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, ImportError) as error:
        print(f"IMAGE_PROVENANCE_INVALID: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
