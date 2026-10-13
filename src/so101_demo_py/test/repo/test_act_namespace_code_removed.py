"""The per-worker ROS namespace code of the ACT container shard is gone from the source tree.

An ACT instance runs at one fixed identity (domain 181, root namespace, the un-namespaced names of the plain ACT
execution stack). Everything that existed only to give each shard its own namespace was removed, so no file, symbol,
marker or error code of it may come back. Tokens are built from fragments so this file does not match its own scan.
"""
from pathlib import Path
import subprocess

import pytest
from paths import REPOSITORY


def _join(*parts):
    return "".join(parts)


REMOVED_FILES = [
    "src/so101_demo_py/src/runtime/container_campaign/" + _join("ros", "_namespace.py"),
    "src/so101_demo_py/src/runtime/container_campaign/" + _join("stack", "_launch.py"),
    "src/so101_demo_py/launch/" + _join("so101_mujoco_container", "_shard.launch.py"),
    "src/so101_demo_py/src/act/offline/" + _join("container", "_bag_topics.py"),
    "src/so101_mujoco_support/src/" + _join("act_scoped", "_bag_record.cpp"),
]

REMOVED_TOKENS = [
    _join("ros", "_namespace"),
    _join("ContainerAct", "StackLaunch"),
    _join("container_ros", "_init_options"),
    _join("container_ros", "_global_init_options"),
    _join("SO101_ACT_CONTAINER", "_NAMESPACE"),
    _join("logical", "_channel_map"),
    _join("bag-topic", "-map"),
    _join("act_scoped", "_bag_record"),
    _join("graph_in", "_namespace"),
    _join("--ros", "-namespace"),
    _join("Push", "RosNamespace"),
    _join("namespace", "_remappings"),
    _join("namespaced", "_parameters"),
    _join("NAMESPACE", "_DRIFT"),
    _join("container", "_bag_topics"),
    _join("container_campaign", ".stack_launch"),
    _join("so101_mujoco", "_container_shard"),
]


def _tracked_text_files():
    listing = subprocess.run(["git", "ls-files", "-z", "--", "src"], cwd=REPOSITORY, check=True,
                             capture_output=True).stdout
    for name in listing.split(b"\0"):
        if not name:
            continue
        path = REPOSITORY / name.decode()
        if path == Path(__file__).resolve() or not path.is_file():
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


@pytest.mark.parametrize("relative", REMOVED_FILES)
def test_a_removed_namespace_file_is_gone(relative):
    assert not (REPOSITORY / relative).exists()


def test_no_source_file_mentions_a_removed_namespace_symbol_marker_or_error_code():
    offenders = {}
    for path, text in _tracked_text_files():
        found = [token for token in REMOVED_TOKENS if token in text]
        if found:
            offenders[str(path.relative_to(REPOSITORY))] = found
    assert not offenders, offenders
