"""Prepare one private processor container (phase 2) in an admitted processor slot.

A processor is launched per slot and per launch generation: `<run>/processing/pNN/gK` holds its private directories, the spec the
`campaign_processor` program loads is `<run>/processor-pNN-gK.json`, and the registry launch is `processing-pNN-gK`.

Mounts (plan amendment A1). A dynamic queue may hand any scene to any processor, so every processor mounts, read-only, every
phase-1 sealed attempt directory of this run (all waves). The one writable mount is the whole `<run>/processing` tree, not only the
processor's own `pNN/gK`: the design says "one writable output directory", and a task writes its episode under
`<run>/processing/<scene>/<attempt>-proc-<n>`, which belongs to the scene, not to the processor that happened to take it.
"""

import hashlib
from pathlib import Path
import secrets

from so101_demo.runtime.act_processor.spec import load_processor_spec
from so101_demo.runtime.container_campaign.launch import ProcessorLaunchArgs
from so101_demo.runtime.container_campaign.paths import _phase1_attempt
from so101_demo.runtime.container_campaign.processor_owner import ContainerProcessorOwner
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.service_owner import _docker, _write
from so101_demo.runtime.container_campaign.shard_owner import read_container_namespace
from so101_demo.runtime.inference.config import validate_file_ref
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.worker_slots import ActWorkerSlot


def all_phase1_attempts(run):
    """Every sealed phase-1 attempt directory of the run, in sorted order (the glob is the shape `_phase1_attempt` accepts)."""
    run = Path(run)
    found = []
    for path in run.glob("/".join(("wave-*", "w*", "g*", "output", "tasks", "*", "attempts", "*", "*", "sealed"))):
        try:
            found.append(_phase1_attempt(path, run))
        except ValueError:
            continue
    return tuple(sorted(found))


class ContainerProcessorLauncher:
    def __init__(self, *, context, images, paths, registry, parallel_runtime, approved_inputs, config_paths,
                 docker_runner=_docker, namespace_reader=read_container_namespace, mount_build, cpuset_cpus=None):
        if type(images) is not dict or set(images) != {"head", "teacher", "shard"}:
            raise ValueError("PROCESSOR_LAUNCHER_INVALID")
        self._common(context=context, paths=paths, registry=registry, parallel_runtime=parallel_runtime,
                     approved_inputs=approved_inputs, config_paths=config_paths)
        self.images = images
        self.docker_runner, self.namespace_reader = docker_runner, namespace_reader
        self.mount_build, self.cpuset_cpus = mount_build, cpuset_cpus

    def _common(self, *, context, paths, registry, parallel_runtime, approved_inputs, config_paths):
        from so101_demo.parallel_batch.two_worker_composition import load_execution_config as _load_runtime_config

        if (type(context) is not AdmittedCampaignContext or context.workload_kind != "act_collection_start"
                or type(registry) is not ContainerLaunchRegistry or str(paths["run"]) != context.evidence_root
                or type(approved_inputs) is not tuple or type(config_paths) is not tuple):
            raise ValueError("PROCESSOR_LAUNCHER_INVALID")
        self.context, self.paths, self.registry = context, paths, registry
        self.parallel_runtime = dict(parallel_runtime)
        self.runtime = _load_runtime_config(validate_file_ref(parallel_runtime))
        self.approved_inputs, self.config_paths = approved_inputs, config_paths

    def _launch(self, *, slot, generation, short, root):
        return ContainerLaunch(launch_id=f"processing-{slot.worker_id}-g{generation}", role="processor", worker_id=slot.worker_id,
                               wave_id=None, launch_generation=generation,
                               container_name=f"so101-act-{short}-{slot.worker_id}-g{generation}",
                               image_digest=self.images["shard"]["digest"], owned_root=str(root), session_id=None)

    def _owner(self, *, launch, spec_path, token, attempts):
        return ContainerProcessorOwner(admitted_context=self.context, launch=launch, entry=ProcessorLaunchArgs(spec=spec_path),
            images=self.images, paths=self.paths, registry=self.registry, approved_inputs=self.approved_inputs,
            config_paths=tuple(dict.fromkeys((*self.config_paths, spec_path))), phase1_attempts=attempts,
            service_token=token, startup_timeout_s=self.runtime.initializing_hard_timeout_s,
            status_timeout_s=self.runtime.heartbeat_timeout_s, max_frame_bytes=self.runtime.broker_max_frame_bytes,
            stop_timeout_s=self.runtime.worker_recovery_timeout_s, docker_runner=self.docker_runner,
            namespace_reader=self.namespace_reader, mount_build=self.mount_build,
            cpuset_cpus=self.cpuset_cpus)

    def __call__(self, *, slot, generation):
        context = self.context
        if (type(slot) is not ActWorkerSlot or not slot.is_processor or slot.campaign_id != context.campaign_id
                or slot.execution_generation != context.execution_generation
                or type(generation) is not int or generation < 1):
            raise ValueError("PROCESSOR_LAUNCH_SLOT_INVALID")
        run = Path(self.paths["run"])
        attempts = all_phase1_attempts(run)
        if not attempts:
            raise ValueError("PROCESSOR_LAUNCH_NO_PHASE1_ATTEMPTS")
        validate_file_ref(self.parallel_runtime)
        processing = run / "processing"
        processing.mkdir(mode=0o700, exist_ok=True)
        root = processing / slot.worker_id / f"g{generation}"
        root.mkdir(parents=True, mode=0o700)
        for name in ("tmp", "control", "output", "task-inputs"):
            (root / name).mkdir(mode=0o700)
        short = hashlib.sha256((context.campaign_id + ":" + context.operation_id).encode()).hexdigest()[:16]
        token = secrets.token_hex(32)
        suffix = f"{slot.worker_id}-g{generation}"
        spec = dict(schema_version=1, kind="ACT_CONTAINER_PROCESSOR", campaign_id=context.campaign_id,
                    processor_id=slot.worker_id, launch_generation=generation,
                    execution_generation=context.execution_generation, runtime_id=f"runtime-{short}-{suffix}",
                    service_epoch=context.service_epoch, service_token=token, owned_root=str(root),
                    processing_root=str(processing), parallel_runtime=self.parallel_runtime,
                    deadline_monotonic_s=context.deadline_monotonic_s)
        spec_path = run / f"processor-{suffix}.json"
        _write(spec_path, spec)
        if load_processor_spec(spec_path)[0] != spec:
            raise ValueError("PROCESSOR_SPEC_DRIFT")
        launch = self._launch(slot=slot, generation=generation, short=short, root=root)
        return self._owner(launch=launch, spec_path=spec_path, token=token, attempts=attempts)
