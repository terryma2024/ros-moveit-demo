"""A campaign image runs only its installed role after actual freeze readback."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


def module():
    return importlib.import_module("so101_demo.runtime.container_campaign.image_bootstrap")


@pytest.mark.parametrize("role,command,expected", [
    ("inference", ["campaign_inference", "--role", "head", "--config", "/inputs/head.json"], "campaign_inference"),
    ("inference", ["campaign_inference", "--role", "teacher", "--config", "/inputs/teacher.json"], "campaign_inference"),
    ("shard", ["campaign_shard", "--spec", "/inputs/shard.json"], "campaign_shard"),
    ("shard", ["campaign_processor", "--spec", "/inputs/processor.json"], "campaign_processor"),
])
def test_installed_role_provenance_precedes_exec(monkeypatch, capsys, role, command, expected):
    mod = module()
    calls = []
    monkeypatch.setattr(mod, "read_role", lambda: role)
    monkeypatch.setattr(mod, "readback", lambda: calls.append("readback") or {"kind": "actual-readback"})
    monkeypatch.setattr(mod.os, "execv", lambda binary, argv: calls.append((binary, argv)))
    monkeypatch.setattr(mod.sys, "executable", "/act/venv/bin/python")
    assert mod.main(command) == 0
    assert calls == ["readback", ("/act/venv/bin/python", ["/act/venv/bin/python", "-I", "-m",
                    "so101_demo.cli."+expected, *command[1:]])]
    assert '"kind":"actual-readback"' in capsys.readouterr().out


@pytest.mark.parametrize("role,command", [
    ("inference", ["bash", "-c", "something"]),
    ("inference", ["campaign_shard", "--spec", "/inputs/shard.json"]),
    ("shard", ["campaign_inference", "--role", "head"]),
    ("inference", ["campaign_processor", "--spec", "/inputs/processor.json"]),
    ("unknown", ["campaign_inference", "--role", "head"]),
    ("inference", []),
])
def test_foreign_command_never_executes(monkeypatch, role, command):
    mod = module()
    monkeypatch.setattr(mod, "read_role", lambda: role)
    monkeypatch.setattr(mod, "readback", lambda: pytest.fail("invalid role must be rejected before importing runtime"))
    monkeypatch.setattr(mod.os, "execv", lambda *args: pytest.fail("foreign command executed"))
    assert mod.main(command) == 2


def test_unproved_image_never_executes(monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, "read_role", lambda: "inference")
    def failed():
        raise ValueError("IMAGE_PROVENANCE_INVALID")
    monkeypatch.setattr(mod, "readback", failed)
    monkeypatch.setattr(mod.os, "execv", lambda *args: pytest.fail("unproved image executed"))
    assert mod.main(["campaign_inference", "--role", "head"]) == 2


def test_launch_processor_entry_name_is_admitted_by_the_shard_image(monkeypatch):
    """The name launch.py puts after the image digest must be one the image entrypoint runs."""
    import re
    source = (Path(module().__file__).parent / "launch.py").read_text()
    names = set(re.findall(r'command = \["(campaign_\w+)"', source))
    mod = module()
    monkeypatch.setattr(mod, "read_role", lambda: "shard")
    monkeypatch.setattr(mod, "readback", lambda: {})
    monkeypatch.setattr(mod.os, "execv", lambda *args: None)
    monkeypatch.setattr(mod.sys, "executable", "/act/venv/bin/python")
    assert "campaign_processor" in names
    for name in names - {"campaign_inference"}:
        assert mod.main([name]) == 0, name
