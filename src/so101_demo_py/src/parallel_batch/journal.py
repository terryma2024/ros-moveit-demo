"""Fsync-backed, hash-chained history owned by one coordinator process.

JSON projections and worker artifacts are deliberately outside this boundary.
An append returns only after fsync; an ambiguous I/O failure poisons the owner
until it is closed and recovery verifies the on-disk history.
"""

import fcntl
import hashlib
import json
import os
import struct
import tempfile
import threading
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path


_ZERO_HASH = '0' * 64
_MAX_PAYLOAD = 64 * 1024 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _frame(value):
    payload = _canonical(value)
    if len(payload) > _MAX_PAYLOAD:
        raise ValueError('journal payload is too large')
    return struct.pack('>Q', len(payload)) + _digest(payload).encode('ascii') + payload + b'\n'


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir(path):
    if not path.exists():
        _mkdir(path.parent)
        path.mkdir()
        _fsync_directory(path.parent)


def _atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    # Failed temporary writes are retained for diagnostics, never replayed.
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, path)
    _fsync_directory(path.parent)


@dataclass(frozen=True)
class JournalEvent:
    """One committed event; returned payloads are detached from journal state."""

    type: str  # noqa: A003 - public event.type contract
    idempotency_key: str
    payload: dict
    coordinator_epoch: int
    sequence: int
    prev_frame_sha256: str
    frame_sha256: str


@dataclass(frozen=True)
class JournalReplay:
    """Verified events and the most recently preserved torn-tail evidence."""

    events: tuple[JournalEvent, ...]
    damaged_tail_path: Path | None = None


class JournalCorruption(RuntimeError):
    """Committed journal history cannot be verified."""


class CoordinatorJournal:
    """Exclusive owner of a batch's durable event history."""

    def __init__(self, root, batch_id):
        """Prepare an owner without acquiring or modifying the journal."""
        if not isinstance(batch_id, str) or not batch_id:
            raise ValueError('batch_id must be a nonempty string')
        self.root = Path(root).resolve()
        self.batch_id = batch_id
        self.coordinator_epoch = 0
        self.segment_path = None
        self._lock = None
        self._stream = None
        self._pid = None
        self._failed = False
        self._mutex = threading.RLock()
        self._events = []
        self._by_key = {}
        self._terminal = _ZERO_HASH
        self._damaged_tail_path = None

    @classmethod
    def create(cls, root, batch_id):
        """Acquire and open a journal, or fail without issuing authorization."""
        journal = cls(root, batch_id)
        journal.acquire()
        return journal

    def acquire(self):
        """Acquire the nonblocking flock, validate history, then open a new epoch."""
        with self._mutex:
            if self._lock is not None:
                self._require_owner()
                return self
            _mkdir(self.root)
            lock = (self.root / 'coordinator.lock').open('a+b')
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                lock.close()
                raise
            self._lock = lock
            self._pid = os.getpid()
            self._failed = False
            try:
                _fsync_directory(self.root)
                events_dir = self.root / 'events'
                _mkdir(events_dir)
                events, terminal, last_epoch, tail = self._read_history()
                epoch_path = self.root / 'coordinator_epoch.json'
                counter = 0
                if epoch_path.exists():
                    try:
                        state = json.loads(epoch_path.read_bytes())
                        counter = state['coordinator_epoch']
                        if (state['batch_id'] != self.batch_id or type(counter) is not int
                                or counter < last_epoch):
                            raise ValueError('invalid epoch state')
                    except (ValueError, KeyError, TypeError) as exc:
                        raise JournalCorruption('invalid epoch file') from exc
                if tail:
                    tail_path, tail_bytes = tail
                    self._preserve_tail(tail_path, tail_bytes)
                epoch = max(counter, last_epoch) + 1
                header = {
                    'kind': 'segment', 'batch_id': self.batch_id,
                    'coordinator_epoch': epoch, 'prev_segment_sha256': terminal,
                    'prev_tail_sha256': _digest(tail[1]) if tail else None,
                }
                # Persist the epoch first: a crash before segment creation leaves a
                # harmless counter gap, and never reuses an issued epoch.
                _atomic_write(epoch_path, _canonical({
                    'batch_id': self.batch_id, 'coordinator_epoch': epoch}))
                self.segment_path = events_dir / f'segment-{epoch:020d}.journal'
                raw = _frame(header)
                _atomic_write(self.segment_path, raw)
                self._stream = self.segment_path.open('ab')
                self.coordinator_epoch = epoch
                self._terminal = _digest(raw)
                self._events = events
                self._by_key = {event.idempotency_key: event for event in events}
                return self
            except BaseException:
                self.close()
                raise

    def _preserve_tail(self, path, data):
        if path.exists():
            if path.read_bytes() != data:
                raise JournalCorruption('preserved torn tail does not match history')
        else:
            _atomic_write(path, data)
        self._damaged_tail_path = path

    @staticmethod
    def _contains_frame(data):
        # A damaged length must not hide a later complete frame as an EOF tear.
        for offset in range(1, max(1, len(data) - 72)):
            size = struct.unpack('>Q', data[offset:offset + 8])[0]
            end = offset + 72 + size
            if (0 < size <= _MAX_PAYLOAD and end < len(data)
                    and data[end:end + 1] == b'\n'
                    and data[offset + 8:offset + 72] ==
                    _digest(data[offset + 72:end]).encode('ascii')):
                return True
        return False

    def _read_history(self):
        events = []
        keys = set()
        terminal = _ZERO_HASH
        last_epoch = 0
        pending_tail = None
        for path in sorted((self.root / 'events').glob('segment-*.journal')):
            try:
                epoch = int(path.stem.removeprefix('segment-'))
            except ValueError as exc:
                raise JournalCorruption('invalid segment filename') from exc
            if epoch <= last_epoch or path.name != f'segment-{epoch:020d}.journal':
                raise JournalCorruption('invalid segment epoch order')
            data = path.read_bytes()
            offset = 0
            header_seen = False
            while offset < len(data):
                remaining = data[offset:]
                if len(remaining) < 8:
                    break
                size = struct.unpack('>Q', remaining[:8])[0]
                if size == 0 or size > _MAX_PAYLOAD:
                    raise JournalCorruption('invalid frame length')
                checksum = remaining[8:72]
                if any(c not in b'0123456789abcdef' for c in checksum):
                    raise JournalCorruption('invalid frame checksum header')
                if len(remaining) < 72:
                    break
                if len(remaining) < 72 + size:
                    break
                payload = remaining[72:72 + size]
                if checksum != _digest(payload).encode('ascii'):
                    raise JournalCorruption('frame checksum mismatch')
                if len(remaining) == 72 + size:
                    break
                if remaining[72 + size:73 + size] != b'\n':
                    raise JournalCorruption('invalid frame delimiter')
                raw = remaining[:73 + size]
                try:
                    value = json.loads(payload)
                    if _canonical(value) != payload or not isinstance(value, dict):
                        raise ValueError('noncanonical frame')
                    if not header_seen:
                        if (type(value.get('coordinator_epoch')) is not int or value != {
                            'kind': 'segment', 'batch_id': self.batch_id,
                            'coordinator_epoch': epoch, 'prev_segment_sha256': terminal,
                            'prev_tail_sha256': _digest(pending_tail[1]) if pending_tail else None,
                        }):
                            raise ValueError('segment chain mismatch')
                        if pending_tail:
                            if (not pending_tail[0].is_file()
                                    or pending_tail[0].read_bytes() != pending_tail[1]):
                                raise ValueError('missing or altered preserved tail')
                            self._damaged_tail_path = pending_tail[0]
                        pending_tail = None
                        header_seen = True
                    else:
                        if (set(value) != {
                                'kind', 'batch_id', 'type', 'idempotency_key', 'payload',
                                'coordinator_epoch', 'sequence', 'prev_frame_sha256'}
                                or value['kind'] != 'event' or value['batch_id'] != self.batch_id
                                or type(value['coordinator_epoch']) is not int
                                or value['coordinator_epoch'] != epoch
                                or type(value['sequence']) is not int
                                or value['sequence'] != len(events) + 1
                                or value['prev_frame_sha256'] != terminal
                                or not isinstance(value['type'], str) or not value['type']
                                or not isinstance(value['idempotency_key'], str)
                                or not value['idempotency_key']
                                or value['idempotency_key'] in keys
                                or not isinstance(value['payload'], dict)):
                            raise ValueError('event chain or schema mismatch')
                        keys.add(value['idempotency_key'])
                        events.append(JournalEvent(
                            value['type'], value['idempotency_key'], value['payload'],
                            epoch, value['sequence'], terminal, _digest(raw)))
                except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                    raise JournalCorruption(f'invalid history in {path.name}') from exc
                terminal = _digest(raw)
                offset += len(raw)
            if offset < len(data) or not header_seen:
                if pending_tail is not None or self._contains_frame(data[offset:]):
                    raise JournalCorruption('unverifiable mid-segment damage')
                pending_tail = (path.parent / f'torn-tail-{epoch}.bin', data[offset:])
            last_epoch = epoch
        return events, terminal, last_epoch, pending_tail

    def _require_owner(self):
        if self._lock is None or self._failed or self._pid != os.getpid():
            raise RuntimeError('journal is not acquired or requires recovery')

    def append(self, event_type, idempotency_key, payload):
        """Durably append once per key; repeated keys return the original event."""
        with self._mutex:
            self._require_owner()
            if not isinstance(idempotency_key, str) or not idempotency_key:
                raise ValueError('idempotency_key must be a nonempty string')
            if idempotency_key in self._by_key:
                return deepcopy(self._by_key[idempotency_key])
            if not isinstance(event_type, str) or not event_type or not isinstance(payload, dict):
                raise ValueError('event requires a nonempty type and an object payload')
            value = {
                'kind': 'event', 'batch_id': self.batch_id,
                'type': event_type, 'idempotency_key': idempotency_key,
                'payload': payload, 'coordinator_epoch': self.coordinator_epoch,
                'sequence': len(self._events) + 1, 'prev_frame_sha256': self._terminal,
            }
            raw = _frame(value)
            event = JournalEvent(event_type, idempotency_key, json.loads(_canonical(payload)),
                                 self.coordinator_epoch, value['sequence'],
                                 self._terminal, _digest(raw))
            try:
                self._stream.write(raw)
                self._stream.flush()
                os.fsync(self._stream.fileno())
            except BaseException:
                self._failed = True
                raise
            self._terminal = event.frame_sha256
            self._events.append(event)
            self._by_key[idempotency_key] = event
            return deepcopy(event)

    def replay(self):
        """Validate authoritative frames under the lock, without reading projections."""
        with self._mutex:
            self._require_owner()
            try:
                events, terminal, _, tail = self._read_history()
                if tail or terminal != self._terminal:
                    raise JournalCorruption('active journal changed outside its owner')
                return JournalReplay(tuple(deepcopy(events)), self._damaged_tail_path)
            except BaseException:
                self._failed = True
                raise

    def close(self):
        """Release resources; an inherited child must never unlock its parent's flock."""
        with self._mutex:
            try:
                if self._stream is not None:
                    self._stream.close()
            finally:
                self._stream = None
                if self._lock is not None:
                    if self._pid == os.getpid():
                        fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
                    self._lock.close()
                    self._lock = None

    def __enter__(self):
        """Hold ownership for the context lifetime."""
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback):
        """Release ownership even when the caller fails."""
        self.close()
