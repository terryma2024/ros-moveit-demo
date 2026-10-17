"""Resolve recorded names into the selected package, never arbitrary host paths."""
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


def read_json(path: Path, document: str, *, max_bytes: int = 16*1024*1024) -> dict:
    try:
        with path.open('rb') as stream:
            raw=stream.read(max_bytes+1)
        if len(raw)>max_bytes: invalid(document,'document exceeds size limit')
        value=json.loads(raw)
        if not isinstance(value,dict): invalid(document,'expected a JSON object')
        return value
    except (ValueError,UnicodeError) as error: invalid(document,str(error))
    except OSError: refuse('ARCHIVE_FILE_NOT_FOUND',f'{document}: not readable')
