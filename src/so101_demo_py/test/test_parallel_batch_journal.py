"""Durability and authorization boundaries of the coordinator journal."""

import hashlib
import json
import os
import stat
import struct
import subprocess
import sys

import pytest

from so101_demo.parallel_batch.journal import CoordinatorJournal, JournalCorruption


def frames(path):
    """Decode the independently specified byte framing for assertions."""
    data = path.read_bytes()
    result = []
    while data:
        size = struct.unpack('>Q', data[:8])[0]
        frame, data = data[:73 + size], data[73 + size:]
        assert frame[-1:] == b'\n'
        assert frame[8:72] == hashlib.sha256(frame[72:-1]).hexdigest().encode()
        result.append((frame, json.loads(frame[72:-1])))
    return result


def rewrite_frame(path, index, mutate):
    """Inject semantic corruption while retaining a valid payload checksum."""
    original = frames(path)
    value = original[index][1]
    mutate(value)
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode()
    original[index] = (struct.pack('>Q', len(payload)) +
                       hashlib.sha256(payload).hexdigest().encode() + payload + b'\n', value)
    path.write_bytes(b''.join(frame for frame, _ in original))


def seed(root):
    """Commit a real lease and release ownership for recovery scenarios."""
    journal = CoordinatorJournal.create(root, 'batch-a')
    event = journal.append('LEASE_GRANTED', 'lease-1', {'slot': 'worker-01', 'k_debit': 1})
    path = journal.segment_path
    epoch = journal.coordinator_epoch
    journal.close()
    return path, event, epoch


@pytest.mark.parametrize('tail', [b'\x00\x00\x00', struct.pack('>Q', 100) + b'a' * 64 + b'{'])
def test_replay_preserves_torn_tail_and_rotates_epoch(tmp_path, tail):
    """An unfinished EOF frame must not discard already committed leases."""
    path, event, epoch = seed(tmp_path)
    before = path.read_bytes() + tail
    path.write_bytes(before)
    with CoordinatorJournal.create(tmp_path, 'batch-a') as second:
        replay = second.replay()
        assert replay.events == (event,)
        assert replay.damaged_tail_path.read_bytes() == tail
        assert path.read_bytes() == before
        assert second.coordinator_epoch == epoch + 1
        second.append('LEASE_GRANTED', 'lease-2', {'slot': 'worker-02'})
    with CoordinatorJournal.create(tmp_path, 'batch-a') as third:
        assert len(third.replay().events) == 2


def test_exact_frame_and_cross_segment_hash_chain(tmp_path):
    """Event and segment links must cover the exact preceding frame bytes."""
    path, event, epoch = seed(tmp_path)
    first = frames(path)
    assert len(first) == 2
    assert first[1][1]['prev_frame_sha256'] == hashlib.sha256(first[0][0]).hexdigest()
    assert first[1][1]['payload'] == {'slot': 'worker-01', 'k_debit': 1}
    with CoordinatorJournal.create(tmp_path, 'batch-a') as second:
        header = frames(second.segment_path)[0][1]
        assert header['prev_segment_sha256'] == hashlib.sha256(first[-1][0]).hexdigest()
        assert second.coordinator_epoch == epoch + 1
        assert second.replay().events == (event,)


@pytest.mark.parametrize('damage', ['checksum', 'middle', 'event_chain', 'segment_chain', 'batch'])
def test_corruption_fails_closed_without_epoch_advance(tmp_path, damage):
    """Committed corruption must neither issue epochs nor rewrite evidence."""
    path, _, _ = seed(tmp_path)
    if damage in ('checksum', 'middle'):
        data = bytearray(path.read_bytes())
        offset = len(frames(path)[0][0])
        data[offset + 8] = ord('0') if data[offset + 8] != ord('0') else ord('1')
        path.write_bytes(data)
        if damage == 'middle':
            with path.open('ab') as stream:
                stream.write(frames_from_good_event())
    elif damage == 'event_chain':
        rewrite_frame(path, 1, lambda value: value.update(prev_frame_sha256='f' * 64))
    elif damage == 'batch':
        rewrite_frame(path, 0, lambda value: value.update(batch_id='other'))
    else:
        with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
            path = journal.segment_path
        rewrite_frame(path, 0, lambda value: value.update(prev_segment_sha256='f' * 64))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(JournalCorruption):
        CoordinatorJournal.create(tmp_path, 'batch-a')
    after = {p.relative_to(tmp_path): p.read_bytes()
             for p in tmp_path.rglob('*') if p.is_file()}
    assert after == before


def frames_from_good_event():
    """Create a checksum-valid frame independent of journal serialization."""
    payload = b'{"type":"LEASE_GRANTED"}'
    return (struct.pack('>Q', len(payload)) + hashlib.sha256(payload).hexdigest().encode()
            + payload + b'\n')


def test_corrupt_length_cannot_hide_later_complete_frame(tmp_path):
    """A length damaged in the middle must not consume later frames as a tear."""
    path, _, _ = seed(tmp_path)
    data = bytearray(path.read_bytes())
    offset = len(frames(path)[0][0])
    data[offset:offset + 8] = struct.pack('>Q', 10000)
    path.write_bytes(data + frames_from_good_event())
    with pytest.raises(JournalCorruption):
        CoordinatorJournal.create(tmp_path, 'batch-a')


def test_second_coordinator_cannot_acquire_or_advance_epoch(tmp_path):
    """A contender must leave the active owner's epoch and lease authority intact."""
    with CoordinatorJournal.create(tmp_path, 'batch-a') as first:
        epoch_bytes = (tmp_path / 'coordinator_epoch.json').read_bytes()
        contender = CoordinatorJournal(tmp_path, 'batch-a')
        with pytest.raises(BlockingIOError):
            contender.acquire()
        with pytest.raises(BlockingIOError):
            CoordinatorJournal.create(tmp_path, 'batch-a')
        assert (tmp_path / 'coordinator_epoch.json').read_bytes() == epoch_bytes
        assert first.append('LEASE_GRANTED', 'lease-1', {}).type == 'LEASE_GRANTED'
    with CoordinatorJournal.create(tmp_path, 'batch-a') as next_owner:
        assert next_owner.coordinator_epoch == first.coordinator_epoch + 1


def test_idempotency_survives_restart_and_returns_original(tmp_path):
    """Repeated keys must not debit capacity again or expose mutable cached data."""
    path, original, _ = seed(tmp_path)
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        before = journal.segment_path.read_bytes()
        assert journal.append('DIFFERENT', 'lease-1', {'k_debit': 99}) == original
        assert journal.segment_path.read_bytes() == before
        assert len(journal.replay().events) == 1
        new = journal.append('LEASE_GRANTED', 'lease-2', {'nested': [1]})
        new.payload['nested'].append(2)
        assert journal.append('LEASE_GRANTED', 'lease-2', {}).payload == {'nested': [1]}


def test_projection_is_not_recovery_authority(tmp_path):
    """Broken and contradictory projections must not replace journal history."""
    _, event, _ = seed(tmp_path)
    (tmp_path / 'batch_state.json').write_text('{broken projection')
    (tmp_path / 'workers.json').write_text('{"leases": []}')
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        assert journal.replay().events == (event,)
        assert (tmp_path / 'batch_state.json').read_text() == '{broken projection'


def test_file_and_directory_fsync_precede_return(tmp_path, monkeypatch):
    """File data and new directory entries must be durable before success returns."""
    real = os.fsync
    synced = []

    def fsync(fd):
        synced.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        real(fd)

    monkeypatch.setattr(os, 'fsync', fsync)
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        assert True in synced
        synced.clear()
        journal.append('LEASE_GRANTED', 'lease-1', {})
        assert False in synced


def test_failed_fsync_stops_further_authorization(tmp_path, monkeypatch):
    """An uncertain write outcome must poison subsequent lease authorization."""
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        def fail(fd):
            raise OSError('injected fsync failure')

        with monkeypatch.context() as patch:
            patch.setattr(os, 'fsync', fail)
            with pytest.raises(OSError):
                journal.append('LEASE_GRANTED', 'lease-1', {})
        with pytest.raises(RuntimeError):
            journal.append('LEASE_GRANTED', 'lease-2', {})


def test_closed_or_unacquired_journal_cannot_append(tmp_path):
    """Possessing an object without its flock must never authorize an append."""
    journal = CoordinatorJournal(tmp_path, 'batch-a')
    with pytest.raises(RuntimeError):
        journal.append('LEASE_GRANTED', 'lease-1', {})
    journal.acquire()
    journal.close()
    with pytest.raises(RuntimeError):
        journal.append('LEASE_GRANTED', 'lease-1', {})


def test_invalid_payload_does_not_damage_journal(tmp_path):
    """Nonfinite JSON must be rejected before modifying durable bytes."""
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        before = journal.segment_path.read_bytes()
        with pytest.raises(ValueError):
            journal.append('LEASE_GRANTED', 'lease-1', {'bad': float('nan')})
        assert journal.segment_path.read_bytes() == before
        assert journal.append('LEASE_GRANTED', 'lease-1', {}).payload == {}


@pytest.mark.parametrize('tail', [
    struct.pack('>Q', 2 ** 63), struct.pack('>Q', 100) + b'not-hex'])
def test_invalid_partial_header_is_corruption(tmp_path, tail):
    """A partial header with already-invalid fields cannot be an ordinary tear."""
    path, _, _ = seed(tmp_path)
    path.write_bytes(path.read_bytes() + tail)
    before = (tmp_path / 'coordinator_epoch.json').read_bytes()
    with pytest.raises(JournalCorruption):
        CoordinatorJournal.create(tmp_path, 'batch-a')
    assert (tmp_path / 'coordinator_epoch.json').read_bytes() == before


@pytest.mark.parametrize('mutation', ['boolean_epoch', 'extra_field'])
def test_replay_rejects_noncanonical_event_schema(tmp_path, mutation):
    """Boolean epochs and unknown event fields must fail closed on replay."""
    path, _, _ = seed(tmp_path)
    change = {'coordinator_epoch': True} if mutation == 'boolean_epoch' else {'unknown': 1}
    rewrite_frame(path, 1, lambda value: value.update(change))
    with pytest.raises(JournalCorruption):
        CoordinatorJournal.create(tmp_path, 'batch-a')


def test_complete_payload_missing_delimiter_is_torn_only_with_valid_checksum(tmp_path):
    """A missing final delimiter leaves the last event uncommitted."""
    path, _, _ = seed(tmp_path)
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        journal.append('LEASE_GRANTED', 'lease-2', {})
        path = journal.segment_path
    raw = path.read_bytes()
    tail = frames(path)[-1][0][:-1]
    path.write_bytes(raw[:-1])
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        assert len(journal.replay().events) == 1
        assert journal.replay().damaged_tail_path.read_bytes() == tail


def test_epoch_persistence_crash_does_not_reuse_epoch(tmp_path, monkeypatch):
    """A crash between epoch persistence and segment publication must skip reuse."""
    _, _, epoch = seed(tmp_path)
    replace = os.replace

    def crash(source, target):
        if str(target).endswith('.journal'):
            raise OSError('crash before publishing segment')
        replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', crash)
        with pytest.raises(OSError):
            CoordinatorJournal.create(tmp_path, 'batch-a')
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        assert journal.coordinator_epoch == epoch + 2
        assert len(journal.replay().events) == 1


def test_subprocess_lock_and_abrupt_exit_recovery(tmp_path):
    """An independent process must respect flock and recover after abrupt exit."""
    code = """
import os, sys
from so101_demo.parallel_batch.journal import CoordinatorJournal
try:
    journal = CoordinatorJournal.create(sys.argv[1], "batch-a")
except BlockingIOError:
    sys.exit(17)
journal.append("LEASE_GRANTED", "child-lease", {"k_debit": 1})
os._exit(0)
"""
    with CoordinatorJournal.create(tmp_path, 'batch-a'):
        child = subprocess.run([sys.executable, '-c', code, str(tmp_path)], check=False)
        assert child.returncode == 17
    child = subprocess.run([sys.executable, '-c', code, str(tmp_path)], check=False)
    assert child.returncode == 0
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        assert [event.idempotency_key for event in journal.replay().events] == ['child-lease']


def test_historical_torn_tail_change_fails_closed(tmp_path):
    """Later recovery must verify the bytes of an acknowledged historical tear."""
    path, _, _ = seed(tmp_path)
    path.write_bytes(path.read_bytes() + b'\x00\x00')
    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        tail = journal.replay().damaged_tail_path
    tail.write_bytes(b'changed')
    before = (tmp_path / 'coordinator_epoch.json').read_bytes()
    with pytest.raises(JournalCorruption):
        CoordinatorJournal.create(tmp_path, 'batch-a')
    assert (tmp_path / 'coordinator_epoch.json').read_bytes() == before


def test_concurrent_duplicate_append_debits_once(tmp_path):
    """Concurrent callers using one key must obtain only one committed event."""
    from concurrent.futures import ThreadPoolExecutor

    with CoordinatorJournal.create(tmp_path, 'batch-a') as journal:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _: journal.append('LEASE_GRANTED', 'lease-1', {'k_debit': 1}),
                range(20)))
        assert results == [results[0]] * 20
        assert len(journal.replay().events) == 1
