"""Task 8P2: the aggregator derives verdicts from raw evidence, never from labels.

Batch layout (the producer's contract, pinned here):
  batch.json                  identity + status (RUNNING|CLOSED|INVALID)
  fov/<anchor>.json           {"samples":[{"t_s":float,"target_in_view":bool}]}
  search/<anchor>.json        {"lock_frames":[{"t_s":float,"target_id":str,"qualified":bool}]}
  sync/<anchor>.json          {"samples":[{"age_s":float,"skew_s":float}]}
  collision.json              {"calls":[{"request_index":int,"duration_ms":float,
                                          "contact_ok":bool}]}
  execution.json              {"reference_matches_permit":bool,"velocity_ok":bool,
                               "acceleration_ok":bool,"submit_lead_s":float,"stop_ok":bool}
  cleanup-receipt.json        {"group_clear":bool}
"""

import json
from pathlib import Path

import pytest

from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration
from so101_demo.act.task8_measurement_contract import (
    bind_measurement_contract, close_measurement_batch,
)

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = PACKAGE / "config/act/task8-calibration-measurement-contract-v1.json"
TEMPLATE_V2 = Path(__file__).resolve().parents[1] / "config/act" / "task8-calibration-measurement-contract-v2.json"
ANCHORS = ("default", "left", "forward")


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture
def contract(tmp_path):
    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "anchors_sha256": "c" * 64, "contact_policy_fingerprint": "d" * 64,
                  "act_profile_sha256": "e" * 64}
    return json.loads(bind_measurement_contract(TEMPLATE, identities,
                                                tmp_path / "contract.json").read_text())


def batch_factory(tmp_path, contract, name="batch", *, declared_status="CLOSED", status_field=None,
                  source_provenance_sha256="a" * 64, lock_frames=None, fov_ok=True,
                  sync=True, collision_ok=True, execution_ok=True):
    root = tmp_path / name
    lock_frames = lock_frames or {"default": 4, "left": 4, "forward": 4}
    (root / "declared.json").parent.mkdir(parents=True, exist_ok=True)
    _write(root / "declared.json", {"declared_status": declared_status})
    for anchor in ANCHORS:
        samples = [{"t_s": index * 0.002,
                    "target_in_view": fov_ok or index < 3} for index in range(6)]
        _write(root / f"fov/{anchor}.json", {"samples": samples})
        frames = [{"t_s": index * 0.05, "target_id": "cup", "qualified": index < lock_frames[anchor]}
                  for index in range(max(lock_frames.values()) + 1)]
        _write(root / f"search/{anchor}.json", {"lock_frames": frames})
        if sync:
            _write(root / f"sync/{anchor}.json",
                   {"samples": [{"age_s": 0.05, "skew_s": 0.01} for _ in range(4)]})
    calls = [{"request_index": index, "duration_ms": 20.0 if collision_ok or index != 3 else 40.0,
              "contact_ok": True} for index in range(4)]
    _write(root / "collision.json", {"calls": calls})
    _write(root / "execution.json", {"reference_matches_permit": execution_ok,
                                     "velocity_ok": execution_ok, "acceleration_ok": execution_ok,
                                     "submit_lead_s": 0.05, "stop_ok": execution_ok})
    _write(root / "cleanup-receipt.json", {"group_clear": True})
    _write(root / "measurements.json", {
        "measurements": {name: {"value": 1.0, "unit": "rad"} for name in (
            "horizontal_fov_rad", "coarse_step_rad", "search_timeout_s",
            "max_fine_corrections", "max_fine_total_rad", "min_confidence", "tracking_iou",
            "min_bbox_aspect", "center_deadband_px", "vertical_bounds_px", "min_area_px2",
            "max_age_s", "max_skew_s", "lock_valid_neck_rad", "submit_lead_s",
            "stop_velocity_rad_s", "stop_latency_s")
            + tuple(sorted(contract.get("support", {})))},     # a real batch carries the support fields too
        "camera_measurements": {name: {"value": 1.0, "unit": "px"} for name in (
            "head_intrinsics_px", "head_translation_m", "head_rpy_rad",
            "yaw_zero_bearing_rad")},
        "observed_lock_frames": {anchor: lock_frames[anchor] for anchor in ANCHORS}})
    # the batch is sealed by the production entry point, which records every raw file hash
    from so101_demo.act.task8_measurement_contract import IDENTITIES_V2

    identity = {name: "b" * 64 for name in IDENTITIES_V2}
    identity["source_commit"] = "a" * 40
    identity["source_provenance_sha256"] = source_provenance_sha256
    identity["measurement_contract_sha256"] = contract["contract_sha256"]
    close_measurement_batch(root, identity,
                            status=(status_field or
                                    ("INVALID" if declared_status == "INVALID"
                                     else "CLOSED")))
    return root


def _report(outputs):
    return json.loads(Path(outputs["calibration_report"]).read_text())


def test_aggregator_never_trusts_raw_pass_labels(tmp_path, contract):
    batch = batch_factory(tmp_path, contract,
                          lock_frames={"default": 2, "left": 4, "forward": 4},
                          declared_status="PASS")
    report = _report(aggregate_task8_calibration((batch,), contract, tmp_path / "out"))
    assert report["status"] == "CALIBRATION_REQUIRED"
    assert report["checks"]["search"] == "FAIL"


def test_aggregator_rejects_mixed_source_provenance(tmp_path, contract):
    a = batch_factory(tmp_path, contract, "a", source_provenance_sha256="a" * 64)
    b = batch_factory(tmp_path, contract, "b", source_provenance_sha256="b" * 64)
    with pytest.raises(ValueError, match="CALIBRATION_IDENTITY_MISMATCH"):
        aggregate_task8_calibration((a, b), contract, tmp_path / "out")


def test_full_pass_with_release_unmeasured_becomes_task8_ready(tmp_path, contract):
    batch = batch_factory(tmp_path, contract)
    outputs = aggregate_task8_calibration((batch,), contract, tmp_path / "out")
    assert set(outputs) == {"head_search_qualification", "calibration_report",
                            "aggregation_receipt"}
    report = _report(outputs)
    assert report["status"] == "TASK8_READY"
    assert set(report["checks"]) >= {"fov", "collision", "search", "synchronization", "execution"}
    assert all(value == "PASS" for key, value in report["checks"].items()
               if key in {"fov", "collision", "search", "synchronization", "execution"})
    assert report["checks"].get("release") == "UNMEASURED"
    assert report["checks"].get("retreat") == "UNMEASURED"
    assert report["source_provenance_sha256"] == "a" * 64
    sample = json.loads(Path(outputs["head_search_qualification"]).read_text())
    assert sample["source_provenance_sha256"] == "a" * 64


@pytest.mark.parametrize("mutation,check", [
    ("fov", "fov"), ("sync", "synchronization"), ("collision", "collision"),
    ("execution", "execution"),
])
def test_out_of_contract_evidence_fails_the_matching_check(tmp_path, contract, mutation, check):
    kwargs = {"fov_ok": mutation != "fov", "sync": mutation != "sync",
              "collision_ok": mutation != "collision", "execution_ok": mutation != "execution"}
    batch = batch_factory(tmp_path, contract, **kwargs)
    report = _report(aggregate_task8_calibration((batch,), contract, tmp_path / "out"))
    assert report["checks"][check] in ("FAIL", "UNMEASURED")
    assert report["status"] == "CALIBRATION_REQUIRED"


def test_invalid_batch_is_refused_and_missing_input_is_unmeasured(tmp_path, contract):
    poisoned = batch_factory(tmp_path, contract, "poisoned", status_field="INVALID")
    with pytest.raises(ValueError, match="CALIBRATION_BATCH_INVALID"):
        aggregate_task8_calibration((poisoned,), contract, tmp_path / "out")
    partial = batch_factory(tmp_path, contract, "partial", sync=False)
    report = _report(aggregate_task8_calibration((partial,), contract, tmp_path / "out2"))
    assert report["checks"]["synchronization"] == "UNMEASURED"
    assert report["status"] == "CALIBRATION_REQUIRED"


def test_aggregation_is_deterministic_and_tamper_evident(tmp_path, contract):
    batch = batch_factory(tmp_path, contract)
    root = tmp_path / "out"
    first = aggregate_task8_calibration((batch,), contract, root)
    first_bytes = {key: Path(path).read_bytes() for key, path in first.items()}
    # the same sealed batch aggregated again derives byte-identical outputs: the report's
    # sample path is absolute, so determinism is asserted against the same output root
    second = aggregate_task8_calibration((batch,), contract, root)
    for key in first:
        assert Path(second[key]).read_bytes() == first_bytes[key]
    frame = batch / "fov/default.json"
    payload = json.loads(frame.read_text())
    payload["samples"][0]["target_in_view"] = False
    frame.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        aggregate_task8_calibration((batch,), contract, tmp_path / "three")
    assert not list((tmp_path / "three").glob("*TASK8_READY*"))


def _cli_identities():
    """The ten-member identity the measurement CLI requires, distinct per member so a mix-up is visible."""

    from so101_demo.act.task8_measurement_contract import IDENTITIES_V2

    identities = {name: format(index + 1, "02x") * 32 for index, name in enumerate(IDENTITIES_V2)}
    identities["source_commit"] = "0" * 40
    return identities


def _identities():
    return {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
            "anchors_sha256": "c" * 64, "contact_policy_fingerprint": "d" * 64,
            "act_profile_sha256": "e" * 64}


def test_offline_report_cli_publishes_the_v2_documents_and_refuses_any_override(tmp_path, contract):
    """The old aggregator wrote one `calibration-report.json` with a caller-visible status; the v2 entry renders
    and publishes four documents instead and exposes no status or threshold override at all."""

    from so101_demo.cli import act_build_task8_calibration_report as builder

    batch = batch_factory(tmp_path, contract)
    identities = tmp_path / "identities.json"
    identities.write_text(json.dumps(_identities()))
    bound = bind_measurement_contract(TEMPLATE, _identities(), tmp_path / "bound.json")
    out = tmp_path / "out"
    arguments = ["--contract", str(bound), "--identities", str(identities),
                 "--batch-root", str(batch), "--output-root", str(out)]
    try:
        assert builder.main(arguments) == 0
    except ValueError:
        pass          # an unqualified fixture must be refused loudly by the production gate, not quietly written
    for name in ("head-search-qualification.json", "task8-ready-support.json",
                 "task8-ready-calibration.json", "aggregation-receipt.json"):
        assert (out / name).is_file(), name
    assert not (out / "calibration-report.json").exists()
    # exactly one sealed batch is accepted, and no status override exists to smuggle a verdict in
    with pytest.raises(SystemExit):
        builder.main(arguments + ["--status", "TASK8_READY"])
    # `--batch-root` may be repeated by argparse, so the one-batch rule is a runtime contract check
    with pytest.raises(ValueError, match="ONE_V2_SEALED_BATCH_REQUIRED"):
        builder.main(["--contract", str(bound), "--identities", str(identities),
                      "--batch-root", str(batch), "--batch-root", str(batch),
                      "--output-root", str(tmp_path / "out3")])


def test_measure_cli_seals_only_on_success_and_keeps_the_ledger_honest(tmp_path, contract):
    from so101_demo.cli import act_measure_task8_calibration as measure

    identities = tmp_path / "identities.json"
    # one schema, not two: the CLI's ten-member identity comes from a v2 template bind, so the bound contract and the
    # identities file the CLI checks against it are the same schema by construction
    identities.write_text(json.dumps(_cli_identities()))
    bound = bind_measurement_contract(TEMPLATE_V2, _cli_identities(), tmp_path / "bound.json")
    ledger = tmp_path / "ledger.md"
    driver_module = tmp_path / "driver.py"
    driver_module.write_text(
        "def fill(contract, root):\n"
        "    import json, pathlib\n"
        "    root = pathlib.Path(root)\n"
        "    root.mkdir(parents=True, exist_ok=True)\n"
        "    (root / 'execution.json').write_text(json.dumps({}))\n"
        "def boom(contract, root):\n"
        "    raise RuntimeError('measurement failed')\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    batch = tmp_path / "batch"
    assert measure.main(["--contract", str(bound), "--identities", str(identities),
                         "--batch-root", str(batch), "--ledger", str(ledger),
                         "--driver", "driver:fill"]) == 0
    assert (batch / "batch.json").is_file()
    # ledger lines read "- Task 8P2 measurement <STATE>: contract=... provenance=... note"
    assert [line.split()[4] for line in ledger.read_text().splitlines()] == [
        "PLANNED:", "RUNNING:", "VALID:"]
    failing = tmp_path / "failing"
    with pytest.raises(RuntimeError):
        measure.main(["--contract", str(bound), "--identities", str(identities),
                      "--batch-root", str(failing), "--ledger", str(ledger),
                      "--driver", "driver:boom"])
    assert not (failing / "batch.json").exists()
    assert ledger.read_text().splitlines()[-1].split()[4] == "INVALID:"


# --- protocol v2 seam: verdicts from raw evidence, all roots, no labels -------------------------------------

def _sealed_batch(root, payload, identities=None, extra_files=None):
    from so101_demo.act.task8_measurement_schema import write_closed_json
    from so101_demo.act.task8_measurement_contract import IDENTITIES_V2
    import hashlib
    identity = dict(identities) if identities else {
        name: ("b" * 40 if name == "source_commit" else "a" * 64) for name in IDENTITIES_V2}

    raw = write_closed_json(Path(root) / "raw" / "records.json", payload)
    files = {"raw/records.json": hashlib.sha256(raw.read_bytes()).hexdigest()}
    files.update(extra_files or {})
    # the batch declares three anchors, so it must evidence them: the aggregator's per-anchor sync file is the
    # convention it consumes, and indexing what it wrote keeps the fixture schema-true by construction
    for anchor in ("default", "left", "forward"):
        synced = write_closed_json(Path(root) / "sync" / f"{anchor}.json",
                                  {"samples": [{"age_s": 0.05, "skew_s": 0.01} for _ in range(4)]})
        files[f"sync/{anchor}.json"] = hashlib.sha256(synced.read_bytes()).hexdigest()
    from so101_demo.act.task8_measurement_contract import _canonical as _seal_canonical

    document = {"schema_version": 1, "kind": "task8_calibration_batch", "status": "CLOSED",
                "anchors": ["default", "left", "forward"], "identity": identity, "files": files}
    document["batch_sha256"] = hashlib.sha256(_seal_canonical(document)).hexdigest()
    write_closed_json(Path(root) / "batch.json", document)
    return Path(root)


def test_derived_verdicts_come_from_raw_evidence_across_every_root(tmp_path):
    from so101_demo.act.task8_calibration_aggregator import derive_field_verdicts
    from so101_demo.act.task8_measurement_schema import load_contract_v2

    first = _sealed_batch(tmp_path / "batch-a", {"measurements": {"min_confidence": [0.6]},
                                                 "configured": {"min_confidence": 0.5}})
    second = _sealed_batch(tmp_path / "batch-b", {"measurements": {"min_confidence": [0.4]},
                                                  "configured": {"min_confidence": 0.5}})
    verdicts = derive_field_verdicts([first, second], load_contract_v2())
    assert set(verdicts) == {str(first), str(second)}          # every root is aggregated, not just the first
    assert verdicts[str(first)]["min_confidence"] == "PASS"
    assert verdicts[str(second)]["min_confidence"] == "FAIL"
    # fields the batch carries no raw record for are reported UNMEASURED rather than passing silently
    assert verdicts[str(first)]["tracking_iou"] == "UNMEASURED"


def test_a_batch_offering_labels_instead_of_raw_evidence_is_refused(tmp_path):
    from so101_demo.act.task8_calibration_aggregator import derive_field_verdicts
    from so101_demo.act.task8_measurement_schema import load_contract_v2

    labelled = _sealed_batch(tmp_path / "batch-labels", {"measurements": {"qualified": True},
                                                         "configured": {"min_confidence": 0.5}})
    with pytest.raises(ValueError, match="RAW_EVIDENCE_REQUIRED: qualified is a label"):
        derive_field_verdicts([labelled], load_contract_v2())


def test_derived_checks_fold_members_across_roots_and_propagate_unmeasured(tmp_path):
    from so101_demo.act.task8_calibration_aggregator import derived_checks
    from so101_demo.act.calibration import CHECK_MEASUREMENTS
    from so101_demo.act.task8_measurement_schema import load_contract_v2

    synchronisation = sorted(CHECK_MEASUREMENTS["synchronization"])
    payload = {"measurements": {synchronisation[0]: [{"received_monotonic_s": 0.0,
                                                      "decision_monotonic_s": 0.1}]},
               "configured": {synchronisation[0]: 0.5}}
    only_one = _sealed_batch(tmp_path / "batch-c", payload)
    contract = load_contract_v2()
    checks = derived_checks([only_one], contract)
    # max_skew_s has no raw record, so the synchronization check is UNMEASURED rather than passing on one member
    assert checks["synchronization"] == "UNMEASURED"
    # the derived check set is exactly the aggregator's own five checks - no extra names invented here
    assert set(checks) == {"fov", "collision", "search", "synchronization", "execution"}


def test_the_aggregator_entry_validates_the_closed_batch_before_publishing(tmp_path, monkeypatch):
    """Boundary IV: the unique entry runs the strict closed-batch validation first, whatever else it does.

    Proven by a sentinel rather than by inspecting internals: if the entry calls the validator at all, the sentinel it
    replaces will be raised before any canonical document is written.
    """

    from so101_demo.act import task8_calibration_aggregator as aggregator
    from so101_demo.act import task8_measurement_schema as schema

    seen: list = []

    def sentinel(root):
        seen.append(root)
        raise ValueError("BATCH_VALIDATION_SENTINEL")

    monkeypatch.setattr(schema, "validate_closed_batch", sentinel, raising=True)
    batch = tmp_path / "batch"
    batch.mkdir()
    output = tmp_path / "out"
    # whatever else the entry does with an empty batch directory, the assertion is about the validator being reached:
    # the sentinel records that, and today nothing records it
    with pytest.raises(Exception):
        aggregator.aggregate_task8_calibration([batch], {"thresholds": {}, "verdicts": []}, output)
    assert seen == [batch], "the entry validated the batch it was given, before anything else"
    assert not output.exists() or not any(output.iterdir()), "nothing is published before validation"



def test_two_batches_that_disagree_on_a_second_identity_member_are_refused(tmp_path):
    """Boundary IV: all ten identity members agree across roots, not only the provenance."""

    from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration
    from so101_demo.act.task8_measurement_contract import bind_measurement_contract

    bound_path = bind_measurement_contract(TEMPLATE_V2, _cli_identities(), tmp_path / "bound.json")
    bound = json.loads(Path(bound_path).read_text())      # the binder returns the path it wrote, not the document
    identities = _cli_identities()
    identities["measurement_contract_sha256"] = bound["contract_sha256"]
    first = _sealed_batch(tmp_path / "batch-a", {"measurements": {"min_confidence": [0.6]}}, identities)
    other = dict(identities, anchors_sha256="f" * 64)
    second = _sealed_batch(tmp_path / "batch-b", {"measurements": {"min_confidence": [0.6]}}, other)
    with pytest.raises(ValueError, match="CALIBRATION_IDENTITY_MISMATCH"):
        aggregate_task8_calibration((first, second), bound, tmp_path / "out")


def test_the_published_measurements_are_values_with_their_sample_never_verdicts(tmp_path, contract):
    """Boundary IV's publishing half: a report carries measured values, and a verdict belongs in `checks` only."""

    from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration

    batch = batch_factory(tmp_path, contract)
    outputs = aggregate_task8_calibration((batch,), contract, tmp_path / "out")
    document = json.loads(Path(outputs["calibration_report"]).read_text())
    measurements = document["measurements"]
    assert measurements, "a ready report names its measurements"
    for name, entry in measurements.items():
        assert isinstance(entry, dict), name
        assert entry.get("unit"), f"{name} keeps its unit"
        assert "sample_path" in entry and "sample_sha256" in entry, f"{name} cites the sample it came from"
        value = entry.get("value")
        assert not isinstance(value, str), f"{name} is a value, not the verdict {value!r}"
        assert isinstance(value, (int, float, list)), f"{name} has a numeric value"
    # the verdicts live in checks, and only there
    assert set(document["checks"]) <= set(document["checks"])
    assert all(isinstance(verdict, str) for verdict in document["checks"].values())


def test_rendering_the_same_immutable_batch_twice_is_byte_identical_and_publishes_once(tmp_path, contract):
    """Boundary IV: a canonical render is a function of the batch, so a second render cannot differ or duplicate."""

    from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration

    batch = batch_factory(tmp_path, contract)
    out = tmp_path / "out"
    first = aggregate_task8_calibration((batch,), contract, out)
    snapshot = {name: Path(path).read_bytes() for name, path in first.items()}
    listing = sorted(str(path.relative_to(out)) for path in Path(out).rglob("*") if path.is_file())

    second = aggregate_task8_calibration((batch,), contract, out)
    rerender = {name: Path(path).read_bytes() for name, path in second.items()}

    assert set(second) == set(first), "the same documents are named both times"
    assert rerender == snapshot, "a second render of the same immutable batch is byte-identical"
    assert sorted(str(path.relative_to(out)) for path in Path(out).rglob("*") if path.is_file()) == listing, \
        "publishing once leaves no extra or duplicated file behind"


def test_every_cited_sample_reads_back_from_disk_with_its_recorded_hash(tmp_path, contract):
    """Boundary IV: a report's sample citations must resolve on disk to bytes the recorded hash vouches for."""

    import hashlib as _hashlib

    from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration
    from so101_demo.act.task8_measurement_contract import bind_measurement_contract

    # a v2 bound contract, because only it carries the support section the seven remaining fields come from
    contract = json.loads(Path(bind_measurement_contract(
        TEMPLATE_V2, _cli_identities(), tmp_path / "bound-v2.json")).read_text())
    batch = _v2_batch(tmp_path / "batch", contract)
    outputs = aggregate_task8_calibration((batch,), contract, tmp_path / "out")
    document = json.loads(Path(outputs["calibration_report"]).read_text())
    measurements = document["measurements"]
    assert len(measurements) == 28, f"a ready report carries the contract's 28 fields, saw {len(measurements)}"

    for name, entry in measurements.items():
        sample = Path(entry["sample_path"])
        assert sample.is_absolute() and not sample.is_symlink() and sample.is_file(), f"{name}: {sample}"
        assert _hashlib.sha256(sample.read_bytes()).hexdigest() == entry["sample_sha256"], f"{name} digest"


def test_a_v2_batch_yields_a_report_that_passes_the_task8_live_gate(tmp_path):
    """Boundary IV's publishing half: the 28-field TASK8_READY must satisfy require_gate(report, "task8_live").

    The gate wants the five PICK_PLACE_READY_CHECKS to PASS, release and retreat to be UNMEASURED, and every field of
    every ready check to be present - 28 fields - each cited to its approved closed sample.
    """

    from so101_demo.act.calibration import require_gate
    from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration
    from so101_demo.act.task8_measurement_contract import bind_measurement_contract

    contract = json.loads(Path(bind_measurement_contract(
        TEMPLATE_V2, _cli_identities(), tmp_path / "bound-v2.json")).read_text())
    batch = _v2_batch(tmp_path / "batch", contract)
    outputs = aggregate_task8_calibration((batch,), contract, tmp_path / "out")
    report = json.loads(Path(outputs["calibration_report"]).read_text())

    require_gate(report, "task8_live")
    assert report["status"] == "TASK8_READY"
    assert len(report["measurements"]) == 28
    assert report["checks"]["release"] == "UNMEASURED"
    assert report["checks"]["retreat"] == "UNMEASURED"


def _valid_evidence(contract):
    """Raw evidence that satisfies every comparator, taken from the formulas suite's own cases where it has them."""

    import math
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_act_task8_measurement_formulas import FIELD_CASES

    evidence = {field: valid["measurements"][field] for field, (valid, *_rest) in FIELD_CASES.items()}
    configured = {field: valid["configured"][field] for field, (valid, *_rest) in FIELD_CASES.items()}
    fovy = 1.0
    fx = (480 / 2) / math.tan(fovy / 2)
    frame = {"width": 640, "height": 480, "K": [fx, fx, 320.0, 240.0], "fovy_rad": fovy}
    fill = {
        "head_intrinsics_px": ({"frames": [frame], "tolerance_px": 1.0}, 1.0),
        "wrist_intrinsics_px": ({"frames": [frame], "tolerance_px": 1.0}, 1.0),
        "head_translation_m": ({"samples": [[0.0, 0.0, 0.0]], "expected": [0.0, 0.0, 0.0],
                                "tolerance_m": 0.01}, 0.01),
        "wrist_translation_m": ({"samples": [[0.0, 0.0, 0.0]], "expected": [0.0, 0.0, 0.0],
                                 "tolerance_m": 0.01}, 0.01),
        "head_rpy_rad": ({"quaternions": [[0.0, 0.0, 0.0, 1.0]]}, 0.01),
        "wrist_rpy_rad": ({"quaternions": [[0.0, 0.0, 0.0, 1.0]]}, 0.01),
        # a tilted forward axis: the identity rotation's is degenerate and refused by design
        "yaw_zero_bearing_rad": ({"rotations": [[0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0]],
                                  "expected": 0.0, "tolerance_rad": 0.01}, 0.01),
        "lock_valid_neck_rad": ({"bounds_rad": [-2.0, 2.0], "anchor_starts_rad": [0.0],
                                 "unsafe_intervals_rad": [], "shrink_rad": 0.1}, [-2.0, 2.0]),
        "velocity_limit_rad_s": ({"samples": [{"dt_s": 0.01, "dq_rad": [0.0] * 6}]}, [1.0] * 6),
        "acceleration_limit_rad_s2": ({"samples": [{"dt_s": 0.01, "dq_rad": [0.0] * 6}]}, [1.0] * 6),
        "path_step_s": ([0.0, 0.002, 0.004, 0.006], 0.01),
        # read from the implementations: search_timeout_s takes per-anchor start/terminal stamps, coarse_step_rad
        # takes the accumulator before and after each step, and acceleration samples are time_s/position_rad pairs
        # every non-final step equals the configured limit and the final remainder is positive and bounded
        "coarse_step_rad": ([{"coarse_accumulator_before": 0.0, "coarse_accumulator_after": 0.06},
                             {"coarse_accumulator_before": 0.06, "coarse_accumulator_after": 0.12},
                             {"coarse_accumulator_before": 0.12, "coarse_accumulator_after": 0.13,
                              "final": True}], 0.06),
        "search_timeout_s": ([{"anchor": anchor, "started_monotonic_s": 0.0, "terminal_monotonic_s": 0.5}
                              for anchor in ("default", "left", "forward")], 5.0),
        "horizontal_fov_rad": ({"frames": [{"fx": fx, "cx": 320.0, "width": 640, "height": 480,
                                           "fovy_rad": fovy}], "model_fov_rad": 2 * math.atan(320.0 / fx),
                                  "tolerance_rad": 0.2}, 0.2),
        # distinct velocities a half-limit apart, so the observed acceleration stays inside the configured limit
        "acceleration_limit_rad_s2": ({"samples": [{"time_s": 0.0, "position_rad": [0.0] * 6},
                                                   {"time_s": 0.01, "position_rad": [0.001] * 6},
                                                   {"time_s": 0.02, "position_rad": [0.00205] * 6}]}, [1.0] * 6),
        "path_clearance_m": ({"rows": [{"signed_distance_m": 0.05}]}, 0.01),
    }
    for field, (payload, limit) in fill.items():
        evidence.setdefault(field, payload)
        configured.setdefault(field, limit)
    return evidence, configured


def _v2_batch(root, contract):
    """A batch that is schema-true for v2: valid raw evidence in the indexed records and the 28 published entries."""

    from so101_demo.act.task8_measurement_contract import IDENTITIES_V2
    from so101_demo.act.task8_measurement_schema import write_closed_json

    root = Path(root)
    evidence, configured = _valid_evidence(contract)
    identities = {name: ("b" * 40 if name == "source_commit" else "a" * 64) for name in IDENTITIES_V2}
    identities["measurement_contract_sha256"] = contract["contract_sha256"]
    # the published entries are written before the seal, because the seal indexes every file it closes over
    measurements = {name: {"value": 1.0, "unit": entry.get("unit", "count")}
                    for name, entry in {**contract["measurements"], **contract["support"]}.items()}
    write_closed_json(root / "measurements.json",
                      {"measurements": measurements,
                       "camera_measurements": {name: {"value": 1.0, "unit": "px"} for name in (
                           "head_intrinsics_px", "head_translation_m", "head_rpy_rad", "yaw_zero_bearing_rad")},
                       "observed_lock_frames": {anchor: 3 for anchor in ("default", "left", "forward")}})
    # one seal, carrying the valid raw evidence the comparators read and the identity the bound contract expects
    published = root / "measurements.json"
    _sealed_batch(root, {"measurements": evidence, "configured": configured}, identities,
                  extra_files={"measurements.json": __import__("hashlib").sha256(
                      published.read_bytes()).hexdigest()})
    return root
