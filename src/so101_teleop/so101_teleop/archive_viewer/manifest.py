"""Immutable manifest metadata, read once without touching payload files."""
import bisect
import hashlib
import json
from pathlib import Path, PurePosixPath
from .errors import invalid, refuse


class ManifestIndex:
    def __init__(self, ref):
        self.path = ref.path.with_name(ref.path.name + '.seal-manifest.jsonl')
        recorded = Path(ref.seal.get('manifest', str(self.path)))
        expected = ref.recorded_root.with_name(ref.recorded_root.name + '.seal-manifest.jsonl')
        if recorded not in (expected, self.path) or self.path.is_symlink() or self.path.resolve().parent != ref.path.parent:
            refuse('ARCHIVE_PATH_OUTSIDE_PACKAGE', 'manifest must be the exact package sibling', 409)
        self.entries = {}
        digest = hashlib.sha256()
        try:
            with self.path.open('rb') as stream:
                while raw := stream.readline(65537):
                    if len(raw) > 65536:
                        invalid('seal-manifest.jsonl', 'manifest line exceeds limit')
                    digest.update(raw)
                    row = json.loads(raw)
                    name = row['path']
                    parts = PurePosixPath(name)
                    if not isinstance(name, str) or parts.is_absolute() or '..' in parts.parts or str(parts) != name or name in self.entries:
                        invalid('seal-manifest.jsonl', 'invalid or duplicate relative path')
                    if not isinstance(row.get('bytes'), int) or row['bytes'] < 0:
                        invalid('seal-manifest.jsonl', 'invalid file size')
                    self.entries[name] = row
        except (ValueError, KeyError, TypeError, UnicodeError):
            invalid('seal-manifest.jsonl', 'malformed manifest entry')
        except OSError:
            refuse('ARCHIVE_FILE_NOT_FOUND', 'seal manifest is not readable')
        if digest.hexdigest() != ref.seal.get('manifest_sha256'):
            invalid('seal-manifest.jsonl', 'manifest SHA256 mismatch')
        self.names = sorted(self.entries)

    def below(self, prefix: str) -> list[dict]:
        prefix = prefix.rstrip('/') + '/'
        first = bisect.bisect_left(self.names, prefix)
        last = bisect.bisect_left(self.names, prefix + chr(0x10ffff))
        return [self.entries[name] for name in self.names[first:last]]
