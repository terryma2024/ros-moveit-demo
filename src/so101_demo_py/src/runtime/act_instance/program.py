"""The ACT instance program: the one implementation of an instance's collection logic, for every launcher.

`run_instance(spec, runtime_config, layout)` is what a shard does from its validated spec to its stop: start the plain ACT
execution stack at the fixed identity, serve the Host's four task operations on the control socket, run each collection task
through the shared task builder, and retire the stack with the original stop evidence. The only inputs that differ between a
container and a native single worker are the `InstanceLayout` values and the process environment the launcher sets. This module
therefore holds no launcher-specific check: the container shell checks its own facts (pid 1, interpreter, installed prefix)
before it calls here, and the native shell checks its own.
"""

import asyncio
from dataclasses import asdict
import functools
import hashlib
import os
from pathlib import Path
import signal

from so101_demo.runtime.act_instance.identity import (
    ACT_INSTANCE_ROS_DOMAIN_ID, mark_instance, verify_instance_environment)
from so101_demo.runtime.act_instance.layout import InstanceLayout
from so101_demo.runtime.container_campaign.process_identity import read_process_owner
from so101_demo.runtime.parallel_ipc.frames import canonical_json


def _refuse_motion(_task):
    raise ValueError("SHARD_READINESS_HAS_NO_MOTION_PORT")


def shard_builder(spec,*,stack,layout,ready_check=None,scene_switch=None):
    """The executor's task builder for this workload; readiness shards have no motion port.

    Collection tasks gate on `ready_check`, a repeatable fresh observation of the borrowed stack. The stack's own
    `ready_probe` is the single-use start probe, already consumed by the shard start, so it is never the gate.

    `scene_switch` (indoor P3) gives the stack the scene of each task when the scene list carries an appearance plan."""
    if spec['workload_kind']=='no_motion_readiness':return _refuse_motion
    if spec['workload_kind']=='act_collection':
        from so101_demo.runtime.container_campaign.task_builder import build_collection_task
        if not callable(ready_check):raise ValueError('CAMPAIGN_SHARD_READY_CHECK_REQUIRED')
        return functools.partial(build_collection_task,stack=stack,shard_spec=spec,output_root=layout.output_root,
            teacher_socket=layout.teacher_socket,ready_check=ready_check,scene_switch=scene_switch)
    if spec['workload_kind']=='act_rollout':
        from so101_demo.runtime.act_rollout.task_builder import build_rollout_task
        return functools.partial(build_rollout_task,stack=stack,shard_spec=spec,output_root=layout.output_root,
            policy_socket=layout.policy_socket,install_prefix=layout.install_prefix)
    raise ValueError('CAMPAIGN_SHARD_WORKLOAD_UNKNOWN')


class StackStartAwareRetirement:
    """Native retirement that lets an in-flight stack start settle first, as the old driver's stop did."""

    def __init__(self,retirement):
        self.retirement,self.start_task=retirement,None

    async def retire(self,*,fenced):
        if self.start_task is not None:
            await asyncio.wait({self.start_task})
        return await self.retirement.retire(fenced=fenced)


def instance_id_for(spec):
    """The Host launch id `<wave>-<worker>-g<launch generation>`; the wave is the owned root's grandparent."""
    return f"{Path(spec['owned_root']).parent.parent.name}-{spec['worker_id']}-g{spec['launch_generation']}"


async def serve_instance(spec, runtime_config, layout, *, process, stack, ready, retirement, install_signals=True,
                         ready_check=None, scene_switch=None):
    """Serve the Host's task operations until the executor has stopped; return the process exit code."""
    from so101_demo.runtime.container_campaign import task_executor
    from so101_demo.runtime.container_campaign.retirement import _write
    from so101_teleop.unified.child_runtime import ContainerChildIdentity, ContainerChildIpcServer
    from so101_teleop.unified.contracts import OwnerKey

    root = Path(spec["owned_root"])
    if type(layout) is not InstanceLayout or layout.owned_root != root:
        raise ValueError("ACT_INSTANCE_LAYOUT_MISMATCH")
    output_root = layout.output_root if spec["workload_kind"] in ("act_collection", "act_rollout") else root / "tmp"
    start_aware = StackStartAwareRetirement(retirement)
    # Host status polling bounds owner silence (heartbeat_timeout_s); the frozen worker recovery bound covers
    # helper stop and native retirement.
    executor = task_executor.ContainerTaskExecutor(instance_id=instance_id_for(spec),
        builder=shard_builder(spec,stack=stack,layout=layout,ready_check=ready_check,scene_switch=scene_switch),
        retirement=start_aware,output_root=output_root,
        owner_timeout_s=runtime_config.heartbeat_timeout_s,stop_timeout_s=runtime_config.worker_recovery_timeout_s,
        retire_timeout_s=runtime_config.worker_recovery_timeout_s,ready=False)
    identity = ContainerChildIdentity(runtime_id=spec["runtime_id"],act_campaign_id=spec["campaign_id"],
        act_worker_id=spec["worker_id"],act_generation=spec["execution_generation"],normal_queue_limit=2)
    server = ContainerChildIpcServer(identity,socket_root=layout.control_root,owner=OwnerKey(**asdict(process)),
        service_epoch=spec["service_epoch"],service_token=spec["service_token"],
        max_bytes=runtime_config.broker_max_frame_bytes,task_port=executor,generation=spec["launch_generation"],
        close_timeout_s=runtime_config.heartbeat_timeout_s,process_owner=process)
    loop = asyncio.get_running_loop()
    terminations = []
    signals = (signal.SIGTERM,signal.SIGINT) if install_signals else ()
    for sig in signals:
        loop.add_signal_handler(sig,lambda: terminations.append(asyncio.ensure_future(executor.terminate("SIGTERM"))))
    failed = False
    try:
        await server.start()
        start_aware.start_task = asyncio.create_task(stack.start(timeout_s=runtime_config.initializing_hard_timeout_s))
        stopped = asyncio.ensure_future(executor.wait_stopped())
        try:
            await asyncio.wait({start_aware.start_task,stopped},return_when=asyncio.FIRST_COMPLETED)
            if start_aware.start_task.done():
                start_aware.start_task.result()
                if not executor.closing:
                    _write(root,"runtime-ready.json",canonical_json(dict(schema_version=2,kind="ACT_SHARD_RUNTIME_READY",
                        generation=spec["launch_generation"],process_owner=asdict(process),
                        readiness_sha256=hashlib.sha256(ready.readiness_bytes).hexdigest())))
                    _write(root,"stack-readiness.json",ready.readiness_bytes)
                    executor.mark_ready()
        except Exception as error:
            failed = True
            await executor.terminate(f"SHARD_START_FAILED: {type(error).__name__}")
        await stopped
    finally:
        try:
            await executor.terminate("SHARD_SERVE_ENDED")
            status = await executor.get_status()
            _write(root,"instance-exit.json",canonical_json(dict(schema_version=1,kind="ACT_SHARD_INSTANCE_EXIT",
                state=status.state,fault_reason=status.fault_reason,
                task=None if status.task is None else status.task.model_dump(),
                cleanup_confirmed=executor.cleanup_confirmed,cleanup_errors=executor.cleanup_errors)))
        finally:
            for sig in signals:
                loop.remove_signal_handler(sig)
            close = getattr(ready_check,'close',None)
            if callable(close):
                try:close()   # the kept readiness session's context; the instance exit does not depend on it
                except Exception:pass
            await asyncio.gather(*terminations,return_exceptions=True)
            await server.close()
    return 0 if executor.cleanup_confirmed and not failed else 1


def _releasing_graph_clear_probe_class():
    from so101_teleop.unified.act_stack_probes import RosGraphClearProbe
    from so101_demo.ros.kept_nodes import release_kept_ros_nodes

    class ReleasingGraphClearProbe(RosGraphClearProbe):
        """The stack stop's proof that the domain has no node, after this process closed the nodes it keeps (the readiness
        session, the retained evidence reader): they are participants of the same domain, and left open they are what the proof
        finds (GRAPH_NOT_CLEARED, EXP-658)."""

        def __call__(self) -> bool:
            release_kept_ros_nodes()
            return super().__call__()
    return ReleasingGraphClearProbe


def _ReleasingGraphClearProbe(launch):
    return _releasing_graph_clear_probe_class()(launch)


def compose_stack(launch, observer):
    """The shard's stack owner and its probes: returns `(start_probe, ready_check, stack)`.

    The start probe is the single-use `InstalledActStackReadinessProbe` the stack owner consumes at start (its
    `readiness_bytes` are the startup evidence). `ready_check` is the task gates' separate repeatable check: a kept observation session inside the instance, and a
    fresh probe from the same launch and observer for anything it does not itself prove ready; it never touches the start probe."""
    from so101_teleop.unified.act_stack import ActStackProcessOwner
    from so101_teleop.unified.act_stack_probes import RepeatableActStackStopProbe, RosGraphClearProbe
    from so101_demo.runtime.act_instance.ready_check import KeptActStackReadyCheck
    from so101_teleop.unified.pick_place_startup_issuer import InstalledActStackReadinessProbe

    ready = InstalledActStackReadinessProbe(launch,observer)
    ready_check = KeptActStackReadyCheck(launch,observer)
    stack = ActStackProcessOwner(launch,ready_probe=ready,
        stop_probe=RepeatableActStackStopProbe(launch,observer),graph_clear_probe=_ReleasingGraphClearProbe(launch))
    return ready,ready_check,stack


def instance_stack_launch(spec, *, ros2, stack_root, environment, rig=None, share=None, mujoco_scene=None):
    """The instance's stack: the plain ACT execution stack at the fixed instance identity, no namespace wrapper.

    `rig` (default: the rig the spec's campaign config names) is the camera rig the stack composes; a rig other than the default is
    launched with `rig:=<name>` and its profile file under `share` (default: the installed share) is what readiness observes.
    `mujoco_scene` (default: the rig's own scene) is the evaluation-only scene variant file of a rollout shard."""
    from so101_demo.act.rig_files import rig_model_files
    from so101_demo.act.rig_profile import DEFAULT_RIG
    from so101_demo.runtime.act_instance.spec import instance_rig
    from so101_teleop.unified.act_stack import ActStackLaunch

    rig = instance_rig(spec) if rig is None else rig
    rig_arguments = {}
    if rig is not DEFAULT_RIG:
        if share is None:
            from ament_index_python.packages import get_package_share_directory
            share = get_package_share_directory("so101_demo_py")
        rig_arguments = dict(rig=rig.rig, rig_profile=Path(share) / rig_model_files(rig).profile)
    return ActStackLaunch(ros2_executable=ros2,session_id=spec["simulation_session_id"],evidence_root=stack_root,
        ros_domain_id=ACT_INSTANCE_ROS_DOMAIN_ID,
        environment=dict(environment) | {"GZ_PARTITION":spec["simulation_session_id"]},mujoco_scene=mujoco_scene,**rig_arguments)


async def run_instance(spec, runtime_config, layout):
    """Run one instance from its validated spec to its stop, under `layout`; returns the process exit code.

    The caller (a launcher shell) has already checked its own facts and has set the process environment. This function checks
    what every instance needs: the fixed ROS identity in that environment, the installed code the layout names, and the
    selected GPU."""
    from ament_index_python.packages import get_package_prefix
    from so101_demo.runtime.container_campaign.retirement import NativeShardRetirement, _write
    from so101_demo.runtime.container_campaign.controller_stop import observe_act_controller_stop
    from so101_demo.runtime.container_campaign.gpu_driver import verify_selected_gpu

    if type(layout) is not InstanceLayout or layout.owned_root != Path(spec["owned_root"]):
        raise ValueError("ACT_INSTANCE_LAYOUT_MISMATCH")
    try:
        verify_instance_environment(os.environ,session_id=spec["simulation_session_id"])
    except ValueError as error:
        raise ValueError("CAMPAIGN_SHARD_ENVIRONMENT_DRIFT") from error
    mark_instance(layout.owned_root,layout.output_root)
    prefix = Path(get_package_prefix("so101_demo_py"))
    observer = prefix / "lib/so101_demo_py/act_stack_ready"
    ros2 = layout.ros2_executable
    if prefix != layout.install_prefix or not os.access(observer,os.X_OK) or not os.access(ros2,os.X_OK):
        raise ValueError("CAMPAIGN_SHARD_INSTALLED_EXECUTABLE_MISSING")
    root = layout.owned_root
    stack_root = root / "stack"
    stack_root.mkdir(mode=0o700)
    gpu = verify_selected_gpu(spec["gpu_uuid"])
    _write(root,"gpu-driver.json",canonical_json(gpu))
    from so101_demo.runtime.act_instance.spec import instance_rig
    rig = instance_rig(spec)
    from so101_demo.act import scene_variant_run
    # an evaluation-only scene variant (rollout spec only): realized and proven physics-equal into the owned root before the stack starts
    scene,_variant = scene_variant_run.prepare_shard_scene(spec,prefix/"share"/"so101_demo_py")
    launch = instance_stack_launch(spec,ros2=ros2,stack_root=stack_root,environment=os.environ,rig=rig,mujoco_scene=scene)
    ready,ready_check,stack = compose_stack(launch,observer)
    process = read_process_owner(os.getpid())
    # a rig without a neck has no neck action lane to cancel and observe
    lanes = {} if rig.has_neck else dict(goal_stop_probe=functools.partial(observe_act_controller_stop,has_neck=False))
    retirement = NativeShardRetirement(process_owner=process,launch_generation=spec["launch_generation"],
        evidence_root=root,stack=stack,
        goal_stop_budget_s=runtime_config.heartbeat_timeout_s,stack_stop_budget_s=stack.stop_timeout_s,**lanes)
    scene_switch = None
    if spec["workload_kind"] == "act_collection":
        # indoor P3: a scene list with an appearance plan gives each task its own scene; the stack is started again for it
        from so101_demo.runtime.container_campaign.scene_switch import StackSceneSwitch
        from so101_teleop.unified.pick_place_startup_issuer import InstalledActStackReadinessProbe
        scene_switch = StackSceneSwitch(stack=stack,owned_root=root,share=prefix/"share"/"so101_demo_py",
            new_ready_probe=lambda switched_launch: InstalledActStackReadinessProbe(switched_launch,observer),
            start_timeout_s=runtime_config.initializing_hard_timeout_s)
    return await serve_instance(spec,runtime_config,layout,process=process,stack=stack,ready=ready,
        retirement=retirement,ready_check=ready_check,scene_switch=scene_switch)
