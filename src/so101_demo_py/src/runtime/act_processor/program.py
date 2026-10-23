"""The ACT processor program: the one implementation of a processor's life, for a container and for a native process.

`run_processor(spec, runtime_config, layout)` serves the Host's four one-way operations (start, assign_task, get_status, terminate)
on the control socket with the same task executor, task messages and result files as a shard, and runs each assigned task
through `processing.ProcessingExecution`. There is no ROS graph, no simulator and no GPU: the only runtime is the offline
processor child. The container shell (`cli/campaign_processor.py`) checks its own facts before it calls here; a native owner builds
its own `ProcessorLayout`.

Files in the processor's owned root: `processor-ready.json` (written once the control server accepts calls) and
`instance-exit.json` (the same closed exit record a shard writes, so the Host reads both alike).
"""

import asyncio
from dataclasses import asdict
import functools
import os
from pathlib import Path
import signal

from so101_demo.runtime.act_processor.layout import ProcessorLayout
from so101_demo.runtime.act_processor.processing import ProcessingExecution, load_processing_task
from so101_demo.runtime.act_processor.spec import processor_launch_id
from so101_demo.runtime.container_campaign.process_identity import read_process_owner
from so101_demo.runtime.parallel_ipc.frames import canonical_json

READY_NAME = "processor-ready.json"
READY_KIND = "ACT_PROCESSOR_RUNTIME_READY"


class NoRosRetirement:
    """A processor owns no goal, controller, ROS child or graph, so there is nothing to stop; the proofs are vacuous and said so."""

    async def retire(self, *, fenced):
        return dict(goals_stopped=True, controllers_stopped=True, ros_children_exited=True, ros_graph_empty=True,
                    forced=False, no_ros_graph=True)


def processor_builder(spec, *, layout, runner_factory=None, grader=None, memo_check=None):
    """The executor's task builder: validates the assignment, then returns the execution (run on a worker thread)."""
    def build(task):
        from so101_demo.runtime.container_campaign.task_results import reserve_task_output

        processing = load_processing_task(task, owned_root=layout.owned_root, processing_root=spec["processing_root"],
                                          processor_id=spec["processor_id"], launch_generation=spec["launch_generation"])
        if task.deadline_monotonic_s > spec["deadline_monotonic_s"]:
            raise ValueError("PROCESSING_TASK_DEADLINE_INVALID")
        reserve_task_output(layout.output_root, task.task_id)
        extra = {name: value for name, value in (("grader", grader), ("memo_check", memo_check)) if value is not None}
        return ProcessingExecution(task=processing, python=layout.python,
                                   runner=None if runner_factory is None else runner_factory(), **extra)
    return build


async def serve_processor(spec, runtime_config, layout, *, process, builder=None, install_signals=True):
    """Serve the Host's task operations until the executor has stopped; return the process exit code."""
    from so101_demo.runtime.container_campaign import task_executor
    from so101_demo.runtime.container_campaign.retirement import _write
    from so101_teleop.unified.child_runtime import ContainerChildIdentity, ContainerChildIpcServer
    from so101_teleop.unified.contracts import OwnerKey

    root = Path(spec["owned_root"])
    if type(layout) is not ProcessorLayout or layout.owned_root != root:
        raise ValueError("ACT_PROCESSOR_LAYOUT_MISMATCH")
    executor = task_executor.ContainerTaskExecutor(
        instance_id=processor_launch_id(spec), builder=builder or processor_builder(spec, layout=layout),
        retirement=NoRosRetirement(), output_root=layout.output_root,
        owner_timeout_s=runtime_config.heartbeat_timeout_s, stop_timeout_s=runtime_config.worker_recovery_timeout_s,
        retire_timeout_s=runtime_config.worker_recovery_timeout_s, ready=True)
    identity = ContainerChildIdentity(runtime_id=spec["runtime_id"], act_campaign_id=spec["campaign_id"],
        act_worker_id=spec["processor_id"], act_generation=spec["execution_generation"], normal_queue_limit=2)
    server = ContainerChildIpcServer(identity, socket_root=layout.control_root, owner=OwnerKey(**asdict(process)),
        service_epoch=spec["service_epoch"], service_token=spec["service_token"],
        max_bytes=runtime_config.broker_max_frame_bytes, task_port=executor, generation=spec["launch_generation"],
        close_timeout_s=runtime_config.heartbeat_timeout_s, process_owner=process)
    loop = asyncio.get_running_loop()
    terminations = []
    signals = (signal.SIGTERM, signal.SIGINT) if install_signals else ()
    for sig in signals:
        loop.add_signal_handler(sig, lambda: terminations.append(asyncio.ensure_future(executor.terminate("SIGTERM"))))
    failed = False
    try:
        await server.start()
        _write(root, READY_NAME, canonical_json(dict(schema_version=1, kind=READY_KIND,
            generation=spec["launch_generation"], process_owner=asdict(process))))
        await executor.wait_stopped()
    except Exception as error:
        failed = True
        await executor.terminate(f"PROCESSOR_START_FAILED: {type(error).__name__}")
    finally:
        try:
            await executor.terminate("PROCESSOR_SERVE_ENDED")
            status = await executor.get_status()
            _write(root, "instance-exit.json", canonical_json(dict(schema_version=1, kind="ACT_SHARD_INSTANCE_EXIT",
                state=status.state, fault_reason=status.fault_reason,
                task=None if status.task is None else status.task.model_dump(),
                cleanup_confirmed=executor.cleanup_confirmed, cleanup_errors=executor.cleanup_errors)))
        finally:
            for sig in signals:
                loop.remove_signal_handler(sig)
            await asyncio.gather(*terminations, return_exceptions=True)
            await server.close()
    return 0 if executor.cleanup_confirmed and not failed else 1


async def run_processor(spec, runtime_config, layout):
    """Run one processor from its validated spec to its stop under `layout`; the launcher has set up its own facts."""
    if type(layout) is not ProcessorLayout or layout.owned_root != Path(spec["owned_root"]):
        raise ValueError("ACT_PROCESSOR_LAYOUT_MISMATCH")
    if not os.access(layout.python, os.X_OK):
        raise ValueError("CAMPAIGN_PROCESSOR_INTERPRETER_MISSING")
    for directory in (layout.output_root, layout.control_root):
        directory.mkdir(mode=0o700, exist_ok=True)
    return await serve_processor(spec, runtime_config, layout, process=read_process_owner(os.getpid()))
