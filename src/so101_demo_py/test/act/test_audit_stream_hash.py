"""The audit's size and digest checks read a stream in blocks instead of holding the whole file in memory (twice).

`verify_audit_manifest` took `read_bytes()` of every stream for its length and then `_sha256(path)` read it again: two copies of the
280 MB events stream alive at once. The length and the digest are now computed by streaming in two separate passes; the digest and
the length are those of the same bytes, and every refusal keeps its code.
"""

import hashlib
import json
import os
import tracemalloc

import pytest
from so101_demo.act.episode_audit import checks
from so101_demo.act.episode_audit.verification import verify_audit_manifest

BLOCK = 1 << 20


@pytest.mark.parametrize("size", [0, 1, BLOCK - 1, BLOCK, BLOCK + 1, 5 * BLOCK + 3])
def test_the_streamed_digest_and_length_are_those_of_the_bytes(tmp_path, size):
    path = tmp_path / "stream.bin"
    payload = os.urandom(size)
    path.write_bytes(payload)
    assert checks._sha256(path) == hashlib.sha256(payload).hexdigest()
    assert checks._byte_length(path) == len(payload)


def test_unreadable_paths_raise_what_read_bytes_raised(tmp_path):
    (tmp_path / "directory").mkdir()
    for name in ("directory", "absent"):
        for function in (checks._sha256, checks._byte_length):
            with pytest.raises(OSError) as streamed:
                function(tmp_path / name)
            with pytest.raises(OSError) as original:
                (tmp_path / name).read_bytes()
            assert type(streamed.value) is type(original.value) and str(streamed.value) == str(original.value)


def peak_of(function, path):
    tracemalloc.start()
    try:
        function(path)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_a_large_file_is_digested_and_measured_without_being_held(tmp_path):
    path = tmp_path / "events.jsonl"
    size = 24 * BLOCK
    path.write_bytes(os.urandom(size))
    assert peak_of(checks._sha256, path) < 4 * BLOCK
    assert peak_of(checks._byte_length, path) < 4 * BLOCK
    assert peak_of(lambda target: target.read_bytes(), path) >= size


@pytest.fixture(scope="module")
def sealed_audit(tmp_path_factory):
    from test_act_episode_recorder import NOT_EXHAUSTED, build, result_of

    tmp_path = tmp_path_factory.mktemp("sealed")
    engine, _, working = build(tmp_path)
    assert engine.process(NOT_EXHAUSTED) == 0 and result_of(working)["status"] == "VALID"
    return working / "episode" / "audit"


def copy_audit(source, destination):
    destination.mkdir()
    for item in source.iterdir():
        (destination / item.name).write_bytes(item.read_bytes())
    return destination / "audit-manifest.json"


def code_of(path):
    try:
        verify_audit_manifest(path)
    except ValueError as error:
        return str(error)
    return "OK"


def test_the_manifest_verification_keeps_its_codes_for_a_size_a_hash_a_symlink_and_a_directory(sealed_audit, tmp_path):
    manifest = copy_audit(sealed_audit, tmp_path / "ok")
    assert code_of(manifest) == "OK"

    longer = copy_audit(sealed_audit, tmp_path / "longer")
    with open(longer.parent / "references.jsonl", "ab") as stream:
        stream.write(b"\n")
    assert code_of(longer) == "AUDIT_HASH_MISMATCH"

    flipped = copy_audit(sealed_audit, tmp_path / "flipped")
    stream_path = flipped.parent / "references.jsonl"
    data = bytearray(stream_path.read_bytes())
    data[len(data) // 2] ^= 0x01
    stream_path.write_bytes(bytes(data))
    assert json.loads(manifest.read_bytes())["files"]["references.jsonl"]["size"] == len(data)
    assert code_of(flipped) == "AUDIT_HASH_MISMATCH"

    linked = copy_audit(sealed_audit, tmp_path / "linked")
    original = linked.parent / "references.jsonl"
    moved = tmp_path / "references-elsewhere.jsonl"
    original.rename(moved)
    original.symlink_to(moved)
    assert code_of(linked) == "AUDIT_MANIFEST_INVENTORY_INVALID"

    directory = copy_audit(sealed_audit, tmp_path / "directory")
    (directory.parent / "references.jsonl").unlink()
    (directory.parent / "references.jsonl").mkdir()
    assert code_of(directory) == "AUDIT_MANIFEST_INVENTORY_INVALID"
