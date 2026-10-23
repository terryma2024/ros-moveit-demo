"""Host ownership of a native ACT instance by process identity, the counterpart of `ContainerBridgeProcessOwner`.

A container instance is identified by Docker and proves its PID namespace differs from the Host's. A native instance is a Host
process that leads a process group of its own, so it is identified by its kernel process identity and its group, and it
proves the opposite about itself: it reports the Host's own PID namespace. The ready record is checked field for field like the
container's; what changes is the socket paths it names (the instance's own control directory) and these identity checks:

* the reporting pid is the registered leader, and it leads the registered process group (so it belongs to the owned group);
* the process identity the instance reports about itself is what the Host reads about that pid, the same five fields;
* the PID namespace it reports is the Host's, which is what makes the later group and descendant scans meaningful.
"""

from __future__ import annotations

import os
from pathlib import Path

from .child_runtime import NORMAL_SOCKET_NAME, SAFETY_SOCKET_NAME
from .contracts import MutationError

_READY_FIELDS = {"schema_version", "kind", "generation", "process_owner", "pid_namespace_inode", "service_epoch",
                 "runtime_id", "campaign_id", "worker_id", "execution_generation", "normal_socket", "safety_socket"}


class NativeBridgeProcessOwner:
    def __init__(self, *, native_owner, control_socket_root, runtime_id, service_epoch, campaign_id, worker_id,
                 execution_generation, session_id, read_process_owner=None, host_namespace=None):
        from so101_demo.runtime.container_campaign.process_identity import NativeOwnerKey, read_process_owner as read

        root = Path(control_socket_root)
        if (type(native_owner) is not NativeOwnerKey or not root.is_absolute() or root.resolve(strict=True) != root
                or any(type(value) is not str or not value for value in (
                    runtime_id, service_epoch, campaign_id, worker_id, session_id))
                or type(execution_generation) is not int or execution_generation <= 0):
            raise MutationError("NATIVE_BRIDGE_CONFIG_INVALID")
        self.native_owner, self.control_socket_root = native_owner, root
        self.runtime_id, self.service_epoch = runtime_id, service_epoch
        self.campaign_id, self.worker_id = campaign_id, worker_id
        self.execution_generation, self.session_id = execution_generation, session_id
        self._read_process_owner = read_process_owner or read
        self._host_namespace = host_namespace or (lambda: os.stat("/proc/self/ns/pid").st_ino)
        self.binding = None

    def accept_ready(self, document):
        from so101_demo.runtime.container_campaign.process_identity import ContainerChildBinding, ProcessOwnerKey

        owner = self.native_owner
        expected = dict(schema_version=1, kind="container_child_ready", generation=owner.launch_generation,
            service_epoch=self.service_epoch, runtime_id=self.runtime_id, campaign_id=self.campaign_id,
            worker_id=self.worker_id, execution_generation=self.execution_generation,
            normal_socket=str(self.control_socket_root / NORMAL_SOCKET_NAME),
            safety_socket=str(self.control_socket_root / SAFETY_SOCKET_NAME))
        try:
            if (type(document) is not dict or set(document) != _READY_FIELDS or self.binding is not None
                    or any(type(document[name]) is not int for name in (
                        "schema_version", "generation", "execution_generation", "pid_namespace_inode"))
                    or any(document[name] != value for name, value in expected.items())):
                raise ValueError("ready binding")
            process = ProcessOwnerKey(**document["process_owner"])
            # the reporter is the registered leader and leads the registered group: it belongs to the owned process group
            if process != owner.process_key():
                raise ValueError("process identity")
            if self._read_process_owner(process.pid) != process:
                raise ValueError("process identity")
            namespace = self._host_namespace()
            if type(namespace) is not int or namespace <= 0 or namespace != document["pid_namespace_inode"]:
                raise ValueError("PID namespace")
            self.binding = ContainerChildBinding(owner, process, namespace,
                                                str(self.control_socket_root / NORMAL_SOCKET_NAME))
            return self.binding
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as error:
            raise MutationError("NATIVE_READY_IDENTITY_INVALID") from error

    def ready(self):
        """Whether the registered leader is still the same live process the binding names."""
        if self.binding is None:
            return False
        try:
            return (self._read_process_owner(self.native_owner.pid) == self.native_owner.process_key()
                    and self._host_namespace() == self.binding.pid_namespace_inode)
        except (OSError, RuntimeError, ValueError, KeyError, MutationError):
            return False
