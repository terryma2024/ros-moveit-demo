"""Prepare the private container shards of one rollout wave, in the manner of `ContainerShardLauncher` (collection).

The spec is the rollout's own (`workload_kind` act_rollout): it carries the run identity, the rig profile hash and the parallel
runtime that bounds the instance, and no Teacher or campaign field. The shard owner is the collection's `ContainerShardOwner`
unchanged: the same registered launch intent, original container identity, bridge, bounded start, and stop proof.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import secrets

from so101_demo.cli.mujoco_batch.request import _load_runtime_config
from so101_demo.runtime.act_instance.program import instance_id_for
from so101_demo.runtime.act_instance.spec import SPEC_SCHEMA_VERSION, load_spec
from so101_demo.runtime.container_campaign.launch import ShardLaunchArgs
from so101_demo.runtime.container_campaign.mount_build import mount_from_config
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.service_owner import _docker, _write
from so101_demo.runtime.container_campaign.shard_owner import ContainerShardOwner, read_container_namespace
from so101_demo.runtime.inference.config import validate_file_ref
from so101_teleop.unified.contracts import AdmittedCampaignContext

WORKLOAD_KIND = "act_rollout_start"


class RolloutShardLauncher:
    def __init__(self, *, context, config, run, registry, parallel_runtime, rollout_identity, rig_profile_sha256,
                 approved_inputs, config_paths, docker_runner=_docker, namespace_reader=read_container_namespace,
                 scene_variant=None):
        if (type(context) is not AdmittedCampaignContext or context.workload_kind != WORKLOAD_KIND
                or type(registry) is not ContainerLaunchRegistry or str(run) != context.evidence_root
                or type(approved_inputs) is not tuple or type(config_paths) is not tuple):
            raise ValueError("ROLLOUT_SHARD_LAUNCHER_INVALID")
        self.context, self.config, self.run, self.registry = context, config, Path(run), registry
        self.parallel_runtime = dict(parallel_runtime)
        self.runtime = _load_runtime_config(validate_file_ref(parallel_runtime))
        self.rollout_identity, self.rig_profile_sha256 = dict(rollout_identity), rig_profile_sha256
        self.approved_inputs, self.config_paths = approved_inputs, config_paths
        self.docker_runner, self.namespace_reader = docker_runner, namespace_reader
        self.mount_build = mount_from_config(config)
        # the evaluation-only scene variant entry (`scene_variant_run.spec_entry`), written into every spec; None is a nominal run
        self.scene_variant = None if scene_variant is None else dict(scene_variant)
        self.socket_roots = {"policy": self.run / "ipc" / "policy"}
        self._next_wave = 0

    def _launch(self, *, worker_id, wave_id, generation, short, root, session):
        return ContainerLaunch(launch_id=wave_id + "-" + worker_id + "-g" + str(generation), role="shard", worker_id=worker_id,
                               wave_id=wave_id, launch_generation=generation,
                               container_name="so101-act-" + short + "-" + worker_id + "-g" + str(generation),
                               image_digest=self.config["shard_image"]["digest"], owned_root=str(root), session_id=session)

    def __call__(self, *, plan, worker_ids, context):
        """One owner per worker for wave `plan['wave_index']`; `context` is the wave's (its worker count is the wave's)."""
        wave = plan["wave_index"]
        if (type(wave) is not int or wave != self._next_wave or type(worker_ids) is not tuple or not worker_ids
                or context != replace(self.context, worker_count=len(worker_ids))):
            raise ValueError("ROLLOUT_SHARD_WAVE_INVALID")
        validate_file_ref(self.parallel_runtime)
        short = hashlib.sha256((self.context.campaign_id + ":" + self.context.operation_id).encode()).hexdigest()[:16]
        wave_id = "wave-" + str(wave)
        generation = wave + 1
        images = dict(head=self.config["head_service"]["image"], teacher=self.config["teacher_service"]["image"],
                      shard=self.config["shard_image"])
        paths = {"run": self.run, "socket_roots": dict(self.socket_roots)}
        owners = []
        for worker_id in worker_ids:
            root = self.run / wave_id / worker_id / ("g" + str(generation))
            root.mkdir(parents=True, mode=0o700)
            for name in ("tmp", "control", "output", "task-inputs"):
                (root / name).mkdir(mode=0o700)
            session = "act-" + short + "-" + worker_id + "-g" + str(generation)
            token = secrets.token_hex(32)
            spec = dict(schema_version=SPEC_SCHEMA_VERSION, kind="ACT_CONTAINER_SHARD", workload_kind="act_rollout",
                        campaign_id=context.campaign_id, worker_id=worker_id, launch_generation=generation,
                        execution_generation=context.execution_generation,
                        runtime_id="runtime-" + short + "-" + worker_id + "-g" + str(generation),
                        service_epoch=context.service_epoch, service_token=token, owned_root=str(root),
                        simulation_session_id=session, gpu_uuid=context.physical_gpu_uuid,
                        controlled_runtime=self.config["controlled_runtime"], rollout_identity=dict(self.rollout_identity),
                        rig_profile_sha256=self.rig_profile_sha256, parallel_runtime=dict(self.parallel_runtime),
                        wave_id=wave_id, deadline_monotonic_s=context.deadline_monotonic_s)
            if self.scene_variant is not None:
                spec["scene_variant"] = dict(self.scene_variant)
            spec_path = self.run / ("shard-" + wave_id + "-" + worker_id + "-g" + str(generation) + ".json")
            _write(spec_path, spec)
            if load_spec(spec_path)[0] != spec:
                raise ValueError("ROLLOUT_SHARD_SPEC_DRIFT")
            launch = self._launch(worker_id=worker_id, wave_id=wave_id, generation=generation, short=short, root=root,
                                  session=session)
            if launch.launch_id != instance_id_for(spec):
                raise ValueError("ROLLOUT_SHARD_INSTANCE_ID_DRIFT")
            owners.append(ContainerShardOwner(
                admitted_context=context, launch=launch, entry=ShardLaunchArgs(spec=spec_path, mujoco_session_id=session),
                images=images, paths=paths, registry=self.registry, approved_inputs=self.approved_inputs,
                config_paths=tuple(dict.fromkeys((*self.config_paths, spec_path))), service_token=token,
                startup_timeout_s=self.runtime.initializing_hard_timeout_s, status_timeout_s=self.runtime.heartbeat_timeout_s,
                max_frame_bytes=self.runtime.broker_max_frame_bytes, stop_timeout_s=self.runtime.worker_recovery_timeout_s,
                docker_runner=self.docker_runner, namespace_reader=self.namespace_reader, mount_build=self.mount_build))
        self._next_wave += 1
        return tuple(owners)
