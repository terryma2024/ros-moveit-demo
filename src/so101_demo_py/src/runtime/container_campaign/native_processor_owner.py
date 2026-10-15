"""Host ownership of one native processor (phase 2 of a native single-worker run): a Host process group running the same
`campaign_processor` program a processor container runs.

It is `NativeInstanceOwner` with the differences a processor has (see `processor_owner.ContainerProcessorOwner` for the container
counterpart): no ROS identity, no GPU, no Teacher socket and no simulation session; the launch is the role `processor` with the
launcher `native`; readiness is the program's own `processor-ready.json`; and a processor has no ROS graph, so the graph reading of
its exit proof is vacuously clear. Everything else is inherited unchanged: the process group of its own, the durable intent before
the spawn, SIGTERM to the registered leader only, and a stop proven by the Host's observation that the leader is gone, its group is
empty and no process still carries its marker (`native_stop`). Anything it left behind is terminated, recorded in
`native-leftovers.json`, and makes that stop unconfirmed for good.
"""

import asyncio
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time

from so101_demo.runtime.act_instance.identity import INSTANCE_OUTPUT_ENV, INSTANCE_ROOT_ENV
from so101_demo.runtime.act_processor.program import READY_NAME
from so101_demo.runtime.act_processor.spec import load_processor_spec
from so101_demo.runtime.container_campaign.launch import ProcessorLaunchArgs, instance_private_environment
from so101_demo.runtime.container_campaign.native_owner import _NOT_INHERITED, NativeInstanceOwner
from so101_demo.runtime.container_campaign.process_identity import pid_namespace_inode
from so101_demo.runtime.container_campaign.processor_owner import check_processor_ready
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.service_owner import _write
from so101_teleop.unified.contracts import AdmittedCampaignContext


def native_processor_environment(base, *, owned_root):
    """The environment of a native processor: the Host's, with private locations and the instance marker on top.

    A processor has no ROS identity (it joins no graph), no display and no GPU: `CUDA_VISIBLE_DEVICES` is empty, as in its
    container, which gets no GPU. The marker names the owned root so that every descendant (the offline processor child runs in
    a session of its own) can be found after an abnormal exit."""
    environment = {name: value for name, value in base.items() if name not in _NOT_INHERITED and not name.startswith("ROS_")}
    for entry in instance_private_environment(Path(owned_root), gpu=False):
        name, _, value = entry.partition("=")
        environment[name] = value
    environment[INSTANCE_ROOT_ENV] = str(owned_root)
    environment[INSTANCE_OUTPUT_ENV] = str(Path(owned_root) / "output")
    environment["CUDA_VISIBLE_DEVICES"] = ""
    return environment


def no_ros_graph():
    """A processor owns no ROS node; the Host graph reading of its exit proof is clear by construction."""
    return True


class NativeProcessorOwner(NativeInstanceOwner):
    CODE = 'PROCESSOR'
    ROLE = 'processor'

    def __init__(self, *, admitted_context, launch, entry, paths, registry, service_token, startup_timeout_s, status_timeout_s,
                 max_frame_bytes, stop_timeout_s, install_prefix, command, base_environment, popen=subprocess.Popen,
                 monotonic_ns=time.monotonic_ns):
        run = Path(paths['run'])
        if (type(admitted_context) is not AdmittedCampaignContext or type(launch) is not ContainerLaunch
                or launch.role != 'processor' or launch.launcher != 'native' or type(entry) is not ProcessorLaunchArgs
                or type(registry) is not ContainerLaunchRegistry or str(run) != admitted_context.evidence_root
                or Path(launch.owned_root).resolve(strict=True) != Path(launch.owned_root)
                or not Path(launch.owned_root).is_relative_to(run / 'processing')
                or type(service_token) is not str or re.fullmatch(r'[0-9a-f]{64}', service_token) is None
                or type(max_frame_bytes) is not int or max_frame_bytes <= 0
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in
                       (startup_timeout_s, status_timeout_s, stop_timeout_s))
                or not Path(install_prefix).is_absolute()
                or type(command) is not list or not command or any(type(item) is not str for item in command)
                or not callable(popen)):
            raise ValueError('PROCESSOR_OWNER_CONFIG_INVALID')
        self.context, self.launch, self.entry, self.registry = admitted_context, launch, entry, registry
        self.root = Path(launch.owned_root)
        self.spec, _runtime = load_processor_spec(entry.spec)
        expected = dict(campaign_id=admitted_context.campaign_id, processor_id=launch.worker_id,
                        launch_generation=launch.launch_generation, execution_generation=admitted_context.execution_generation,
                        service_epoch=admitted_context.service_epoch, service_token=service_token,
                        owned_root=str(self.root), processing_root=str(run / 'processing'))
        if (any(self.spec.get(name) != value or type(self.spec.get(name)) is not type(value) for name, value in expected.items())
                or self.spec['deadline_monotonic_s'] > admitted_context.deadline_monotonic_s):
            raise ValueError('PROCESSOR_SPEC_CONTEXT_MISMATCH')
        self.spec_sha256 = hashlib.sha256(entry.spec.read_bytes()).hexdigest()
        self.install_prefix, self._teacher_socket = Path(install_prefix), None
        self.argv = [*command, '--spec', str(entry.spec), '--install-prefix', str(self.install_prefix)]
        self.environment = native_processor_environment(base_environment, owned_root=self.root)
        self.token, self.startup_budget, self.status_budget, self.stop_budget = (
            service_token, startup_timeout_s, status_timeout_s, stop_timeout_s)
        self.max_bytes, self.graph_probe, self.popen, self.clock = max_frame_bytes, no_ros_graph, popen, monotonic_ns
        self.process, self.owner, self.bridge, self._log = None, None, None, None
        self._registered, self._closing, self._runtime_ready = False, False, False
        self._start_task = self._close_task = None
        self._startup_done = asyncio.Event()

    @property
    def teacher_socket(self):
        """A processor reaches no Teacher."""
        return None

    # ---- what a processor does differently from a shard instance -----------------------------------------------------------

    def _spec_unchanged(self):
        return load_processor_spec(self.entry.spec)[0] == self.spec

    def _launch_record(self):
        return dict(argv=self.argv, launcher='native', role='processor',
            environment_sha256=hashlib.sha256(json.dumps(self.environment, sort_keys=True).encode()).hexdigest(),
            fixed_environment={name: self.environment[name] for name in (INSTANCE_ROOT_ENV, INSTANCE_OUTPUT_ENV,
                                                                         'CUDA_VISIBLE_DEVICES')})

    def _session_id(self):
        return self.launch.launch_id

    async def _await_runtime(self, binding, deadline):
        await self._wait_file(self.root / READY_NAME, deadline)
        check_processor_ready(self.root, generation=self.launch.launch_generation, process=binding.process)

    def _write_provenance(self):
        _write(self.root / 'native-processor-provenance.json', dict(schema_version=1, kind='ACT_NATIVE_PROCESSOR_PROVENANCE',
            install_prefix=str(self.install_prefix), argv=self.argv, spec_sha256=self.spec_sha256,
            process_owner=asdict(self.owner.process_key()), host_pid_namespace_inode=pid_namespace_inode()))
