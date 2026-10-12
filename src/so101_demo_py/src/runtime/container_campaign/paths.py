"""Derive private new-run directories and explicit least-privilege mounts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from so101_demo.runtime.inference.config import _open_regular


@dataclass(frozen=True)
class RoleMount:
    source: Path
    target: Path
    read_only: bool
    purpose: str


def _path(value, *, directory=False):
    path = Path(value)
    if (not path.is_absolute() or ".." in path.parts or path.resolve(strict=True) != path
            or (directory and not path.is_dir()) or (not directory and not (path.is_file() or path.is_dir()))):
        raise ValueError("canonical existing path required")
    return path


def validate_registered_evidence_root(config_root, payload_root, *, registration):
    """The unified entry calls this once with its trusted root registration."""
    try:
        if type(registration) is not dict or set(registration) != {"path", "uid", "gid"}:
            raise ValueError("registration shape")
        if type(config_root) is not str or config_root != payload_root or config_root != registration["path"]:
            raise ValueError("root mismatch")
        root = _path(config_root, directory=True)
        metadata = root.stat()
        if (type(registration["uid"]) is not int or type(registration["gid"]) is not int
                or (metadata.st_uid, metadata.st_gid) != (registration["uid"], registration["gid"])):
            raise ValueError("root owner")
    except (OSError, ValueError, TypeError) as error:
        raise ValueError("REGISTERED_EVIDENCE_ROOT_INVALID") from error
    return root


def make_campaign_paths(root, run_id):
    root = _path(root, directory=True)
    if type(run_id) is not str or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", run_id) is None:
        raise ValueError("CAMPAIGN_RUN_ID_INVALID")
    run = root / run_id
    try:
        run.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ValueError("CAMPAIGN_RUN_EXISTS") from error
    paths = {"run": run, "host": run / "host", "measurement": run / "measurement",
             "live": run / "live", "services": {role: run / "services" / role for role in ("head", "teacher")},
             "socket_roots": {role: run / "ipc" / role for role in ("head", "teacher")}}
    for parent in (run / "services", run / "ipc", paths["host"], paths["measurement"], paths["live"]):
        parent.mkdir(mode=0o700)
    for group in (paths["services"], paths["socket_roots"]):
        for path in group.values():
            path.mkdir(mode=0o700)
    document = {"root": str(root), "run_id": run_id, "uid": os.getuid(), "gid": os.getgid()}
    fd = os.open(run / ".campaign-layout.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(document, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(run, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return paths


def _layout(owned_root):
    for run in owned_root.parents:
        marker = run / ".campaign-layout.json"
        if marker.exists():
            with _open_regular(marker) as stream:
                document = json.load(stream)
            if (set(document) != {"root", "run_id", "uid", "gid"}
                    or run != Path(document["root"]) / document["run_id"]
                    or (document["uid"], document["gid"]) != (os.getuid(), os.getgid())):
                raise ValueError("layout identity")
            return run
    raise ValueError("unknown owned directory")


def _owned_role(role, owned, run):
    if role in ("head", "teacher"):
        if owned != run / "services" / role:
            raise ValueError("service private directory")
        return
    if role != "shard":
        raise ValueError("unknown role")
    parts = owned.relative_to(run).parts
    if (len(parts) not in (3, 4) or re.fullmatch(r"g[1-9][0-9]*", parts[-1]) is None
            or re.fullmatch(r"w[0-9]{2}", parts[-2]) is None):
        raise ValueError("shard private directory")
    if len(parts) == 3:
        if re.fullmatch(r"wave-[0-9]+", parts[0]) is None and parts[0] != "measurement":
            raise ValueError("wave or measurement path")
    elif parts[0] != "live" or re.fullmatch(r"case-[a-zA-Z0-9_-]+", parts[1]) is None:
        raise ValueError("live case path")


def build_role_mounts(role, *, owned_root, approved_inputs, socket_roots, config_paths,
                      task_output_root=None):
    """Produce launch mounts; artifact contents/path contracts remain unchanged.

    This checks local mount provenance only. Campaign resource authorization
    remains at the unified entry and is never repeated in inference services.
    """
    try:
        owned = _path(owned_root, directory=True)
        run = _layout(owned)
        _owned_role(role, owned, run)
        if type(approved_inputs) is not tuple or type(config_paths) is not tuple:
            raise ValueError("input list")
        mounts = [RoleMount(owned, owned, False, "evidence" if role == "shard" else "service_logs")]
        if task_output_root is not None:
            output = _path(task_output_root, directory=True)
            if role != 'shard' or output != owned/'output':
                raise ValueError('task output owner')
            mounts.append(RoleMount(output, Path('/act/output'), False, 'task_output'))
        for source in (*approved_inputs, *config_paths):
            source = _path(source)
            # Do not expose the root, another shard, or any Host journal to a role.
            private = False
            if source.is_relative_to(run) and source != run:
                first = source.relative_to(run).parts[0]
                private = first in {"host", "services", "ipc", "measurement", "live", ".campaign-layout.json"}
                private = private or re.fullmatch(r"wave-[0-9]+", first) is not None
            if (source == run or private or run.is_relative_to(source)
                    or source.is_relative_to("/act/source") or source.is_relative_to("/act/install")):
                raise ValueError("broad, Host-owned, or source override input")
            mounts.append(RoleMount(source, source, True, "input"))
        for service_role in (("head", "teacher") if role == "shard" else (role,)):
            source = _path(socket_roots[service_role], directory=True)
            if source != run / "ipc" / service_role:
                raise ValueError("service socket owner")
            target = Path("/act/ipc") / service_role if role == "shard" else Path("/act/ipc")
            mounts.append(RoleMount(source, target, role == "shard", "ipc"))
        if role == "shard":
            control = _path(socket_roots["control"], directory=True)
            if control != owned / "control":
                raise ValueError("control socket owner")
            mounts.append(RoleMount(control, Path("/act/control"), False, "control"))
        targets = [mount.target for mount in mounts]
        if len(targets) != len(set(targets)):
            raise ValueError("duplicate mount target")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError("ROLE_MOUNT_INVALID") from error
    return tuple(mounts)


def task_output_path(output_root, task_id):
    """Locate one task without accepting a path from the task request."""
    from .task_contracts import TASK_ID_PATTERN

    try:
        root = _path(output_root, directory=True)
        if type(task_id) is not str or re.fullmatch(TASK_ID_PATTERN, task_id) is None:
            raise ValueError('task id')
        path = root/'tasks'/task_id
        if path.resolve() != path or path.is_symlink():
            raise ValueError('task path')
        return path
    except (OSError, TypeError, ValueError) as error:
        raise ValueError('TASK_OUTPUT_PATH_INVALID') from error


def host_task_output(owner_root, task_id):
    return task_output_path(_path(owner_root, directory=True)/'output', task_id)
