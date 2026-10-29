"""A campaign config without `mount_build` is refused by the collection and processing CLIs before the run id is used: no run
root, no frozen inputs, no Docker call, no lease or slot (image mode is retired; `load_campaign_config` stays shared because the
recompute reads sealed image-mode configs through it)."""

import json
from pathlib import Path

import pytest

from test_act_process_parallel_cli import process, _service_store_released  # noqa: F401 - fixture
from test_container_task_campaign_integration import (  # noqa: F401 - fixtures and the world builder
    _short_polls, controlled_verifier, make_world, run, shared)


def unmounted_world(tmp_path, shared, monkeypatch, plane):
    world = make_world(tmp_path, shared, monkeypatch, plane=plane, mount=False)
    document = json.loads(Path(world.campaign_path).read_text())
    assert "mount_build" not in document
    return world


@pytest.mark.parametrize("plane", ["W1", "W8"])
def test_collect_refuses_a_config_without_a_mount_build_before_the_run_exists(tmp_path, shared, monkeypatch, capsys, plane):
    world = unmounted_world(tmp_path, shared, monkeypatch, plane)
    code, out, err = run(world, capsys)
    assert code == 2 and "MOUNT_BUILD_REQUIRED" in err and out == ""
    assert world.docker.calls == []
    assert not (world.evidence / "run-one").exists()


def test_process_refuses_a_config_without_a_mount_build_before_the_run_is_read(tmp_path, shared, monkeypatch, capsys):
    world = unmounted_world(tmp_path, shared, monkeypatch, "W1")
    code, out, err = process(world, capsys, "--phase2")
    assert code == 2 and "MOUNT_BUILD_REQUIRED" in err
    assert world.docker.calls == []
    assert not (world.evidence / "run-one").exists()
