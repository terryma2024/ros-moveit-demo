"""A native ACT processor world for tests: the real owner, registry and processor program around a real subprocess processor.

Real: `NativeProcessorOwner`, the launch registry and its durable intent, the Host process-group primitives and the processor
program (`run_processor`) with its control server and durable writers, in a real subprocess that leads a session of its own.
Nothing is controlled except the spawn seam (`popen`): a processor has no ROS stack and no graph.

This file is also the processor's entry point: the owner's command is `python native_processor_world.py --mode <mode> ...`.
Modes: `serve` (serve until SIGTERM, then exit 0), `die_early` (exit before the ready record), `orphan` (as `serve`, but leave a
stray process in a session of its own that outlives the processor and carries its marker).
"""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def processor_main(argv):
    from so101_demo.cli.campaign_processor_native import native_layout
    from so101_demo.runtime.act_processor.program import run_processor
    from so101_demo.runtime.act_processor.spec import load_processor_spec

    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--install-prefix', type=Path, required=True)
    parser.add_argument('--mode', default='serve')
    args = parser.parse_args(argv)
    spec, runtime = load_processor_spec(args.spec)
    if args.mode == 'die_early':
        return 3
    if args.mode == 'orphan':
        subprocess.Popen(['sleep', '120'], start_new_session=True)
    return asyncio.run(run_processor(spec, runtime, native_layout(spec)))


def build_world(tmp_path, *, mode='serve', stop_budget=20., startup_budget=90., popen=subprocess.Popen, generation=1, after=None):
    """A registered, admitted-looking native single worker whose `NativeProcessorOwner` is ready to start.

    `after` is an earlier world of the same run: the next generation of the slot shares its paths and registry."""
    from so101_demo.runtime.container_campaign.launch import ProcessorLaunchArgs
    from so101_demo.runtime.container_campaign.native_processor_owner import NativeProcessorOwner
    from so101_demo.runtime.container_campaign.paths import make_campaign_paths
    from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
    from so101_teleop.unified.contracts import AdmittedCampaignContext

    paths = make_campaign_paths(tmp_path, 'campaign') if after is None else after.paths
    processing = paths['run']/'processing'
    processing.mkdir(mode=0o700, exist_ok=True)
    root = processing/'p00'/f'g{generation}'
    root.mkdir(parents=True, mode=0o700)
    for name in ('tmp', 'control', 'output', 'task-inputs'):
        (root/name).mkdir(mode=0o700)
    runtime = paths['run']/'runtime.yaml'
    if not runtime.exists():
        shutil.copyfile(SOURCE_ROOT/'config/mujoco/parallel_batch_linux_cuda.yaml', runtime)
    token = 'e'*64
    spec_path = paths['run']/f'processor-p00-g{generation}.json'
    spec_path.write_text(json.dumps(dict(schema_version=1, kind='ACT_CONTAINER_PROCESSOR', campaign_id='campaign',
        processor_id='p00', launch_generation=generation, execution_generation=1, runtime_id='runtime', service_epoch='epoch',
        service_token=token, owned_root=str(root), processing_root=str(processing),
        parallel_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()),
        deadline_monotonic_s=time.monotonic()+3600)))
    gpu = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'
    context = AdmittedCampaignContext(campaign_id='campaign', operation_id='operation',
        workload_kind='act_collection_start', service_epoch='epoch', execution_generation=1, stable_host_id='host',
        physical_gpu_uuid=gpu, worker_count=1, source_sha256='d'*64, manifest_sha256='d'*64,
        runtime_config_sha256='d'*64, collection_config_sha256='d'*64, contact_policy_fingerprint='d'*64,
        domain_session_map_sha256='d'*64, resource_binding_id='binding', evidence_root=str(paths['run']),
        admitted_at_monotonic_s=1, deadline_monotonic_s=time.monotonic()+3600, registered_evidence_root=str(tmp_path),
        campaign_config_path=str(spec_path), campaign_config_sha256='d'*64)
    launch = ContainerLaunch(launch_id=f'processing-p00-g{generation}', role='processor', worker_id='p00', wave_id=None,
        launch_generation=generation, container_name=None, image_digest=None, owned_root=str(root), session_id=None,
        launcher='native')
    registry_path = paths['host']/'launches.sqlite3'
    registry = ContainerLaunchRegistry(registry_path) if after is None else after.registry
    world = SimpleNamespace(paths=paths, root=root, context=context, launch=launch, registry=registry, spec_path=spec_path,
        token=token, runtime_path=runtime)
    world.owner = NativeProcessorOwner(admitted_context=context, launch=launch, entry=ProcessorLaunchArgs(spec=spec_path),
        paths=paths, registry=registry, service_token=token, startup_timeout_s=startup_budget, status_timeout_s=5.,
        max_frame_bytes=8388608, stop_timeout_s=stop_budget, install_prefix=tmp_path,
        command=[sys.executable, str(Path(__file__).resolve()), '--mode', mode],
        base_environment=dict(os.environ), popen=popen)
    world.cleanup = lambda: cleanup(world)
    return world


def cleanup(world):
    """Leave nothing behind: kill the processor's group and any stray carrying its marker, then close the registry."""
    from so101_demo.runtime.container_campaign.native_stop import marker_survivors
    from so101_teleop.owned_group import terminate_group

    process = world.owner.process
    if process is not None and process.poll() is None:
        terminate_group(pgid=process.pid, timeout_s=2.)
        process.wait()
    for pid in marker_survivors(world.root, started_ticks=0):
        if pid > 0:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass
    world.registry.close()


if __name__ == '__main__':
    raise SystemExit(processor_main(sys.argv[1:]))
