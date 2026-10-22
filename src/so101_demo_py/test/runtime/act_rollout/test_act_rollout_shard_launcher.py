"""The Host prepares rollout shards: real spec writer and loader, real mount rules, real container argv; owners are never started."""

import hashlib
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path

import pytest

from test_config_identity import campaign_fixture, write_config
from so101_demo.act.rig_profile import DEFAULT_RIG
from so101_demo.runtime.act_instance.program import instance_id_for
from so101_demo.runtime.act_instance.spec import _FIELDS, _ROLLOUT_FIELDS, load_spec
from so101_demo.runtime.act_rollout.shard_launcher import WORKLOAD_KIND, RolloutShardLauncher
from so101_demo.runtime.container_campaign.mount_build import MountBuild
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.inference.config import load_campaign_config
from so101_teleop.unified.contracts import AdmittedCampaignContext

from paths import PACKAGE_ROOT

GPU = "GPU-28221cec-9d21-7753-fd5a-da645740df19"
IDENTITY = {"run_identity_sha256": "1" * 64, "scenes_sha256": "2" * 64, "policy_sha256": "3" * 64, "bundle_sha256": "4" * 64}


def prepared(tmp_path, *, workers=1, mount=None, kind=WORKLOAD_KIND):
    paths = make_campaign_paths(tmp_path, "run-1")
    (paths["run"] / "ipc" / "policy").mkdir(mode=0o700)
    campaign = campaign_fixture(tmp_path)
    campaign["gpu_uuid"] = GPU
    if mount is not None:
        campaign["shard_image"] = dict(campaign["teacher_service"]["image"])
        campaign["mount_build"] = mount.document()
    campaign_path = write_config(tmp_path, campaign)
    campaign_sha = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    runtime = tmp_path / "parallel.yaml"
    shutil.copyfile(PACKAGE_ROOT / "config/mujoco/parallel_batch_linux_cuda.yaml", runtime)
    context = AdmittedCampaignContext(
        campaign_id="run-1", operation_id="run-1", workload_kind=kind, service_epoch="epoch", execution_generation=1,
        stable_host_id="host", physical_gpu_uuid=GPU, worker_count=workers, source_sha256="d" * 64,
        manifest_sha256=IDENTITY["scenes_sha256"], runtime_config_sha256=campaign["controlled_runtime"]["sha256"],
        collection_config_sha256=IDENTITY["run_identity_sha256"], contact_policy_fingerprint=IDENTITY["policy_sha256"],
        domain_session_map_sha256="d" * 64, resource_binding_id="self", evidence_root=str(paths["run"]),
        admitted_at_monotonic_s=1, deadline_monotonic_s=time.monotonic() + 3600, registered_evidence_root=str(tmp_path),
        campaign_config_path=str(campaign_path), campaign_config_sha256=campaign_sha)
    registry = ContainerLaunchRegistry(paths["host"] / "launches.sqlite3")
    launcher = RolloutShardLauncher(
        context=context, config=load_campaign_config(campaign_path, expected_sha256=campaign_sha), run=paths["run"],
        registry=registry, parallel_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()),
        rollout_identity=IDENTITY, rig_profile_sha256=DEFAULT_RIG.profile_sha256, approved_inputs=(), config_paths=())
    return launcher, registry, context, paths


def workers(count):
    return tuple(f"w{index:02d}" for index in range(count))


def test_the_launcher_writes_a_spec_the_real_shard_loader_accepts_and_one_owner_per_worker(tmp_path):
    launcher, registry, context, paths = prepared(tmp_path, workers=2)
    try:
        owners = launcher(plan={"wave_index": 0}, worker_ids=workers(2), context=context)
        assert [owner.launch.worker_id for owner in owners] == ["w00", "w01"]
        for owner in owners:
            written = json.loads(owner.entry.spec.read_text())
            spec, runtime = load_spec(owner.entry.spec)
            assert spec == written == owner.spec and set(written) == _FIELDS | _ROLLOUT_FIELDS
            assert written["workload_kind"] == "act_rollout" and written["rollout_identity"] == IDENTITY
            assert written["rig_profile_sha256"] == DEFAULT_RIG.profile_sha256 and written["wave_id"] == "wave-0"
            assert written["deadline_monotonic_s"] == context.deadline_monotonic_s
            assert "campaign_config" not in written and "business_identity" not in written
            assert owner.launch.launch_id == instance_id_for(written) == f"wave-0-{owner.launch.worker_id}-g1"
            assert owner.startup_budget == runtime.initializing_hard_timeout_s and owner.max_bytes == runtime.broker_max_frame_bytes
            root = Path(written["owned_root"])
            assert [path.name for path in sorted(root.iterdir())] == ["control", "output", "task-inputs", "tmp"]
        assert len({owner.spec["simulation_session_id"] for owner in owners}) == 2
        assert len({owner.spec["service_token"] for owner in owners}) == 2
    finally:
        registry.close()


def test_the_container_argv_mounts_the_task_output_and_the_policy_socket_and_nothing_of_the_teacher(tmp_path):
    launcher, registry, context, paths = prepared(tmp_path)
    try:
        (owner,) = launcher(plan={"wave_index": 0}, worker_ids=workers(1), context=context)
        argv = owner.argv
        mounts = [argv[index + 1] for index, value in enumerate(argv) if value == "--mount"]
        run = paths["run"]
        assert f"type=bind,src={run / 'ipc' / 'policy'},dst=/act/ipc/policy,readonly" in mounts
        root = owner.root
        assert f"type=bind,src={root / 'output'},dst=/act/output" in mounts and f"type=bind,src={root / 'control'},dst=/act/control" in mounts
        assert not any("/act/ipc/teacher" in mount or "/act/ipc/head" in mount for mount in mounts)
        assert argv[argv.index("--network") + 1] == "none" and argv[argv.index("--ipc") + 1] == "private"
        assert "campaign_shard" in argv and "SO101_MUJOCO_SESSION_ID=" + owner.spec["simulation_session_id"] in argv
        assert "ROS_DOMAIN_ID=181" in argv and not any(value.startswith("ROS_NAMESPACE") for value in argv)
        assert argv[argv.index("--gpus") + 1] == "device=" + GPU
    finally:
        registry.close()


def test_the_next_wave_gets_the_next_generation_and_waves_cannot_be_skipped_or_repeated(tmp_path):
    launcher, registry, context, paths = prepared(tmp_path, workers=2)
    try:
        launcher(plan={"wave_index": 0}, worker_ids=workers(2), context=context)
        smaller = replace(context, worker_count=1)
        (second,) = launcher(plan={"wave_index": 1}, worker_ids=workers(1), context=smaller)
        assert second.launch.launch_id == "wave-1-w00-g2" and second.spec["launch_generation"] == 2
        assert Path(second.spec["owned_root"]) == paths["run"] / "wave-1" / "w00" / "g2"
        for wave in (1, 5):
            with pytest.raises(ValueError, match="ROLLOUT_SHARD_WAVE_INVALID"):
                launcher(plan={"wave_index": wave}, worker_ids=workers(1), context=smaller)
        with pytest.raises(ValueError, match="ROLLOUT_SHARD_WAVE_INVALID"):
            launcher(plan={"wave_index": 2}, worker_ids=workers(1), context=context)       # worker count disagrees
    finally:
        registry.close()


def test_a_context_of_another_workload_is_refused(tmp_path):
    with pytest.raises(ValueError, match="ROLLOUT_SHARD_LAUNCHER_INVALID"):
        prepared(tmp_path, kind="act_collection_start")


def test_in_mount_mode_the_shard_gets_the_build_environment_and_read_only_trees(tmp_path):
    commit = "a" * 40
    mount = MountBuild(commit=commit, root=tmp_path / "build" / commit[:12])
    for name in ("install", "source"):
        (mount.root / name).mkdir(parents=True)
        (mount.root / name / "BUILD-COMMIT").write_text(commit + "\n")
    (tmp_path / "mounted").mkdir()
    launcher, registry, context, paths = prepared(tmp_path / "mounted", workers=1, mount=mount)
    try:
        (owner,) = launcher(plan={"wave_index": 0}, worker_ids=workers(1), context=context)
        mounts = [owner.argv[index + 1] for index, value in enumerate(owner.argv) if value == "--mount"]
        assert f"type=bind,src={mount.install},dst={mount.install},readonly" in mounts
        assert f"type=bind,src={mount.source},dst={mount.source},readonly" in mounts
        assert f"SO101_MOUNT_INSTALL={mount.install}" in owner.argv and f"SO101_EXPECTED_COMMIT={commit}" in owner.argv
        assert owner.argv[owner.argv.index("campaign_shard") - 1].endswith("image_bootstrap")
    finally:
        registry.close()
