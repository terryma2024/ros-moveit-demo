"""A campaign container runs only its mounted role, after the readback of the mounted trees (the base image has no role file)."""

import importlib
from pathlib import Path

import pytest


def module():
    return importlib.import_module("so101_demo.runtime.container_campaign.image_bootstrap")


@pytest.fixture
def mounted(monkeypatch):
    mod = module()
    monkeypatch.setenv("SO101_MOUNT_INSTALL", "/build/mount/0123456789ab/install")
    monkeypatch.setattr(mod.sys, "executable", "/act/venv/bin/python")
    return mod


@pytest.mark.parametrize("command,role", [
    (["campaign_inference", "--role", "head", "--config", "/inputs/head.json"], "inference"),
    (["campaign_inference", "--role", "teacher", "--config", "/inputs/teacher.json"], "inference"),
    (["campaign_shard", "--spec", "/inputs/shard.json"], "shard"),
    (["campaign_processor", "--spec", "/inputs/processor.json"], "shard"),
])
def test_the_mounted_readback_precedes_exec(mounted, monkeypatch, capsys, command, role):
    calls = []
    monkeypatch.setattr(mounted, "readback", lambda mount_role: calls.append(("readback", mount_role)) or {"kind": "actual-readback"})
    monkeypatch.setattr(mounted.os, "execv", lambda binary, argv: calls.append((binary, argv)))
    assert mounted.main(command) == 0
    assert calls == [("readback", role), ("/act/venv/bin/python", ["/act/venv/bin/python", "-I", "-B", "-m",
                    "so101_demo.cli." + command[0], *command[1:]])]
    assert '"kind":"actual-readback"' in capsys.readouterr().out


@pytest.mark.parametrize("command", [["bash", "-c", "something"], ["not_a_program"], []])
def test_foreign_command_never_executes(mounted, monkeypatch, command):
    monkeypatch.setattr(mounted, "readback", lambda mount_role: pytest.fail("a foreign command must be rejected before the readback"))
    monkeypatch.setattr(mounted.os, "execv", lambda *args: pytest.fail("foreign command executed"))
    assert mounted.main(command) == 2


def test_a_container_without_mounted_trees_never_executes(monkeypatch):
    mod = module()
    monkeypatch.delenv("SO101_MOUNT_INSTALL", raising=False)
    monkeypatch.setattr(mod.sys, "executable", "/act/venv/bin/python")
    monkeypatch.setattr(mod, "readback", lambda mount_role: pytest.fail("image mode is retired"))
    monkeypatch.setattr(mod.os, "execv", lambda *args: pytest.fail("an unmounted container executed"))
    assert mod.main(["campaign_shard", "--spec", "/inputs/shard.json"]) == 2


def test_an_unproved_mount_never_executes(mounted, monkeypatch):
    def failed(mount_role):
        raise ValueError("IMAGE_PROVENANCE_INVALID")
    monkeypatch.setattr(mounted, "readback", failed)
    monkeypatch.setattr(mounted.os, "execv", lambda *args: pytest.fail("unproved mount executed"))
    assert mounted.main(["campaign_inference", "--role", "head"]) == 2


def test_launch_entry_names_are_all_programs_the_bootstrap_runs(mounted, monkeypatch):
    """The name launch.py puts after the image digest must be one the bootstrap runs."""
    import re
    source = (Path(module().__file__).parent / "launch.py").read_text()
    names = set(re.findall(r'command = \["(campaign_\w+)"', source))
    monkeypatch.setattr(mounted, "readback", lambda mount_role: {})
    monkeypatch.setattr(mounted.os, "execv", lambda *args: None)
    assert "campaign_processor" in names
    for name in names - {"campaign_inference"}:
        assert mounted.main([name]) == 0, name
