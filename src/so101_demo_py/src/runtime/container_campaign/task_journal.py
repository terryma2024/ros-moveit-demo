"""Host-private record of which task ran where; attribution is task_id and the registered instance only.

No hash chain and no proof protocol: a collected record freezes the task-result bytes hash and
the summary verbatim, and never judges the summary's content.
"""

import functools
import hashlib
import json
from pathlib import Path
import re
import threading
import time

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.container_campaign.paths import _path, host_task_output, task_output_path
from so101_demo.runtime.container_campaign.service_owner import _write
from so101_demo.runtime.container_campaign.task_contracts import TASK_ID_PATTERN, TaskSpec
from so101_demo.runtime.container_campaign.task_results import (
    MAX_TASK_RESULT_BYTES, _fsync_directory, read_task_result,
)
from so101_demo.runtime.inference.config import _open_regular, validate_file_ref

_INSTANCE = {'owner_root', 'worker_id', 'launch_generation', 'wave_id'}
_IDENTITY = ('task_id', 'instance_id', 'worker_id', 'launch_generation', 'wave_id', 'scene_id',
             'owner_root', 'host_output')
_ASSIGNED = {'schema_version', 'kind', *_IDENTITY, 'task', 'assigned_monotonic_s'}
ASSIGNED_KIND = 'ACT_CONTAINER_TASK_ASSIGNED'
COLLECTED_KIND = 'ACT_CONTAINER_TASK_COLLECTED'
FAILED_KIND = 'ACT_CONTAINER_TASK_FAILED'


def _locked(method):
    """Instances call from worker threads; a task directory without its record is never visible half-built."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


def read_container_task_result(owner_root, *, task_id):
    """Identity and closed shape of one task-result.json under a registered owner root; no semantic checks."""
    try:
        root = _path(owner_root, directory=True)
        output = root/'output'
        document = read_task_result(output, task_id)
        with _open_regular(task_output_path(output, task_id)/'task-result.json') as stream:
            raw = stream.read(MAX_TASK_RESULT_BYTES+1)
        if json.loads(raw) != document:
            raise ValueError('result changed')
        return dict(task_id=task_id, result=document['result'],
                    task_result_sha256=hashlib.sha256(raw).hexdigest(),
                    task_dir=str(host_task_output(root, task_id)))
    except (OSError, TypeError, ValueError) as error:
        raise ValueError('TASK_RESULT_ID_OR_FILE_INVALID') from error


def _registered_instances(instances):
    """The closed instance table: every owner root exists, none contains another."""
    if type(instances) is not dict or not instances:
        raise ValueError('TASK_JOURNAL_CONFIG_INVALID')
    registered = {}
    for instance_id, item in instances.items():
        if (type(instance_id) is not str or not instance_id or type(item) is not dict
                or set(item) != _INSTANCE or type(item['worker_id']) is not str
                or type(item['wave_id']) is not str or type(item['launch_generation']) is not int):
            raise ValueError('TASK_JOURNAL_CONFIG_INVALID')
        try:
            owner = _path(item['owner_root'], directory=True)
        except (OSError, ValueError, TypeError) as error:
            raise ValueError('TASK_JOURNAL_INSTANCE_ROOT_INVALID') from error
        registered[instance_id] = dict(item, owner_root=owner)
    return registered


def _distinct_roots(root, registered):
    owners = [item['owner_root'] for item in registered.values()]
    if (len(set(owners)) != len(owners) or any(a != b and (a.is_relative_to(b) or b.is_relative_to(a))
            for a in owners for b in owners)
            or any(root.is_relative_to(owner) or owner.is_relative_to(root) for owner in owners)):
        raise ValueError('TASK_JOURNAL_INSTANCE_ROOT_INVALID')


def _task_dir(root, task_id):
    if type(task_id) is not str or re.fullmatch(TASK_ID_PATTERN, task_id) is None:
        raise ValueError('TASK_JOURNAL_TASK_ID_INVALID')
    return root/task_id


def _read_record(path):
    try:
        return read_document(path)
    except (OSError, ValueError, TypeError) as error:
        raise ValueError('TASK_JOURNAL_RECORD_INVALID') from error


def _assigned_record(root, registered, task_id):
    path = _task_dir(root, task_id)/'assigned.json'
    if not path.exists() and not path.is_symlink():
        raise ValueError('TASK_JOURNAL_TASK_NOT_ASSIGNED')
    record = _read_record(path)
    if (set(record) != _ASSIGNED or record['kind'] != ASSIGNED_KIND or record['task_id'] != task_id
            or record['instance_id'] not in registered):
        raise ValueError('TASK_JOURNAL_RECORD_INVALID')
    return record


def _journal_records(root, registered):
    try:
        names = sorted(path.name for path in root.iterdir())
    except OSError as error:
        raise ValueError('TASK_JOURNAL_ROOT_INVALID') from error
    values = {}
    for name in names:
        terminal = None
        for kind in ('collected', 'failed'):
            path = _task_dir(root, name)/(kind+'.json')
            if path.exists() or path.is_symlink():
                if terminal is not None:
                    raise ValueError('TASK_JOURNAL_RECORD_INVALID')
                terminal = {kind: _read_record(path)}
        values[name] = dict(assigned=_assigned_record(root, registered, name),
            collected=None if terminal is None else terminal.get('collected'),
            failed=None if terminal is None else terminal.get('failed'))
    return values


def read_task_journal(root, instances):
    """Every task record under an existing journal root, read without creating, repairing or syncing anything.

    The same instance table and record rules as `ContainerTaskJournal.records`; an absent or non-canonical root is an error,
    never a directory to make. This is the reader of the independent qualification verifier."""
    root = Path(root)
    if not root.is_absolute() or '..' in root.parts:
        raise ValueError('TASK_JOURNAL_CONFIG_INVALID')
    registered = _registered_instances(instances)
    try:
        if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
            raise ValueError('journal root')
    except (OSError, ValueError) as error:
        raise ValueError('TASK_JOURNAL_ROOT_INVALID') from error
    _distinct_roots(root, registered)
    return _journal_records(root, registered)


class ContainerTaskJournal:
    def __init__(self, root, *, instances, clock=time.monotonic):
        root = Path(root)
        if not root.is_absolute() or ".." in root.parts or not callable(clock):
            raise ValueError('TASK_JOURNAL_CONFIG_INVALID')
        registered = _registered_instances(instances)
        _distinct_roots(root, registered)
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if root.is_symlink() or root.resolve(strict=True) != root:
                raise ValueError('journal root')
            _fsync_directory(root)
        except (OSError, ValueError) as error:
            raise ValueError('TASK_JOURNAL_ROOT_INVALID') from error
        self.root, self.instances, self.clock = root, registered, clock
        self._lock = threading.RLock()

    def _dir(self, task_id):
        return _task_dir(self.root, task_id)

    def _read(self, path):
        return _read_record(path)

    def _assigned(self, task_id):
        return _assigned_record(self.root, self.instances, task_id)

    def _terminal_exists(self, task_id):
        directory = self._dir(task_id)
        return any((directory/name).exists() or (directory/name).is_symlink()
                   for name in ('collected.json', 'failed.json'))

    @_locked
    def assign(self, *, instance_id, task, host_output):
        instance = self.instances.get(instance_id)
        if instance is None or type(task) is not TaskSpec:
            raise ValueError('TASK_JOURNAL_INSTANCE_UNREGISTERED')
        owner = instance['owner_root']
        try:
            expected_output = host_task_output(owner, task.task_id)
        except ValueError as error:
            raise ValueError('TASK_JOURNAL_OUTPUT_INVALID') from error
        if (task.inputs_ref.path != str(owner/'task-inputs'/(task.task_id+'.json'))
                or Path(str(host_output)) != expected_output):
            raise ValueError('TASK_JOURNAL_FOREIGN_OUTPUT')
        try:
            validate_file_ref(task.inputs_ref.model_dump())
            document = read_document(Path(task.inputs_ref.path))
            scene_id = document['scene_id']
            if (document['task_id'] != task.task_id or type(scene_id) is not str or not scene_id
                    or any(document[name] != instance[name] or type(document[name]) is not type(instance[name])
                           for name in ('worker_id', 'launch_generation', 'wave_id'))):
                raise ValueError('input identity')
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ValueError('TASK_JOURNAL_INPUT_INVALID') from error
        if any(item['assigned']['scene_id'] == scene_id for item in self.records().values()):
            raise ValueError('TASK_JOURNAL_SCENE_DUPLICATE')
        directory = self._dir(task.task_id)
        try:
            directory.mkdir(mode=0o700)
            _fsync_directory(self.root)
        except OSError as error:
            raise ValueError('TASK_JOURNAL_TASK_DUPLICATE') from error
        record = dict(schema_version=1, kind=ASSIGNED_KIND, task_id=task.task_id, instance_id=instance_id,
            worker_id=instance['worker_id'], launch_generation=instance['launch_generation'],
            wave_id=instance['wave_id'], scene_id=scene_id, owner_root=str(owner),
            host_output=str(expected_output), task=task.model_dump(),
            assigned_monotonic_s=float(self.clock()))
        _write(directory/'assigned.json', record)
        return record

    @_locked
    def collect(self, *, task_id, result):
        assigned = self._assigned(task_id)
        if self._terminal_exists(task_id):
            raise ValueError('TASK_JOURNAL_ALREADY_TERMINAL')
        if (type(result) is not dict or set(result) != {'task_id', 'result', 'task_result_sha256', 'task_dir'}
                or result['task_id'] != task_id or assigned['task']['task_id'] != task_id
                or type(result['result']) is not dict or result['task_dir'] != assigned['host_output']
                or type(result['task_result_sha256']) is not str
                or re.fullmatch(r'[0-9a-f]{64}', result['task_result_sha256']) is None):
            raise ValueError('TASK_JOURNAL_RESULT_MISMATCH')
        record = {name: assigned[name] for name in _IDENTITY}
        record.update(schema_version=1, kind=COLLECTED_KIND, task_result_sha256=result['task_result_sha256'],
                      result=result['result'], task=assigned['task'],
                      assigned_monotonic_s=assigned['assigned_monotonic_s'], collected_monotonic_s=float(self.clock()))
        _write(self._dir(task_id)/'collected.json', record)
        return record

    @_locked
    def fail(self, *, task_id, reason):
        assigned = self._assigned(task_id)
        directory = self._dir(task_id)
        if (directory/'collected.json').exists():
            raise ValueError('TASK_JOURNAL_ALREADY_COLLECTED')
        if type(reason) is not str or not reason:
            raise ValueError('TASK_JOURNAL_REASON_INVALID')
        if (directory/'failed.json').exists():
            return self._read(directory/'failed.json')
        record = {name: assigned[name] for name in _IDENTITY}
        record.update(schema_version=1, kind=FAILED_KIND, reason=reason[:300],
                      failed_monotonic_s=float(self.clock()))
        _write(directory/'failed.json', record)
        return record

    @_locked
    def records(self):
        return _journal_records(self.root, self.instances)
