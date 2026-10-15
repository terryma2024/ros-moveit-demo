"""Prepare the native single-worker instance in the admitted slot: the native counterpart of `ContainerShardLauncher`.

The spec, the instance directories, the launch registry record and the wave coordinator are the same as for a container;
this launcher only changes how the instance is started (`NativeInstanceOwner`) and how it reaches the Teacher service, which
still runs in its container: through the Host path of the same Unix socket the container mounts as `/act/ipc/teacher`.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys

from so101_demo.runtime.act_instance.identity import ACT_INSTANCE_ROS_DOMAIN_ID
from so101_demo.runtime.container_campaign.native_owner import NativeInstanceOwner
from so101_demo.runtime.container_campaign.native_processor_owner import NativeProcessorOwner
from so101_demo.runtime.container_campaign.processor_launcher import ContainerProcessorLauncher
from so101_demo.runtime.container_campaign.launch import ProcessorLaunchArgs
from so101_demo.runtime.container_campaign.registry import ContainerLaunch
from so101_demo.runtime.container_campaign.shard_launcher import ContainerShardLauncher

#: The module the native instance runs; the same installed code a container image holds, started as a Host process.
NATIVE_INSTANCE_MODULE = 'so101_demo.cli.act_instance_native'

#: The module the native processor runs: the native shell of the same `campaign_processor` program a processor container runs.
NATIVE_PROCESSOR_MODULE = 'so101_demo.cli.campaign_processor_native'

#: How long the Host's graph probe discovers before it lists the nodes of the instance's domain.
GRAPH_SPIN_TIME_S = 3.0


def installed_graph_probe(ros2_executable, launch, environment):
    """The Host ROS graph probe on the instance's fixed domain: `ros2 node list` with the instance's discovery settings.

    The probe's environment is the instance's without the instance marker, so that the probe itself never counts as a
    survivor of the instance. It discovers for `GRAPH_SPIN_TIME_S` before it lists: with localhost-only discovery the
    default spin of `ros2 node list --no-daemon` misses a live node on repeated short calls (measured on the Host, 0 of 5
    default listings saw a node that 5 of 5 listings with a 3 s spin saw), and a clear graph must mean no node."""
    from so101_demo.runtime.act_instance.identity import INSTANCE_OUTPUT_ENV, INSTANCE_ROOT_ENV
    from so101_teleop.unified.act_stack import ActStackLaunch
    from so101_teleop.unified.act_stack_probes import RosGraphClearProbe

    probe_environment = {name: value for name, value in environment.items()
                         if name not in (INSTANCE_ROOT_ENV, INSTANCE_OUTPUT_ENV)}
    return RosGraphClearProbe(ActStackLaunch(ros2_executable=Path(ros2_executable),
        session_id=launch.session_id, evidence_root=Path(launch.owned_root), ros_domain_id=ACT_INSTANCE_ROS_DOMAIN_ID,
        environment=probe_environment), timeout_s=10., spin_time_s=GRAPH_SPIN_TIME_S)


class NativeInstanceLauncher(ContainerShardLauncher):
    def __init__(self, *, install_prefix, ros2_executable=None, command=None, base_environment=None,
                 popen=subprocess.Popen, graph_probe_factory=installed_graph_probe, **arguments):
        super().__init__(**arguments)
        self.base_environment = dict(os.environ if base_environment is None else base_environment)
        if ros2_executable is None:
            found = shutil.which('ros2', path=self.base_environment.get('PATH', ''))
            ros2_executable = None if found is None else Path(found).absolute()
        if (not Path(install_prefix).is_absolute() or ros2_executable is None or not Path(ros2_executable).is_absolute()
                or not callable(graph_probe_factory) or not callable(popen) or self.context.worker_count != 1):
            raise ValueError('COLLECTION_NATIVE_LAUNCHER_INVALID')
        self.install_prefix, self.ros2_executable = Path(install_prefix), Path(ros2_executable)
        self.command = list(command) if command is not None else [sys.executable, '-m', NATIVE_INSTANCE_MODULE]
        self.popen, self.graph_probe_factory = popen, graph_probe_factory

    def _launch(self, *, slot, wave_id, generation, short, root, session):
        return ContainerLaunch(launch_id=wave_id+'-'+slot.worker_id+'-g'+str(generation), role='shard',
            worker_id=slot.worker_id, wave_id=wave_id, launch_generation=generation, container_name=None,
            image_digest=None, owned_root=str(root), session_id=session, launcher='native')

    def _owner(self, *, launch, entry, spec_path, token, images, endpoints):
        owner_environment = None

        def graph_probe():
            nonlocal owner_environment
            return self.graph_probe_factory(self.ros2_executable, launch, owner_environment)()
        owner = NativeInstanceOwner(admitted_context=self.context, launch=launch, entry=entry, paths=self.paths,
            registry=self.registry, service_token=token, startup_timeout_s=self.runtime.initializing_hard_timeout_s,
            status_timeout_s=self.runtime.heartbeat_timeout_s, max_frame_bytes=self.runtime.broker_max_frame_bytes,
            stop_timeout_s=self.runtime.worker_recovery_timeout_s, install_prefix=self.install_prefix,
            ros2_executable=self.ros2_executable,
            teacher_socket=endpoints['teacher'].socket_path, command=self.command,
            base_environment=self.base_environment, graph_probe=graph_probe, popen=self.popen)
        owner_environment = owner.environment
        return owner


class NativeProcessorLauncher(ContainerProcessorLauncher):
    """Prepare the native processor of a native single-worker run (phase 2): the native counterpart of `ContainerProcessorLauncher`.

    The private directories, the spec and the launch record are the container processor's; only the launcher differs (a Host process
    group, no container, no image), and so does what the owner mounts: nothing, since the processor reads the same host paths."""

    def __init__(self, *, context, paths, registry, parallel_runtime, approved_inputs, config_paths, install_prefix,
                 command=None, base_environment=None, popen=subprocess.Popen):
        self._common(context=context, paths=paths, registry=registry, parallel_runtime=parallel_runtime,
                     approved_inputs=approved_inputs, config_paths=config_paths)
        self.base_environment = dict(os.environ if base_environment is None else base_environment)
        if not Path(install_prefix).is_absolute() or not callable(popen) or self.context.worker_count != 1:
            raise ValueError('COLLECTION_NATIVE_LAUNCHER_INVALID')
        self.install_prefix = Path(install_prefix)
        self.command = list(command) if command is not None else [sys.executable, '-m', NATIVE_PROCESSOR_MODULE]
        self.popen = popen

    def _launch(self, *, slot, generation, short, root):
        return ContainerLaunch(launch_id=f'processing-{slot.worker_id}-g{generation}', role='processor', worker_id=slot.worker_id,
            wave_id=None, launch_generation=generation, container_name=None, image_digest=None, owned_root=str(root),
            session_id=None, launcher='native')

    def _owner(self, *, launch, spec_path, token, attempts):
        return NativeProcessorOwner(admitted_context=self.context, launch=launch, entry=ProcessorLaunchArgs(spec=spec_path),
            paths=self.paths, registry=self.registry, service_token=token,
            startup_timeout_s=self.runtime.initializing_hard_timeout_s, status_timeout_s=self.runtime.heartbeat_timeout_s,
            max_frame_bytes=self.runtime.broker_max_frame_bytes, stop_timeout_s=self.runtime.worker_recovery_timeout_s,
            install_prefix=self.install_prefix, command=self.command, base_environment=self.base_environment, popen=self.popen)
