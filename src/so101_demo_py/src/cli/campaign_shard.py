"""Private campaign shard entry, currently provisioning the no-motion image gate.

Collection/measurement/live handlers are added at their owning integration
boundaries. Unknown workload kinds fail before ROS; they never use a generic
or diagnostic Teacher as a substitute for the campaign's actual execution port.
"""

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import signal
import sys

from so101_demo.runtime.container_campaign.paths import _path
from so101_demo.runtime.container_campaign.process_identity import read_process_owner
from so101_demo.runtime.container_campaign.ros_namespace import validate_container_namespace
from so101_demo.runtime.inference.config import _open_regular, validate_file_ref, calibration_runtime_hash
from so101_demo.runtime.parallel_ipc.frames import _pairs, canonical_json


_FIELDS = {"schema_version", "kind", "workload_kind", "campaign_id", "worker_id", "launch_generation",
    "execution_generation", "runtime_id", "service_epoch", "service_token", "owned_root", "ros_namespace",
    "ros_domain_id", "simulation_session_id", "gpu_uuid", "controlled_runtime"}


def load_spec(path):
    from so101_demo.cli.mujoco_batch.request import _load_runtime_config

    try:
        with _open_regular(path) as stream:
            raw = stream.read(1024*1024+1)
        if len(raw)>1024*1024:
            raise ValueError("size")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")))
        if (type(document) is not dict or set(document) != _FIELDS
                or type(document["schema_version"]) is not int or document["schema_version"] != 1
                or document["kind"] != "ACT_CONTAINER_SHARD"
                or document["workload_kind"] != "no_motion_readiness"):
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
        runtime = _load_runtime_config(runtime_path)
        if (type(document["ros_domain_id"]) is not int or document["ros_domain_id"] not in runtime.ros_domain_ids
                or calibration_runtime_hash(runtime_path) != document["controlled_runtime"]["sha256"]):
            raise ValueError("runtime/domain drift")
        return document, runtime
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError("CAMPAIGN_SHARD_SPEC_INVALID") from error


class NoMotionReadinessDriver:
    """The image gate never forwards a goal; loss still retires its real stack."""
    def __init__(self, retirement):
        self.retirement = retirement
        self.start_task = None
        self.stop_receipt = None

    async def submit(self, *args):
        raise ValueError("SHARD_READINESS_HAS_NO_MOTION_PORT")

    async def cancel(self, *args):
        raise ValueError("SHARD_READINESS_HAS_NO_MOTION_PORT")

    async def terminal(self, *args):
        raise ValueError("SHARD_READINESS_HAS_NO_MOTION_PORT")

    async def stop_act(self, reason):
        if self.start_task is not None:
            try:
                await asyncio.shield(self.start_task)
            except Exception:
                pass
        self.stop_receipt = await self.retirement.retire(fenced=True)
        return all(self.stop_receipt[name] for name in (
            "goals_stopped", "controllers_stopped", "ros_children_exited", "ros_graph_empty")) and not self.stop_receipt["forced"]


async def run_shard(spec, runtime_config):
    if os.getpid() != 1 or sys.executable != "/act/venv/bin/python":
        raise ValueError("CAMPAIGN_SHARD_PRIVATE_CONTAINER_REQUIRED")
    from ament_index_python.packages import get_package_prefix
    from so101_teleop.unified.act_stack import ActStackProcessOwner
    from so101_teleop.unified.act_stack_probes import RepeatableActStackStopProbe, RosGraphClearProbe
    from so101_teleop.unified.child_runtime import ChildRuntime, ContainerChildIpcServer
    from so101_teleop.unified.contracts import OwnerKey
    from so101_teleop.unified.pick_place_startup_issuer import InstalledActStackReadinessProbe
    from so101_teleop.unified.ros_child import container_watchdog
    from so101_demo.runtime.container_campaign.heartbeat import OwnerHeartbeatMonitor
    from so101_demo.runtime.container_campaign.retirement import NativeShardRetirement, _write
    from so101_demo.runtime.container_campaign.stack_launch import ContainerActStackLaunch
    from so101_demo.runtime.container_campaign.gpu_driver import verify_selected_gpu

    if (os.environ.get("ROS_DOMAIN_ID") != str(spec["ros_domain_id"])
            or os.environ.get("ROS_NAMESPACE") != spec["ros_namespace"]
            or os.environ.get("MUJOCO_GL") != "egl"):
        raise ValueError("CAMPAIGN_SHARD_ENVIRONMENT_DRIFT")
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
    ready = InstalledActStackReadinessProbe(launch,observer)
    stack = ActStackProcessOwner(launch,ready_probe=ready,
        stop_probe=RepeatableActStackStopProbe(launch,observer),graph_clear_probe=RosGraphClearProbe(launch))
    process = read_process_owner(os.getpid())
    retirement = NativeShardRetirement(process_owner=process,launch_generation=spec["launch_generation"],
        evidence_root=root,stack=stack,ros_namespace=spec["ros_namespace"],
        goal_stop_budget_s=runtime_config.heartbeat_timeout_s,stack_stop_budget_s=stack.stop_timeout_s)
    driver = NoMotionReadinessDriver(retirement)
    owner = OwnerKey(**asdict(process))
    runtime = ChildRuntime(driver,owner=owner,service_epoch=spec["service_epoch"],runtime_id=spec["runtime_id"],
        normal_queue_limit=2,act_campaign_id=spec["campaign_id"],act_worker_id=spec["worker_id"],
        act_generation=spec["execution_generation"])
    monitor = OwnerHeartbeatMonitor(generation=spec["launch_generation"],
        timeout_ns=int(runtime_config.heartbeat_timeout_s*1e9))
    server = ContainerChildIpcServer(runtime,socket_root=Path("/act/control"),owner=owner,
        service_epoch=spec["service_epoch"],service_token=spec["service_token"],
        max_bytes=runtime_config.broker_max_frame_bytes,owner_monitor=monitor,process_owner=process)
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):
        loop.add_signal_handler(sig,stopping.set)
    watchdog = None
    okay = False
    try:
        await server.start()
        watchdog = asyncio.create_task(container_watchdog(runtime,owner_monitor=monitor))
        driver.start_task = asyncio.create_task(stack.start(timeout_s=runtime_config.initializing_hard_timeout_s))
        await asyncio.shield(driver.start_task)
        if runtime.web_dead or monitor.expired:
            raise ValueError("CAMPAIGN_SHARD_OWNER_LOST_DURING_START")
        _write(root,"runtime-ready.json",canonical_json(dict(schema_version=1,kind="ACT_SHARD_RUNTIME_READY",
            generation=spec["launch_generation"],process_owner=asdict(process),ros_namespace=spec["ros_namespace"],
            readiness_sha256=__import__('hashlib').sha256(ready.readiness_bytes).hexdigest())))
        _write(root,"stack-readiness.json",ready.readiness_bytes)
        wait_signal = asyncio.create_task(stopping.wait())
        wait_owner = asyncio.create_task(runtime.web_dead_latch.wait())
        try:
            await asyncio.wait([wait_signal,wait_owner],return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (wait_signal,wait_owner):
                task.cancel()
            await asyncio.gather(wait_signal,wait_owner,return_exceptions=True)
        okay = True
    finally:
        try:
            await runtime.mark_web_dead("SHARD_RETIREMENT")
            okay = await driver.stop_act("SHARD_RETIREMENT") and okay
        finally:
            if watchdog is not None:
                watchdog.cancel()
                await asyncio.gather(watchdog,return_exceptions=True)
            await server.close()
    return 0 if okay else 1


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
