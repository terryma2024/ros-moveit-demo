"""Task 8P2: the measurement contract is bound to frozen identities before measuring."""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.task8_measurement_contract import (
    bind_measurement_contract, close_measurement_batch, load_measurement_contract,
)

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = PACKAGE / "config/act/task8-calibration-measurement-contract-v1.json"
ANCHORS = ["default", "left", "forward"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def identities():
    return {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
            "anchors_sha256": _sha(PACKAGE / "config/act/task8-live-anchors.yaml"),
            "contact_policy_fingerprint": "c" * 64, "act_profile_sha256": "d" * 64}


def test_bind_records_every_source_hash_and_refuses_the_unbound_template(tmp_path, identities):
    output = tmp_path / "contract.json"
    bound = bind_measurement_contract(TEMPLATE, identities, output)
    assert bound == output and output.is_file()
    document = load_measurement_contract(output, expected_hashes=identities)
    assert document["identities"] == identities
    assert document["source_hashes"]["template"] == _sha(TEMPLATE)
    with pytest.raises(ValueError):
        load_measurement_contract(TEMPLATE, expected_hashes=identities)   # template is unbound


def test_bind_refuses_to_overwrite_and_rejects_wrong_identity(tmp_path, identities):
    output = tmp_path / "contract.json"
    bind_measurement_contract(TEMPLATE, identities, output)
    with pytest.raises(ValueError):
        bind_measurement_contract(TEMPLATE, identities, output)
    mismatched = dict(identities, runtime_config_sha256="e" * 64)
    with pytest.raises(ValueError, match="MEASUREMENT_CONTRACT_IDENTITY_MISMATCH"):
        load_measurement_contract(output, expected_hashes=mismatched)


def test_bound_contract_carries_the_frozen_thresholds(tmp_path, identities):
    bound = bind_measurement_contract(TEMPLATE, identities, tmp_path / "contract.json")
    document = load_measurement_contract(bound, expected_hashes=identities)
    assert document["thresholds"]["search"]["min_consecutive_lock_frames"] == 3
    assert document["thresholds"]["fov"]["sample_period_s"] == 0.002
    assert document["thresholds"]["collision"]["full_request_budget_ms"] == 25
    assert document["thresholds"]["collision"]["full_request_count"] == 4
    # the contract carries exactly the three frozen anchors, in the template order
    assert document["anchors"] == ANCHORS
    assert sorted(document["anchors"]) == sorted(ANCHORS)


def test_batch_close_is_one_way_and_identity_bound(tmp_path):
    root = tmp_path / "batch"
    # the batch carries the contract's ten-member identity: the schema that admitted the measurement seals it
    from so101_demo.act.task8_measurement_contract import IDENTITIES_V2

    identity = {name: "a" * 64 for name in IDENTITIES_V2}
    identity["source_commit"] = "0" * 40
    sealed = close_measurement_batch(root, identity)
    assert Path(sealed).is_file()
    with pytest.raises(ValueError):
        close_measurement_batch(root, identity)
    document = json.loads(Path(sealed).read_text())
    assert document["identity"] == identity
    assert document["status"] == "CLOSED"


# --- Task 1 (approved measurement protocol v2): contract fixtures, batch closure, closed schemas -----------

HEAD_SEARCH_FIELDS = frozenset({
    "head_intrinsics_px", "head_translation_m", "head_rpy_rad", "yaw_zero_bearing_rad",
    "horizontal_fov_rad", "coarse_step_rad", "search_timeout_s", "max_fine_corrections",
    "max_fine_total_rad", "min_confidence", "tracking_iou", "min_bbox_aspect",
    "center_deadband_px", "vertical_bounds_px", "min_area_px2", "max_age_s", "max_skew_s",
    "lock_valid_neck_rad", "submit_lead_s", "stop_velocity_rad_s", "stop_latency_s",
})
SUPPORT_FIELDS = frozenset({
    "wrist_intrinsics_px", "wrist_translation_m", "wrist_rpy_rad", "velocity_limit_rad_s",
    "acceleration_limit_rad_s2", "path_step_s", "path_clearance_m",
})
IDENTITY_MEMBERS = (
    "source_commit", "config_sha256", "source_provenance_sha256", "runtime_config_sha256",
    "anchors_sha256", "contact_policy_fingerprint", "act_profile_sha256",
    "measurement_contract_sha256", "phase_camera_matrix_sha256", "driver_source_sha256",
)
EXPECTED_OCCLUDERS = [
    "fixed_fingertip_pad_visual",
    "gripper_visual_00",
    "gripper_visual_01",
    "jaw_visual_00",
    "moving_fingertip_pad_visual",
]


def test_contract_v2_freezes_the_21_head_search_fields_with_calibration_units():
    from so101_demo.act.calibration import REQUIRED_MEASUREMENTS
    from so101_demo.act.task8_measurement_schema import load_contract_v2

    document = load_contract_v2()
    assert set(document["measurements"]) == HEAD_SEARCH_FIELDS
    assert len(HEAD_SEARCH_FIELDS) == 21
    for name, entry in document["measurements"].items():
        assert entry["unit"] == REQUIRED_MEASUREMENTS[name][0], name
        assert set(entry) >= {"unit", "source_kind", "comparator", "formula_id", "window",
                              "threshold_source", "failure_code"}, name


def test_contract_v2_freezes_the_seven_support_fields():
    from so101_demo.act.calibration import REQUIRED_MEASUREMENTS
    from so101_demo.act.task8_measurement_schema import load_contract_v2

    document = load_contract_v2()
    assert set(document["support"]) == SUPPORT_FIELDS
    assert len(SUPPORT_FIELDS) == 7
    for name, entry in document["support"].items():
        assert entry["unit"] == REQUIRED_MEASUREMENTS[name][0], name


def test_identity_binds_exactly_the_ten_approved_members():
    from so101_demo.act.task8_measurement_schema import MeasurementIdentity

    assert MeasurementIdentity.MEMBERS == IDENTITY_MEMBERS
    assert len(IDENTITY_MEMBERS) == 10


def test_phase_camera_matrix_rejects_a_changed_occluder_list(tmp_path):
    from so101_demo.act.task8_measurement_schema import load_phase_camera_matrix

    document = load_phase_camera_matrix()
    assert document["occluders"] == EXPECTED_OCCLUDERS
    broken = tmp_path / "matrix.json"
    broken.write_text(json.dumps({**document, "occluders": EXPECTED_OCCLUDERS[:-1]}))
    with pytest.raises(ValueError, match="PHASE_CAMERA_OCCLUDERS_INVALID"):
        load_phase_camera_matrix(broken)


def test_closed_batch_accepts_an_indexed_batch_and_rejects_closure_violations(tmp_path):
    from so101_demo.act.task8_measurement_schema import validate_closed_batch, write_closed_json

    root = tmp_path / "batch"
    root.mkdir()
    raw = write_closed_json(root / "raw" / "default.json", {"value": 1})
    identity = {name: "a" * 64 for name in IDENTITY_MEMBERS}
    identity["source_commit"] = "b" * 40
    batch = {"schema_version": 1, "kind": "task8_calibration_batch", "status": "CLOSED",
             "anchors": ["default", "left", "forward"], "batch_sha256": "0" * 64,
             "identity": identity,
             "files": _index_anchor_evidence(root, {str(raw.relative_to(root)): hashlib.sha256(raw.read_bytes()).hexdigest()},
                                             write_closed_json, hashlib)}
    from so101_demo.act.task8_measurement_contract import _canonical as _seal_canonical

    batch.pop("batch_sha256")
    batch["batch_sha256"] = hashlib.sha256(_seal_canonical(batch)).hexdigest()
    write_closed_json(root / "batch.json", batch)

    validated = validate_closed_batch(root)
    assert validated.identity["measurement_contract_sha256"] == "a" * 64

    (root / "unindexed.json").write_text("{}")
    with pytest.raises(ValueError, match="BATCH_CLOSURE_INVALID"):
        validate_closed_batch(root)

    (root / "unindexed.json").unlink()
    (root / "raw" / "extra.json").write_text("{}")
    with pytest.raises(ValueError, match="BATCH_CLOSURE_INVALID"):
        validate_closed_batch(root)
    (root / "raw" / "extra.json").unlink()

    raw.unlink()
    with pytest.raises(ValueError, match="BATCH_CLOSURE_INVALID"):
        validate_closed_batch(root)

    # rewriting the raw file with different bytes trips the digest check first; the canonical bytes are
    # b'{"value":1}' (no spaces), restored directly because write_closed_json refuses an existing target
    raw.write_bytes(b'{"value":1}')
    target = root / "link.json"
    target.symlink_to(raw)
    with pytest.raises(ValueError, match="BATCH_PATH_INVALID"):
        validate_closed_batch(root)


def test_closing_a_batch_refuses_an_identity_that_is_not_the_contract_identity(tmp_path):
    """Boundary I: the sealed batch must carry the contract's ten-member identity, not whatever the caller held.

    The CLI today seals with a two-key mapping it builds for its ledger line, so this asserts the schema boundary the
    contract already defines: an identity that is not ``IDENTITIES_V2`` cannot close a batch.
    """

    from so101_demo.act.task8_measurement_contract import (IDENTITIES_V2, close_measurement_batch,
                                                          require_v2_identity)

    batch = tmp_path / "batch"
    batch.mkdir()
    two_key = {"source_provenance_sha256": "a" * 64, "contract_sha256": "b" * 64}
    assert tuple(sorted(IDENTITIES_V2)) != tuple(sorted(two_key)), "the fixture must not be a valid identity"
    with pytest.raises(ValueError, match="MEASUREMENT_BATCH_IDENTITY_INVALID"):
        close_measurement_batch(batch, two_key)
    with pytest.raises(ValueError, match="MEASUREMENT_CONTRACT_IDENTITY_INVALID"):
        require_v2_identity(two_key)


def test_the_measurement_cli_requires_a_context_document_separate_from_the_identity(tmp_path):
    """Boundary I: runtime/admission inputs belong to a context document, not to the identity mapping.

    Today the CLI reads ``measurement_plan_sha256``, ``safe_interval_rad``, ``candidate_sha256``, ``policy_sha256``,
    ``controller_generation``, ``broker_generation`` and ``resource_binding`` out of the identities file, so a document
    that carries only the contract's ten identity members fails with a bare ``KeyError`` instead of a named refusal.
    """

    from so101_demo.cli.act_measure_task8_calibration import main

    # a bound v2 contract plus an identities file carrying exactly the contract's ten identity members, so the run
    # reaches the context boundary instead of stopping at an unbound template or a missing file
    from so101_demo.act.task8_measurement_contract import (IDENTITIES_V2, KIND, SCHEMA_VERSION_V2,
                                                          _contract_sha256)

    identities = {name: "a" * 64 for name in IDENTITIES_V2}
    identities["source_commit"] = "0" * 40
    document = {"schema_version": SCHEMA_VERSION_V2, "kind": KIND, "identities": identities,
                "source_hashes": {"anchors": "b" * 64}, "bound_files": {"anchors": "config/act/anchors.yaml"},
                "measurements": {}, "support": {}}
    document["contract_sha256"] = _contract_sha256(document)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(document))
    identities_path = tmp_path / "identities.json"
    identities_path.write_text(json.dumps(identities))
    argv = ["--contract", str(contract_path),
            "--identities", str(identities_path),
            "--batch-root", str(tmp_path / "batch"),
            "--ledger", str(tmp_path / "ledger.md")]
    with pytest.raises(ValueError, match="MEASUREMENT_CONTEXT_REQUIRED"):
        main(argv)


def _bound_contract(tmp_path):
    """A bound v2 contract plus the identities file that matches it - the pair the CLI's admission requires."""

    from so101_demo.act.task8_measurement_contract import (IDENTITIES_V2, KIND, SCHEMA_VERSION_V2,
                                                          _contract_sha256)

    identities = {name: "a" * 64 for name in IDENTITIES_V2}
    identities["source_commit"] = "0" * 40
    document = {"schema_version": SCHEMA_VERSION_V2, "kind": KIND, "identities": identities,
                "source_hashes": {"anchors": "b" * 64}, "bound_files": {"anchors": "config/act/anchors.yaml"},
                "measurements": {}, "support": {}}
    document["contract_sha256"] = _contract_sha256(document)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(document))
    identities_path = tmp_path / "identities.json"
    identities_path.write_text(json.dumps(identities))
    return contract_path, identities_path


def test_the_cli_is_the_only_batch_seal_owner(tmp_path, monkeypatch):
    """One seal owner: a driver writes raw evidence, the CLI closes the batch - and a driver that seals first wins.

    The rule the review asks for, asserted behaviourally rather than by documentation: whichever side seals, the batch
    carries exactly one seal and the later attempt is refused by name.
    """

    import sys
    from so101_demo.cli.act_measure_task8_calibration import main

    contract_path, identities_path = _bound_contract(tmp_path)
    driver_dir = tmp_path / "drivers"
    driver_dir.mkdir()
    (driver_dir / "raw_driver.py").write_text(
        "from pathlib import Path\n"
        "def run(contract, batch_root):\n"
        "    root = Path(batch_root)\n"
        "    root.mkdir(parents=True, exist_ok=True)\n"
        "    (root / 'raw.json').write_text('{\"row\": 1}')\n")
    # the CLI hands the driver the *bound contract document*, not a path
    (driver_dir / "sealing_driver.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[0]))\n"
        "from raw_driver import run as write_raw\n"
        "from so101_demo.act.task8_measurement_contract import close_measurement_batch, require_v2_identity\n"
        "def run(contract, batch_root):\n"
        "    write_raw(contract, batch_root)\n"
        "    close_measurement_batch(Path(batch_root), require_v2_identity(contract['identities']))\n")
    monkeypatch.syspath_prepend(str(driver_dir))

    batch_root = tmp_path / "batch"
    ledger = tmp_path / "ledger.md"
    assert main(["--contract", str(contract_path), "--identities", str(identities_path),
                 "--batch-root", str(batch_root), "--ledger", str(ledger),
                 "--driver", "raw_driver:run"]) == 0
    sealed = json.loads((batch_root / "batch.json").read_text())
    assert sealed["status"] == "CLOSED"
    assert "raw.json" in sealed["files"], "the driver's raw evidence is sealed by the CLI"
    assert ledger.read_text().count("VALID") == 1

    # a driver that seals the same batch on its own makes the CLI's later close refuse, by name
    other_root = tmp_path / "batch-two"
    with pytest.raises(ValueError, match="MEASUREMENT_BATCH_ALREADY_CLOSED"):
        main(["--contract", str(contract_path), "--identities", str(identities_path),
              "--batch-root", str(other_root), "--ledger", str(tmp_path / "ledger-two.md"),
              "--driver", "sealing_driver:run"])


def test_a_batch_whose_self_digest_does_not_match_its_document_is_refused(tmp_path):
    """Boundary IV: the validator verifies the seal's self-digest, not merely its shape.

    A batch document carries ``batch_sha256`` computed over itself, which is what makes its identity and status
    uneditable after the fact - so a document whose digest was replaced must be refused, not merely checked for looking
    like a sha256.
    """

    from so101_demo.act.task8_measurement_contract import (IDENTITIES_V2, close_measurement_batch,
                                                          require_v2_identity)
    from so101_demo.act.task8_measurement_schema import validate_closed_batch

    identities = {name: "a" * 64 for name in IDENTITIES_V2}
    identities["source_commit"] = "0" * 40
    root = tmp_path / "batch"
    root.mkdir()
    (root / "raw.json").write_text('{"row": 1}')
    for anchor in ("default", "left", "forward"):                       # the seal declares three, so evidence three
        (root / "sync").mkdir(exist_ok=True)
        (root / "sync" / f"{anchor}.json").write_text('{"samples": []}')
    sealed = Path(close_measurement_batch(root, require_v2_identity(identities)))
    assert validate_closed_batch(root) is not None, "an untouched sealed batch validates"

    document = json.loads(sealed.read_text())
    document["batch_sha256"] = "0" * 64
    sealed.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="BATCH_INVALID"):
        validate_closed_batch(root)


def _index_anchor_evidence(root, files, write_closed_json, hashlib_module):
    """Give a hand-built batch one indexed per-anchor file per anchor it declares."""

    for anchor in ("default", "left", "forward"):
        written = write_closed_json(Path(root) / "sync" / f"{anchor}.json", {"samples": []})
        files[f"sync/{anchor}.json"] = hashlib_module.sha256(written.read_bytes()).hexdigest()
    return files


def test_a_batch_hiding_a_symlink_is_refused_even_when_it_is_indexed(tmp_path):
    """Boundary IV: the closed raw index is regular files only, so an indexed symlink must be refused."""

    import hashlib as _hashlib

    from so101_demo.act.task8_measurement_contract import _canonical as _seal_canonical
    from so101_demo.act.task8_measurement_schema import validate_closed_batch, write_closed_json

    root = tmp_path / "batch"
    (root / "raw").mkdir(parents=True)
    real = root / "raw" / "real.json"
    real.write_text('{"row": 1}')
    link = root / "raw" / "link.json"
    link.symlink_to(real)
    assert link.is_symlink(), "the fixture must actually contain a symlink"

    digest = _hashlib.sha256(real.read_bytes()).hexdigest()
    identity = {name: "a" * 64 for name in IDENTITY_MEMBERS}
    identity["source_commit"] = "b" * 40
    document = {"schema_version": 1, "kind": "task8_calibration_batch", "status": "CLOSED",
                "anchors": ["default", "left", "forward"], "identity": identity,
                "files": _index_anchor_evidence(root, {"raw/real.json": digest, "raw/link.json": digest},
                                                write_closed_json, _hashlib)}
    document["batch_sha256"] = _hashlib.sha256(_seal_canonical(document)).hexdigest()
    write_closed_json(root / "batch.json", document)
    # the rule already exists and is better named than the fixture assumed: an indexed symlink is refused as a path
    # problem rather than as a closure problem, which is the more precise diagnosis
    with pytest.raises(ValueError, match="BATCH_PATH_INVALID"):
        validate_closed_batch(root)


def test_a_batch_records_its_cleanup_and_a_contaminated_one_is_refused(tmp_path):
    """Boundary IV: the driver's own batch document validates, and contamination disqualifies it.

    The measurement driver writes ``cleanup`` and ``contamination`` beside the seal's fields, so the validator must
    accept that shape when cleanup was confirmed - and refuse the batch when it was not, because a contaminated batch
    must never feed a published report.
    """

    import hashlib as _hashlib

    from so101_demo.act.task8_measurement_contract import _canonical as _seal_canonical
    from so101_demo.act.task8_measurement_schema import validate_closed_batch, write_closed_json

    def build(root, contamination):
        (root / "raw").mkdir(parents=True)
        (root / "raw" / "row.json").write_text('{"row": 1}')
        digest = _hashlib.sha256((root / "raw" / "row.json").read_bytes()).hexdigest()
        identity = {name: "a" * 64 for name in IDENTITY_MEMBERS}
        identity["source_commit"] = "b" * 40
        document = {"schema_version": 1, "kind": "task8_calibration_batch", "status": "CLOSED",
                    "anchors": ["default", "left", "forward"], "identity": identity,
                    "files": _index_anchor_evidence(root, {"raw/row.json": digest}, write_closed_json,
                                                    _hashlib),
                    "cleanup": {"requested": {"anchor": "forward", "generation": "gen-1"}, "status": "CONFIRMED"},
                    "contamination": contamination}
        document["batch_sha256"] = _hashlib.sha256(_seal_canonical(document)).hexdigest()
        write_closed_json(root / "batch.json", document)
        return root

    confirmed = build(tmp_path / "clean", None)
    assert validate_closed_batch(confirmed) is not None, "the driver's batch shape validates when cleanup confirmed"

    dirty = build(tmp_path / "dirty", "CLEANUP_REFUSED: RuntimeError")
    with pytest.raises(ValueError, match="BATCH_INVALID"):
        validate_closed_batch(dirty)


def test_a_batch_that_does_not_cover_every_declared_anchor_is_refused(tmp_path):
    """Boundary IV: the raw index closes over anchors, so a declared anchor with no rows disqualifies the batch."""

    import hashlib as _hashlib

    from so101_demo.act.task8_measurement_contract import _canonical as _seal_canonical
    from so101_demo.act.task8_measurement_schema import validate_closed_batch, write_closed_json

    root = tmp_path / "batch"
    (root / "anchors" / "default").mkdir(parents=True)
    (root / "anchors" / "default" / "geometry-00.json").write_text('{"row": 1}')
    digest = _hashlib.sha256((root / "anchors" / "default" / "geometry-00.json").read_bytes()).hexdigest()
    identity = {name: "a" * 64 for name in IDENTITY_MEMBERS}
    identity["source_commit"] = "b" * 40
    document = {"schema_version": 1, "kind": "task8_calibration_batch", "status": "CLOSED",
                "anchors": ["default", "left", "forward"], "identity": identity,
                "files": {"anchors/default/geometry-00.json": digest}}          # only one of three anchors
    document["batch_sha256"] = _hashlib.sha256(_seal_canonical(document)).hexdigest()
    write_closed_json(root / "batch.json", document)

    with pytest.raises(ValueError, match="BATCH_ANCHOR_MISSING"):
        validate_closed_batch(root)


def test_a_driver_batch_that_misses_a_phase_for_an_anchor_is_refused(tmp_path):
    """Boundary IV: when a batch evidences anchors the way the driver does, the nine phases must all be there."""

    import hashlib as _hashlib

    from so101_demo.act.task8_measurement_contract import _canonical as _seal_canonical
    from so101_demo.act.task8_measurement_schema import validate_closed_batch, write_closed_json

    root = tmp_path / "batch"
    files = {}
    for anchor in ("default", "left", "forward"):
        (root / "anchors" / anchor).mkdir(parents=True)
        # eight of the nine phases: RELEASE is missing, which the closure check alone cannot notice
        for index, phase in enumerate(("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN",
                                       "RADIAL_RETREAT", "FINAL_CHECK")):
            written = write_closed_json(root / "anchors" / anchor / f"phase-{index:02d}-{phase.lower()}.json",
                                        {"phase": phase, "index": index})
            files[f"anchors/{anchor}/{written.name}"] = _hashlib.sha256(written.read_bytes()).hexdigest()
    identity = {name: "a" * 64 for name in IDENTITY_MEMBERS}
    identity["source_commit"] = "b" * 40
    document = {"schema_version": 1, "kind": "task8_calibration_batch", "status": "CLOSED",
                "anchors": ["default", "left", "forward"], "identity": identity, "files": files}
    document["batch_sha256"] = _hashlib.sha256(_seal_canonical(document)).hexdigest()
    write_closed_json(root / "batch.json", document)

    with pytest.raises(ValueError, match="BATCH_PHASE_MISSING"):
        validate_closed_batch(root)
