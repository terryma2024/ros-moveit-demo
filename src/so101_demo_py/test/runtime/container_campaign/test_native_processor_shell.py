"""The native shell of the processor program: the same program as the container shell, with the native-only facts checked first."""

import asyncio
import os
from pathlib import Path
import sys

import pytest

from so101_demo.cli import campaign_processor, campaign_processor_native
from so101_demo.runtime.act_instance.identity import INSTANCE_OUTPUT_ENV, INSTANCE_ROOT_ENV
from so101_demo.runtime.act_processor import program

SPEC = {"owned_root": "/run/x/processing/p00/g1"}


def test_the_native_layout_differs_from_the_container_layout_only_in_where_the_control_sockets_and_the_interpreter_are():
    native = campaign_processor_native.native_layout(SPEC)
    container = campaign_processor.container_layout(SPEC)
    assert native.owned_root == container.owned_root == Path(SPEC["owned_root"])
    assert native.output_root == container.output_root == Path(SPEC["owned_root"]) / "output"
    assert native.control_root == Path(SPEC["owned_root"]) / "control" and native.python == Path(sys.executable)


def test_both_shells_run_the_same_program(monkeypatch):
    assert campaign_processor_native.run_processor is program.run_processor
    assert campaign_processor.run_processor is program.run_processor
    calls = []

    async def fake(spec, runtime, layout):
        calls.append(("program", layout))
        return 0
    monkeypatch.setattr(campaign_processor_native, "run_processor", fake)
    monkeypatch.setattr(campaign_processor_native, "check_native_process", lambda spec, prefix: calls.append(("checked", prefix)))
    assert asyncio.run(campaign_processor_native.run_native(SPEC, object(), Path("/prefix"))) == 0
    assert [name for name, _ in calls] == ["checked", "program"]


@pytest.mark.parametrize("problem", ["not_a_group_leader", "environment_drift", "source_tree"])
def test_a_native_processor_refuses_to_run_when_a_native_fact_is_missing(monkeypatch, tmp_path, problem):
    root = str(tmp_path)
    monkeypatch.setenv(INSTANCE_ROOT_ENV, root if problem != "environment_drift" else "/elsewhere")
    monkeypatch.setenv(INSTANCE_OUTPUT_ENV, root + "/output")
    if problem == "not_a_group_leader":
        monkeypatch.setattr(os, "getpgrp", lambda: os.getpid() + 1)
    monkeypatch.setattr(campaign_processor_native, "running_installed_code", lambda prefix: problem != "source_tree")
    expected = {"not_a_group_leader": "CAMPAIGN_NATIVE_GROUP_REQUIRED", "environment_drift": "CAMPAIGN_NATIVE_ENVIRONMENT_DRIFT",
                "source_tree": "CAMPAIGN_NATIVE_CODE_NOT_INSTALLED"}[problem]
    if problem != "not_a_group_leader":
        monkeypatch.setattr(os, "getpgrp", lambda: os.getpid())
        monkeypatch.setattr(os, "getsid", lambda pid: os.getpid())
    with pytest.raises(ValueError, match=expected):
        campaign_processor_native.check_native_process({"owned_root": root}, tmp_path)
