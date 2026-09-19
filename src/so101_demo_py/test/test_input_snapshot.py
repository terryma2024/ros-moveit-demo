"""The v4 RED tests for an immutable inference input snapshot.

Task 6 of the macOS MPS / private IPC plan. The v4 design (section 7.3) keeps raw RGB-D arrays
out of the control frame: a Worker writes a snapshot into a task-owned input root, atomically
renames it, and registers a descriptor; the Broker opens that descriptor under the pinned root,
verifies size/SHA-256/shape/dtype, reads, and closes. The snapshot lives at least until the
request completes, is cancelled, or is invalidated.

Every rejection here is a closed failure: absolute paths, `..`, symlinks, a tampered file, an
oversized file, a wrong shape or a wrong dtype all refuse rather than being coerced.
"""

import hashlib
import os
import time
from pathlib import Path

import pytest

from so101_demo.parallel_batch.input_snapshot import (
    DELETION_CANDIDATE,
    MaxSnapshotExceeded,
    SnapshotDescriptor,
    SnapshotError,
    SnapshotRegistry,
    SnapshotStore,
)

NP = pytest.importorskip("numpy")


@pytest.fixture
def store(tmp_path):
    return SnapshotStore(root=tmp_path / "input-root", max_snapshot_bytes=1 << 20)


def _array(shape=(4, 4, 3), dtype="uint8", fill=7):
    return NP.full(shape, fill, dtype=dtype)


# --------------------------------------------------------------------------------------
# descriptor validation
# --------------------------------------------------------------------------------------


def test_descriptor_records_the_required_immutable_facts():
    """The descriptor carries exactly the design's fields and validates its own types."""

    descriptor = SnapshotDescriptor(
        relative_path="slot-0/frame-0001.npy", size_bytes=48, sha256="a" * 64,
        shape=(4, 4, 3), dtype="uint8", encoding="npy", frame_timestamp_ns=123456789,
    )
    assert descriptor.relative_path == "slot-0/frame-0001.npy"
    assert descriptor.shape == (4, 4, 3)
    assert descriptor.dtype == "uint8"
    assert descriptor.encoding == "npy"
    assert descriptor.frame_timestamp_ns == 123456789

    for mutated in (
        {"relative_path": "/abs/frame.npy"},  # a path failure is SnapshotError, not ValueError
        {"relative_path": "../escape.npy"},
        {"relative_path": "sub/../../escape.npy"},
        {"relative_path": ""},
        {"size_bytes": -1},
        {"size_bytes": 1.5},
        {"sha256": "not-a-hash"},
        {"shape": ()},
        {"shape": (4, -1, 3)},
        {"dtype": ""},
        {"encoding": ""},
        {"frame_timestamp_ns": -1},
    ):
        payload = dict(relative_path="frame.npy", size_bytes=48, sha256="a" * 64,
                       shape=(4, 4, 3), dtype="uint8", encoding="npy",
                       frame_timestamp_ns=1)
        payload.update(mutated)
        with pytest.raises((ValueError, SnapshotError)):
            SnapshotDescriptor(**payload)


# --------------------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------------------


def test_write_produces_an_atomic_immutable_snapshot(store):
    """The snapshot is written under a temporary name, fsynced, renamed, and then read-only."""

    descriptor = store.write(_array(), slot="slot-0", frame_timestamp_ns=42)
    path = store.resolve(descriptor)
    assert path.is_file()
    assert store.root in path.parents
    assert not path.is_symlink()
    assert descriptor.size_bytes == path.stat().st_size
    assert descriptor.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert descriptor.shape == (4, 4, 3)
    assert descriptor.dtype == "uint8"
    assert descriptor.encoding == "npy"
    assert descriptor.frame_timestamp_ns == 42
    # No temporary sibling survives.
    assert list(path.parent.glob("*.part")) == []
    # The file is immutable for the campaign: the owner write bit is gone.
    mode = path.stat().st_mode & 0o777
    assert mode & 0o200 == 0, f"snapshot is still writable: {mode:04o}"


def test_write_refuses_an_oversized_snapshot(store):
    """The snapshot limit is enforced before the file is committed."""

    big = SnapshotStore(root=store.root, max_snapshot_bytes=64)
    with pytest.raises(MaxSnapshotExceeded, match="MAX_INPUT_SNAPSHOT_BYTES"):
        big.write(_array(shape=(64, 64, 3)), slot="slot-0", frame_timestamp_ns=1)
    # Nothing partial is left behind.
    if big.root.exists():
        assert [item for item in big.root.rglob("*") if item.is_file()] == []


def test_write_refuses_a_non_array_and_a_non_contiguous_slot(store):
    """The writer accepts only a real array and a sanitised slot name."""

    with pytest.raises(SnapshotError, match="SNAPSHOT_VALUE"):
        store.write({"not": "an array"}, slot="slot-0", frame_timestamp_ns=1)
    with pytest.raises(SnapshotError, match="SNAPSHOT_SLOT"):
        store.write(_array(), slot="../escape", frame_timestamp_ns=1)
    with pytest.raises(SnapshotError, match="SNAPSHOT_SLOT"):
        store.write(_array(), slot="", frame_timestamp_ns=1)


# --------------------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------------------


def test_read_verifies_and_returns_the_array(store):
    """A healthy snapshot reads back with the declared shape, dtype and bytes."""

    array = _array(fill=11)
    descriptor = store.write(array, slot="slot-0", frame_timestamp_ns=7)
    loaded, readback = store.read(descriptor)
    assert NP.array_equal(loaded, array)
    assert readback.verified is True
    assert readback.relative_path == descriptor.relative_path
    assert readback.size_bytes == descriptor.size_bytes


def test_read_refuses_an_absolute_path(tmp_path, store):
    """A descriptor may not point outside the pinned root, even absolutely."""

    outside = tmp_path / "outside.npy"
    NP.save(outside, _array())
    # SnapshotDescriptor refuses an absolute path outright; the raw document reader must too,
    # because that is the shape an attacker actually controls on the wire.
    with pytest.raises(SnapshotError):
        SnapshotDescriptor(relative_path=str(outside), size_bytes=outside.stat().st_size,
                           sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
                           shape=(4, 4, 3), dtype="uint8", encoding="npy",
                           frame_timestamp_ns=1)
    with pytest.raises((SnapshotError, ValueError)):
        store.read_document({"relative_path": str(outside),
                             "size_bytes": outside.stat().st_size,
                             "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                             "shape": [4, 4, 3], "dtype": "uint8", "encoding": "npy",
                             "frame_timestamp_ns": 1})



def test_read_refuses_traversal_and_symlinks(tmp_path, store):
    """`..`, an escaping relative path and a symlinked snapshot are all refused."""

    store.write(_array(), slot="slot-0", frame_timestamp_ns=1)
    with pytest.raises((SnapshotError, ValueError)):
        store.read_document({"relative_path": "../escape.npy", "size_bytes": 1,
                             "sha256": "a" * 64, "shape": [1], "dtype": "uint8",
                             "encoding": "npy", "frame_timestamp_ns": 1})

    outside = tmp_path / "outside.npy"
    NP.save(outside, _array())
    link = store.root / "slot-0" / "link.npy"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    with pytest.raises(SnapshotError, match="SNAPSHOT_SYMLINK"):
        store.read_document({"relative_path": "slot-0/link.npy",
                             "size_bytes": outside.stat().st_size,
                             "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                             "shape": [4, 4, 3], "dtype": "uint8", "encoding": "npy",
                             "frame_timestamp_ns": 1})


def test_read_refuses_a_tampered_size_sha_shape_or_dtype(store):
    """Every declared fact is re-derived from the bytes; a mismatch is a refusal."""

    descriptor = store.write(_array(shape=(4, 4, 3), dtype="uint8"), slot="slot-0",
                             frame_timestamp_ns=1)
    for mutated, reason in (
        ({"size_bytes": descriptor.size_bytes + 1}, "SNAPSHOT_SIZE"),
        ({"sha256": "b" * 64}, "SNAPSHOT_SHA256"),
        ({"shape": (5, 4, 3)}, "SNAPSHOT_SHAPE"),
        ({"dtype": "float32"}, "SNAPSHOT_DTYPE"),
    ):
        payload = {"relative_path": descriptor.relative_path,
                   "size_bytes": descriptor.size_bytes, "sha256": descriptor.sha256,
                   "shape": list(descriptor.shape), "dtype": descriptor.dtype,
                   "encoding": descriptor.encoding,
                   "frame_timestamp_ns": descriptor.frame_timestamp_ns}
        payload.update(mutated)
        with pytest.raises(SnapshotError, match=reason):
            store.read_document(payload)


def test_read_refuses_a_missing_file(store):
    """A descriptor for a file that is not there is a refusal, not an empty array."""

    descriptor = store.write(_array(), slot="slot-0", frame_timestamp_ns=1)
    store.resolve(descriptor).unlink()
    with pytest.raises(SnapshotError, match="SNAPSHOT_MISSING"):
        store.read(descriptor)


def test_read_refuses_an_oversized_file_even_when_the_descriptor_agrees(store):
    """The limit is enforced on the file, not only on the writer that produced it."""

    huge = SnapshotStore(root=store.root, max_snapshot_bytes=64)
    path = store.root / "slot-0" / "huge.npy"
    path.parent.mkdir(parents=True, exist_ok=True)
    NP.save(path, NP.zeros((64, 64, 3), dtype="uint8"))
    with pytest.raises(MaxSnapshotExceeded, match="MAX_INPUT_SNAPSHOT_BYTES"):
        huge.read_document({"relative_path": "slot-0/huge.npy",
                            "size_bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "shape": [64, 64, 3], "dtype": "uint8", "encoding": "npy",
                            "frame_timestamp_ns": 1})


def test_control_frames_stay_separate_from_snapshot_bytes(store):
    """A frame descriptor is small; the bytes are never in the control frame."""

    from so101_demo.runtime.parallel_ipc_v4 import V4Request

    descriptor = store.write(_array(shape=(64, 64, 3)), slot="slot-0", frame_timestamp_ns=1)
    request = V4Request(request_id="r-1", operation="broker.infer",
                        deadline_monotonic_ns=time.monotonic_ns() + 10**9,
                        payload={"input_descriptor": descriptor.to_document()})
    encoded = str(request.to_document())
    assert descriptor.relative_path in encoded
    assert len(encoded) < 1024, "the control frame must carry the descriptor, not the array"


# --------------------------------------------------------------------------------------
# lifecycle
# --------------------------------------------------------------------------------------


def test_registry_holds_a_snapshot_until_the_request_finishes(store):
    """The registry keeps the file alive, then lists it as a deletion candidate only."""

    registry = SnapshotRegistry(store=store)
    descriptor = registry.register(request_id="r-1", slot="slot-0", array=_array(),
                                   frame_timestamp_ns=1)
    assert registry.live(request_id="r-1") == (descriptor,)
    assert registry.pending_deletion_candidates() == ()

    registry.complete(request_id="r-1")
    assert registry.live(request_id="r-1") == ()
    candidates = registry.pending_deletion_candidates()
    assert [item.outcome for item in candidates] == [DELETION_CANDIDATE]
    assert store.resolve(descriptor).exists(), "a candidate is reported, never deleted"


def test_registry_holds_a_snapshot_across_cancel_and_invalidate(store):
    """Cancel and broker invalidation also release the snapshot, without deleting it."""

    registry = SnapshotRegistry(store=store)
    first = registry.register(request_id="r-1", slot="slot-0", array=_array(),
                              frame_timestamp_ns=1)
    second = registry.register(request_id="r-2", slot="slot-1", array=_array(),
                               frame_timestamp_ns=2)
    registry.cancel(request_id="r-1", reason="client cancelled")
    assert registry.live(request_id="r-1") == ()
    assert registry.live(request_id="r-2") == (second,)

    released = registry.invalidate_all(reason="broker replaced")
    assert set(released) == {second}
    assert registry.live(request_id="r-2") == ()
    assert len(registry.pending_deletion_candidates()) == 2
    assert store.resolve(first).exists() and store.resolve(second).exists()


def test_registry_refuses_a_duplicate_request_id(store):
    """A request id is never reused for a second snapshot."""

    registry = SnapshotRegistry(store=store)
    registry.register(request_id="r-1", slot="slot-0", array=_array(), frame_timestamp_ns=1)
    with pytest.raises(SnapshotError, match="SNAPSHOT_REQUEST_DUPLICATE"):
        registry.register(request_id="r-1", slot="slot-0", array=_array(),
                          frame_timestamp_ns=2)


def test_registry_unknown_request_is_reported_not_guessed(store):
    """Completing an unknown request is a refusal, so a late completion cannot be silent."""

    registry = SnapshotRegistry(store=store)
    with pytest.raises(SnapshotError, match="SNAPSHOT_REQUEST_UNKNOWN"):
        registry.complete(request_id="never-registered")
    with pytest.raises(SnapshotError, match="SNAPSHOT_REQUEST_UNKNOWN"):
        registry.cancel(request_id="never-registered", reason="x")


def test_store_root_is_created_private_and_never_escapes(store):
    """The input root is task-owned and 0700, and a relative path is always inside it."""

    store.write(_array(), slot="slot-0", frame_timestamp_ns=1)
    mode = store.root.stat().st_mode & 0o777
    assert mode == 0o700, f"input root mode is {mode:04o}"
    descriptor = store.write(_array(), slot="slot-1", frame_timestamp_ns=1)
    resolved = store.resolve(descriptor)
    assert store.root in resolved.parents
    assert os.path.realpath(resolved).startswith(os.path.realpath(store.root))
