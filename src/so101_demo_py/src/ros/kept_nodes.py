"""The ROS nodes a process keeps between calls, and the one call that closes them.

A node that lives longer than one call (the kept readiness session of an ACT instance, the retained evidence reader of a task) is a
participant of the instance's ROS domain for as long as it lives. The inventory checks of that domain (the point initial gate's worker
node inventory, the shutdown observation) accept exactly the nodes of a worker and refuse every other one, and they stay that way.
So a holder registers here, and `release_kept_ros_nodes()` is called before each such check: the holder closes what it keeps and opens it
again when it is next used.
"""

from __future__ import annotations

import threading
import weakref

_lock = threading.Lock()
_holders: "weakref.WeakSet" = weakref.WeakSet()


def register_kept_ros_nodes(holder) -> None:
    """`holder.release()` closes its kept nodes and must leave it usable (it reopens on its next use). Held weakly."""
    with _lock:
        _holders.add(holder)


def release_kept_ros_nodes() -> int:
    """Close the kept nodes of every holder of this process; returns how many holders were asked. Never raises."""
    with _lock:
        holders = list(_holders)
    for holder in holders:
        try:
            holder.release()
        except Exception:   # noqa: BLE001 - a holder that cannot close is dropped by its own failure path; the check then judges the graph
            pass
    return len(holders)
