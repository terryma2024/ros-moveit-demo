"""Immutable output files; recovery attributes results only by task_id."""

import json
import os

from .paths import _path, task_output_path
from .task_contracts import _unique_fields, _reject_constant
from so101_demo.runtime.inference.config import _open_regular

MAX_TASK_RESULT_BYTES = 1024*1024


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def reserve_task_output(output_root, task_id):
    path = task_output_path(output_root, task_id)
    try:
        path.parent.mkdir(mode=0o700, exist_ok=True)
        _path(path.parent, directory=True)
        path.mkdir(mode=0o700)
        _fsync_directory(path.parent)
        _fsync_directory(path.parent.parent)
        return path
    except (OSError, ValueError) as error:
        raise ValueError('TASK_OUTPUT_ALREADY_EXISTS_OR_INVALID') from error


def write_task_result(output_root, task_id, result):
    root = _path(task_output_path(output_root, task_id), directory=True)
    if type(result) is not dict:
        raise ValueError('TASK_RESULT_INVALID')
    data = json.dumps({'task_id': task_id, 'result': result}, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()+b'\n'
    if len(data) > MAX_TASK_RESULT_BYTES:
        raise ValueError('TASK_RESULT_OVERSIZE')
    path = root/'task-result.json'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(root)
    except OSError as error:
        raise ValueError('TASK_RESULT_WRITE_REFUSED') from error
    return path


def read_task_result(output_root, task_id):
    try:
        root = _path(task_output_path(output_root, task_id), directory=True)
        with _open_regular(root/'task-result.json') as stream:
            raw = stream.read(MAX_TASK_RESULT_BYTES+1)
        if len(raw) > MAX_TASK_RESULT_BYTES:
            raise ValueError('result size')
        document = json.loads(raw, object_pairs_hook=_unique_fields,
                              parse_constant=_reject_constant)
        if (type(document) is not dict or set(document) != {'task_id', 'result'}
                or document['task_id'] != task_id or type(document['result']) is not dict):
            raise ValueError('task id or result shape')
        return document
    except (OSError, TypeError, ValueError) as error:
        raise ValueError('TASK_RESULT_ID_OR_FILE_INVALID') from error
