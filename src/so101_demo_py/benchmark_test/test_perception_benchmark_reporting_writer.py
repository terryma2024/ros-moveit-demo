"""The report writer and the public evidence index loaders."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from perception_benchmark_reporting_support import _fixture
import pytest

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.reporting.aggregator import MetricsAggregator
from so101_demo.perception_benchmark.reporting.records import (
    EvidenceEntry,
    EvidenceIndex,
)
from so101_demo.perception_benchmark.reporting.writer import (
    ReportWriter,
    load_evidence_index,
    verify_evidence_index,
)


def _file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_report_writer_is_deterministic_and_indexes_payload_not_itself(
    tmp_path: Path,
) -> None:
    summary = MetricsAggregator().aggregate(_fixture(tmp_path / "fixture"))
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = ReportWriter().write(summary, first_root)
    second = ReportWriter().write(summary, second_root)

    expected_files = {
        "metrics/summary.json",
        "metrics/per-scenario.csv",
        "metrics/per-image.csv",
        "metrics/cross-platform-mismatches.csv",
        "performance/latency.json",
        "performance/resources.json",
        "report/benchmark.md",
        "evidence-index.json",
    }
    assert set(_file_digests(first_root)) == expected_files
    assert _file_digests(first_root) == _file_digests(second_root)
    assert first == second
    assert {entry.relative_path for entry in first.entries} == expected_files - {
        "evidence-index.json"
    }
    index_document = json.loads((first_root / "evidence-index.json").read_text())
    assert index_document["payload_index_semantics"] == (
        "payload files only; evidence-index.json is excluded to avoid self-reference"
    )
    report = (first_root / "report/benchmark.md").read_text()
    assert "TEST_RAW_FROZEN raw capability" in report
    assert "Production safety contract" in report
    assert "NON_FORMAL_INVALID_FOR_DEPLOYMENT" in report
    assert "ORACLE_DIAGNOSTIC" not in report


def test_report_writer_never_publishes_partial_root_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from so101_demo.perception_benchmark.reporting import writer as reporting_writer

    summary = MetricsAggregator().aggregate(_fixture(tmp_path / "fixture"))
    output_root = tmp_path / "report-output"
    original = reporting_writer._atomic_write_bytes

    def fail_on_per_image(path: Path, payload: bytes) -> None:
        if path.name == "per-image.csv":
            raise OSError("injected write failure")
        original(path, payload)

    monkeypatch.setattr(reporting_writer, "_atomic_write_bytes", fail_on_per_image)

    with pytest.raises(OSError, match="injected write failure"):
        ReportWriter().write(summary, output_root)

    assert not output_root.exists()


def _write_generic_evidence_index(
    root: Path,
    *,
    entries: tuple[dict[str, object], ...] | None = None,
    schema_version: str = "so101-perception-benchmark/evidence-index/v1",
    semantics: str = (
        "payload files only; evidence-index.json is excluded to avoid self-reference"
    ),
) -> None:
    if entries is None:
        payload = b'{"formal":false}\n'
        path = root / "records/000000.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        entries = (
            {
                "relative_path": "records/000000.json",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
    (root / "evidence-index.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": schema_version,
                "payload_index_semantics": semantics,
                "entries": list(entries),
            }
        )
    )


def test_public_evidence_index_loaders_verify_report_and_generic_dry_run_trees(
    tmp_path: Path,
) -> None:
    summary = MetricsAggregator().aggregate(_fixture(tmp_path / "fixture"))
    report_root = tmp_path / "report"
    written = ReportWriter().write(summary, report_root)

    loaded = load_evidence_index(report_root)

    assert loaded == written
    assert verify_evidence_index(report_root) == written
    assert isinstance(loaded, EvidenceIndex)
    assert all(isinstance(entry, EvidenceEntry) for entry in loaded.entries)

    dry_run_root = tmp_path / "dry-run"
    dry_run_root.mkdir()
    _write_generic_evidence_index(dry_run_root)
    generic = verify_evidence_index(dry_run_root)
    assert generic.entries == (
        EvidenceEntry(
            "records/000000.json",
            len(b'{"formal":false}\n'),
            hashlib.sha256(b'{"formal":false}\n').hexdigest(),
        ),
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "tamper",
        "extra-file",
        "path-traversal",
        "self-entry",
        "duplicate",
        "size",
        "sha",
        "schema",
        "semantics",
        "noncanonical-index",
        "symlink-file",
        "symlink-directory",
    ),
)
def test_public_evidence_index_loader_rejects_tree_or_index_relaxation(
    tmp_path: Path, mutation: str
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    _write_generic_evidence_index(root)
    document = json.loads((root / "evidence-index.json").read_bytes())
    payload_path = root / "records/000000.json"
    if mutation == "tamper":
        payload_path.write_bytes(payload_path.read_bytes() + b"tamper")
    elif mutation == "extra-file":
        (root / "extra.txt").write_text("extra\n")
    elif mutation == "path-traversal":
        document["entries"][0]["relative_path"] = "../escape.json"
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "self-entry":
        document["entries"][0]["relative_path"] = "evidence-index.json"
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "duplicate":
        document["entries"].append(dict(document["entries"][0]))
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "size":
        document["entries"][0]["size_bytes"] += 1
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "sha":
        document["entries"][0]["sha256"] = "0" * 64
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "schema":
        _write_generic_evidence_index(root, schema_version="unknown")
    elif mutation == "semantics":
        _write_generic_evidence_index(root, semantics="self is included")
    elif mutation == "noncanonical-index":
        (root / "evidence-index.json").write_text(
            json.dumps(document, indent=2), encoding="utf-8"
        )
    elif mutation == "symlink-file":
        outside = tmp_path / "outside.json"
        outside.write_bytes(payload_path.read_bytes())
        payload_path.unlink()
        payload_path.symlink_to(outside)
    else:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "000000.json").write_bytes(payload_path.read_bytes())
        payload_path.unlink()
        (root / "records").rmdir()
        (root / "records").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError):
        load_evidence_index(root)


def test_round1_public_evidence_index_loader_rejects_hardlinked_payload(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    _write_generic_evidence_index(root)
    os.link(root / "records/000000.json", tmp_path / "external-record.json")

    with pytest.raises(ValueError, match="hardlink|regular in-root file"):
        load_evidence_index(root)


@pytest.mark.parametrize(
    "alias_base",
    (Path("/tmp"), Path(tempfile.gettempdir())),
    ids=("tmp-alias", "default-var-alias"),
)
def test_round2_public_evidence_index_loader_accepts_macos_system_ancestor_aliases(
    alias_base: Path,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="so101-public-index-", dir=alias_base
    ) as temporary:
        root = Path(temporary) / "evidence"
        root.mkdir()
        _write_generic_evidence_index(root)

        loaded = load_evidence_index(root)

        assert len(loaded.entries) == 1


def test_round2_public_evidence_index_loader_rejects_final_root_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    _write_generic_evidence_index(root)
    linked_root = tmp_path / "linked-evidence"
    linked_root.symlink_to(root, target_is_directory=True)

    with pytest.raises(ValueError, match="non-symlink directory"):
        load_evidence_index(linked_root)
