"""The constants, the private directory chain and the isolated ROS node of one worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import threading

_RESET_JOINTS = (0.0,) * 6


_ACTIVE_GOAL_STATES = {1, 2, 3}


_NODE_DIAGNOSTIC_LIMIT = 16


_NODE_DIAGNOSTIC_NAME_LIMIT = 96


_EXACT_TF_DISCOVERY_TIMEOUT_S = 5.0


def _mkdir_private_chain(root, target):
    """Create and verify each target directory beneath a private root."""

    root = Path(root).absolute()
    target = Path(target).absolute()
    try:
        parts = target.relative_to(root).parts
    except ValueError as error:
        raise RuntimeError("BROKER_INPUT_DIRECTORY_ESCAPE") from error
    current = root
    for part in (None, *parts):
        if part is not None:
            current = current / part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
        info = current.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or current.is_symlink()
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise RuntimeError("BROKER_INPUT_DIRECTORY_IDENTITY")
    return target


def _worker_node_diagnostic(observed, expected):
    """Return bounded deterministic detail without changing exact equality."""

    normalized = tuple(
        node if isinstance(node, str) else f"<non-string:{type(node).__name__}>"
        for node in observed
    )
    counts = {}
    for node in normalized:
        counts[node] = counts.get(node, 0) + 1
    observed_set = set(normalized)
    groups = {
        "missing": sorted(set(expected) - observed_set),
        "unexpected": sorted(observed_set - set(expected)),
        "duplicates": sorted(node for node, count in counts.items() if count > 1),
    }
    truncated = any(
        len(values) > _NODE_DIAGNOSTIC_LIMIT
        or any(len(value) > _NODE_DIAGNOSTIC_NAME_LIMIT for value in values)
        for values in groups.values()
    )
    bounded = {
        name: [
            value[:_NODE_DIAGNOSTIC_NAME_LIMIT]
            for value in values[:_NODE_DIAGNOSTIC_LIMIT]
        ]
        for name, values in groups.items()
    }
    bounded["truncated"] = truncated
    payload = json.dumps(bounded, sort_keys=True, separators=(",", ":"))
    while len(payload.encode()) > 320:
        for name in ("unexpected", "duplicates", "missing"):
            if bounded[name]:
                bounded[name].pop()
                bounded["truncated"] = True
                break
        else:  # pragma: no cover - fixed JSON keys alone are well below the cap
            raise RuntimeError("NODE_DIAGNOSTIC_BOUND")
        payload = json.dumps(bounded, sort_keys=True, separators=(",", ":"))
    return payload


class _IsolatedRosNode:
    def __init__(self, node, context, executor):
        self.node = node
        self.context = context
        self.executor = executor
        self._closed = False
        self._spin_lock = threading.Lock()
        self._background_stop = threading.Event()
        self._background_thread = None

    def spin_once(self, *, timeout_sec):
        if self._closed:
            raise RuntimeError("ISOLATED_ROS_NODE_CLOSED")
        with self._spin_lock:
            if self._closed:
                raise RuntimeError("ISOLATED_ROS_NODE_CLOSED")
            self.executor.spin_once(timeout_sec=timeout_sec)

    def start_background_spin(self):
        if self._closed:
            raise RuntimeError("ISOLATED_ROS_NODE_CLOSED")
        if self._background_thread is not None:
            return

        def spin():
            while not self._background_stop.is_set():
                self.spin_once(timeout_sec=0.02)
                self._background_stop.wait(0.001)

        self._background_thread = threading.Thread(
            target=spin,
            name=f"{self.node.get_name()}-executor",
            daemon=True,
        )
        self._background_thread.start()

    def close(self):
        if self._closed:
            return
        self._background_stop.set()
        if self._background_thread is not None:
            self._background_thread.join(timeout=1.0)
        self._closed = True
        try:
            self.executor.remove_node(self.node)
        finally:
            try:
                self.executor.shutdown()
            finally:
                try:
                    self.node.destroy_node()
                finally:
                    self.context.shutdown()


def _open_isolated_ros_node(rclpy, name, **node_options):
    """Create a node whose init/shutdown cannot touch another runtime context."""

    from rclpy.executors import SingleThreadedExecutor

    context = rclpy.context.Context()
    rclpy.init(context=context)
    try:
        node = rclpy.create_node(name, context=context, **node_options)
    except Exception:
        context.shutdown()
        raise
    try:
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
    except Exception:
        node.destroy_node()
        context.shutdown()
        raise
    return _IsolatedRosNode(node, context, executor)


def _ready_failure_message(completed) -> str:
    """One bounded line naming why `motion_stack_ready` refused: its failure code, phase and unmet dependency."""
    text = (completed.stdout or "").strip().splitlines()
    for line in reversed(text):
        try:
            document = json.loads(line)
        except ValueError:
            continue
        if isinstance(document, dict) and "failure_code" in document:
            evidence = document.get("evidence") if isinstance(document.get("evidence"), dict) else {}
            parts = [f"READY_PROBE_FAILED code={document.get('failure_code')} phase={document.get('phase')}"]
            if evidence.get("dependency"):
                parts.append(f"dependency={evidence['dependency']}")
            return " ".join(parts)[:300]
    return f"READY_PROBE_FAILED rc={completed.returncode} " + ((completed.stderr or "").strip()[-200:] or "no output")
