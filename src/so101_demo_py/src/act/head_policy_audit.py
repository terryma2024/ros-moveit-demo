"""Read-only calibration measurement audit; no ROS, CUDA or motion authority."""
import ctypes
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

from . import head_feedback_measurement
from .head_feedback_measurement import evaluate_feedback_window
from .head_evidence_identity import digest

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_CONTEXT = {'epoch', 'generation', 'session_id', 'dependencies'}
_REQUEST_LIMIT = 8192
_REPLY_LIMIT = 16384


def peer(pid):
    info = os.stat('/proc/' + str(pid))
    text = Path('/proc/' + str(pid) + '/stat').read_text()
    fields = text[text.rfind(')') + 2:].split()
    if fields[0] == 'Z':
        raise PermissionError('HEAD_POLICY_AUDIT_PEER_RETIRED')
    return dict(uid=info.st_uid, pid=pid, start_ticks=int(fields[19]))


def validate_context(context):
    if (type(context) is not dict or set(context) != _CONTEXT
            or any(type(context[k]) is not str or not 0 < len(context[k]) <= 128
                   for k in ('epoch', 'session_id'))
            or type(context['generation']) is not int or context['generation'] <= 0
            or type(context['dependencies']) is not dict
            or set(context['dependencies']) != {'weights', 'geometry', 'candidate', 'runtime_manifest'}):
        raise ValueError('HEAD_POLICY_AUDIT_CONTEXT_INVALID')
    for reference in context['dependencies'].values():
        _reference(reference)


def _reference(reference):
    if (type(reference) is not dict or set(reference) != {'path', 'sha256'}
            or type(reference['path']) is not str
            or type(reference['sha256']) is not str or not _SHA.fullmatch(reference['sha256'])):
        raise ValueError('HEAD_POLICY_AUDIT_REFERENCE_INVALID')
    path = Path(reference['path'])
    if not path.is_absolute() or str(path) != os.path.normpath(reference['path']):
        raise PermissionError('HEAD_MONITOR_INPUT_PATH_INVALID')
    return path


def audit_measurement(reference, *, context, stop_latency_s):
    validate_context(context)
    if (type(stop_latency_s) not in (int, float) or not math.isfinite(stop_latency_s)
            or stop_latency_s <= 0):
        raise ValueError('HEAD_POLICY_AUDIT_STOP_LATENCY_INVALID')
    path = _reference(reference)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise PermissionError('HEAD_MONITOR_INPUT_FILE_INVALID')
        payload = handle.read(64 * 1024 * 1024 + 1)
    if len(payload) > 64 * 1024 * 1024 or hashlib.sha256(payload).hexdigest() != reference['sha256']:
        raise PermissionError('HEAD_MONITOR_INPUT_HASH_INVALID')
    document = json.loads(payload)
    if (type(document) is not dict or set(document) != _CONTEXT | {'window', 'sha256'}
            or {k: document[k] for k in _CONTEXT} != context
            or type(document['generation']) is not int
            or type(document['sha256']) is not str
            or document['sha256'] != digest({k: v for k, v in document.items() if k != 'sha256'})):
        raise PermissionError('HEAD_MONITOR_MEASUREMENT_BINDING_INVALID')
    computed = evaluate_feedback_window(document['window'], stop_latency_s=stop_latency_s)
    return dict(purpose='calibration', motion_authority=False, reference=dict(reference),
                context=context, body_sha256=document['sha256'], computed=computed)


def module_origins():
    modules = {'so101_demo.act.head_policy_audit': Path(__file__),
               head_feedback_measurement.__name__: Path(head_feedback_measurement.__file__)}
    return {name: dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            for name, path in modules.items()}


def _collector():
    return dict(enabled=gc.isenabled(), thresholds=list(gc.get_threshold()))


def _read_request():
    payload = sys.stdin.buffer.readline(_REQUEST_LIMIT + 1)
    if not payload or len(payload) > _REQUEST_LIMIT or not payload.endswith(b'\n'):
        raise PermissionError('HEAD_POLICY_AUDIT_FRAME_INVALID')
    value = json.loads(payload)
    if type(value) is not dict:
        raise ValueError('HEAD_POLICY_AUDIT_REQUEST_INVALID')
    return value


def _send(record):
    payload = (json.dumps(record, sort_keys=True, allow_nan=False) + '\n').encode('ascii')
    if len(payload) > _REPLY_LIMIT:
        raise ValueError('HEAD_POLICY_AUDIT_REPLY_TOO_LARGE')
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def main():
    # This child owns no file writer, controller capability or ROS executor.
    # Parent death terminates this exact read-only child, including a busy audit.
    parent_pid = os.getppid()
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0 or os.getppid() != parent_pid:
        return 2
    identity = peer(os.getpid())
    try:
        bootstrap = _read_request()
        if (set(bootstrap) != {'operation', 'parent_peer', 'context'}
                or bootstrap['operation'] != 'BIND_ENTRY'
                or bootstrap['parent_peer'] != peer(parent_pid)):
            raise PermissionError('HEAD_POLICY_AUDIT_ENTRY_INVALID')
        context = bootstrap['context']
        validate_context(context)
        common = dict(peer=identity, parent_peer=bootstrap['parent_peer'], context=context,
                      motion_authority=False)
        _send(dict(common, event='POLICY_AUDIT_ENTRY', module_origins=module_origins(),
                   collector=_collector(), dont_write_bytecode=sys.dont_write_bytecode,
                   ros_imported='rclpy' in sys.modules, cuda_imported='torch' in sys.modules))
        used = False
        while True:
            request = _read_request()
            if request == {'operation': 'RETIRE'}:
                _send(dict(common, event='POLICY_AUDIT_RETIRED', collector=_collector()))
                # Remain live for the parent's final identity check. EOF after
                # its verified ACK and stdin close is authoritative owned exit.
                if sys.stdin.buffer.read(1):
                    raise PermissionError('HEAD_POLICY_AUDIT_RETIRE_TRAILING_BYTES')
                return 0
            if (used or set(request) != {'operation', 'reference', 'context', 'stop_latency_s'}
                    or request['operation'] != 'AUDIT_MEASUREMENT' or request['context'] != context):
                raise PermissionError('HEAD_POLICY_AUDIT_JOB_REFUSED')
            used = True
            started = time.monotonic()
            audit = audit_measurement(request['reference'], context=context,
                                      stop_latency_s=request['stop_latency_s'])
            _send(dict(common, event='MEASUREMENT_VERIFIED', audit=audit,
                       started_wall_s=started, completed_wall_s=time.monotonic()))
    except (OSError, ValueError, TypeError, PermissionError):
        # Never serialize the request, controller data or exception message.
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
