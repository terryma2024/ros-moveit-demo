"""The `act_rollout` workload kind in the instance machinery: spec, layout, mounts, container argv and the shard builder."""

import functools
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.rig_profile import DEFAULT_RIG, KNOWN_RIGS
from so101_demo.runtime.act_instance import program
from so101_demo.runtime.act_instance.layout import InstanceLayout
from so101_demo.runtime.act_instance.spec import _FIELDS, _ROLLOUT_FIELDS, ROLLOUT_IDENTITY_FIELDS, instance_rig, load_spec
from so101_demo.runtime.container_campaign import launch, paths
from so101_demo.runtime.container_campaign.instance_owner_common import load_instance_spec
from so101_teleop.unified.contracts import AdmittedCampaignContext

from paths import PACKAGE_ROOT

GPU = "GPU-28221cec-9d21-7753-fd5a-da645740df19"
HEX = "a" * 64


def rollout_spec(tmp_path, *, wave="wave-0", worker="w00", generation=1, rig=None, **changes):
    run = paths.make_campaign_paths(tmp_path, "campaign")["run"]
    owned = run / wave / worker / f"g{generation}"
    owned.mkdir(parents=True)
    controlled = tmp_path / "controlled.json"
    controlled.write_bytes(b'{"sampling_hz":10}\n')
    runtime = tmp_path / "parallel.yaml"
    shutil.copyfile(PACKAGE_ROOT / "config/mujoco/parallel_batch_linux_cuda.yaml", runtime)
    spec = {"schema_version": 2, "kind": "ACT_CONTAINER_SHARD", "workload_kind": "act_rollout", "campaign_id": "campaign",
            "worker_id": worker, "launch_generation": generation, "execution_generation": 1, "runtime_id": "runtime-1",
            "service_epoch": "epoch", "service_token": "9" * 64, "owned_root": str(owned),
            "simulation_session_id": "act-session-w00-g1", "gpu_uuid": GPU,
            "controlled_runtime": {"path": str(controlled), "sha256": hashlib.sha256(controlled.read_bytes()).hexdigest()},
            "rollout_identity": {name: HEX for name in ROLLOUT_IDENTITY_FIELDS},
            "rig_profile_sha256": (DEFAULT_RIG if rig is None else rig).profile_sha256,
            "parallel_runtime": {"path": str(runtime), "sha256": hashlib.sha256(runtime.read_bytes()).hexdigest()},
            "wave_id": wave, "deadline_monotonic_s": time.monotonic() + 3600}
    spec.update(changes)
    path = run / "shard-spec.json"
    path.write_text(json.dumps(spec))
    return spec, path, owned, run


def test_the_rollout_spec_has_exactly_the_closed_fields_and_loads(tmp_path):
    spec, path, owned, _run = rollout_spec(tmp_path)
    assert set(spec) == _FIELDS | _ROLLOUT_FIELDS
    loaded, runtime = load_spec(path)
    assert loaded == spec and runtime.heartbeat_timeout_s > 0 and runtime.worker_recovery_timeout_s > 0
    assert program.instance_id_for(loaded) == "wave-0-w00-g1"


@pytest.mark.parametrize("changes", [
    {"rollout_identity": {name: HEX for name in ("run_identity_sha256", "scenes_sha256", "policy_sha256")}},
    {"rollout_identity": {name: "xyz" for name in ROLLOUT_IDENTITY_FIELDS}},
    {"rig_profile_sha256": "0" * 64}, {"rig_profile_sha256": None}, {"wave_id": "wave-7"}, {"wave_id": "round-0"},
    {"deadline_monotonic_s": 1.0}, {"deadline_monotonic_s": float("inf")}, {"extra": 1},
    {"parallel_runtime": {"path": "/nowhere.yaml", "sha256": HEX}},
])
def test_a_rollout_spec_that_is_not_closed_or_not_true_is_refused(tmp_path, changes):
    spec, path, _owned, _run = rollout_spec(tmp_path, **changes)
    with pytest.raises(ValueError, match="CAMPAIGN_SHARD_SPEC_INVALID"):
        load_spec(path)


def test_the_rollout_spec_must_not_carry_a_collection_field_or_lack_a_rollout_one(tmp_path):
    spec, path, _owned, _run = rollout_spec(tmp_path)
    spec["campaign_config"] = {"path": "/x", "sha256": HEX}
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="CAMPAIGN_SHARD_SPEC_INVALID"):
        load_spec(path)
    spec.pop("campaign_config")
    spec.pop("rig_profile_sha256")
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="CAMPAIGN_SHARD_SPEC_INVALID"):
        load_spec(path)


def test_the_rig_of_a_rollout_instance_is_the_one_its_spec_names(tmp_path):
    spec, path, _owned, _run = rollout_spec(tmp_path)
    assert instance_rig(spec) is DEFAULT_RIG
    other = next(rig for rig in KNOWN_RIGS.values() if rig is not DEFAULT_RIG)
    (tmp_path / "other").mkdir()
    changed, changed_path, _o, _r = rollout_spec(tmp_path / "other", rig=other)
    assert instance_rig(changed) is other and load_spec(changed_path)[0]["rig_profile_sha256"] == other.profile_sha256


def context(spec, run, **changes):
    values = dict(campaign_id="campaign", operation_id="operation", workload_kind="act_rollout_start", service_epoch="epoch",
                  execution_generation=1, stable_host_id="host", physical_gpu_uuid=GPU, worker_count=1, source_sha256="d" * 64,
                  manifest_sha256=HEX, runtime_config_sha256=spec["controlled_runtime"]["sha256"],
                  collection_config_sha256=HEX, contact_policy_fingerprint=HEX, domain_session_map_sha256="d" * 64,
                  resource_binding_id="binding", evidence_root=str(run), admitted_at_monotonic_s=1,
                  deadline_monotonic_s=spec["deadline_monotonic_s"])
    values.update(changes)
    return AdmittedCampaignContext(**values)


def launch_for(spec):
    return SimpleNamespace(worker_id=spec["worker_id"], launch_generation=spec["launch_generation"], wave_id=spec["wave_id"],
                           session_id=spec["simulation_session_id"], owned_root=spec["owned_root"])


def test_the_host_proves_the_spec_names_this_admitted_run_launch_and_token(tmp_path):
    spec, path, _owned, run = rollout_spec(tmp_path)
    admitted = context(spec, run)
    assert load_instance_spec(path, admitted_context=admitted, launch=launch_for(spec), service_token="9" * 64) == spec
    for changes in ({"manifest_sha256": "b" * 64}, {"collection_config_sha256": "b" * 64},
                    {"contact_policy_fingerprint": "b" * 64}, {"deadline_monotonic_s": spec["deadline_monotonic_s"] + 1}):
        with pytest.raises(ValueError, match="SHARD_SPEC_CONTEXT_MISMATCH"):
            load_instance_spec(path, admitted_context=context(spec, run, **changes), launch=launch_for(spec),
                               service_token="9" * 64)
    with pytest.raises(ValueError, match="SHARD_SPEC_CONTEXT_MISMATCH"):
        load_instance_spec(path, admitted_context=admitted, launch=launch_for(spec), service_token="8" * 64)


def test_the_layout_carries_an_optional_policy_socket_and_refuses_a_relative_one():
    base = dict(owned_root="/o", output_root="/o/output", control_root="/o/control", teacher_socket="/t.sock",
                install_prefix="/i", ros2_executable="/r")
    assert InstanceLayout(**base).policy_socket is None
    assert InstanceLayout(**base, policy_socket="/act/ipc/policy/policy.sock").policy_socket == Path("/act/ipc/policy/policy.sock")
    with pytest.raises(ValueError, match="ACT_INSTANCE_LAYOUT_INVALID"):
        InstanceLayout(**base, policy_socket="policy.sock")


def test_the_container_layout_names_the_policy_socket_for_a_rollout_only(tmp_path, monkeypatch):
    from so101_demo.cli import campaign_shard

    monkeypatch.delenv("SO101_MOUNT_INSTALL", raising=False)
    spec, _path, _owned, _run = rollout_spec(tmp_path)
    assert campaign_shard.container_layout(spec).policy_socket == paths.CONTAINER_POLICY_SOCKET
    assert campaign_shard.container_layout(dict(spec, workload_kind="act_collection")).policy_socket is None


def rollout_mounts(tmp_path):
    spec, path, owned, run = rollout_spec(tmp_path)
    (owned / "control").mkdir(mode=0o700)
    (owned / "output").mkdir(mode=0o700)
    (owned / "tmp").mkdir(mode=0o700)
    policy = run / "ipc" / "policy"
    policy.mkdir(mode=0o700)
    roots = {"policy": policy, "control": owned / "control"}
    return spec, path, owned, run, roots


def test_a_rollout_shard_mounts_the_policy_socket_read_only_and_neither_head_nor_teacher(tmp_path):
    _spec, _path, owned, run, roots = rollout_mounts(tmp_path)
    mounts = paths.build_role_mounts("shard", owned_root=owned, approved_inputs=(), socket_roots=roots, config_paths=(),
                                     task_output_root=owned / "output")
    by_purpose = {(mount.purpose, str(mount.target)): mount for mount in mounts}
    policy = by_purpose[("ipc", "/act/ipc/policy")]
    assert policy.source == run / "ipc" / "policy" and policy.read_only is True
    assert not any(str(mount.target).endswith(("/head", "/teacher")) for mount in mounts)
    assert by_purpose[("task_output", "/act/output")].read_only is False
    assert by_purpose[("control", "/act/control")].source == owned / "control"


def test_the_policy_socket_directory_must_be_the_runs_own(tmp_path):
    _spec, _path, owned, run, roots = rollout_mounts(tmp_path)
    foreign = tmp_path / "elsewhere"
    foreign.mkdir()
    with pytest.raises(ValueError, match="ROLE_MOUNT_INVALID"):
        paths.build_role_mounts("shard", owned_root=owned, approved_inputs=(), socket_roots=dict(roots, policy=foreign),
                                config_paths=(), task_output_root=owned / "output")


def test_a_collection_shard_still_mounts_head_and_teacher_and_no_policy(tmp_path):
    run_paths = paths.make_campaign_paths(tmp_path, "campaign-2")
    owned = run_paths["run"] / "wave-0" / "w00" / "g1"
    (owned / "control").mkdir(parents=True, mode=0o700)
    mounts = paths.build_role_mounts("shard", owned_root=owned, approved_inputs=(),
                                     socket_roots=run_paths["socket_roots"] | {"control": owned / "control"}, config_paths=())
    targets = {str(mount.target) for mount in mounts}
    assert {"/act/ipc/head", "/act/ipc/teacher"} <= targets and "/act/ipc/policy" not in targets


def test_the_container_argv_of_a_rollout_shard_has_the_task_output_and_the_policy_mount(tmp_path):
    spec, path, owned, run, roots = rollout_mounts(tmp_path)
    images = {name: dict(digest="sha256:" + digest * 64, package_source_sha256="c" * 64, install_sha256="d" * 64)
              for name, digest in (("head", "a"), ("teacher", "a"), ("shard", "b"))}
    argv = launch.build_container_argv(
        role="shard", image=images, gpu_uuid=GPU, container_name="so101-rollout-w00-g1", uid=os.getuid(), gid=os.getgid(),
        host_paths=dict(owned_root=owned, approved_inputs=(), socket_roots=roots, config_paths=(path,),
                        entry=launch.ShardLaunchArgs(spec=path, mujoco_session_id="act-session-w00-g1")))
    mounts = [argv[index + 1] for index, value in enumerate(argv) if value == "--mount"]
    assert f"type=bind,src={run / 'ipc' / 'policy'},dst=/act/ipc/policy,readonly" in mounts
    assert f"type=bind,src={owned / 'output'},dst=/act/output" in mounts
    assert not any("/act/ipc/teacher" in mount or "/act/ipc/head" in mount for mount in mounts)
    assert argv[argv.index("--network") + 1] == "none" and argv[argv.index("--ipc") + 1] == "private"
    assert argv[argv.index(images["shard"]["digest"]) + 1] == "campaign_shard"


def test_the_shard_builder_gives_a_rollout_its_stack_output_socket_and_install(tmp_path):
    spec, _path, owned, _run = rollout_spec(tmp_path)
    layout = InstanceLayout(owned_root=owned, output_root="/act/output", control_root="/act/control",
                            teacher_socket="/act/ipc/teacher/inference.sock", install_prefix="/mounted/install/so101_demo_py",
                            ros2_executable="/opt/ros/jazzy/bin/ros2", policy_socket="/act/ipc/policy/policy.sock")
    stack = object()
    builder = program.shard_builder(spec, stack=stack, layout=layout)
    assert isinstance(builder, functools.partial)
    assert builder.func.__name__ == "build_rollout_task" and builder.keywords["stack"] is stack
    assert builder.keywords["output_root"] == Path("/act/output")
    assert builder.keywords["policy_socket"] == Path("/act/ipc/policy/policy.sock")
    assert builder.keywords["install_prefix"] == Path("/mounted/install/so101_demo_py")
    assert builder.keywords["shard_spec"] is spec
    with pytest.raises(ValueError, match="CAMPAIGN_SHARD_WORKLOAD_UNKNOWN"):
        program.shard_builder(dict(spec, workload_kind="surprise"), stack=stack, layout=layout)
