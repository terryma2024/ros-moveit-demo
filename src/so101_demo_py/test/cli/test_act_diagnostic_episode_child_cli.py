"""Recorder composition through the actual child CLI entry point."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.cli import dynamic_cup_pick_place
from so101_demo.act import episode_assembly
from so101_demo.ros import dynamic_runtime
from test_act_child_recorder_binding import frozen_child_inputs, _options


@pytest.mark.parametrize("final_stop_proof", [True, False])
def test_the_teacher_child_cli_takes_the_frozen_manifest_and_records_nothing(tmp_path, monkeypatch, final_stop_proof):
    inputs, frozen, snapshot = frozen_child_inputs(tmp_path)
    opened, executed = [], []
    monkeypatch.setattr(episode_assembly, "open_point_episode", lambda **kwargs: opened.append(kwargs))

    def execute(options):
        executed.append(options)
        return 0

    monkeypatch.setattr(dynamic_runtime, "run_dynamic_execute", execute)
    argv = ["--backend", "mujoco", "--mode", "execute", "--execute",
            "--session-id", "session", "--attempt-id", "attempt", "--expected-reset-epoch", "2",
            "--evidence-root", str(tmp_path / "dynamic"), "--frozen-inputs-manifest", str(inputs)]
    if final_stop_proof:
        argv.append("--final-stop-proof")
    assert dynamic_cup_pick_place.main(argv) == 0
    assert len(executed) == 1 and opened == [], "the Teacher opens no episode: the Recorder owns it"
    assert executed[0].frozen_inputs_manifest == inputs and executed[0].final_stop_proof is final_stop_proof
    for removed in ("episode_scope", "episode_inputs_manifest", "episode_root"):
        assert not hasattr(executed[0], removed), removed


