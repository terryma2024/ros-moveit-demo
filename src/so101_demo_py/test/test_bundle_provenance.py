import json
import subprocess
import sys
from pathlib import Path

from so101_demo.runtime.provenance import build_bundle_manifest


def test_bundle_hash_is_canonical_across_mapping_order(tmp_path: Path) -> None:
    """Catch non-deterministic bundle hashes caused by insertion order or JSON whitespace."""

    artifact = tmp_path / "policy.yaml"
    artifact.write_bytes(b"policy-bytes\n")
    first = build_bundle_manifest({"source_commit": "a" * 40, "policy": artifact})
    second = build_bundle_manifest({"policy": artifact, "source_commit": "a" * 40})
    assert first.bundle_sha256 == second.bundle_sha256
    assert json.dumps(first.manifest, sort_keys=True, separators=(",", ":"))


def test_bundle_hash_changes_when_an_input_byte_changes(tmp_path: Path) -> None:
    """Catch a bundle fingerprint that omits the bytes of a named runtime input."""

    artifact = tmp_path / "scene.xml"
    artifact.write_bytes(b"first")
    first = build_bundle_manifest({"scene": artifact})
    artifact.write_bytes(b"second")
    second = build_bundle_manifest({"scene": artifact})
    assert first.bundle_sha256 != second.bundle_sha256


def test_bundle_rejects_nonfinite_or_boolean_numeric_values() -> None:
    """Catch unstable JSON fingerprints or booleans accepted as numeric provenance."""

    for value in (float("nan"), float("inf"), True):
        try:
            build_bundle_manifest({"numeric": value})
        except ValueError:
            continue
        raise AssertionError(f"bundle accepted noncanonical numeric value {value!r}")


def test_installed_provenance_module_prints_one_clean_hash() -> None:
    """Catch eager package imports that contaminate qualification evidence with runpy warnings."""

    completed = subprocess.run(
        [sys.executable, "-m", "so101_demo.runtime.provenance", "--print-bundle-sha256"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert len(completed.stdout.strip()) == 64
    assert completed.stderr == ""
