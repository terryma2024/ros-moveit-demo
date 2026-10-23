"""A native ACT instance world for tests: the real owner, registry and instance program around a real subprocess instance.

Real: `NativeInstanceOwner`, the launch registry and its durable intent, the Host process-group primitives, the instance
program (`serve_instance`) with its control server and durable writers, and the instance's own `NativeShardRetirement`
that writes the original stop receipt. The instance is a real subprocess that leads a session of its own.
Controlled doubles: the ROS stack the instance would own and its goal-stop probe (no ROS here), and the Host ROS graph probe.

This file is also the instance's entry point: the owner's command is `python native_instance_world.py --mode <mode> ...`.
Modes: `serve` (serve until SIGTERM, then retire and exit 0), `die_early` (exit before the ready record),
`ignore_term` (ready, then ignore SIGTERM), `hard_exit` (ready, then exit at once on SIGTERM without a stop receipt),
`orphan` and `group_orphan` (as `serve`, but leave a stray process that survives the instance, in another session or in the
instance's own process group).
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


def instance_main(argv):
    from so101_demo.cli.act_instance_native import native_layout
    from so101_demo.runtime.act_instance import program
    from so101_demo.runtime.act_instance.identity import mark_instance
    from so101_demo.runtime.act_instance.spec import load_spec
    from so101_demo.runtime.container_campaign.controller_stop import ControllerStopObservation
    from so101_demo.runtime.container_campaign.process_identity import read_process_owner
    from so101_demo.runtime.container_campaign.retirement import NativeShardRetirement
    from so101_demo.runtime.parallel_ipc.frames import canonical_json
    from so101_teleop.unified.act_stack import ActStackLaunch, ActStackProcessOwner
    from so101_teleop.unified.contracts import OwnerKey

    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--install-prefix', type=Path, required=True)
    parser.add_argument('--ros2', type=Path, required=True)
    parser.add_argument('--mode', default='serve')
    parser.add_argument('--goal-stop', type=Path, required=True)
    args = parser.parse_args(argv)
    spec, runtime = load_spec(args.spec)
    layout = native_layout(spec, args.install_prefix, args.ros2)
    mark_instance(layout.owned_root, layout.output_root)
    if args.mode == 'die_early':
        return 3
    root = layout.owned_root
    stack_root = root/'stack'
    stack_root.mkdir(mode=0o700)
    process = read_process_owner(os.getpid())
    native = OwnerKey(501, 501, 100, 'a'*64, 'b'*64)

    class Stack(ActStackProcessOwner):
        async def start(self, *, timeout_s):
            return native

        async def stop(self, **kwargs):
            (stack_root/'cleanup-receipt.json').write_bytes(canonical_json(dict(schema_version=1,
                leader_pid=native.pid, pgid=native.pgid, started_ticks=native.started_ticks,
                argv_sha256=native.argv_sha256, session_id=spec['simulation_session_id'], ros_domain_id=181,
                group_clear=True, graph_clear=True, physical_stop_confirmed=True, parent_exited=False,
                term_sent=True, kill_sent=False, finished_at_monotonic_ns=time.monotonic_ns())))
            self.process = self.owner = None

    launch = ActStackLaunch(ros2_executable=Path('/usr/bin/true'), session_id=spec['simulation_session_id'],
        evidence_root=stack_root, ros_domain_id=181, environment={})
    stack = Stack(launch, ready_probe=lambda: True, stop_probe=lambda: True, graph_clear_probe=lambda: True)
    stack.owner, stack.process = native, SimpleNamespace(pid=501)
    goals = ControllerStopObservation(args.goal_stop.read_bytes())
    retirement = NativeShardRetirement(process_owner=process, launch_generation=spec['launch_generation'],
        evidence_root=root, stack=stack, goal_stop_budget_s=5, stack_stop_budget_s=15,
        goal_stop_probe=lambda **kwargs: goals)
    ready = SimpleNamespace(readiness_bytes=b'{"ready":true}\n')
    if args.mode in ('orphan', 'group_orphan'):
        # a stray that outlives the instance, carrying the instance marker like the ROS stack's processes would: in a
        # session of its own (`orphan`) or in the instance's own process group (`group_orphan`)
        subprocess.Popen(['sleep', '120'], start_new_session=args.mode == 'orphan')
    if args.mode == 'ignore_term':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if args.mode == 'hard_exit':
        signal.signal(signal.SIGTERM, lambda *_: os._exit(9))
    signals = args.mode not in ('ignore_term', 'hard_exit')
    return asyncio.run(program.serve_instance(spec, runtime, layout, process=process, stack=stack, ready=ready,
        retirement=retirement, install_signals=signals, ready_check=lambda: True))


def build_world(tmp_path, monkeypatch, *, mode='serve', stop_budget=20., startup_budget=90., popen=subprocess.Popen):
    """A registered, admitted-looking native single worker whose `NativeInstanceOwner` is ready to start."""
    from test_controller_stop import run_probe
    from so101_demo.runtime.container_campaign.launch import ShardLaunchArgs
    from so101_demo.runtime.container_campaign.native_owner import NativeInstanceOwner
    from so101_demo.runtime.container_campaign.paths import host_teacher_socket, make_campaign_paths
    from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
    from so101_teleop.unified.contracts import AdmittedCampaignContext

    paths = make_campaign_paths(tmp_path, 'campaign')
    root = paths['measurement']/'w00'/'g1'
    root.mkdir(parents=True, mode=0o700)
    for name in ('tmp', 'control', 'output', 'task-inputs'):
        (root/name).mkdir(mode=0o700)
    runtime = paths['run']/'runtime.yaml'
    shutil.copyfile(SOURCE_ROOT/'config/mujoco/parallel_batch_linux_cuda.yaml', runtime)
    gpu = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'
    session, token = 'campaign-w00-g1', 'e'*64
    spec_path = paths['run']/'spec.json'
    spec_path.write_text(json.dumps(dict(schema_version=2, kind='ACT_CONTAINER_SHARD', workload_kind='no_motion_readiness',
        campaign_id='campaign', worker_id='w00', execution_generation=1, service_epoch='epoch', launch_generation=1,
        owned_root=str(root), simulation_session_id=session, gpu_uuid=gpu, service_token=token, runtime_id='runtime',
        controlled_runtime=dict(path=str(runtime), sha256=hashlib.sha256(runtime.read_bytes()).hexdigest()))))
    _, goals, _ = run_probe(monkeypatch)
    goal_file = paths['run']/'goal-stop.json'
    goal_file.write_bytes(goals.payload)
    context = AdmittedCampaignContext(campaign_id='campaign', operation_id='operation',
        workload_kind='act_collection_start', service_epoch='epoch', execution_generation=1, stable_host_id='host',
        physical_gpu_uuid=gpu, worker_count=1, source_sha256='d'*64, manifest_sha256='d'*64,
        runtime_config_sha256='d'*64, collection_config_sha256='d'*64, contact_policy_fingerprint='d'*64,
        domain_session_map_sha256='d'*64, resource_binding_id='binding', evidence_root=str(paths['run']),
        admitted_at_monotonic_s=1, deadline_monotonic_s=time.monotonic()+3600, registered_evidence_root=str(tmp_path),
        campaign_config_path=str(spec_path), campaign_config_sha256='d'*64)
    launch = ContainerLaunch(launch_id='measurement-w00-g1', role='shard', worker_id='w00', wave_id='measurement',
        launch_generation=1, container_name=None, image_digest=None, owned_root=str(root), session_id=session,
        launcher='native')
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3')
    world = SimpleNamespace(paths=paths, root=root, context=context, launch=launch, registry=registry,
        spec_path=spec_path, goal_file=goal_file, graph_clear=True, session=session, token=token, runtime_path=runtime)
    world.owner = NativeInstanceOwner(admitted_context=context, launch=launch,
        entry=ShardLaunchArgs(spec=spec_path, mujoco_session_id=session), paths=paths, registry=registry,
        service_token=token, startup_timeout_s=startup_budget, status_timeout_s=5., max_frame_bytes=8388608,
        stop_timeout_s=stop_budget, install_prefix=tmp_path, ros2_executable=tmp_path/'host-ros/bin/ros2', teacher_socket=host_teacher_socket(paths['run']),
        command=[sys.executable, str(Path(__file__).resolve()), '--mode', mode, '--goal-stop', str(goal_file)],
        base_environment=dict(os.environ), graph_probe=lambda: world.graph_clear, popen=popen)
    world.cleanup = lambda: cleanup(world)
    return world


def cleanup(world):
    """Leave nothing behind: kill the instance's group and any stray carrying its marker, then close the registry."""
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
    raise SystemExit(instance_main(sys.argv[1:]))
