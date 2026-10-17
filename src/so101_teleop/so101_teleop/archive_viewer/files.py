"""Bounded, read-only JSON and byte-offset UTF-8 JSONL views."""
import json
from .errors import invalid, refuse
from .models import FileView

MAX_BYTES = 2 * 1024 * 1024


def read_file(path, *, offset=0, limit=100):
    if offset < 0 or not 1 <= limit <= 500:
        invalid('file page', 'invalid offset or limit')
    try:
        with path.open('rb') as stream:
            if path.suffix == '.json':
                raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    refuse('ARCHIVE_FILE_TOO_LARGE', 'JSON exceeds 2 MiB', 413)
                return FileView(kind='json', content=json.loads(raw))
            if path.suffix != '.jsonl':
                refuse('ARCHIVE_FILE_UNSUPPORTED', 'only JSON and JSONL can be viewed', 415)
            size = stream.seek(0, 2)
            if offset > size:
                invalid('offset', 'offset beyond end of file')
            if offset and offset != size:
                stream.seek(offset-1)
                if stream.read(1) != b'\n':
                    invalid('offset', 'offset must be on a line boundary')
            stream.seek(offset)
            lines = []; used = 0
            while len(lines) < limit:
                start = stream.tell()
                raw = stream.readline(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    refuse('ARCHIVE_LINE_TOO_LARGE', 'JSONL line exceeds 2 MiB', 413)
                if not raw:
                    break
                if used + len(raw) > MAX_BYTES:
                    stream.seek(start)
                    break
                used += len(raw)
                lines.append(raw.decode('utf8').rstrip('\n').rstrip('\r'))
            position = stream.tell()
            eof = position == size
            return FileView(kind='jsonl', lines=lines, next_offset=None if eof else position, eof=eof)
    except (ValueError, UnicodeError):
        invalid(path.name, 'invalid JSON or UTF-8')
    except OSError:
        refuse('ARCHIVE_FILE_NOT_FOUND', 'file is not readable')
