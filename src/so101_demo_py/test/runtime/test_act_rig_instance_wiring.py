"""Everything launched or configured per ACT instance takes its rig from the campaign: the stack, its readiness, the recorder, the
reset, the inventory gate and the task."""

import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from so101_demo.act.diagnostic_episode_inputs import rig_profile_binding
from so101_demo.act.offline.orchestration import OfflineCollection
from so101_demo.act.offline.pilot import PilotRecording
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG, dump_rig_profile
from so101_demo.runtime.act_instance.spec import instance_rig
from test_config_identity import campaign_fixture, write_config


def _ref(path):
    return {"path": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def test_an_instance_takes_the_rig_its_campaign_config_names(tmp_path):
    for named, rig in ((None, HEAD_WRIST_RIG), (HEAD_WRIST_RIG.profile_sha256, HEAD_WRIST_RIG),
                       (SIDE_WRIST_RIG.profile_sha256, SIDE_WRIST_RIG)):
        campaign = campaign_fixture(tmp_path)
        if named is not None:
            campaign["rig_profile_sha256"] = named
        spec = {"workload_kind": "act_collection", "campaign_config": _ref(write_config(tmp_path, campaign))}
        assert instance_rig(spec) is rig
    # a spec with no campaign config (a readiness shard, a rollout) is the default rig
    assert instance_rig({"workload_kind": "no_motion_readiness"}) is HEAD_WRIST_RIG
    campaign = dict(campaign_fixture(tmp_path), rig_profile_sha256="0" * 64)
    with pytest.raises(ValueError, match="RIG_PROFILE_UNKNOWN"):
        instance_rig({"campaign_config": _ref(write_config(tmp_path, campaign))})


class _Processes:
    def __init__(self):
        self.started = []

    def start(self, spec, *, environment):
        self.started.append(spec)
        return "identity"

    def exit_code(self, _identity):
        return 0


def _recorder_argv(tmp_path, **rig):
    processes = _Processes()
    recording = PilotRecording(processes=processes, root=tmp_path / "raw", environment={},
                               spec_factory=lambda argv: tuple(argv), timeout_s=0.1, **rig)
    recording.start()
    return list(processes.started[0])


def test_the_raw_recorder_gets_the_rig_profile_only_for_a_rig_that_is_not_the_default(tmp_path):
    default = _recorder_argv(tmp_path / "a")
    assert "--rig-profile" not in default and default[-2:] == ["--ready-timeout-s", "0.1"]
    profile = tmp_path / "rig-v2.yaml"
    profile.write_bytes(dump_rig_profile(SIDE_WRIST_RIG))
    side = _recorder_argv(tmp_path / "b", rig_profile=profile)
    assert side[-2:] == ["--rig-profile", str(profile)]
    assert [item.replace("/b/raw", "/a/raw") for item in side[:-2]] == default     # every other argument is the default's


def test_the_collection_records_under_the_frozen_rig_profile_of_its_inputs(tmp_path):
    def collection(frozen_rig):
        directory = tmp_path / frozen_rig.rig
        (directory / "policies").mkdir(parents=True)
        payload = dump_rig_profile(frozen_rig)
        (directory / "policies" / "rig_profile.yaml").write_bytes(payload)
        manifest = directory / "inputs-manifest.json"
        manifest.write_text(json.dumps({"rig_profile": rig_profile_binding(payload)}))
        item = OfflineCollection.__new__(OfflineCollection)
        item._inputs_manifest = manifest
        return item

    assert collection(HEAD_WRIST_RIG)._rig_profile() is None
    assert collection(SIDE_WRIST_RIG)._rig_profile() == tmp_path / "side-wrist" / "policies" / "rig_profile.yaml"
    legacy = OfflineCollection.__new__(OfflineCollection)
    legacy._inputs_manifest = tmp_path / "legacy.json"
    legacy._inputs_manifest.write_text("{}")
    assert legacy._rig_profile() is None            # a frozen set sealed before profiles is the head+wrist rig


def _ports(**dependencies):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    return ParallelRosRuntimePorts(SimpleNamespace(session_id="s", worker_id="w", generation=1), catalog={},
                                   dependencies=dependencies)


def test_the_ready_probe_asks_for_the_neck_only_of_a_rig_with_a_neck(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda command, **_kw: seen.append(list(command))
                        or SimpleNamespace(returncode=0, stdout="", stderr=""))
    for rig, neck in ((HEAD_WRIST_RIG, True), (SIDE_WRIST_RIG, False), (None, True)):
        assert _ports(act_profile=True, rig=rig).ready_probe(None) is True
        assert ("--include-neck" in seen[-1]) is neck
    assert _ports(rig=SIDE_WRIST_RIG).ready_probe(None) is True and "--include-neck" not in seen[-1]


def test_the_point_reset_names_the_rig_only_when_it_is_not_the_default():
    lease = SimpleNamespace(batch_id="b", coordinator_epoch=1, worker_id="w", worker_generation=1, point_id="P",
                            attempt_id="a", lease_generation=1)
    for rig, expected in ((None, {"act_profile": True}), (HEAD_WRIST_RIG, {"act_profile": True}),
                          (SIDE_WRIST_RIG, {"act_profile": True, "rig": SIDE_WRIST_RIG})):
        calls = []

        def execute(session_id, *, keyframe, cup_position_world_m, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(simulation_session_id="s", new_epoch=2), SimpleNamespace(success=True)

        ports = _ports(act_profile=True, **({} if rig is None else {"rig": rig}), execute_reset=execute,
                       current_evidence=lambda _session: SimpleNamespace(simulation_session_id="s", reset_epoch=2,
                                                                         simulation_time_s=1.0))
        ports.catalog = {"P": {"cup_position_world_m": [0.1, -0.2, 0.17]}}
        ports.reset_point(lease)
        assert calls == [expected]
