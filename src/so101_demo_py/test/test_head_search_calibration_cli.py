"""The installed subcommands: approval verification, qualification and refusal to resume."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.cli.head_search_calibration import main
from so101_demo.perception_benchmark.contracts import canonical_sha256


def _bundle(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    document = {"schema_version": 1, "measurements": {"max_age_s": {"value": 0.05}}}
    (root / "head-search-bundle.json").write_text(json.dumps(document), encoding="utf-8")
    return canonical_sha256(document)


def test_verify_promoted_config_needs_the_approved_digest(tmp_path: Path) -> None:
    _bundle(tmp_path)
    assert main(["verify-promoted-config", "--run-root", str(tmp_path)]) == 2


def test_verify_promoted_config_refuses_a_drifted_bundle(tmp_path: Path) -> None:
    _bundle(tmp_path)
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path),
                "--approved-bundle-sha256",
                "0" * 64,
            ]
        )
        == 2
    )


def test_verify_promoted_config_writes_an_approval_receipt(tmp_path: Path) -> None:
    approved = _bundle(tmp_path)
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path),
                "--approved-bundle-sha256",
                approved,
            ]
        )
        == 0
    )
    receipt = json.loads((tmp_path / "approval-receipt.json").read_text(encoding="utf-8"))
    assert receipt["approved_bundle_sha256"] == approved
    assert receipt["verified"] is True


def test_qualify_refuses_an_existing_root_and_publishes_nothing_without_evidence(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    with pytest.raises(ValueError, match="RUN_ROOT_ALREADY_EXISTS"):
        main(["qualify", "--run-root", str(run_root)])
    fresh = tmp_path / "fresh"
    with pytest.raises(ValueError, match="HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE"):
        main(["qualify", "--run-root", str(fresh)])


def test_qualify_publishes_the_closed_report_with_evidence(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    promoted = tmp_path / "promoted"
    _bundle(promoted)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for name in ("production_smoke", "scenarios", "restarts"):
        (evidence / f"{name}.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    assert (
        main(
            [
                "qualify",
                "--run-root",
                str(run_root),
                "--promoted-config",
                str(promoted / "head-search-bundle.json"),
                "--evidence-root",
                str(evidence),
            ]
        )
        == 0
    )
    report = json.loads(
        (run_root / "head-search-qualified-report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "HEAD_SEARCH_QUALIFIED"
    assert set(report["evidence_sha256"]) == {"production_smoke", "scenarios", "restarts"}


def test_run_refuses_to_resume_or_start_without_the_frozen_runtime(tmp_path: Path) -> None:
    assert main(["run", "--run-root", str(tmp_path / "run")]) == 2


def test_the_approval_receipt_is_immutable(tmp_path: Path) -> None:
    approved = _bundle(tmp_path)
    arguments = [
        "verify-promoted-config",
        "--run-root",
        str(tmp_path),
        "--approved-bundle-sha256",
        approved,
    ]
    assert main(arguments) == 0
    receipt = tmp_path / "approval-receipt.json"
    first = receipt.read_text(encoding="utf-8")
    assert main(arguments) == 2, "an approval must not be rewritten"
    assert receipt.read_text(encoding="utf-8") == first


def test_a_run_needs_the_frozen_runtime_and_then_runs_every_phase_once(tmp_path: Path) -> None:
    from so101_demo.act.head_search_qualification import RUN_PHASES

    run_root = tmp_path / "run"
    assert main(["run", "--run-root", str(run_root)]) == 2
    assert not run_root.exists(), "a refused run must not create its root"

    (tmp_path / "frozen-runtime.json").write_text(
        json.dumps({"runtime_id": "runtime-0001", "allow_cpu_fallback": False}), encoding="utf-8"
    )
    assert main(["run", "--run-root", str(run_root)]) == 0
    receipt = json.loads((run_root / "run-receipt.json").read_text(encoding="utf-8"))
    assert tuple(receipt["phases"]) == RUN_PHASES
    state = json.loads((run_root / "calibration-state.json").read_text(encoding="utf-8"))
    assert state["state"] == "SUCCEEDED"
    assert main(["run", "--run-root", str(run_root)]) == 2, "a finished run cannot be resumed"


def test_qualification_evidence_must_be_hexadecimal(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    promoted = tmp_path / "promoted"
    _bundle(promoted)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "production_smoke.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    good = main(
        [
            "qualify",
            "--run-root",
            str(run_root),
            "--promoted-config",
            str(promoted / "head-search-bundle.json"),
            "--evidence-root",
            str(evidence),
        ]
    )
    assert good == 0

    other = tmp_path / "other"
    bad_evidence = tmp_path / "bad-evidence"
    bad_evidence.mkdir()
    (bad_evidence / "production_smoke.json").write_text("z" * 8, encoding="utf-8")
    (bad_evidence / "scenarios.json").write_text(json.dumps({"y": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE"):
        main(
            [
                "qualify",
                "--run-root",
                str(other),
                "--promoted-config",
                str(promoted / "head-search-bundle.json"),
                "--evidence-root",
                str(bad_evidence / ".."),
            ]
        )
