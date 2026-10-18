"""Resolve recorded names into the selected package, never arbitrary host paths."""
import errno
import os
import stat
import json
from pathlib import Path
from .errors import invalid, refuse


def resolve_package_path(package_root: Path, recorded_root: Path, value: str, *, base: Path | None = None) -> Path:
    candidate=Path(value)
    if candidate.is_absolute():
        try: relative=candidate.relative_to(recorded_root)
        except ValueError: refuse('ARCHIVE_PATH_OUTSIDE_PACKAGE','recorded path is outside the package',409)
        candidate=package_root/relative
    else:
        candidate=(base or package_root)/candidate
    try:
        resolved=candidate.resolve()
        resolved.relative_to(package_root.resolve())
    except (ValueError, OSError, RuntimeError):
        refuse('ARCHIVE_PATH_OUTSIDE_PACKAGE','resolved path is outside the package',409)
    return resolved


def read_json(path: Path, document: str, *, max_bytes: int = 16*1024*1024, root: Path | None = None) -> dict:
    try:
        with (open_readonly(root, path) if root is not None else path.open('rb')) as stream:
            raw=stream.read(max_bytes+1)
        if len(raw)>max_bytes: invalid(document,'document exceeds size limit')
        value=json.loads(raw)
        if not isinstance(value,dict): invalid(document,'expected a JSON object')
        return value
    except (ValueError,UnicodeError) as error: invalid(document,str(error))
    except OSError: refuse('ARCHIVE_FILE_NOT_FOUND',f'{document}: not readable')


def open_readonly(root: Path, path: Path):
    """Pin the package and each directory; a link replacement can never redirect the open."""
    directory = None
    fd = None
    try:
        parts = path.relative_to(root).parts
        if not parts or any(part in ('.', '..') for part in parts):
            raise ValueError('invalid relative path')
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            refuse('ARCHIVE_PATH_OUTSIDE_PACKAGE', 'only regular files may be read', 409)
        stream = os.fdopen(fd, 'rb')
        fd = None
        return stream
    except ValueError:
        refuse('ARCHIVE_PATH_OUTSIDE_PACKAGE', 'file path is outside the package', 409)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            refuse('ARCHIVE_PATH_OUTSIDE_PACKAGE', 'link replacement refused on open', 409)
        refuse('ARCHIVE_FILE_NOT_FOUND', 'file is missing or not readable')
    finally:
        if fd is not None: os.close(fd)
        if directory is not None: os.close(directory)
