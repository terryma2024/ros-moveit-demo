"""scripts/evidence/seal_roots.py hashes the files of a root on threads (SEAL_WORKERS) and writes what the serial loop wrote;
verify_sealed_roots.py reads the seal back. Fixture trees only: every check runs the scripts as they are run on a host."""

from __future__ import annotations

import json
import os
from pathlib import Path
import random
import subprocess
import sys

import pytest

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"


def make_tree(root: Path) -> None:
    (root / "a" / "deep" / "er").mkdir(parents=True)
    (root / "b").mkdir()
    (root / "empty.bin").write_bytes(b"")
    (root / "a" / "small.txt").write_text("one\n")
    (root / "a" / "deep" / "er" / "z.json").write_text('{"k": [1, 2, 3]}\n')
    (root / "b" / "big.bin").write_bytes(random.Random(7).randbytes(9 * 1024 * 1024 + 17))     # more than one 8 MiB read
    for index in range(40):
        (root / "b" / f"f{index:02d}.dat").write_bytes(bytes([index]) * (index * 1000))
    (root / "dangling").symlink_to("missing-target")
    (root / "a" / "link").symlink_to("small.txt")
    os.mkfifo(root / "pipe")


def run_seal(registry: Path, root: Path, workers: str | None):
    environment = {key: value for key, value in os.environ.items() if key != "SEAL_WORKERS"}
    if workers is not None:
        environment["SEAL_WORKERS"] = workers
    return subprocess.run([sys.executable, str(EVIDENCE / "seal_roots.py"), "--registry-root", str(registry), "test", str(root)],
                          capture_output=True, text=True, env=environment)


def verify(registry: Path):
    return subprocess.run([sys.executable, str(EVIDENCE / "verify_sealed_roots.py"), "--registry-root", str(registry), "4"],
                          capture_output=True, text=True)


def sealed(tmp_path: Path, name: str, workers: str | None):
    registry = tmp_path / name
    root = registry / "root"
    make_tree(root)
    return registry, root, run_seal(registry, root, workers)


def test_the_parallel_manifest_is_byte_identical_to_the_serial_one(tmp_path):
    serial, serial_root, done_serial = sealed(tmp_path, "serial", "1")
    parallel, _root, done_parallel = sealed(tmp_path, "parallel", "16")
    assert done_serial.returncode == 0 == done_parallel.returncode, (done_serial.stderr, done_parallel.stderr)
    manifest = (serial / "root.seal-manifest.jsonl").read_bytes()
    assert manifest == (parallel / "root.seal-manifest.jsonl").read_bytes()
    lines = [json.loads(line) for line in manifest.decode().splitlines()]
    assert len(lines) == sum(len(names) for _, _, names in os.walk(serial_root)) - 1      # every entry once (SEALED.json is not one)
    assert any("symlink" in line for line in lines) and any(line.get("special") for line in lines)


def test_the_seal_record_and_the_registry_differ_only_in_where_and_when(tmp_path):
    serial, _a, _b = sealed(tmp_path, "serial", "1")
    parallel, _c, _d = sealed(tmp_path, "parallel", "16")

    def stable(directory: Path):
        record = json.loads((directory / "root" / "SEALED.json").read_text())
        registry = json.loads((directory / "SEALED-ROOTS.json").read_text())
        for item in [record, *registry["roots"]]:
            for key in ("root", "manifest", "sealed_at"):
                item.pop(key)
        return record, registry
    assert stable(serial) == stable(parallel)


def test_the_default_worker_count_and_one_worker_give_the_same_seal(tmp_path):
    default, _a, done_default = sealed(tmp_path, "default", None)
    one, _b, done_one = sealed(tmp_path, "one", "1")
    assert done_default.returncode == 0 == done_one.returncode
    assert (default / "root.seal-manifest.jsonl").read_bytes() == (one / "root.seal-manifest.jsonl").read_bytes()


def test_a_parallel_seal_reads_back_clean_and_a_changed_byte_is_found(tmp_path):
    registry, root, done = sealed(tmp_path, "parallel", "16")
    assert done.returncode == 0
    clean = verify(registry)
    assert clean.returncode == 0 and "problems 0" in clean.stdout, clean.stdout
    target = root / "a" / "small.txt"
    target.parent.chmod(0o755)
    target.chmod(0o644)
    target.write_text("two\n")       # same size, other bytes
    broken = verify(registry)
    assert broken.returncode == 1 and f"SHA {target}" in broken.stdout


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads files whatever their mode")
@pytest.mark.parametrize("workers", ["1", "16"])
def test_an_unreadable_file_stops_the_seal_in_both_modes_and_leaves_no_seal_record(tmp_path, workers):
    registry = tmp_path / "unreadable"
    root = registry / "root"
    make_tree(root)
    (root / "b" / "f07.dat").chmod(0)
    done = run_seal(registry, root, workers)
    assert done.returncode != 0 and "PermissionError" in done.stderr
    assert not (root / "SEALED.json").exists() and not (registry / "SEALED-ROOTS.json").exists()


@pytest.mark.parametrize("value", ["0", "-3", "many"])
def test_a_worker_count_that_is_not_a_positive_integer_is_refused_before_anything_is_sealed(tmp_path, value):
    registry = tmp_path / "bad"
    root = registry / "root"
    make_tree(root)
    done = run_seal(registry, root, value)
    assert done.returncode == 2 and "SEAL_WORKERS" in done.stderr
    assert not (registry / "root.seal-manifest.jsonl").exists() and not (root / "SEALED.json").exists()
