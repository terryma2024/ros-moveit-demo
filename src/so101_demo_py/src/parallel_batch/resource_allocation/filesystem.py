"""Trusted directories, private files and JSON helpers of the allocation."""

from __future__ import annotations

import errno
import json
import math
import os
from pathlib import Path
import stat
import sys
from types import MappingProxyType
from typing import Mapping

from so101_demo.parallel_batch.resource_allocation.models import ResourceAllocationError


def _verify_trusted_directory(
    descriptor: int, name: str, *, final_parent: bool = False, private: bool = False
) -> os.stat_result:
    value = os.fstat(descriptor)
    if not stat.S_ISDIR(value.st_mode):
        raise ResourceAllocationError(f'NOT_DIRECTORY: {name}')
    uid = os.getuid()
    mode = stat.S_IMODE(value.st_mode)
    if private:
        if value.st_uid != uid:
            raise ResourceAllocationError(f'UNSAFE_DIRECTORY_OWNER: {name}')
        if mode != 0o700:
            raise ResourceAllocationError(f'UNSAFE_DIRECTORY_MODE: {name}')
        return value
    if value.st_uid not in {0, uid} or (final_parent and value.st_uid != uid):
        raise ResourceAllocationError(f'UNSAFE_DIRECTORY_OWNER: {name}')
    root_owned_sticky = (
        not final_parent
        and value.st_uid == 0
        and bool(mode & stat.S_ISVTX)
    )
    if (mode & 0o002 or (value.st_uid == 0 and mode & 0o020)) and not root_owned_sticky:
        raise ResourceAllocationError(f'UNSAFE_DIRECTORY_MODE: {name}')
    return value


def _trusted_macos_tmp_path(path: Path) -> Path:
    if sys.platform != 'darwin' or path.parts[:2] != ('/', 'tmp'):
        return path
    alias = Path('/tmp')
    try:
        alias_info = alias.lstat()
        target = (alias.parent / os.readlink(alias)).resolve(strict=True)
        target_info = target.stat()
    except OSError as error:
        raise ResourceAllocationError(f'SYMLINK_PATH: {path}') from error
    if (
        alias_info.st_uid != 0
        or not stat.S_ISLNK(alias_info.st_mode)
        or target != Path('/private/tmp')
        or target_info.st_uid != 0
        or not stat.S_ISDIR(target_info.st_mode)
        or not stat.S_IMODE(target_info.st_mode) & stat.S_ISVTX
    ):
        raise ResourceAllocationError(f'SYMLINK_PATH: {path}')
    return target.joinpath(*path.parts[2:])


def _open_trusted_parent(path: Path) -> int:
    if not path.is_absolute() or not path.name:
        raise ResourceAllocationError('ABSOLUTE_PATH_REQUIRED')
    display_path = path
    path = _trusted_macos_tmp_path(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open('/', flags)
    parts = path.parent.parts[1:]
    try:
        _verify_trusted_directory(descriptor, '/')
        for index, part in enumerate(parts):
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except OSError as error:
                if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ResourceAllocationError(f'SYMLINK_PATH: {display_path}') from error
                raise ResourceAllocationError(
                    f'PATH_ANCESTOR_UNAVAILABLE: {display_path}'
                ) from error
            os.close(descriptor)
            descriptor = child
            _verify_trusted_directory(
                descriptor,
                str(path.parent),
                final_parent=index == len(parts) - 1,
            )
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_or_create_private_directory(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        pass
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ResourceAllocationError(f'SYMLINK_PATH: {name}') from error
        raise ResourceAllocationError(f'DIRECTORY_OPEN_FAILED: {name}') from error
    try:
        _verify_trusted_directory(descriptor, name, private=True)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _mkdir_private_at(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        descriptor = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
    except FileExistsError as error:
        raise ResourceAllocationError(f'DIRECTORY_CONFLICT: {name}') from error
    except OSError as error:
        raise ResourceAllocationError(f'DIRECTORY_CREATION_FAILED: {name}') from error
    try:
        _verify_trusted_directory(descriptor, name, private=True)
        os.fsync(parent_fd)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _verify_private_regular(descriptor: int, name: str) -> os.stat_result:
    value = os.fstat(descriptor)
    if not stat.S_ISREG(value.st_mode):
        raise ResourceAllocationError(f'NOT_REGULAR_FILE: {name}')
    if value.st_uid != os.getuid():
        raise ResourceAllocationError(f'UNSAFE_FILE_OWNER: {name}')
    if stat.S_IMODE(value.st_mode) != 0o600:
        raise ResourceAllocationError(f'UNSAFE_FILE_MODE: {name}')
    return value


def _replace_fd_contents(descriptor: int, payload: bytes) -> None:
    os.ftruncate(descriptor, 0)
    os.lseek(descriptor, 0, os.SEEK_SET)
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError('short write')
        offset += written
    os.fsync(descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)
    if _read_fd(descriptor, len(payload) + 1) != payload:
        raise ResourceAllocationError('FILE_READBACK_FAILED')


def _read_fd(descriptor: int, limit: int) -> bytes:
    chunks = []
    remaining = limit
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def _json_bytes(document) -> bytes:
    def validate(value):
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError('non-string JSON key')
            for child in value.values():
                validate(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                validate(child)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('non-finite JSON number')

    validate(document)
    return json.dumps(
        document, sort_keys=True, separators=(',', ':'), allow_nan=False
    ).encode('utf-8')


def _freeze_json(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value):
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(child) for child in value]
    return value
