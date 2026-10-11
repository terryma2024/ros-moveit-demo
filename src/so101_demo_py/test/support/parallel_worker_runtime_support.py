"""Fakes and helpers shared by the parallel worker runtime tests."""

from dataclasses import replace
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from so101_demo.parallel_batch.resource_allocation.models import WorkerResources


def _resources(root: Path, worker: str, slot: int, domain: int) -> WorkerResources:
    worker_root = root / worker
    paths = {
        "render": worker_root / "render",
        "ros_home": worker_root / "ros-home",
        "ros_log": worker_root / "ros-log",
        "tmp": worker_root / "tmp",
        "socket": worker_root / "socket",
    }
    for path in paths.values():
        path.mkdir(parents=True)
    return WorkerResources(
        worker_id=worker,
        slot_index=slot,
        generation=1,
        ros_domain_id=domain,
        simulation_port="not_applicable",
        bridge_port="not_applicable",
        gz_partition="not_applicable",
        session_id=f"session-{worker}",
        controller_namespace=f"/{worker}",
        render_backend="egl",
        render_context_id=f"egl-{worker}",
        render_context_namespace=paths["render"],
        virtual_display="not_applicable",
        ros_home=paths["ros_home"],
        ros_log_dir=paths["ros_log"],
        temp_dir=paths["tmp"],
        socket_namespace=paths["socket"],
        socket_path=paths["socket"] / "worker.sock",
        worker_root=worker_root,
        environment={
            "ROS_DOMAIN_ID": str(domain),
            "ROS_HOME": str(paths["ros_home"]),
            "ROS_LOG_DIR": str(paths["ros_log"]),
            "TMPDIR": str(paths["tmp"]),
        },
    )


class _Child:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        del timeout
        self.returncode = 0
        return 0


class _ProcessGroup:
    def __init__(self, events=None, on_shutdown=None) -> None:
        self.specs = []
        self.environments = []
        self.shutdown_calls = 0
        self.events = events
        self.on_shutdown = on_shutdown
        self.inherited_descriptors = []

    @property
    def manifest(self):
        from so101_demo.runtime.task_stack import OwnedProcessManifest

        return OwnedProcessManifest(tuple())

    def start(self, spec, *, environment=None, pass_fds=()):
        self.specs.append(spec)
        self.environments.append(dict(environment or {}))
        self.inherited_descriptors.append(pass_fds)
        if self.events is not None:
            self.events.append(("start", spec.role))
        return SimpleNamespace(
            role=spec.role,
            pid=100 + len(self.specs),
            pgid=100 + len(self.specs),
        )

    def shutdown(self):
        self.shutdown_calls += 1
        if self.on_shutdown is not None:
            self.on_shutdown()

    def stop(self, child):
        if self.events is not None:
            self.events.append(("stop", child.pid))


class _HandoffProcessGroup(_ProcessGroup):
    """Keeps a duplicate of each inherited hand-off end, as the real child would hold it."""

    def __init__(self, events=None, on_shutdown=None, *, keep_children=True) -> None:
        super().__init__(events, on_shutdown)
        self.child_sockets = []
        self.keep_children = keep_children

    def start(self, spec, *, environment=None, pass_fds=()):
        import os
        import socket

        if self.keep_children:
            for fd in pass_fds:
                self.child_sockets.append(socket.socket(fileno=os.dup(fd)))
        return super().start(spec, environment=environment, pass_fds=pass_fds)


def _lease(
    worker="worker-1", *, generation=1, point="P01", attempt="attempt-1"
):
    return SimpleNamespace(
        lease_issued_monotonic_s=10.0,
        lease_deadline_monotonic_s=310.0,
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id=worker,
        worker_generation=generation,
        point_id=point,
        attempt_id=attempt,
        lease_generation=1,
    )


def _write_capture(path, source_stamp, source_stamp_ns=12_000_000_000):
    from so101_demo.runtime.parallel_worker_parts.process_tree import SourceStampedCapture
    from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix != ".npy":
        path.write_bytes(b"rgb")
        return SourceStampedCapture(path, source_stamp)
    buffer = io.BytesIO()
    np.save(buffer, np.zeros((4, 5, 3), dtype=np.uint8), allow_pickle=False)
    payload = buffer.getvalue()
    path.write_bytes(payload)
    path.chmod(0o400)
    return InferenceSnapshotReceipt(
        path,
        source_stamp,
        source_stamp_ns=source_stamp_ns,
        source_frame_id="task_camera_frame",
        shape=(4, 5, 3),
        input_sha256=hashlib.sha256(payload).hexdigest(),
        simulation_session_id="session-worker-1",
        source_clock="ros_sim",
    )


def _write_numeric(root, source_stamp):
    from so101_demo.runtime.parallel_worker_parts.receipts import NumericEvidenceReceipt

    root.mkdir(parents=True, exist_ok=True)
    paths = tuple(root / name for name in ("depth.json", "tf.json", "physical.json"))
    for path in paths:
        path.write_text("{}")
    return NumericEvidenceReceipt(*paths, source_stamp)


def _plan_receipt(states, completion=25.0):
    from so101_demo.runtime.parallel_worker_parts.receipts import (
        PlanPrefixReceipt,
        PlanSegmentReceipt,
    )

    terminals = [f"terminal-{index}" for index in range(len(states))]
    return PlanPrefixReceipt(
        tuple(
            PlanSegmentReceipt(
                state,
                "initial" if index == 0 else terminals[index - 1],
                terminals[index],
                f"plan-{index}",
                f"before-{index}",
                f"after-{index}",
            )
            for index, state in enumerate(states)
        ),
        completion,
    )


def _replacement(resources: WorkerResources) -> WorkerResources:
    generation = resources.generation + 1
    session_id = f"session-{resources.worker_id}-generation-{generation}"
    environment = dict(resources.environment)
    environment["SO101_WORKER_GENERATION"] = str(generation)
    environment["SO101_SESSION_ID"] = session_id
    return replace(
        resources,
        generation=generation,
        session_id=session_id,
        environment=environment,
    )
