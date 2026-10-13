"""Durable launch intents and actual container identities, separate from slots.

Reopening preserves termination evidence for crash cleanup; it grants no resume,
takeover, new dispatch or resource lease. Unknown launch identity remains fenced.
"""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import urllib.parse

from so101_demo.runtime.act_instance.identity import ACT_INSTANCE_ROS_DOMAIN_ID
from so101_demo.runtime.container_campaign.paths import _path
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerChildBinding, ContainerOwnerKey, ProcessOwnerKey, container_exit_proven, shard_stop_proven,
)
from so101_demo.runtime.container_campaign.retirement import read_shard_stop_evidence
from so101_demo.runtime.parallel_ipc.frames import canonical_json


#: 2: a launch record carries no ROS domain or namespace (the fixed instance identity), and the stop audit schema is 2.
REGISTRY_VERSION = 2


@dataclass(frozen=True, slots=True)
class ContainerLaunch:
    launch_id: str
    role: str
    worker_id: str | None
    wave_id: str | None
    launch_generation: int
    container_name: str
    image_digest: str
    owned_root: str
    session_id: str | None = None

    def __post_init__(self):
        try:
            for value in (self.launch_id, self.container_name):
                if type(value) is not str or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', value) is None:
                    raise ValueError('id')
            if (self.role not in ('head', 'teacher', 'shard')
                    or type(self.launch_generation) is not int or self.launch_generation <= 0
                    or type(self.image_digest) is not str
                    or re.fullmatch(r'sha256:[0-9a-f]{64}', self.image_digest) is None):
                raise ValueError('role/image/generation')
            _path(self.owned_root, directory=True)
            if self.role != 'shard':
                if any(value is not None for value in (self.worker_id, self.wave_id, self.session_id)):
                    raise ValueError('service scope')
            elif (type(self.worker_id) is not str or re.fullmatch(r'w[0-9]{2}', self.worker_id) is None
                    or type(self.wave_id) is not str or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', self.wave_id) is None
                    or type(self.session_id) is not str
                    or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', self.session_id) is None):
                raise ValueError('shard scope')
        except (OSError, ValueError, TypeError) as error:
            raise ValueError('CONTAINER_LAUNCH_RECORD_INVALID') from error


class ContainerLaunchRegistry:
    def __init__(self, path: Path, *, create=True, read_only=False):
        path = Path(path)
        if (type(create) is not bool or type(read_only) is not bool or (create and read_only)
                or not path.is_absolute() or path.parent.resolve(strict=True) != path.parent or path.is_symlink()):
            raise ValueError('LAUNCH_REGISTRY_PATH_INVALID')
        if create:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise ValueError('LAUNCH_REGISTRY_PATH_INVALID')
        self._lock = threading.RLock()
        self._read_only = read_only
        if read_only:
            # mode=ro: the file is never written, no PRAGMA is issued and no journal or wal file can be created
            self._connection = sqlite3.connect('file:'+urllib.parse.quote(str(path))+'?mode=ro', uri=True,
                                               check_same_thread=False)
        else:
            self._connection = sqlite3.connect(path, check_same_thread=False)
            self._connection.execute('PRAGMA synchronous=FULL')
        if create:
            with self._connection:
                self._connection.execute('CREATE TABLE metadata (version INTEGER, kind TEXT)')
                self._connection.execute('INSERT INTO metadata VALUES (?, ?)', (REGISTRY_VERSION, 'ACT_CONTAINER_LAUNCH_REGISTRY'))
                self._connection.execute('CREATE TABLE launches (sequence INTEGER PRIMARY KEY, launch_id TEXT UNIQUE, '
                                         'launch_json TEXT, owner_json TEXT, binding_json TEXT, exit_json TEXT)')
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        if self._connection.execute('SELECT version, kind FROM metadata').fetchall() != [
                (REGISTRY_VERSION, 'ACT_CONTAINER_LAUNCH_REGISTRY')]:
            self._connection.close()
            raise ValueError('LAUNCH_REGISTRY_SCHEMA_INVALID')

    def records(self):
        with self._lock:
            rows = self._connection.execute('SELECT launch_json, owner_json, binding_json, exit_json '
                                            'FROM launches ORDER BY sequence').fetchall()
            return tuple(dict(zip(('launch', 'owner', 'binding', 'exit_inspect'),
                                  (json.loads(value) if value is not None else None for value in row),
                                  strict=True)) for row in rows)

    def _record(self, launch_id):
        for record in self.records():
            if record['launch']['launch_id'] == launch_id:
                return record
        raise ValueError('LAUNCH_NOT_REGISTERED')

    def _writable(self):
        if self._read_only:
            raise ValueError('LAUNCH_REGISTRY_READ_ONLY')

    def register(self, launch: ContainerLaunch):
        self._writable()
        if type(launch) is not ContainerLaunch:
            raise ValueError('CONTAINER_LAUNCH_RECORD_INVALID')
        with self._lock, self._connection:
            for record in self.records():
                previous = record['launch']
                if (previous['launch_id'] == launch.launch_id
                        or previous['container_name'] == launch.container_name
                        or previous['owned_root'] == launch.owned_root):
                    raise ValueError('LAUNCH_COLLISION')
                if launch.role != 'shard' and previous['role'] == launch.role:
                    raise ValueError('LAUNCH_COLLISION: services start once per campaign')
                if launch.role == previous['role'] == 'shard':
                    if previous['session_id'] == launch.session_id:
                        raise ValueError('LAUNCH_COLLISION: session reuse')
                    if previous['worker_id'] == launch.worker_id and (
                            record['exit_inspect'] is None
                            or previous['launch_generation'] >= launch.launch_generation):
                        raise ValueError('LAUNCH_COLLISION: slot not retired')
                    if previous['worker_id'] == launch.worker_id:
                        # Cached settlement never substitutes for the original
                        # controller/native evidence when reusing a logical slot.
                        self.prove_terminated(previous['launch_id'], record['exit_inspect'])
            self._connection.execute('INSERT INTO launches (launch_id, launch_json) VALUES (?, ?)',
                                     (launch.launch_id, canonical_json(asdict(launch)).decode()))

    def bind_container(self, launch_id, owner: ContainerOwnerKey):
        self._writable()
        with self._lock, self._connection:
            record = self._record(launch_id)
            if (type(owner) is not ContainerOwnerKey or record['owner'] is not None
                    or owner.launch_generation != record['launch']['launch_generation']
                    or owner.image_digest != record['launch']['image_digest']
                    or any(item['owner'] is not None and item['owner']['container_id'] == owner.container_id
                           for item in self.records())):
                raise ValueError('LAUNCH_BINDING_MISMATCH')
            self._connection.execute('UPDATE launches SET owner_json=? WHERE launch_id=?',
                                     (canonical_json(asdict(owner)).decode(), launch_id))

    def bind_child(self, launch_id, binding: ContainerChildBinding):
        self._writable()
        with self._lock, self._connection:
            record = self._record(launch_id)
            if (type(binding) is not ContainerChildBinding or record['launch']['role'] != 'shard'
                    or record['binding'] is not None or record['owner'] != asdict(binding.container)
                    or binding.control_socket != str(Path(record['launch']['owned_root'])/'control/normal.sock')):
                raise ValueError('LAUNCH_BINDING_MISMATCH')
            self._connection.execute('UPDATE launches SET binding_json=? WHERE launch_id=?',
                                     (canonical_json(asdict(binding)).decode(), launch_id))

    def prove_terminated(self, launch_id, inspect_document):
        with self._lock, self._connection:
            record = self._record(launch_id)
            if record['owner'] is None:
                raise ValueError('LAUNCH_OWNER_UNKNOWN')
            owner = ContainerOwnerKey(**record['owner'])
            if not container_exit_proven(owner, inspect_document):
                raise ValueError('LAUNCH_STOP_UNCONFIRMED')
            if record['launch']['role'] == 'shard':
                try:
                    data = record['binding']
                    binding = ContainerChildBinding(ContainerOwnerKey(**data['container']),
                        ProcessOwnerKey(**data['process']), data['pid_namespace_inode'], data['control_socket'])
                    item = record['launch']
                    receipt = read_shard_stop_evidence(Path(item['owned_root']),
                        process_owner=binding.process, launch_generation=owner.launch_generation,
                        session_id=item['session_id'], ros_domain_id=ACT_INSTANCE_ROS_DOMAIN_ID,
                        namespace_inode=binding.pid_namespace_inode)
                    if not shard_stop_proven(binding, receipt, inspect_document):
                        raise ValueError('native stop not proven')
                except (OSError, ValueError, TypeError, KeyError) as error:
                    raise ValueError('LAUNCH_STOP_UNCONFIRMED') from error
            if record['exit_inspect'] is None:
                self._writable()    # a read-only registry re-proves a stored settlement but never stores one
                self._connection.execute('UPDATE launches SET exit_json=? WHERE launch_id=?',
                                         (canonical_json(inspect_document).decode(), launch_id))
            return True

    def all_terminated(self, inspect_container):
        with self._lock:
            records = self.records()
            if not records or any(item['owner'] is None or item['exit_inspect'] is None for item in records):
                return False
            try:
                return all(self.prove_terminated(item['launch']['launch_id'],
                           inspect_container(item['owner']['container_id'])) for item in records)
            except (OSError, ValueError, RuntimeError, KeyError):
                return False

    def close(self):
        with self._lock:
            self._connection.close()
