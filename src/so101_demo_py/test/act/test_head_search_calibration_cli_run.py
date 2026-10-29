"""The promoted configuration check, the qualify and run subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from head_search_calibration_cli_support import _digest, _run_arguments
from head_search_qualification_fixtures import ANCHORS, build_fixture
from head_search_qualification_fixtures import digest as fixture_digest
import pytest

from so101_demo.act.head_search.aggregate.contracts import GATES
from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_RUN_INPUTS_INCOMPLETE,
)
from so101_demo.cli.head_search_calibration import main


def _bundle(root: Path) -> Path:
    """Write a promoted bundle and return the file, whose bytes are what verification hashes."""

    root.mkdir(parents=True, exist_ok=True)
    document = {"schema_version": 1, "measurements": {"max_age_s": {"value": 0.05}}}
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    target = root / "head-search-bundle.json"
    target.write_bytes(payload)
    return target


def test_verify_promoted_config_needs_the_approved_digest_and_a_bundle(tmp_path: Path) -> None:
    promoted = _bundle(tmp_path / "promoted")
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path / "run"),
                "--promoted-config",
                str(promoted),
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path / "run2"),
                "--approved-bundle-sha256",
                "a" * 64,
            ]
        )
        == 2
    )


def test_verify_promoted_config_refuses_a_drifted_bundle(tmp_path: Path) -> None:
    promoted = _bundle(tmp_path / "promoted")
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path / "run"),
                "--promoted-config",
                str(promoted),
                "--approved-bundle-sha256",
                "0" * 64,
            ]
        )
        == 2
    )
    assert not (tmp_path / "run").exists(), "a refused approval must not create its root"


def test_verify_promoted_config_writes_an_approval_receipt(tmp_path: Path) -> None:
    promoted = _bundle(tmp_path / "promoted")
    run_root = tmp_path / "run"
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(run_root),
                "--promoted-config",
                str(promoted),
                "--approved-bundle-sha256",
                _digest(promoted),
            ]
        )
        == 0
    )
    receipt = json.loads((run_root / "approval-receipt.json").read_text(encoding="utf-8"))
    assert receipt["approved_bundle_sha256"] == _digest(promoted)
    assert receipt["hashed"] == "bytes"
    assert receipt["verified"] is True


def _qualify_argv(fixture, run_root: Path, *, omit: tuple[str, ...] = ()) -> list[str]:
    """The installed `qualify` arguments for one fixture set, minus the gates named in `omit`."""

    arguments = [
        "qualify",
        "--run-root",
        str(run_root),
        "--final-run",
        str(fixture.paths["final_run"]),
        "--promoted-config",
        str(fixture.paths["production_config"]),
        "--approved-bundle",
        str(fixture.paths["approved_bundle"]),
        "--ownership-receipt",
        str(fixture.paths["ownership_receipt"]),
        "--runtime-readback",
        str(fixture.paths["runtime_readback"]),
        "--production-smoke-root",
        str(fixture.paths["production_smoke_root"]),
        "--scenarios-root",
        str(fixture.paths["scenarios_root"]),
        "--teleop-acceptance-receipt",
        str(fixture.paths["teleop_acceptance_receipt"]),
        "--scenario-partitions",
        str(fixture.partitions),
    ]
    for anchor in ANCHORS:
        arguments += ["--restart-receipt", str(fixture.paths[f"restart_{anchor}"])]
    for name in omit:
        flag = "--" + name.replace("_", "-")
        while flag in arguments:
            position = arguments.index(flag)
            del arguments[position : position + 2]
    return arguments


def test_qualify_refuses_an_existing_root_and_never_resumes_it(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    # an existing root is a named refusal with exit code 2, not a traceback
    assert main(["qualify", "--run-root", str(run_root)]) == 2


def test_qualify_without_evidence_refuses_every_gate_by_name(tmp_path: Path, capsys) -> None:
    """No evidence at all is a REFUSED verdict that names every gate; it is not a traceback."""

    run_root = tmp_path / "fresh"
    assert main(["qualify", "--run-root", str(run_root)]) == 2
    verdict = json.loads((run_root / "qualification-verdict.json").read_text(encoding="utf-8"))
    assert verdict["status"] == "HEAD_SEARCH_QUALIFICATION_REFUSED"
    assert {reason["gate"] for reason in verdict["missing"]} == set(GATES)
    assert not (run_root / "head-search-qualification.json").exists()
    assert not (run_root / "head-search-qualified-report.json").exists()
    stderr = capsys.readouterr().err
    assert "HEAD_SEARCH_QUALIFICATION_REFUSED" in stderr
    assert "HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE" in stderr


def test_qualify_publishes_the_plan_documents_only_with_the_declared_citations(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "evidence", run_root=tmp_path / "qualification-run")
    assert main(_qualify_argv(fixture, fixture.run_root)) == 0
    report = json.loads(
        (fixture.run_root / "head-search-qualified-report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "HEAD_SEARCH_QUALIFIED"
    assert report["bundle_sha256"] == fixture_digest(fixture.paths["approved_bundle"])
    for phase in (
        "production_smoke",
        "scenarios",
        "restart_default",
        "restart_left",
        "restart_forward",
        "teleop_acceptance",
    ):
        assert report["citations"][phase]["root"], phase
    qualification = json.loads(
        (fixture.run_root / "head-search-qualification.json").read_text(encoding="utf-8")
    )
    sample = qualification["samples"][0]
    assert sample["status"] == "PASS"
    assert len(sample["values"]) == 17
    assert len(sample["camera_measurements"]) == 4


def test_qualify_refuses_and_names_a_single_missing_phase_root(tmp_path: Path, capsys) -> None:
    """One missing gate is one named refusal and no pass documents, whatever else is present."""

    fixture = build_fixture(tmp_path / "evidence", run_root=tmp_path / "qualification-run")
    assert main(_qualify_argv(fixture, fixture.run_root, omit=("production-smoke-root",))) == 2
    stderr = capsys.readouterr().err
    assert "production_smoke" in stderr and "production_smoke_root" in stderr
    assert not (fixture.run_root / "head-search-qualified-report.json").exists()
    assert not (fixture.run_root / "head-search-qualification.json").exists()
    verdict = json.loads((fixture.run_root / "qualification-verdict.json").read_text(encoding="utf-8"))
    assert verdict["gates"]["production_smoke"]["status"] == "MISSING"
    assert verdict["gates"]["scenario_journal"]["status"] == "HOLDS"


def test_qualify_has_no_digest_only_surface_any_more(tmp_path: Path) -> None:
    """The digest-only defect: a directory of hex digests used to be enough to publish a pass."""

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "production_smoke.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["qualify", "--run-root", str(tmp_path / "run"), "--evidence-root", str(evidence)])


def test_run_needs_its_declared_inputs_and_claims_no_root(tmp_path: Path, capsys) -> None:
    assert main(["run", "--run-root", str(tmp_path / "run")]) == 2

    assert HEAD_SEARCH_RUN_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "run").exists(), "a refused run must not create its root"


def test_run_refuses_a_controller_without_the_bounded_trajectory_contract(
    tmp_path: Path, capsys
) -> None:
    assert main(_run_arguments(tmp_path, bounded=False)) == 2

    assert "CAL_TRAJECTORY_CONTRACT_UNSATISFIED" in capsys.readouterr().err
    assert not (tmp_path / "run").exists(), "the entry precondition claims no run root"


def test_run_stops_at_the_first_refusing_phase_and_writes_only_the_run_status(
    tmp_path: Path, capsys
) -> None:
    assert main(_run_arguments(tmp_path, seal="broken")) == 2

    root = tmp_path / "run"
    status = json.loads((root / "run-status.json").read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"
    assert status["first_failing_phase"] == "input_validation"
    assert status["failure_code"] == "CAL_INPUT_UNSEALED"
    # the run used to write a receipt and a state file that claimed six phases had happened
    assert not (root / "run-receipt.json").exists()
    assert not (root / "calibration-state.json").exists()
    assert not (root / "head-search-calibration-bundle.json").exists()
    assert "RUN_FAILED" in capsys.readouterr().err


def test_run_walks_the_real_phases_and_records_the_gates_own_refusal_code(
    tmp_path: Path, capsys
) -> None:
    """Phases 1-3 are the library modules; phase 4 is the repository's existing gate, not a copy.

    The synthetic inputs name one candidate, so the gate refuses the candidate set before it measures
    anything. That refusal is the gate's own code, and the run records the phase it came from together
    with the evidence the three phases before it produced.
    """

    assert main(_run_arguments(tmp_path)) == 2

    root = tmp_path / "run"
    status = json.loads((root / "run-status.json").read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"
    assert status["first_failing_phase"] == "frozen_candidate_evaluation"
    assert status["failure_code"] == "EVALUATION_CANDIDATE_SET_INVALID"
    assert status["evidence_produced"] == [
        "calibration-inputs.json",
        "geometry-measurements.json",
        "perception-calibration.json",
    ]
    assert "EVALUATION_CANDIDATE_SET_INVALID" in capsys.readouterr().err
    assert not (root / "head-search-calibration-bundle.json").exists()


def test_a_run_root_that_exists_is_not_resumed(tmp_path: Path, capsys) -> None:
    arguments = _run_arguments(tmp_path)
    root = tmp_path / "run"
    root.mkdir()
    (root / "previous.json").write_text("{}\n", encoding="utf-8")

    assert main(arguments) == 2

    assert "RUN_ROOT_ALREADY_EXISTS" in capsys.readouterr().err
    assert {path.name for path in root.iterdir()} == {"previous.json"}


def test_the_run_subcommand_has_no_resume_or_continuation_flag(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["run", "--run-root", str(tmp_path / "run"), "--resume"])

    assert exited.value.code == 2


def test_the_approval_receipt_is_immutable(tmp_path: Path) -> None:
    promoted = _bundle(tmp_path / "promoted")
    run_root = tmp_path / "run"
    arguments = [
        "verify-promoted-config",
        "--run-root",
        str(run_root),
        "--promoted-config",
        str(promoted),
        "--approved-bundle-sha256",
        _digest(promoted),
    ]
    assert main(arguments) == 0
    receipt = run_root / "approval-receipt.json"
    first = receipt.read_text(encoding="utf-8")
    assert main(arguments) == 2, "an approval must not be rewritten"
    assert receipt.read_text(encoding="utf-8") == first


def test_a_formatting_only_change_is_caught_because_bytes_are_hashed(tmp_path: Path) -> None:
    """Canonical JSON would hide this; hashing the bytes does not."""

    promoted = _bundle(tmp_path / "promoted")
    approved = _digest(promoted)
    reformatted = tmp_path / "promoted" / "reformatted.json"
    reformatted.write_text(
        json.dumps(json.loads(promoted.read_text(encoding="utf-8")), sort_keys=False, indent=4),
        encoding="utf-8",
    )
    assert _digest(reformatted) != approved
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path / "run-reformat"),
                "--promoted-config",
                str(reformatted),
                "--approved-bundle-sha256",
                approved,
            ]
        )
        == 2
    )


def test_the_run_declares_the_coarse_step_sweep_as_its_fifteenth_measurement(tmp_path, capsys) -> None:
    from so101_demo.cli.head_search.flags import RUN_PHASE_SIX_MEASUREMENTS

    assert ("coarse_step_observations", "--coarse-step-observations", "document") in (
        RUN_PHASE_SIX_MEASUREMENTS
    )
    # a run that declares no sweep is refused at the entry, before it claims a root
    assert main(_run_arguments(tmp_path, omit=("--coarse-step-observations",))) == 2
    assert HEAD_SEARCH_RUN_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


def test_the_run_takes_the_gates_episode_records_as_a_directory(tmp_path, capsys) -> None:
    """Phase 4's gate reads `--episode-records` as a directory of per-seed documents, so the run does."""

    from so101_demo.cli.head_search.flags import (
        RUN_OPTIONAL_DIRECTORY_FLAGS,
        RUN_OPTIONAL_FILE_FLAGS,
    )

    assert "episode_records" in RUN_OPTIONAL_DIRECTORY_FLAGS
    assert "episode_records" not in RUN_OPTIONAL_FILE_FLAGS
    records = tmp_path / "episodes" / "calibration"
    records.mkdir(parents=True)
    (records / "seed-700000.json").write_text(
        json.dumps({"seed": 700000, "frames": []}) + "\n", encoding="utf-8"
    )
    # the declared directory passes the entry's own path check; the synthetic candidate set then makes
    # the gate refuse at phase 4, which is where this argument set always stops
    arguments = _run_arguments(tmp_path)
    assert main(arguments + ["--episode-records", str(records)]) == 2
    printed = capsys.readouterr().err
    assert "no such input" not in printed
    assert not printed.startswith(HEAD_SEARCH_RUN_INPUTS_INCOMPLETE)
    # a directory that is not there is still refused by name, before any root is claimed
    assert main(arguments + ["--episode-records", str(tmp_path / "absent")]) == 2
    printed = capsys.readouterr().err
    assert printed.startswith(HEAD_SEARCH_RUN_INPUTS_INCOMPLETE)
    assert "no such input" in printed
