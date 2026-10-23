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

    def close_runtime(self):
        self.calls.append("close_runtime")

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
    assert ports.runtime.calls == ["close_runtime", "reset_point", ("initial_gate", 3)]
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


def _composition_stub(tmp_path, rig_profile):
    return SimpleNamespace(environment={"ROS_DOMAIN_ID": "181"}, inputs=SimpleNamespace(
        recorder_policy={"ready_timeout_s": 30.0}, settings=SimpleNamespace(execution_deadline_s=180.0)),
        launch=SimpleNamespace(rig_profile=rig_profile), layout=SimpleNamespace(output_root=tmp_path / "output"), options=SimpleNamespace(run_id="run-1"), attempts=0,
        runtime=object(), binding=None, runner=None, inference=None, transport=None,
        stall_monitor=SimpleNamespace(stop=lambda: None))


def test_the_recorder_records_the_rig_the_stack_composes_not_the_default_rig(tmp_path):
    """A side+wrist stack has no head camera and no neck: a recorder started without the rig profile would wait for the
    default rig's topics and every episode would end as a recorder fault."""
    profile = tmp_path / "rig-v2.yaml"
    profile.write_text("kind: act_rig_profile\n")
    stub = _composition_stub(tmp_path, profile)
    pilot = native.NativeComposition.pilot_factory(stub)(tmp_path / "episode")
    assert pilot.rig_profile == profile and pilot.timeout_s == 30.0 and pilot.root == tmp_path / "episode" / "raw"
    default = native.NativeComposition.pilot_factory(_composition_stub(tmp_path, None))(tmp_path / "episode-2")
    assert default.rig_profile is None                                 # the default rig's recorder command is unchanged


def test_each_episode_gets_a_recorder_factory_of_the_composition(tmp_path):
    profile = tmp_path / "rig-v2.yaml"
    profile.write_text("kind: act_rig_profile\n")
    stub = _composition_stub(tmp_path, profile)
    stub.pilot_factory = lambda: native.NativeComposition.pilot_factory(stub)
    ports = native.NativeComposition.new_ports(stub, {"scene_id": "s1"}, "s1-a1", tmp_path / "ep")
    assert ports.pilot_factory(tmp_path / "ep").rig_profile == profile and stub.attempts == 1


def _launch_for(tmp_path, cameras, state_dim):
    import os

    from paths import PACKAGE_ROOT
    from so101_demo.act.rig_profile import rig_from_observation
    from so101_demo.runtime.act_instance.program import instance_stack_launch

    ros2 = tmp_path / "ros2"
    ros2.write_text("#!/bin/sh\n")
    os.chmod(ros2, 0o755)
    stack_root = tmp_path / "stack"
    stack_root.mkdir()
    rig = rig_from_observation(cameras, state_dim)       # the composition derives the rig from the bundle's observation
    return instance_stack_launch({"simulation_session_id": "rollout-run-1"}, ros2=ros2, stack_root=stack_root,
                                 environment={"ROS_DOMAIN_ID": "181"}, rig=rig, share=PACKAGE_ROOT), rig


def test_a_side_wrist_bundle_launches_the_side_wrist_stack_and_observes_its_profile(tmp_path):
    from paths import PACKAGE_ROOT

    launch, rig = _launch_for(tmp_path, ["side", "wrist"], 6)
    assert (rig.has_head, rig.has_neck) == (False, False)
    assert launch.rig == "side-wrist" and launch.rig_profile == PACKAGE_ROOT / "config/act/rig-v2.yaml"
    assert "rig:=side-wrist" in launch.argv() and "act_profile:=true" in launch.argv()
    assert launch.readiness_arguments() == ["--rig-profile", str(PACKAGE_ROOT / "config/act/rig-v2.yaml")]
    assert not any("neck" in item or "head_" in item or "head-" in item for item in launch.argv())


def test_a_head_wrist_bundle_keeps_the_default_launch(tmp_path):
    launch, rig = _launch_for(tmp_path, ["head", "wrist"], 8)
    assert rig.has_neck and launch.rig == "head-wrist" and launch.rig_profile is None
    assert not any(item.startswith("rig:=") for item in launch.argv()) and launch.readiness_arguments() == []


class WarmPolicy:
    def __init__(self):
        self.calls, self.resets = [], 0

    def infer(self, observation):
        self.calls.append(observation)
        return [[0.0] * 6] * 10

    def reset(self):
        self.resets += 1


def test_the_model_is_warmed_up_on_the_bundle_shapes_and_reset_before_the_first_episode():
    """The first CUDA call takes longer than the frozen max_reply_age_s (0.3 s): without a warm-up the first request of every
    run is refused as stale (measured on the TRAIN-003 bundle: 0.306 s for the first call, 0.010 s after)."""
    policy = WarmPolicy()
    observation = {"cameras": ("side", "wrist"), "state_dim": 6, "image_shape": [480, 640, 3]}
    ticks = iter(x * 0.25 for x in range(100))
    latencies = native.warm_up_policy(policy, observation, calls=3, monotonic=lambda: next(ticks))
    assert latencies == [0.25, 0.25, 0.25] and policy.resets == 1 and len(policy.calls) == 3
    sample = policy.calls[0]
    assert set(sample) == {"sim_time_s", "state", "side", "wrist"} and len(sample["state"]) == 6
    assert sample["side"].shape == (480, 640, 3) and sample["side"].dtype.name == "uint8"


def test_the_recorder_writes_under_the_owned_root_and_the_bag_is_moved_into_the_episode_evidence(tmp_path):
    """The raw recorder refuses a bag outside the instance's owned root (CONTAINER_BAG_ROOT_MISMATCH, found live), so the
    recording is made in <owned>/output/recordings/<attempt> and moved to <episode>/raw after the recorder closed it."""
    profile = tmp_path / "rig-v2.yaml"
    profile.write_text("kind: act_rig_profile\n")
    stub = _composition_stub(tmp_path, profile)
    stub.pilot_factory = lambda: native.NativeComposition.pilot_factory(stub)
    ports = native.NativeComposition.new_ports(stub, {"scene_id": "s1"}, "s1-a1", tmp_path / "ep")
    assert ports.recording_dir == tmp_path / "output" / "recordings" / "s1-a1"

    class Pilot:
        ready, failure = True, None

        def __init__(self, directory):
            self.root = Path(directory) / "raw"

        def start(self):
            (self.root / "bag").mkdir(parents=True)
            (self.root / "ready.json").write_text("{}")

        def finish(self):
            return {"ready": True, "failure": None}

    ports.pilot_factory = Pilot
    (tmp_path / "ep").mkdir()
    recording = ports.start_recorder({"scene_id": "s1"})
    facts = recording.finish()
    assert (tmp_path / "ep" / "raw" / "ready.json").is_file() and not (ports.recording_dir / "raw").exists()
    assert facts["relocated_to"] == str(tmp_path / "ep" / "raw") and facts["failure"] is None


def test_the_composition_releases_its_own_ros_participants_before_the_stack_graph_is_judged(tmp_path, monkeypatch):
    """The retained pause control and the rollout binding are nodes of the instance domain: with them alive the stack's graph
    never reads clear (found live: GRAPH_NOT_CLEARED after a clean run)."""
    import asyncio

    order = []

    class Stack:
        async def stop(self):
            order.append("stack.stop")

    stub = SimpleNamespace(
        layout=SimpleNamespace(owned_root=tmp_path, stack_root=tmp_path), _closed=False, stack=Stack(),
        inference=SimpleNamespace(close=lambda: order.append("inference.close")),
        runtime=SimpleNamespace(close_runtime=lambda: order.append("runtime.close"),
                                resume_physics=lambda lease, receipt: order.append("physics.resume") or True),
        binding=SimpleNamespace(shutdown=lambda: order.append("binding.shutdown")), stall_monitor=SimpleNamespace(stop=lambda: None),
        graph_probe=lambda: order.append("graph_probe") or True)
    stub.close = lambda: native.NativeComposition.close(stub)
    monkeypatch.setattr("so101_demo.runtime.container_campaign.native_stop.marker_survivors", lambda *a, **k: [])
    monkeypatch.setattr("so101_teleop.process_identity.read_identity", lambda pid: SimpleNamespace(start_marker=1))
    proof = native.NativeComposition.stop(stub)
    assert order == ["physics.resume", "inference.close", "runtime.close", "binding.shutdown", "stack.stop", "graph_probe"]
    assert proof["confirmed"] is True and proof["graph_clear"] is True and proof["physics_resumed_before_stop"] is True
    native.NativeComposition.close(stub)                       # the run's final close is a no-op
    assert order.count("runtime.close") == 1
