"""Host observation of a native ACT instance's exit: its leader, its process group, its descendants and the Host ROS graph.

A container instance cannot leave anything behind: its PID namespace and network namespace die with it. A native instance
shares the Host's, so "it exited" has to be read from the Host. The facts below are all read from the operating system (`/proc`
through the platform identity reader) and, for the graph, from a ROS 2 probe on the instance's fixed domain at the time of
the call; none of them is inferred from a signal that was sent.

    leader_state       the registered leader is gone: no process at its pid, an unreaped zombie, or a different process
                       that reuses the pid; never "unknown", never merely "signalled"
    group_members      live members of the instance's process group (the instance leads a group of its own)
    marker_survivors   live processes of this user whose environment carries this instance's marker
                       (`SO101_ACT_INSTANCE_ROOT=<owned root>`); the ROS stack and the recorder run in sessions of their
                       own, so only the marker finds them after an abnormal instance exit
    graph_clear        `ros2 node list` on the instance's fixed domain is empty (admission keeps every other participant off
                       that domain while a native instance is admitted)
"""

import os
from pathlib import Path
import time

from so101_demo.runtime.container_campaign.process_identity import NATIVE_EXIT_KIND, NativeOwnerKey
from so101_teleop.owned_group import terminate_group
from so101_teleop.process_identity import ProcessAbsent, ProcessIdentityError, group_members, read_identity

#: A process whose state or environment cannot be read is reported with this pid-like marker so that the proof fails closed.
UNREADABLE = -1


def _read_leader_state(owner):
    try:
        identity = read_identity(owner.pid)
    except ProcessAbsent:
        return "absent"
    except ProcessIdentityError:
        return "unknown"
    if identity.start_marker != owner.started_ticks:
        return "replaced"
    if not identity.live:
        return "zombie"             # a zombie's command line is gone; its start marker is what names it
    if identity.argv_sha256 != owner.argv_sha256 or identity.pgid != owner.pgid:
        return "unknown"
    return "live"


def leader_state(owner, *, attempts=5, pause_s=.02):
    """`live`, `absent`, `zombie`, `replaced` (a different process now has the pid) or `unknown` (not provable).

    A process that is exiting is briefly unreadable; `unknown` is read again a few times before it is reported."""
    if type(owner) is not NativeOwnerKey:
        raise ValueError("NATIVE_OWNER_KEY_REQUIRED")
    for attempt in range(attempts):
        state = _read_leader_state(owner)
        if state != "unknown" or attempt == attempts-1:
            return state
        time.sleep(pause_s)


def group_survivors(pgid):
    """Pids of live (non-zombie) members of the process group; `[UNREADABLE]` when the group cannot be read."""
    try:
        members = group_members(pgid)
    except ProcessIdentityError:
        return [UNREADABLE]
    return sorted(pid for pid, state in members.items() if state != "Z")


def _carries_marker(entry, wanted, started_ticks, *, attempts=4, pause_s=.05):
    """Whether the process carries the marker: True, False, or None when it is not readable and cannot be ruled out.

    A process that is starting or exiting is briefly unreadable (its memory map is being replaced or torn down), so an
    unreadable environment is read again before it is reported. A process that started before the instance did cannot be
    its descendant and is never reported, however unreadable (the session manager, `sshd`)."""
    for attempt in range(attempts):
        try:
            stat_fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if stat_fields[0] == "Z":
                return False
            return wanted in (entry / "environ").read_bytes().split(b"\x00")
        except (FileNotFoundError, ProcessLookupError):
            return False        # exited while being scanned
        except (OSError, IndexError, ValueError):
            try:
                if int((entry / "stat").read_text().rsplit(")", 1)[1].split()[19]) < started_ticks:
                    return False
            except (FileNotFoundError, ProcessLookupError):
                return False
            except (OSError, IndexError, ValueError):
                pass
            if attempt < attempts-1:
                time.sleep(pause_s)
    return None


def marker_survivors(owned_root, *, started_ticks, proc=Path("/proc"), uid=None, exclude=()):
    """Live processes of this user whose initial environment names `owned_root` as their instance root.

    An unreadable process that cannot be ruled out is reported as `UNREADABLE`, so that the proof fails closed."""
    from so101_demo.runtime.act_instance.identity import INSTANCE_ROOT_ENV

    wanted = (INSTANCE_ROOT_ENV + "=" + str(owned_root)).encode()
    uid = os.getuid() if uid is None else uid
    found = []
    for entry in sorted(Path(proc).iterdir(), key=lambda item: item.name):
        if not entry.name.isdigit() or int(entry.name) in exclude:
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            found.append(UNREADABLE)
            continue
        carries = _carries_marker(entry, wanted, started_ticks)
        if carries is None:
            found.append(UNREADABLE)
        elif carries:
            found.append(int(entry.name))
    return found


def observe_native_exit(owner, owned_root, *, graph_probe, proc=Path("/proc")):
    """One fresh observation of the registered native instance's exit, as the document `native_exit_proven` judges."""
    if type(owner) is not NativeOwnerKey or not callable(graph_probe):
        raise ValueError("NATIVE_OBSERVATION_CONFIG_INVALID")
    try:
        graph_clear = graph_probe() is True
    except Exception:  # noqa: BLE001 - an unreadable graph is not a clear one
        graph_clear = False
    return dict(schema_version=1, kind=NATIVE_EXIT_KIND, pid=owner.pid, pgid=owner.pgid,
        started_ticks=owner.started_ticks, argv_sha256=owner.argv_sha256, owned_root=str(owned_root),
        leader_state=leader_state(owner), group_members=group_survivors(owner.pgid),
        marker_survivors=marker_survivors(owned_root, started_ticks=owner.started_ticks, proc=proc),
        graph_clear=graph_clear)


def stop_descendants(owner, owned_root, *, timeout_s, proc=Path("/proc")):
    """Terminate (SIGTERM, then SIGKILL) what an exited native instance left behind, and return the groups it signalled.

    Only processes that are provably the instance's are touched: the live members of its own process group, and the process
    groups every live member of which carries this instance's marker. A group with a foreign member is reported by the next
    observation as a survivor and left alone."""
    signalled = []
    pgids = []
    if group_survivors(owner.pgid) not in ([], [UNREADABLE]):
        pgids.append(owner.pgid)
    marked = [pid for pid in marker_survivors(owned_root, started_ticks=owner.started_ticks, proc=proc)
              if pid != UNREADABLE]
    marked_groups = {}
    for pid in marked:
        try:
            marked_groups.setdefault(read_identity(pid).pgid, set()).add(pid)
        except ProcessIdentityError:
            continue
    for pgid, pids in sorted(marked_groups.items()):
        try:
            members = {member for member, state in group_members(pgid).items() if state != "Z"}
        except ProcessIdentityError:
            continue
        if members <= pids and pgid != os.getpgrp():
            pgids.append(pgid)
    for pgid in dict.fromkeys(pgids):
        receipt = terminate_group(pgid=pgid, timeout_s=timeout_s)
        signalled.append(dict(pgid=pgid, kill_sent=receipt.kill_sent, survivors=list(receipt.survivors)))
    return signalled
