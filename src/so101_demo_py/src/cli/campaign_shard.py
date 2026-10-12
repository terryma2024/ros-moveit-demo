"""Private native shard entry for no-motion readiness and fixed ACT collection."""

import argparse
import asyncio
from dataclasses import asdict
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
import time

from so101_demo.runtime.container_campaign.paths import _path
from so101_demo.runtime.container_campaign.process_identity import read_process_owner
from so101_demo.runtime.container_campaign.ros_namespace import validate_container_namespace
from so101_demo.runtime.inference.config import _open_regular, validate_file_ref, calibration_runtime_hash
from so101_demo.runtime.parallel_ipc.frames import _pairs, canonical_json


_FIELDS = {"schema_version", "kind", "workload_kind", "campaign_id", "worker_id", "launch_generation",
    "execution_generation", "runtime_id", "service_epoch", "service_token", "owned_root", "ros_namespace",
    "ros_domain_id", "simulation_session_id", "gpu_uuid", "controlled_runtime"}
_COLLECTION_FIELDS={'business_identity','parallel_runtime','campaign_config','wave_id','deadline_monotonic_s'}
_BUSINESS_FIELDS={'manifest_sha256','runtime_config_sha256','collection_config_sha256','contact_policy_fingerprint'}


def load_spec(path):
    from so101_demo.cli.mujoco_batch.request import _load_runtime_config

    try:
        with _open_regular(path) as stream:
            raw = stream.read(1024*1024+1)
        if len(raw)>1024*1024:
            raise ValueError("size")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")))
        if type(document) is not dict:raise ValueError('shape/kind')
        collection=document.get('workload_kind')=='act_collection'
        expected=_FIELDS|_COLLECTION_FIELDS if collection else _FIELDS
        if (set(document) != expected
                or type(document["schema_version"]) is not int or document["schema_version"] != 1
                or document["kind"] != "ACT_CONTAINER_SHARD"
                or document["workload_kind"] not in ("no_motion_readiness",'act_collection')):
            raise ValueError("shape/kind")
        for name in ("campaign_id", "worker_id", "runtime_id", "service_epoch", "simulation_session_id"):
            if type(document[name]) is not str or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", document[name]) is None:
                raise ValueError("identity")
        for name in ("launch_generation", "execution_generation"):
            if type(document[name]) is not int or document[name]<=0:
                raise ValueError("generation")
        if (type(document["service_token"]) is not str or re.fullmatch(r"[0-9a-f]{64}", document["service_token"]) is None
                or type(document["gpu_uuid"]) is not str or re.fullmatch(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",document["gpu_uuid"]) is None):
            raise ValueError("token/device")
        root = _path(document["owned_root"], directory=True)
        if root.name != f"g{document['launch_generation']}" or root.parent.name != document["worker_id"]:
            raise ValueError("private root scope")
        validate_container_namespace(document["ros_namespace"])
        runtime_path = validate_file_ref(document["controlled_runtime"])
        if collection:
            from so101_demo.runtime.inference.config import load_campaign_config
            identity=document['business_identity']
            if (type(identity) is not dict or set(identity)!=_BUSINESS_FIELDS
                    or any(type(value) is not str or re.fullmatch(r'[0-9a-f]{64}',value) is None
                           for value in identity.values())
                    or identity['runtime_config_sha256']!=document['controlled_runtime']['sha256']
                    or document['wave_id']!=root.parent.parent.name
                    or re.fullmatch(r'wave-[0-9]+',document['wave_id']) is None
                    or type(document['deadline_monotonic_s']) not in (int,float)
                    or not math.isfinite(document['deadline_monotonic_s'])
                    or document['deadline_monotonic_s']<=time.monotonic()):
                raise ValueError('collection identity')
            campaign=load_campaign_config(validate_file_ref(document['campaign_config']),roles=('teacher',),
                expected_sha256=document['campaign_config']['sha256'])
            if (campaign['controlled_runtime']!=document['controlled_runtime']
                    or campaign['gpu_uuid']!=document['gpu_uuid']):
                raise ValueError('collection campaign drift')
            runtime = _load_runtime_config(validate_file_ref(document['parallel_runtime']))
        else:
            runtime = _load_runtime_config(runtime_path)
        if (type(document["ros_domain_id"]) is not int or document["ros_domain_id"] not in runtime.ros_domain_ids
                or calibration_runtime_hash(runtime_path) != document["controlled_runtime"]["sha256"]):
            raise ValueError("runtime/domain drift")
        return document, runtime
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError("CAMPAIGN_SHARD_SPEC_INVALID") from error


def _refuse_motion(_task):
    raise ValueError("SHARD_READINESS_HAS_NO_MOTION_PORT")


def shard_builder(spec,*,stack,output_root,ready_check=None):
    """The executor's task builder for this workload; readiness shards have no motion port.

    Collection tasks gate on `ready_check`, a repeatable fresh observation of the borrowed stack. The stack's own
    `ready_probe` is the single-use start probe, already consumed by the shard start, so it is never the gate."""
    if spec['workload_kind']=='no_motion_readiness':return _refuse_motion
    if spec['workload_kind']=='act_collection':
        from so101_demo.runtime.container_campaign.task_builder import build_collection_task
        if not callable(ready_check):raise ValueError('CAMPAIGN_SHARD_READY_CHECK_REQUIRED')
        return functools.partial(build_collection_task,stack=stack,shard_spec=spec,output_root=output_root,
            ready_check=ready_check)
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


async def serve_shard(spec, runtime_config, *, process, stack, ready, retirement, socket_root=Path("/act/control"),
                      output_root=None, install_signals=True, ready_check=None):
    """Serve the Host's task operations until the executor has stopped; return the process exit code."""
    from so101_demo.runtime.container_campaign import task_executor
    from so101_demo.runtime.container_campaign.retirement import _write
    from so101_teleop.unified.child_runtime import ContainerChildIdentity, ContainerChildIpcServer
    from so101_teleop.unified.contracts import OwnerKey

    root = Path(spec["owned_root"])
    if output_root is None:
        output_root = Path("/act/output") if spec["workload_kind"] == "act_collection" else root / "tmp"
    start_aware = StackStartAwareRetirement(retirement)
    # Host status polling bounds owner silence (heartbeat_timeout_s); the frozen worker recovery bound covers
    # helper stop and native retirement.
    executor = task_executor.ContainerTaskExecutor(instance_id=instance_id_for(spec),
        builder=shard_builder(spec,stack=stack,output_root=output_root,ready_check=ready_check),
        retirement=start_aware,output_root=output_root,
        owner_timeout_s=runtime_config.heartbeat_timeout_s,stop_timeout_s=runtime_config.worker_recovery_timeout_s,
        retire_timeout_s=runtime_config.worker_recovery_timeout_s,ready=False)
    identity = ContainerChildIdentity(runtime_id=spec["runtime_id"],act_campaign_id=spec["campaign_id"],
        act_worker_id=spec["worker_id"],act_generation=spec["execution_generation"],normal_queue_limit=2)
    server = ContainerChildIpcServer(identity,socket_root=socket_root,owner=OwnerKey(**asdict(process)),
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
                    _write(root,"runtime-ready.json",canonical_json(dict(schema_version=1,kind="ACT_SHARD_RUNTIME_READY",
                        generation=spec["launch_generation"],process_owner=asdict(process),ros_namespace=spec["ros_namespace"],
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
            await asyncio.gather(*terminations,return_exceptions=True)
            await server.close()
    return 0 if executor.cleanup_confirmed and not failed else 1


def compose_stack(launch, observer):
    """The shard's stack owner and its probes: returns `(start_probe, ready_check, stack)`.

    The start probe is the single-use `InstalledActStackReadinessProbe` the stack owner consumes at start (its
    `readiness_bytes` are the startup evidence). `ready_check` is the task gates' separate repeatable check, which builds
    a fresh probe from the same launch and observer on every call and never touches the start probe."""
    from so101_teleop.unified.act_stack import ActStackProcessOwner
    from so101_teleop.unified.act_stack_probes import (
        RepeatableActStackReadyProbe, RepeatableActStackStopProbe, RosGraphClearProbe)
    from so101_teleop.unified.pick_place_startup_issuer import InstalledActStackReadinessProbe

    ready = InstalledActStackReadinessProbe(launch,observer)
    ready_check = RepeatableActStackReadyProbe(launch,observer)
    stack = ActStackProcessOwner(launch,ready_probe=ready,
        stop_probe=RepeatableActStackStopProbe(launch,observer),graph_clear_probe=RosGraphClearProbe(launch))
    return ready,ready_check,stack


async def run_shard(spec, runtime_config):
    if os.getpid() != 1 or sys.executable != "/act/venv/bin/python":
        raise ValueError("CAMPAIGN_SHARD_PRIVATE_CONTAINER_REQUIRED")
    from ament_index_python.packages import get_package_prefix
    from so101_demo.runtime.container_campaign.retirement import NativeShardRetirement, _write
    from so101_demo.runtime.container_campaign.stack_launch import ContainerActStackLaunch
    from so101_demo.runtime.container_campaign.gpu_driver import verify_selected_gpu

    if (os.environ.get("ROS_DOMAIN_ID") != str(spec["ros_domain_id"])
            or os.environ.get("ROS_NAMESPACE") != spec["ros_namespace"]
            or os.environ.get("MUJOCO_GL") != "egl"):
        raise ValueError("CAMPAIGN_SHARD_ENVIRONMENT_DRIFT")
    os.environ['SO101_ACT_CONTAINER_NAMESPACE']=spec['ros_namespace']
    os.environ['SO101_ACT_CONTAINER_OWNED_ROOT']=spec['owned_root']
    prefix = Path(get_package_prefix("so101_demo_py"))
    observer = prefix / "lib/so101_demo_py/act_stack_ready"
    ros2 = prefix / "bin/ros2"
    if prefix != Path("/act/install") or not os.access(observer,os.X_OK) or not os.access(ros2,os.X_OK):
        raise ValueError("CAMPAIGN_SHARD_INSTALLED_EXECUTABLE_MISSING")
    root = Path(spec["owned_root"])
    stack_root = root / "stack"
    stack_root.mkdir(mode=0o700)
    gpu = verify_selected_gpu(spec["gpu_uuid"])
    _write(root,"gpu-driver.json",canonical_json(gpu))
    environment = dict(os.environ) | {"GZ_PARTITION":spec["simulation_session_id"]}
    launch = ContainerActStackLaunch(ros2_executable=ros2,session_id=spec["simulation_session_id"],
        evidence_root=stack_root,ros_domain_id=spec["ros_domain_id"],environment=environment,
        ros_namespace=spec["ros_namespace"],readiness_timeout_s=runtime_config.initializing_hard_timeout_s)
    ready,ready_check,stack = compose_stack(launch,observer)
    process = read_process_owner(os.getpid())
    retirement = NativeShardRetirement(process_owner=process,launch_generation=spec["launch_generation"],
        evidence_root=root,stack=stack,ros_namespace=spec["ros_namespace"],
        goal_stop_budget_s=runtime_config.heartbeat_timeout_s,stack_stop_budget_s=stack.stop_timeout_s)
    return await serve_shard(spec,runtime_config,process=process,stack=stack,ready=ready,retirement=retirement,
        ready_check=ready_check)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec",type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        spec,runtime = load_spec(args.spec)
    except (OSError,ValueError,RuntimeError) as error:
        print(str(error),file=sys.stderr)
        return 2
    try:
        return asyncio.run(run_shard(spec,runtime))
    except (OSError,ValueError,RuntimeError) as error:
        print(f"CAMPAIGN_SHARD_FAILED: {error}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
