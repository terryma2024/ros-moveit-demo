"""The native rollout command's entry point and its episode ports, with fakes only."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.cli import act_rollout_native as native

from test_act_rollout_native import FakeComposition, _inputs, _passing_probes, _runner


def _argv(tmp_path, **extra):
    values = {"--evidence-root": tmp_path / "evidence", "--run-id": "run-1", "--group": "rollout_validation",
              "--scenes": tmp_path / "scenes.json", "--bundle-dir": tmp_path / "bundle",
              "--inputs-manifest": tmp_path / "inputs-manifest.json", "--runtime-config": tmp_path / "runtime.yaml",
              "--rollout-config": tmp_path / "rollout.yaml", "--install-prefix": tmp_path / "install",
              "--ros2": tmp_path / "ros2", "--gpu-uuid": "GPU-00000000-0000-0000-0000-000000000000",
              "--unified-state-root": tmp_path / "unified"}
    values.update(extra)
    (tmp_path / "evidence").mkdir(exist_ok=True)
    return [item for pair in values.items() for item in (pair[0], str(pair[1]))]


def test_main_runs_the_group_and_returns_the_run_exit_code(tmp_path, capsys):
    composition = FakeComposition(tmp_path)
    code = native.main(_argv(tmp_path), inputs_loader=lambda args: _inputs(), probes=_passing_probes(),
                       composition_factory=lambda **kwargs: composition, preflight=None, environ={},
                       episode_runner=_runner({}, []))
    assert code == native.EXIT_OK
    summary = json.loads(capsys.readouterr().out)
    assert summary["exit_code"] == 0 and summary["scenes"] == 3 and composition.log[0] == "start"


def test_main_refuses_with_exit_two_and_starts_nothing(tmp_path, capsys):
    probes = _passing_probes()
    probes["no_container"] = lambda: (False, ["act-shard-w00"])
    created = []
    code = native.main(_argv(tmp_path), inputs_loader=lambda args: _inputs(), probes=probes,
                       composition_factory=lambda **kwargs: created.append(1), preflight=None, environ={})
    assert code == native.EXIT_REFUSED and created == []
    assert "ROLLOUT_PRECONDITION_FAILED: no_container" in capsys.readouterr().err


def test_a_failed_import_preflight_runs_after_the_environment_and_before_the_composition(tmp_path, capsys):
    order, environ = [], {"DISPLAY": ":0"}

    def preflight():
        order.append(("preflight", dict(environ)))
        raise RuntimeError("ROLLOUT_IMPORT_PREFLIGHT_FAILED: lerobot: No module named lerobot")

    code = native.main(_argv(tmp_path), inputs_loader=lambda args: _inputs(), probes=_passing_probes(),
                       composition_factory=lambda **kwargs: order.append("composition"), preflight=preflight,
                       environ=environ)
    assert code == native.EXIT_REFUSED and [item[0] for item in order] == ["preflight"]
    seen = order[0][1]
    assert seen["ROS_DOMAIN_ID"] == "181" and "DISPLAY" not in seen and "SO101_ACT_INSTANCE_ROOT" in seen
    assert "lerobot" in capsys.readouterr().err
    assert not (tmp_path / "evidence" / "rollout_validation").exists()          # nothing of the group was written


class FakePilot:
    def __init__(self, ready, failure=None):
        self.ready, self.failure, self.finished = ready, failure, 0

    def start(self):
        pass

    def finish(self):
        self.finished += 1
        return {"ready": self.ready, "failure": self.failure}


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def reset_point(self, lease):
        self.calls.append("reset_point")
        return SimpleNamespace(reset_epoch_value=3, simulation_session_id="sim-1", simulation_time_s=0.5,
                               joint_positions=(0.0,) * 6)

    def initial_gate(self, lease, receipt):
        self.calls.append(("initial_gate", receipt.reset_epoch_value))
        return SimpleNamespace(canonical_joints=True, no_controller_goal=True)

    def resume_physics(self, lease, receipt):
        self.calls.append("resume_physics")
        return True

    def cancel_motion(self, lease):
        self.calls.append("cancel_motion")
        return True

    def confirm_no_controller_goal(self, lease):
        self.calls.append("confirm_no_controller_goal")
        return True


def _ports(tmp_path, pilot):
    return native.NativeEpisodePorts(
        runtime=FakeRuntime(), lease=object(), scene={"scene_id": "s"}, directory=tmp_path, inputs=_inputs(),
        environment={}, binding=None, runner=None, inference=None, transport=SimpleNamespace(quiesce=lambda t: True),
        pilot_factory=lambda directory: pilot)


def test_the_episode_ports_translate_the_shard_runtime_receipts(tmp_path):
    ports = _ports(tmp_path, FakePilot(True))
    receipt = ports.reset({"scene_id": "s"})
    assert receipt == {"reset_epoch": 3, "simulation_session_id": "sim-1", "simulation_time_s": 0.5,
                       "joint_positions": (0.0,) * 6}
    assert ports.initial_gate({"scene_id": "s"}, receipt) == {"canonical_joints": True, "no_controller_goal": True}
    assert ports.runtime.calls == ["reset_point", ("initial_gate", 3)]
    assert ports.resume_physics(receipt) is True
    assert ports.cancel_motion() is True and ports.confirm_no_controller_goal() is True


def test_a_recorder_that_is_not_ready_is_closed_and_refused(tmp_path):
    pilot = FakePilot(False, "RAW_PILOT_READY_TIMEOUT")
    with pytest.raises(RuntimeError, match="RAW_PILOT_READY_TIMEOUT"):
        _ports(tmp_path, pilot).start_recorder({"scene_id": "s"})
    assert pilot.finished == 1
    ready = FakePilot(True)
    assert _ports(tmp_path, ready).start_recorder({"scene_id": "s"}) is ready and ready.finished == 0


def test_a_model_call_still_running_blocks_the_next_session(tmp_path):
    ports = native.NativeEpisodePorts(
        runtime=FakeRuntime(), lease=object(), scene={}, directory=tmp_path, inputs=_inputs(), environment={},
        binding=None, runner=None, inference=None, transport=SimpleNamespace(quiesce=lambda timeout: False),
        pilot_factory=None)
    with pytest.raises(RuntimeError, match="ROLLOUT_INFERENCE_NOT_IDLE"):
        ports.open_session({"scene_id": "s"}, {"simulation_session_id": "sim-1", "simulation_time_s": 0.5}, "a1")
