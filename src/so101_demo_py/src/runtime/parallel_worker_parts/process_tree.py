"""Source stamped captures and the worker owned process tree."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

from so101_demo.runtime.task_stack import (
    OwnedProcessIdentity,
    OwnedProcessManifest,
)

_READY_REQUIREMENTS = (
    "controllers",
    "move_group",
    "joint_states",
    "planning_scene",
)


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _finite_timestamp(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class SourceStampedCapture:
    path: Path
    source_stamp_monotonic_s: float
    source_stamp_ns: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(
            self,
            "source_stamp_monotonic_s",
            _finite_timestamp(
                "capture source stamp", self.source_stamp_monotonic_s
            ),
        )
        if self.source_stamp_ns is not None and (
            type(self.source_stamp_ns) is not int or self.source_stamp_ns <= 0
        ):
            raise ValueError("capture ROS source stamp must be positive")


class WorkerOwnedProcessTree:
    """Keep nested runtime children inside the supervisor-owned Worker PGID."""

    def __init__(
        self, *, popen=subprocess.Popen, signal_process=os.kill,
        identity_probe=None, interrupt_timeout_s=20.0, terminate_timeout_s=5.0,
        manifest_path: Path | None = None,
    ):
        from so101_demo.runtime.task_stack import _linux_process_identity

        self._popen = popen
        self._signal_process = signal_process
        self._identity_probe = identity_probe or _linux_process_identity
        self._interrupt_timeout_s = interrupt_timeout_s
        self._terminate_timeout_s = terminate_timeout_s
        self._lock = threading.RLock()
        self._children = []
        self._manifest_path = None if manifest_path is None else Path(manifest_path)
        self._write_manifest()

    def _write_manifest(self):
        with self._lock:
            self._write_manifest_locked()

    def _write_manifest_locked(self):
        if self._manifest_path is None:
            return
        document = {
            "schema_version": 1,
            "processes": [
                {
                    "role": identity.role,
                    "pid": identity.pid,
                    "pgid": identity.pgid,
                    "cmdline": list(identity.cmdline),
                    "start_time_ticks": identity.start_time_ticks,
                }
                for identity, _child in self._children
            ],
        }
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._manifest_path.with_name(
            f".{self._manifest_path.name}.{os.getpid()}.tmp"
        )
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self._manifest_path)
        parent = os.open(
            self._manifest_path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            os.fsync(parent)
        finally:
            os.close(parent)

    @property
    def manifest(self):
        with self._lock:
            return OwnedProcessManifest(
                tuple(identity for identity, _child in self._children)
            )

    def start(self, spec, *, environment=None, pass_fds=()):
        if (not isinstance(pass_fds, tuple)
                or any(type(fd) is not int or fd < 0 for fd in pass_fds)
                or len(set(pass_fds)) != len(pass_fds)):
            raise ValueError("WORKER_INHERITED_FDS_INVALID")
        try:
            for fd in pass_fds:
                os.fstat(fd)
        except OSError as error:
            raise ValueError("WORKER_INHERITED_FDS_INVALID") from error
        with self._lock:
            return self._start_locked(spec, environment=environment, pass_fds=pass_fds)

    def _starting_identity(self, child):
        """Allow the exact child a brief fork/exec window to expose /proc."""

        deadline = time.monotonic() + 0.5
        while True:
            try:
                return self._identity_probe(int(child.pid))
            except (OSError, RuntimeError) as error:
                incomplete = str(error) == (
                    f"incomplete process identity for PID {child.pid}"
                )
                if (
                    not isinstance(error, OSError)
                    and not incomplete
                ) or child.poll() is not None or time.monotonic() >= deadline:
                    raise
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def _start_locked(self, spec, *, environment=None, pass_fds=()):
        if any(identity.role == spec.role for identity, _child in self._children):
            raise RuntimeError(f"owned process role already exists: {spec.role}")
        argv = list(spec.argv)
        from so101_demo.runtime.qualified_commands import (
            qualified_prefix_from_env,
            resolve_role_command,
        )

        prefix = qualified_prefix_from_env()
        if prefix is not None:
            # In a qualified run no child is found by PATH or comes from outside the install
            argv = list(resolve_role_command(argv, prefix=prefix))
        child = self._popen(
            argv, start_new_session=False,
            env=None if environment is None else dict(environment),
            **({"pass_fds": pass_fds} if pass_fds else {}),
        )
        identity = None
        try:
            pgid, cmdline, started = self._starting_identity(child)
            if pgid != os.getpgrp() or not cmdline or not started:
                raise RuntimeError("nested child escaped the Worker process group")
            identity = OwnedProcessIdentity(
                spec.role, int(child.pid), int(pgid), tuple(cmdline), int(started)
            )
            self._children.append((identity, child))
            self._write_manifest()
            return identity
        except Exception:
            if identity is not None:
                self._children = [
                    item for item in self._children if item[1] is not child
                ]
            self._reap_failed_start(child)
            try:
                self._write_manifest()
            except Exception:
                pass
            raise

    def _reap_failed_start(self, child):
        """Terminate only the exact Popen child and always reap it."""

        if child.poll() is not None:
            try:
                child.wait(timeout=0)
            except Exception:
                pass
            return
        terminate = getattr(child, "terminate", None)
        if callable(terminate):
            try:
                terminate()
            except ProcessLookupError:
                pass
        try:
            child.wait(timeout=self._terminate_timeout_s)
            return
        except subprocess.TimeoutExpired:
            pass
        kill = getattr(child, "kill", None)
        if callable(kill):
            try:
                kill()
            except ProcessLookupError:
                pass
        child.wait(timeout=self._terminate_timeout_s)

    def _matches(self, identity):
        try:
            pgid, cmdline, started = self._identity_probe(identity.pid)
        except (OSError, ProcessLookupError):
            return False
        return (pgid, tuple(cmdline), started) == (
            identity.pgid, identity.cmdline, identity.start_time_ticks
        )

    def shutdown(self):
        with self._lock:
            self._shutdown_locked()

    def stop(self, expected):
        """Retire one exact owned child without signalling its Worker siblings."""
        with self._lock:
            matches = [item for item in self._children if item[0] == expected]
            if not matches:
                return True
            identity, child = matches[0]
            if child.poll() is None:
                if not self._matches(identity):
                    raise RuntimeError(f"{identity.role}: identity changed")
                try:
                    self._signal_process(identity.pid, signal.SIGINT)
                    child.wait(timeout=self._interrupt_timeout_s)
                except subprocess.TimeoutExpired:
                    if not self._matches(identity):
                        raise RuntimeError(f"{identity.role}: identity changed")
                    self._signal_process(identity.pid, signal.SIGTERM)
                    child.wait(timeout=self._terminate_timeout_s)
                except ProcessLookupError:
                    pass
            self._children = [
                item for item in self._children if item[0] != identity
            ]
            self._write_manifest_locked()
            return True

    def _owned_child(self, expected):
        for identity, child in self._children:
            if identity == expected:
                return identity, child
        return None

    def exit_code(self, expected):
        """The exact owned child's return code, or None while it still runs (also None for an unknown child)."""
        with self._lock:
            owned = self._owned_child(expected)
            return None if owned is None else owned[1].poll()

    def wait_exit(self, expected, timeout_s):
        """Wait at most `timeout_s` for the exact owned child to exit on its own; its return code, or None if it did not."""
        with self._lock:
            owned = self._owned_child(expected)
        if owned is None:
            return None
        try:
            return owned[1].wait(timeout=max(0.0, float(timeout_s)))
        except subprocess.TimeoutExpired:
            return None

    def terminate(self, expected, grace_s):
        """SIGTERM the exact owned child (never its siblings), allow `grace_s`, then SIGKILL; its return code."""
        with self._lock:
            owned = self._owned_child(expected)
            if owned is None:
                return None
            identity, child = owned
            if child.poll() is None:
                if not self._matches(identity):
                    raise RuntimeError(f"{identity.role}: identity changed")
                try:
                    self._signal_process(identity.pid, signal.SIGTERM)
                    child.wait(timeout=float(grace_s))
                except subprocess.TimeoutExpired:
                    if not self._matches(identity):
                        raise RuntimeError(f"{identity.role}: identity changed")
                    self._signal_process(identity.pid, signal.SIGKILL)
                    child.wait(timeout=self._terminate_timeout_s)
                except ProcessLookupError:
                    pass
            return child.poll()

    def _shutdown_locked(self):
        failures = []
        for identity, child in reversed(self._children):
            if child.poll() is not None:
                continue
            if not self._matches(identity):
                failures.append(f"{identity.role}: identity changed")
                continue
            try:
                self._signal_process(identity.pid, signal.SIGINT)
                child.wait(timeout=self._interrupt_timeout_s)
            except subprocess.TimeoutExpired:
                if not self._matches(identity):
                    failures.append(f"{identity.role}: identity changed")
                    continue
                try:
                    self._signal_process(identity.pid, signal.SIGTERM)
                    child.wait(timeout=self._terminate_timeout_s)
                except Exception as error:
                    failures.append(f"{identity.role}: {error}")
            except ProcessLookupError:
                pass
            except Exception as error:
                failures.append(f"{identity.role}: {error}")
        self._children = [
            (identity, child) for identity, child in self._children
            if child.poll() is None
        ]
        self._write_manifest()
        if failures:
            raise RuntimeError("; ".join(failures))
