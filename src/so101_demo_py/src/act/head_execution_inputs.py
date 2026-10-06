"""Strict, closed execution inputs for one file-protocol Head stage-one run.

The document is the only authority a stage-one run may start from. It names the
exact operation, the development scope, the run identity, the evidence root, a
previously nonexistent run root, the freeze receipt and every controlled input
by absolute path plus SHA-256. Parsing performs read-only verification and
refuses anything else: unknown fields, promoted scopes, rewritten bytes, symlinks,
relative or escaped paths, a reused run root and any attempt to smuggle legacy
phase flags into the new entry.

Nothing here starts ROS, MuJoCo, a detector or a stack; it only reads bytes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path

SCHEMA_VERSION = 1
KIND = 'head_execution_inputs'
OPERATION = 'HEAD_FILE_STAGE1_DEVELOPMENT'
DEVELOPMENT_SCOPE = 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
REQUIRED_CUDA_DEVICE = 'cuda:0'

DOCUMENT_REFUSED = 'EXECUTION_INPUTS_REFUSED'
UNSEALED_REFUSED = 'EXECUTION_INPUTS_UNSEALED'
SCOPE_REFUSED = 'EXECUTION_SCOPE_REFUSED'
ROOT_REFUSED = 'EXECUTION_RUN_ROOT_REFUSED'

#: every controlled input a stage-one run must seal, and nothing else
REF_NAMES = (
    'weights', 'frozen_c', 'camera_geometry', 'development_config', 'local_policy',
    'controller_config', 'mujoco_plugin', 'scene', 'urdf', 'safety_inputs',
    'binding', 'report',
)
REQUIRED_REF_NAMES = frozenset(REF_NAMES) - {'binding', 'report'}
RUN_DECLARATION_FIELDS = {'stop_declaration', 'seal_expectation', 'log_capture',
                          'fault_stop_probes'}
DECLARATION_FIELDS = RUN_DECLARATION_FIELDS | {'snapshot_root'}
STOP_TRIGGERS = ('OPERATOR_STOP', 'FAULT_PRIMARY', 'DEADLINE', 'BUDGET_EXHAUSTED')
TOP_LEVEL_FIELDS = {
    'schema_version', 'kind', 'operation', 'execution_scope', 'run', 'evidence_root',
    'run_root', 'freeze_receipt', 'refs', 'development_pose', 'resources', 'ros',
    'stop_declaration', 'seal_expectation', 'log_capture', 'fault_stop_probes',
    'snapshot_root',
}
REQUIRED_DOCUMENT_FIELDS = TOP_LEVEL_FIELDS - DECLARATION_FIELDS
RUN_FIELDS = {'run_id', 'session_id', 'epoch', 'generation'}
POSE_FIELDS = {'arm_rad', 'neck_rad', 'cup_xyz'}
RESOURCE_FIELDS = {'cuda_device', 'allow_cpu_fallback', 'cpu_allocation'}
ROS_FIELDS = {'domain_id', 'environment'}
REF_FIELDS = {'path', 'sha256'}

TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class HeadExecutionInputsRefused(ValueError):
    """A refused execution input, carrying the exact code the entry records."""

    def __init__(self, code: str, detail: str = '') -> None:
        self.code = code
        self.detail = detail
        super().__init__(f'{code}: {detail}' if detail else code)


def _refuse(code: str, detail: str):
    raise HeadExecutionInputsRefused(code, detail)


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _plain_path(where: str, declared, *, code: str = UNSEALED_REFUSED) -> Path:
    """A declared path must be absolute, plain and free of traversal."""

    if type(declared) is not str or not declared:
        _refuse(code, f'{where}: no path')
    path = Path(declared)
    if not path.is_absolute() or '..' in path.parts:
        _refuse(code, f'{where}: {declared} is not a plain absolute path')
    return path


def _declared_bytes(where: str, declared, expected_sha) -> bytes:
    """Read one sealed regular file without following a symlink, or refuse."""

    if type(expected_sha) is not str or SHA256.fullmatch(expected_sha) is None:
        _refuse(UNSEALED_REFUSED, f'{where}: no declared sha256')
    path = _plain_path(where, declared)
    if path.is_symlink():
        _refuse(UNSEALED_REFUSED, f'{where}: {path} is a symlink')
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                _refuse(UNSEALED_REFUSED, f'{where}: {path} is not a regular file')
            data = stream.read()
    except OSError as error:
        _refuse(UNSEALED_REFUSED,
                f'{where}: {path} is absent or unreadable ({error.strerror or error})')
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha:
        _refuse(UNSEALED_REFUSED, f'{where}: {path} has sha256 {actual}, declared {expected_sha}')
    return data


def _ref_block(where: str, value) -> dict:
    if not isinstance(value, Mapping) or set(value) != REF_FIELDS:
        _refuse(UNSEALED_REFUSED, f'{where}: expected exactly path and sha256')
    return {'path': value['path'], 'sha256': value['sha256']}


def _plain_directory(where: str, declared, *, code: str) -> Path:
    path = _plain_path(where, declared, code=code)
    if path.is_symlink() or not path.is_dir():
        _refuse(code, f'{where}: {path} is not a plain directory')
    return path


def _validate_declarations(document):
    """The CP-HFP-075 run declarations: closed values, validated whenever they are declared."""

    stop = document['stop_declaration']
    if (type(stop) is not dict or set(stop) != {'trigger', 'teardown_timeout_s'}
            or stop['trigger'] not in STOP_TRIGGERS
            or type(stop['teardown_timeout_s']) not in (int, float)
            or not math.isfinite(stop['teardown_timeout_s']) or stop['teardown_timeout_s'] <= 0):
        _refuse(DOCUMENT_REFUSED, 'stop_declaration must name a closed trigger and a positive teardown')
    seal = document['seal_expectation']
    if (type(seal) is not dict or set(seal) != {'completion', 'artifacts'}
            or type(seal['completion']) is not bool or type(seal['artifacts']) is not list
            or any(type(name) is not str or not name for name in seal['artifacts'])):
        _refuse(DOCUMENT_REFUSED, 'seal_expectation must declare completion and artifact names')
    capture = document['log_capture']
    if (type(capture) is not dict or set(capture) != {'stdout', 'stderr'}
            or any(type(value) is not str or not value for value in capture.values())):
        _refuse(DOCUMENT_REFUSED, 'log_capture must name stdout and stderr destinations')
    probes = document['fault_stop_probes']
    if type(probes) is not list or any(type(entry) is not str or not entry for entry in probes):
        _refuse(DOCUMENT_REFUSED, 'fault_stop_probes must be a list of probe names')


def _parse(path):
    """Parse and verify one execution-input document, or refuse it whole."""

    try:
        declared = os.fspath(path)
    except TypeError:
        _refuse(UNSEALED_REFUSED, 'execution_inputs: no path')
    document_path = _plain_path('execution_inputs', declared)
    raw = _read_plain('execution_inputs', document_path)
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _refuse(DOCUMENT_REFUSED, f'execution_inputs: not a JSON document ({error})')
    if (type(document) is not dict or not REQUIRED_DOCUMENT_FIELDS <= set(document)
            or not set(document) <= TOP_LEVEL_FIELDS):
        extra = sorted(set(document) - TOP_LEVEL_FIELDS) if type(document) is dict else []
        missing = sorted(TOP_LEVEL_FIELDS - set(document)) if type(document) is dict else []
        _refuse(DOCUMENT_REFUSED,
                f'execution_inputs: closed schema mismatch (extra={extra}, missing={missing})')
    if (type(document['schema_version']) is not int or document['schema_version'] != SCHEMA_VERSION
            or document['kind'] != KIND or document['operation'] != OPERATION):
        _refuse(DOCUMENT_REFUSED, 'execution_inputs: schema/kind/operation mismatch')
    if 'snapshot_root' in document:
        root = _plain_path('snapshot_root', document['snapshot_root'], code=DOCUMENT_REFUSED)
        if root.is_symlink() or not root.is_dir():
            _refuse(DOCUMENT_REFUSED, f'snapshot_root {root} is not a plain directory')
    if RUN_DECLARATION_FIELDS & set(document):
        missing = RUN_DECLARATION_FIELDS - set(document)
        if missing:
            _refuse(DOCUMENT_REFUSED, f'incomplete run declarations: missing {sorted(missing)}')
        _validate_declarations(document)
    if document['execution_scope'] != DEVELOPMENT_SCOPE:
        _refuse(SCOPE_REFUSED,
                f"execution_scope {document['execution_scope']!r} is not {DEVELOPMENT_SCOPE!r}")
    run = document['run']
    if (not isinstance(run, Mapping) or set(run) != RUN_FIELDS
            or type(run['run_id']) is not str or TOKEN.fullmatch(run['run_id']) is None
            or type(run['session_id']) is not str or TOKEN.fullmatch(run['session_id']) is None
            or type(run['epoch']) is not str or TOKEN.fullmatch(run['epoch']) is None
            or type(run['generation']) is not int or not 0 < run['generation'] < 2 ** 64):
        _refuse(DOCUMENT_REFUSED, 'execution_inputs: run identity invalid')
    evidence_root = _plain_directory('evidence_root', document['evidence_root'],
                                     code=ROOT_REFUSED)
    run_root = _plain_path('run_root', document['run_root'], code=ROOT_REFUSED)
    if evidence_root not in run_root.parents:
        _refuse(ROOT_REFUSED,
                f'run_root {run_root} must be a new directory under the evidence root {evidence_root}')
    if run_root.exists() or run_root.is_symlink():
        _refuse(ROOT_REFUSED, f'run_root {run_root} already exists or is a symlink')
    freeze = _ref_block('freeze_receipt', document['freeze_receipt'])
    _declared_bytes('freeze_receipt', freeze['path'], freeze['sha256'])
    refs = document['refs']
    if (not isinstance(refs, Mapping)
            or not REQUIRED_REF_NAMES <= set(refs) or not set(refs) <= set(REF_NAMES)):
        extra = sorted(set(refs) - set(REF_NAMES)) if isinstance(refs, Mapping) else []
        missing = sorted(set(REF_NAMES) - set(refs)) if isinstance(refs, Mapping) else list(REF_NAMES)
        _refuse(UNSEALED_REFUSED, f'refs: closed set mismatch (extra={extra}, missing={missing})')
    sealed = {}
    for name in sorted(set(REF_NAMES) & set(refs)):
        block = _ref_block(f'refs.{name}', refs[name])
        _declared_bytes(f'refs.{name}', block['path'], block['sha256'])
        sealed[name] = block
    pose = document['development_pose']
    if (not isinstance(pose, Mapping) or set(pose) != POSE_FIELDS
            or type(pose['arm_rad']) is not list or len(pose['arm_rad']) != 6
            or any(not _finite(value) for value in pose['arm_rad'])
            or not _finite(pose['neck_rad'])
            or type(pose['cup_xyz']) is not list or len(pose['cup_xyz']) != 3
            or any(not _finite(value) for value in pose['cup_xyz'])):
        _refuse(DOCUMENT_REFUSED, 'execution_inputs: development_pose invalid')
    resources = document['resources']
    if (not isinstance(resources, Mapping) or set(resources) != RESOURCE_FIELDS
            or resources['cuda_device'] != REQUIRED_CUDA_DEVICE
            or resources['allow_cpu_fallback'] is not False
            or type(resources['cpu_allocation']) is not int
            or not 0 < resources['cpu_allocation'] <= 1024):
        _refuse(DOCUMENT_REFUSED,
                'execution_inputs: resources must name cuda:0, allow_cpu_fallback False and a '
                'positive cpu_allocation')
    ros = document['ros']
    environment = ros['environment'] if isinstance(ros, Mapping) else None
    if (not isinstance(ros, Mapping) or set(ros) != ROS_FIELDS
            or type(ros['domain_id']) is not int or not 0 <= ros['domain_id'] <= 232
            or not isinstance(environment, Mapping) or not environment
            or any(type(key) is not str or not key or type(value) is not str
                   for key, value in environment.items())):
        _refuse(DOCUMENT_REFUSED, 'execution_inputs: ros domain/environment invalid')
    return HeadExecutionInputs(document_path=document_path, document=document, refs=sealed,
                               document_sha256=hashlib.sha256(raw).hexdigest())


def _read_plain(where: str, path: Path) -> bytes:
    if path.is_symlink():
        _refuse(UNSEALED_REFUSED, f'{where}: {path} is a symlink')
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                _refuse(UNSEALED_REFUSED, f'{where}: {path} is not a regular file')
            return stream.read()
    except OSError as error:
        _refuse(UNSEALED_REFUSED,
                f'{where}: {path} is absent or unreadable ({error.strerror or error})')


class HeadExecutionInputs:
    """The verified execution inputs of exactly one development run."""

    __slots__ = ('document_path', 'document', 'refs', 'document_sha256')

    @classmethod
    def parse(cls, path):
        """Read one absolute execution-input document and verify it whole."""
        return _parse(path)

    def __init__(self, *, document_path, document, refs, document_sha256):
        self.document_path = document_path
        self.document = document
        self.refs = refs
        self.document_sha256 = document_sha256

    @property
    def run(self):
        return dict(self.document['run'])

    @property
    def evidence_root(self):
        return Path(self.document['evidence_root'])

    @property
    def run_root(self):
        return Path(self.document['run_root'])

    @property
    def execution_scope(self):
        return self.document['execution_scope']

    def readback(self):
        return {
            'schema_version': SCHEMA_VERSION, 'kind': KIND, 'operation': OPERATION,
            'execution_scope': self.execution_scope, 'run': self.run,
            'evidence_root': str(self.evidence_root), 'run_root': str(self.run_root),
            'document_path': str(self.document_path),
            'document_sha256': self.document_sha256,
            'freeze_receipt': dict(self.document['freeze_receipt']),
            'refs': {name: dict(block) for name, block in sorted(self.refs.items())},
            'development_pose': json.loads(json.dumps(self.document['development_pose'])),
            'resources': dict(self.document['resources']),
            'ros': dict(self.document['ros']),
        }
