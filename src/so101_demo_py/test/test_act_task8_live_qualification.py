"""Task 8P4 RED: qualification is derived from complete live evidence, never asserted."""

import hashlib
import json
from pathlib import Path

import pytest


def _summary(**overrides):
    digests = [f"{index:064d}" for index in range(1, 15)]
    summary = {"status": "PASSED", "prefix_count": 9, "consecutive_full_count": 5,
               "case_journal_sha256": digests}
    summary.update(overrides)
    return summary


def _sample(tmp_path, name="release.json"):
    path = tmp_path / name
    path.write_text('{"sample": true}')
    return {"sample_path": str(path),
            "sample_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_campaign_summary_requires_passed_complete_and_consecutive():
    from so101_demo.act.task8_live_qualification import validate_campaign_summary

    assert validate_campaign_summary(_summary())["status"] == "PASSED"
    for broken, code in ((_summary(status="FAILED"), "TASK8_QUALIFICATION_NOT_PASSED"),
                         (_summary(prefix_count=8), "TASK8_QUALIFICATION_CASE_COUNT_INVALID"),
                         (_summary(consecutive_full_count=4),
                          "TASK8_QUALIFICATION_FULLS_NOT_CONSECUTIVE"),
                         (_summary(case_journal_sha256=["a" * 64] * 14),
                          "TASK8_QUALIFICATION_JOURNAL_DUPLICATE"),
                         (_summary(case_journal_sha256=["nope"] + [f"{i:064d}"
                                                                   for i in range(2, 15)]),
                          "TASK8_QUALIFICATION_JOURNAL_HASH_INVALID"),
                         (_summary(extra=1), "TASK8_QUALIFICATION_SUMMARY_INVALID")):
        with pytest.raises(ValueError, match=code):
            validate_campaign_summary(broken)


def test_release_sample_requires_support_then_contact_loss_and_a_real_file(tmp_path):
    from so101_demo.act.task8_live_qualification import validate_release_sample

    sample = dict(_sample(tmp_path), supported_before_open=True, contact_lost_after_open=True,
                  stable_window_s=0.5)
    assert validate_release_sample(sample)["stable_window_s"] == 0.5
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_RELEASE_INVALID"):
        validate_release_sample(dict(sample, supported_before_open=False))
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_RELEASE_INVALID"):
        validate_release_sample(dict(sample, contact_lost_after_open=False))
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_SAMPLE_HASH_INVALID"):
        validate_release_sample(dict(sample, sample_sha256="0" * 64))
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_SAMPLE_MISSING"):
        validate_release_sample(dict(sample, sample_path=str(tmp_path / "absent.json")))


def test_retreat_sample_requires_distance_stability_and_the_deadline(tmp_path):
    from so101_demo.act.task8_live_qualification import validate_retreat_sample

    sample = dict(_sample(tmp_path, "retreat.json"), retreat_distance_m=0.06, target_stable=True,
                  completed_s=12.5)
    assert validate_retreat_sample(sample)["retreat_distance_m"] == 0.06
    for broken in (dict(sample, target_stable=False), dict(sample, retreat_distance_m=0.0),
                   dict(sample, completed_s=121.0), dict(sample, completed_s=-1.0)):
        with pytest.raises(ValueError, match="TASK8_QUALIFICATION_RETREAT_INVALID"):
            validate_retreat_sample(broken)


def _manifest():
    return {"prefix_cases": [{"case_id": f"prefix-{index:02d}"} for index in range(1, 10)],
            "full_cases": [{"case_id": f"full-{index:02d}"} for index in range(1, 6)]}


def _row(case_id, identity, manifest_document_sha256):
    prefix = case_id.startswith("prefix-")
    row = {"case_id": case_id, "mode": "phase_prefix" if prefix else "full", "status": "PASSED",
           "live_evidence_path": "" if prefix else f"/run/{case_id}-live.json",
           "live_evidence_sha256": "0" * 64 if prefix else "b" * 64,
           "child_retirement_receipt_path": f"/run/{case_id}-child.json",
           "child_retirement_receipt_sha256": "c" * 64,
           "stack_retirement_receipt_path": f"/run/{case_id}-stack.json",
           "stack_retirement_receipt_sha256": "d" * 64,
           "source_provenance_sha256": identity["source_provenance_sha256"],
           "runtime_config_sha256": identity["runtime_config_sha256"],
           "contact_policy_fingerprint": identity["contact_policy_fingerprint"],
           "manifest_document_sha256": manifest_document_sha256}
    return row


def _write_journals(root, identity, manifest_document_sha256, *, skip=None, mutate=None):
    cases = root / "task8-live" / "cases"
    cases.mkdir(parents=True)
    for case in [*_manifest()["prefix_cases"], *_manifest()["full_cases"]]:
        case_id = case["case_id"]
        if case_id == skip:
            continue
        row = _row(case_id, identity, manifest_document_sha256)
        if mutate is not None and case_id == mutate[0]:
            row.update(mutate[1])
        (cases / f"{case_id}.json").write_text(json.dumps(row))


def test_all_fourteen_journals_must_exist_and_match_the_bundle(tmp_path):
    from so101_demo.act.task8_live_qualification import validate_case_journals

    identity = {"source_provenance_sha256": "e" * 64, "runtime_config_sha256": "f" * 64,
                "contact_policy_fingerprint": "a" * 64}
    root = tmp_path / "run"
    root.mkdir()
    _write_journals(root, identity, "9" * 64)
    rows = validate_case_journals(root, _manifest(), identities=identity,
                                  manifest_document_sha256="9" * 64)
    assert [row["case_id"] for row in rows] == [f"prefix-{i:02d}" for i in range(1, 10)] + \
        [f"full-{i:02d}" for i in range(1, 6)]


@pytest.mark.parametrize("skip,mutate,code", [
    ("full-05", None, "TASK8_QUALIFICATION_JOURNAL_MISSING"),   # the last of the five fulls
    (None, ("full-01", {"source_provenance_sha256": "7" * 64}),
     "TASK8_JOURNAL_IDENTITY_MISMATCH"),
    (None, ("prefix-01", {"live_evidence_sha256": "b" * 64}), "TASK8_PREFIX_EVIDENCE_FORBIDDEN"),
    (None, ("full-01", {"stack_retirement_receipt_sha256": "nope"}), "TASK8_JOURNAL_HASH_INVALID"),
])
def test_incomplete_or_foreign_journals_refuse_qualification(tmp_path, skip, mutate, code):
    from so101_demo.act.task8_live_qualification import validate_case_journals

    identity = {"source_provenance_sha256": "e" * 64, "runtime_config_sha256": "f" * 64,
                "contact_policy_fingerprint": "a" * 64}
    root = tmp_path / "run"
    root.mkdir()
    _write_journals(root, identity, "9" * 64, skip=skip, mutate=mutate)
    with pytest.raises(ValueError, match=code):
        validate_case_journals(root, _manifest(), identities=identity,
                               manifest_document_sha256="9" * 64)


def _full_fixture(tmp_path):
    """A verified bundle carrying a REAL v2 manifest, plus a complete campaign."""

    import dataclasses
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from test_act_task8_artifact_bundle import _inputs        # stub-based inputs

    from so101_demo.act.pick_place_validation_manifest import (
        ANCHOR_NAMES, build_pick_place_validation_manifest,
    )
    from so101_demo.act.task8_artifact_bundle import (
        prepare_task8_bundle, verify_prepared_task8_bundle,
    )

    inputs = _inputs(tmp_path)
    identities = dict(inputs.identities)
    anchors = {name: {"cup_start_m": [0.25, 0.0, 0.15], "neck_start_rad": 0.0}
               for name in ANCHOR_NAMES}
    manifest = build_pick_place_validation_manifest(
        anchors, source_sha256=identities["source_provenance_sha256"],
        runtime_config_sha256=identities["runtime_config_sha256"],
        collection_config_sha256=identities["act_profile_sha256"],
        contact_policy_fingerprint=identities["contact_policy_fingerprint"],
        calibration_report_path="calibration-report.json",
        calibration_report_sha256="e" * 64)
    real_manifest = tmp_path / "real-manifest.json"
    real_manifest.write_text(json.dumps(manifest))
    receipt = prepare_task8_bundle(dataclasses.replace(inputs, manifest=real_manifest),
                                   tmp_path / "bundle")
    verified = verify_prepared_task8_bundle(receipt)
    bundled = json.loads(_Path(verified.manifest).read_bytes())
    return receipt, receipt.parent, bundled, dict(verified.identities)


def _campaign(tmp_path, manifest, identities):
    """Fourteen journals plus the summary, written through the committed row shape."""

    case_root = tmp_path / "run"
    (case_root / "task8-live" / "cases").mkdir(parents=True)
    digests = []
    for case in [*manifest["prefix_cases"], *manifest["full_cases"]]:
        case_id = case["case_id"]
        prefix = case_id.startswith("prefix-")
        row = {"case_id": case_id, "mode": "phase_prefix" if prefix else "full",
               "status": "PASSED",
               "live_evidence_path": "" if prefix else f"/run/{case_id}-live.json",
               "live_evidence_sha256": "0" * 64 if prefix else "b" * 64,
               "child_retirement_receipt_path": f"/run/{case_id}-child.json",
               "child_retirement_receipt_sha256": "c" * 64,
               "stack_retirement_receipt_path": f"/run/{case_id}-stack.json",
               "stack_retirement_receipt_sha256": "d" * 64,
               "source_provenance_sha256": identities["source_provenance_sha256"],
               "runtime_config_sha256": identities["runtime_config_sha256"],
               "contact_policy_fingerprint": identities["contact_policy_fingerprint"],
               "manifest_document_sha256": manifest["manifest_document_sha256"]}
        payload = json.dumps(row).encode()
        (case_root / "task8-live" / "cases" / f"{case_id}.json").write_bytes(payload)
        digests.append(hashlib.sha256(payload).hexdigest())
    summary_path = tmp_path / "campaign-result.json"
    summary_path.write_text(json.dumps({"status": "PASSED", "prefix_count": 9,
                                        "consecutive_full_count": 5,
                                        "case_journal_sha256": digests}))
    return case_root, summary_path


def _ready(identities, **overrides):
    document = {"schema_version": 2, "status": "TASK8_READY", "source_commit": "0" * 40,
                "config_sha256": "1" * 64,
                "source_provenance_sha256": identities["source_provenance_sha256"],
                "measurements": {},
                "checks": {"fov": "PASS", "collision": "PASS", "search": "PASS",
                           "synchronization": "PASS", "execution": "PASS",
                           "release": "UNMEASURED", "retreat": "UNMEASURED"}}
    document.update(overrides)
    return document


def test_qualified_report_upgrades_a_ready_document_without_touching_it(tmp_path):
    from so101_demo.act.task8_live_qualification import build_task8_qualified_report

    receipt, _, manifest, identities = _full_fixture(tmp_path)
    case_root, summary_path = _campaign(tmp_path, manifest, identities)
    ready_path = tmp_path / "ready.json"
    ready_path.write_text(json.dumps(_ready(identities)))
    before = ready_path.read_bytes()

    output = build_task8_qualified_report(ready_path, receipt, summary_path, case_root,
                                          tmp_path / "qualified.json")
    document = json.loads(output.read_bytes())
    assert document["status"] == "QUALIFIED"
    assert document["checks"]["release"] == document["checks"]["retreat"] == "PASS"
    assert document["live_campaign"]["journal_sha256"] == json.loads(
        summary_path.read_bytes())["case_journal_sha256"]
    assert ready_path.read_bytes() == before
    assert not (tmp_path / "qualified.json.partial").exists()


@pytest.mark.parametrize("mutation,code", [
    ({"status": "CALIBRATION_REQUIRED"}, "TASK8_QUALIFICATION_READY_INVALID"),
    ({"checks": {"fov": "PASS", "collision": "PASS", "search": "PASS",
                 "synchronization": "FAIL", "execution": "PASS",
                 "release": "UNMEASURED", "retreat": "UNMEASURED"}},
     "TASK8_QUALIFICATION_CHECKS_INCOMPLETE"),
    ({"checks": {"fov": "PASS", "collision": "PASS", "search": "PASS",
                 "synchronization": "PASS", "execution": "PASS",
                 "release": "PASS", "retreat": "UNMEASURED"}},
     "TASK8_QUALIFICATION_CHECKS_INCOMPLETE"),
])
def test_a_failing_gate_leaves_no_qualified_behind(tmp_path, mutation, code):
    from so101_demo.act.task8_live_qualification import build_task8_qualified_report

    receipt, _, manifest, identities = _full_fixture(tmp_path)
    case_root, summary_path = _campaign(tmp_path, manifest, identities)
    ready_path = tmp_path / "ready.json"
    ready_path.write_text(json.dumps(_ready(identities, **mutation)))
    output = tmp_path / "qualified.json"
    with pytest.raises(ValueError, match=code):
        build_task8_qualified_report(ready_path, receipt, summary_path, case_root, output)
    assert not output.exists()


def test_an_existing_output_is_never_overwritten(tmp_path):
    from so101_demo.act.task8_live_qualification import build_task8_qualified_report

    receipt, _, manifest, identities = _full_fixture(tmp_path)
    case_root, summary_path = _campaign(tmp_path, manifest, identities)
    ready_path = tmp_path / "ready.json"
    ready_path.write_text(json.dumps(_ready(identities)))
    output = tmp_path / "qualified.json"
    output.write_text("{}")
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_OUTPUT_EXISTS"):
        build_task8_qualified_report(ready_path, receipt, summary_path, case_root, output)
    assert output.read_text() == "{}"


def test_qualified_cli_runs_the_producer_end_to_end(tmp_path, capsys):
    from so101_demo.cli import act_build_task8_qualified_report as cli

    receipt, _, manifest, identities = _full_fixture(tmp_path)
    case_root, summary_path = _campaign(tmp_path, manifest, identities)
    ready_path = tmp_path / "ready.json"
    ready_path.write_text(json.dumps(_ready(identities)))
    output = tmp_path / "qualified.json"
    assert cli.main(["--task8-ready", str(ready_path), "--preparation-receipt", str(receipt),
                     "--campaign-result", str(summary_path), "--case-root", str(case_root),
                     "--output", str(output)]) == 0
    assert json.loads(output.read_bytes())["status"] == "QUALIFIED"
    assert str(output) in capsys.readouterr().out
    # a second run refuses to overwrite the published report
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_OUTPUT_EXISTS"):
        cli.main(["--task8-ready", str(ready_path), "--preparation-receipt", str(receipt),
                  "--campaign-result", str(summary_path), "--case-root", str(case_root),
                  "--output", str(output)])


def test_qualified_report_validates_only_with_its_campaign_block(tmp_path):
    """The calibration validator requires the provenance block on a QUALIFIED report."""

    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from test_act_calibration import report as qualified_report   # a fully valid QUALIFIED report

    from so101_demo.act.calibration import require_qualified

    document = qualified_report(tmp_path)
    require_qualified(document)                       # accepted with its campaign block
    del document["live_campaign"]
    with pytest.raises(ValueError, match="FIELDS_INVALID"):
        require_qualified(document)                   # a QUALIFIED without it is not well formed
    # a well-formed block with the wrong number of journals is refused on its own terms
    short_block = {"case_root": "/run", "campaign_result_sha256": "c" * 64,
                   "preparation_receipt_sha256": "d" * 64, "journal_sha256": ["e" * 64] * 13}
    with pytest.raises(ValueError, match="CALIBRATION_LIVE_CAMPAIGN_INVALID"):
        require_qualified(dict(qualified_report(tmp_path), live_campaign=short_block))


def test_real_runner_full_case_seals_evidence_through_an_evidence_port(tmp_path):
    """Producer path: real Task8Runner -> port -> CaseEvidenceDriver -> sealed artifact (no fakes)."""

    import hashlib as _hashlib
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from test_act_task8 import FakePort, request as runner_request
    from test_act_task8_live_evidence import _Contact, _Evidence   # the physics-evidence doubles

    from so101_demo.act.task8 import Task8Runner
    from so101_demo.act.task8_live_evidence import (
        CaseEvidenceDriver, LiveEvidenceWindow, derive_frame_aggregates,
    )

    receipt, _, manifest, identities = _full_fixture(tmp_path)
    case_root = tmp_path / "staging"
    case_root.mkdir()
    driver = CaseEvidenceDriver(case_id="full-01", staging_root=case_root, session_id="session-1",
                                attempt_id="attempt-1", reset_epoch=4)

    class _EvidencePort(FakePort):
        """The real port contract, plus evidence emission into this task's driver."""

        def __init__(self):
            super().__init__()
            self.root = driver.case_root
            self._events = 0
            self._grid_index = 0            # the frozen 10 Hz grid advances per observation

        def _observe(self, phase, evidence):
            self._grid_index += 1
            at_s = (self._grid_index - 1) * 0.1
            aggregates = derive_frame_aggregates(
                _Evidence(left=[_Contact()] if evidence.get("bilateral_contact") else [],
                          right=[_Contact()] if evidence.get("bilateral_contact") else [],
                          other=[] if evidence.get("cup_off_table") else [_Contact(body2="table")],
                          simulation_step=evidence["physics_step"],
                          simulation_time_s=at_s,
                          minimum_signed_distance_m=0.02 if evidence.get("cup_off_table") else 0.001),
                support_distance_max_m=0.005)
            record_dir = driver.case_root / "raw"
            record_dir.mkdir(parents=True, exist_ok=True)
            record = record_dir / f"grid-{self._grid_index}.json"
            record.write_bytes(b"{}")
            digest = _hashlib.sha256(record.read_bytes()).hexdigest()
            stamps = {name: at_s
                      for name in ("head", "wrist", "arm", "neck", "world", "scene", "contact")}
            receipts = {name: 0.0 for name in stamps}
            # the recorder's exact record contract: relative_path (no leading slash, no ..) + sha256
            raw = {name: {"relative_path": f"raw/grid-{self._grid_index}.json",
                          "sha256": digest}
                   for name in stamps}
            driver.observe(
                {**aggregates, "physics_step": evidence["physics_step"],
                 "sim_time_s": at_s,
                 "source_stamps_s": stamps, "source_received_monotonic_s": receipts,
                 "raw_records": raw},
                phase="CLOSE" if phase == "CLOSE" else phase,
                frame={"wrist_frame_valid": True, "wrist_target_visible": True},
                contact={"observation_valid": True,
                         "bilateral_contact": aggregates["bilateral_contact"],
                         "no_fingertip_contact": aggregates["no_fingertip_contact"],
                         "cup_supported": aggregates["cup_supported"],
                         "released": evidence.get("released", False),
                         "placement_stable": evidence.get("placement_stable", True)},
                measurements={"cup_support_distance_m": aggregates["cup_support_distance_m"],
                              "end_effector_position_m": [0.0, 0.0, 0.1],
                              "cup_position_m": aggregates["cup_position_m"],
                              "cup_orientation_xyzw": aggregates["cup_orientation_xyzw"]})

        def run_phase(self, phase, req):
            evidence = super().run_phase(phase, req)
            if phase in LiveEvidenceWindow.REQUIRED_PHASES:
                self._observe(phase, evidence)
            return evidence

        def set_down(self, req):
            evidence = super().set_down(req)
            # the runner performs RELEASE through set_down, so that is where the window sees it
            self._observe("RELEASE", dict(evidence, bilateral_contact=False, cup_off_table=False,
                                          released=True))
            return evidence

        def run_retreat_segment(self, direction, distance, req):
            evidence = super().run_retreat_segment(direction, distance, req)
            self._observe("RADIAL_RETREAT", dict(evidence, bilateral_contact=False,
                                                 cup_off_table=False, released=True))
            return evidence

        def seal_live_evidence(self, req):
            return driver.seal()

    port = _EvidencePort()
    # a full case carries no stop_after: the runner refuses that combination (FULL_RESTART_REQUIRED)
    result = Task8Runner(port).run(runner_request(mode="full", stop_after=None))
    assert result["status"] == "PASSED"
    artifact = result["live_evidence_artifact"]
    assert set(artifact) == {"path", "sha256", "schema_version"}
    sealed = _Path(artifact["path"])
    assert sealed.is_file()
    # the recorded digest is the artifact's own bytes: the seal is not a label
    assert _hashlib.sha256(sealed.read_bytes()).hexdigest() == artifact["sha256"]
    assert driver.window.grid_count >= len(LiveEvidenceWindow.REQUIRED_PHASES) - 1


def _evidence_port(driver, *, session_id="session-1", attempt_id="attempt-1"):
    """A port implementing the runner's full contract, emitting evidence into `driver`.

    Module-level (rather than nested in one test) so the closing integration harness can reuse it.
    """

    import hashlib as _hashlib
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from test_act_task8 import FakePort                       # noqa: E402
    from test_act_task8_live_evidence import _Contact, _Evidence   # noqa: E402

    from so101_demo.act.task8_live_evidence import (            # noqa: E402
        LiveEvidenceWindow, derive_frame_aggregates,
    )

    class _EvidencePort(FakePort):
        def __init__(self):
            super().__init__()
            self.root = driver.case_root
            self._grid_index = 0

        def _observe(self, phase, evidence):
            self._grid_index += 1
            at_s = (self._grid_index - 1) * 0.1
            bilateral = bool(evidence.get("bilateral_contact"))
            airborne = bool(evidence.get("cup_off_table"))
            aggregates = derive_frame_aggregates(
                _Evidence(left=[_Contact()] if bilateral else [],
                          right=[_Contact()] if bilateral else [],
                          other=[] if airborne else [_Contact(body2="table")],
                          simulation_step=evidence["physics_step"], simulation_time_s=at_s,
                          minimum_signed_distance_m=0.02 if airborne else 0.001),
                support_distance_max_m=0.005)
            record_dir = driver.case_root / "raw"
            record_dir.mkdir(parents=True, exist_ok=True)
            record = record_dir / f"grid-{self._grid_index}.json"
            record.write_bytes(b"{}")
            digest = _hashlib.sha256(record.read_bytes()).hexdigest()
            stamps = {name: at_s
                      for name in ("head", "wrist", "arm", "neck", "world", "scene", "contact")}
            receipts = {name: 0.0 for name in stamps}
            raw = {name: {"relative_path": f"raw/grid-{self._grid_index}.json",
                          "sha256": digest}
                   for name in stamps}
            driver.observe(
                {**aggregates, "physics_step": evidence["physics_step"], "sim_time_s": at_s,
                 "source_stamps_s": stamps, "source_received_monotonic_s": receipts,
                 "raw_records": raw},
                phase=phase,
                frame={"wrist_frame_valid": True, "wrist_target_visible": True},
                contact={"observation_valid": True,
                         "bilateral_contact": aggregates["bilateral_contact"],
                         "no_fingertip_contact": aggregates["no_fingertip_contact"],
                         "cup_supported": aggregates["cup_supported"],
                         "released": evidence.get("released", False),
                         "placement_stable": evidence.get("placement_stable", True)},
                measurements={"cup_support_distance_m": aggregates["cup_support_distance_m"],
                              "end_effector_position_m": [0.0, 0.0, 0.1],
                              "cup_position_m": aggregates["cup_position_m"],
                              "cup_orientation_xyzw": aggregates["cup_orientation_xyzw"]})

        def run_phase(self, phase, req):
            evidence = super().run_phase(phase, req)
            if phase in LiveEvidenceWindow.REQUIRED_PHASES:
                self._observe(phase, evidence)
            return evidence

        def set_down(self, req):
            evidence = super().set_down(req)
            self._observe("RELEASE", dict(evidence, bilateral_contact=False, cup_off_table=False,
                                          released=True))
            return evidence

        def run_retreat_segment(self, direction, distance, req):
            evidence = super().run_retreat_segment(direction, distance, req)
            self._observe("RADIAL_RETREAT", dict(evidence, bilateral_contact=False,
                                                 cup_off_table=False, released=True))
            return evidence

        def seal_live_evidence(self, req):
            return driver.seal()

    return _EvidencePort()


def test_evidence_port_factory_seals_through_its_driver(tmp_path):
    """The factory is the harness the closing integration test will use."""

    import hashlib as _hashlib
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from test_act_task8 import request as runner_request

    from so101_demo.act.task8 import Task8Runner
    from so101_demo.act.task8_live_evidence import CaseEvidenceDriver

    case_root = tmp_path / "staging"
    case_root.mkdir()
    driver = CaseEvidenceDriver(case_id="full-03", staging_root=case_root, session_id="session-1",
                                attempt_id="attempt-3", reset_epoch=4)
    port = _evidence_port(driver)
    result = Task8Runner(port).run(runner_request(mode="full", stop_after=None))
    assert result["status"] == "PASSED"
    artifact = result["live_evidence_artifact"]
    sealed = _Path(artifact["path"])
    assert sealed.is_file()
    assert _hashlib.sha256(sealed.read_bytes()).hexdigest() == artifact["sha256"]


def test_chain_reaches_a_validated_journal_row_from_real_evidence(tmp_path):
    """Real runner -> sealed artifact -> journal row -> the aggregator's own validation."""

    import hashlib as _hashlib
    import json as _json
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from test_act_task8 import request as runner_request

    from so101_demo.act.task8 import Task8Runner
    from so101_demo.act.task8_live_evidence import (
        CaseEvidenceDriver, case_row_to_journal_row, require_case_row_matches_bundle,
    )

    receipt, _, manifest, identities = _full_fixture(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    driver = CaseEvidenceDriver(case_id="full-01", staging_root=staging, session_id="session-1",
                                attempt_id="full-01", reset_epoch=4)
    result = Task8Runner(_evidence_port(driver)).run(runner_request(mode="full", stop_after=None))
    artifact = result["live_evidence_artifact"]
    assert _Path(artifact["path"]).is_file()

    # the two retirement receipts a real case would have produced
    receipts = {}
    for name in ("stack", "child"):
        path = tmp_path / f"{name}-cleanup-receipt.json"
        path.write_text(_json.dumps({"group_clear": True}))
        receipts[name] = path

    published = {
        "case_id": "full-01", "mode": "full", "status": result["status"],
        "live_evidence_path": artifact["path"], "live_evidence_sha256": artifact["sha256"],
        "child_retirement_receipt_path": str(receipts["child"]),
        "child_receipt_sha256": _hashlib.sha256(receipts["child"].read_bytes()).hexdigest(),
        "stack_retirement_receipt_path": str(receipts["stack"]),
        "stack_receipt_sha256": _hashlib.sha256(receipts["stack"].read_bytes()).hexdigest(),
    }
    row = case_row_to_journal_row(published, identities=identities,
                                  manifest_document_sha256=manifest["manifest_document_sha256"])
    # the aggregator's identity binding accepts the row, and the artifact's bytes still match
    require_case_row_matches_bundle(row, identities=identities,
                                    manifest_document_sha256=manifest["manifest_document_sha256"])
    assert _hashlib.sha256(_Path(row["live_evidence_path"]).read_bytes()).hexdigest() == \
        row["live_evidence_sha256"]


def test_run_pick_place_case_publishes_a_journal_from_the_real_runner(tmp_path):
    """The teleop case path publishes a journal whose result came from the real Task8Runner."""

    import asyncio
    import hashlib as _hashlib
    import json as _json
    import sys
    import time
    from pathlib import Path as _Path

    here = _Path(__file__).resolve()
    sys.path.insert(0, str(here.parent))
    # <worktree>/src/so101_demo_py/test/<this file>: parents[2] is <worktree>/src
    sys.path.insert(0, str(here.parents[2] / "so101_teleop" / "test" / "teleop"))
    from test_task8_case_execution import CHILD_OWNER, STACK_OWNER

    from so101_teleop.unified.pick_place_case_execution import run_pick_place_case

    from so101_demo.act.pick_place_validation_manifest import write_new_manifest
    from so101_demo.act.task8 import Task8Runner
    from so101_demo.act.task8_live_evidence import (
        CaseEvidenceDriver, case_row_to_journal_row, require_case_row_matches_bundle,
    )

    receipt, _, bundled, identities = _full_fixture(tmp_path)
    # a FRESH v2 document for the campaign: the bundled copy has been rebased by the bundle producer,
    # so re-validating it here would compare against a different document digest
    from so101_demo.act.pick_place_validation_manifest import (
        ANCHOR_NAMES, build_pick_place_validation_manifest,
    )
    anchors = {name: {"cup_start_m": [0.25, 0.0, 0.15], "neck_start_rad": 0.0}
               for name in ANCHOR_NAMES}
    manifest = build_pick_place_validation_manifest(
        anchors, source_sha256=identities["source_provenance_sha256"],
        runtime_config_sha256=identities["runtime_config_sha256"],
        collection_config_sha256=identities["act_profile_sha256"],
        contact_policy_fingerprint=identities["contact_policy_fingerprint"],
        calibration_report_path="calibration-report.json", calibration_report_sha256="e" * 64)
    manifest_path = tmp_path / "manifest.json"
    write_new_manifest(manifest_path, manifest)
    manifest_digest = _hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    campaign_id = "case-298"
    stack_root = tmp_path / "task8-live" / campaign_id / "stack"
    child_root = tmp_path / "child"
    stack_root.mkdir(parents=True)
    child_root.mkdir()

    staging = tmp_path / "staging"
    staging.mkdir()
    driver = CaseEvidenceDriver(case_id="full-01", staging_root=staging, session_id="session-298",
                                attempt_id="full-01", reset_epoch=4)
    from types import SimpleNamespace

    context = SimpleNamespace(
        campaign_id=campaign_id, manifest_sha256=manifest_digest,
        workload_kind="task8_full", evidence_root=str(tmp_path), worker_count=1,
        # the campaign binds the manifest to the admitted identity, so the context carries it
        source_sha256=manifest["source_sha256"],
        runtime_config_sha256=manifest["runtime_config_sha256"],
        collection_config_sha256=manifest["collection_config_sha256"],
        contact_policy_fingerprint=manifest["contact_policy_fingerprint"])
    spec = SimpleNamespace(kind="task8_full", deadline_ns=time.monotonic_ns() + 60_000_000_000,
                           payload={"evidence_root": str(tmp_path),
                                    "manifest_path": str(manifest_path),
                                    "manifest_sha256": manifest_digest})
    journal = tmp_path / "result.json"

    class Worker:
        def __init__(self):
            self.context = context            # the campaign reads it back off the worker
            self.launch = SimpleNamespace(mujoco_session_id="session-298",
                                          socket_root=str(child_root), ros_domain_id=198)

        async def run_pick_place(self, request):
            # the runner's request schema is closed: it wants exactly these keys and FULL_RESTART,
            # while the campaign also carries contact_policy_fingerprint for its own binding check
            runner_request_document = {
                "mode": request["mode"], "stop_after": request["stop_after"],
                "lifecycle": "FULL_RESTART", "scenario_id": request["scenario_id"],
                "session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "deadline_ns": request["deadline_ns"],
            }
            return Task8Runner(_evidence_port(driver)).run(runner_request_document)

    class Owner:
        def __init__(self):
            self.context = None
            self.worker = Worker()
            self.stack = SimpleNamespace(
                launch=SimpleNamespace(evidence_root=str(stack_root)))
            self.child_launch = self.worker.launch
            self.stack_owner_key = STACK_OWNER
            self.child_owner_key = CHILD_OWNER
            self._stack_retired = self._child_retired = self._final_clear = False

        async def start(self, passed):
            self.context = context
            return context, self.worker

        async def retire_failed_start(self, *, attempt_id):
            await self.finish(attempt_id=attempt_id)

        async def finish(self, *, attempt_id):
            (stack_root / "cleanup-receipt.json").write_text(_json.dumps({
                "leader_pid": STACK_OWNER.pid, "pgid": STACK_OWNER.pgid,
                "started_ticks": STACK_OWNER.started_ticks,
                "argv_sha256": STACK_OWNER.argv_sha256, "group_clear": True,
                "session_id": "session-298", "ros_domain_id": 198,
                "physical_stop_confirmed": True, "graph_clear": True}))
            (child_root / "cleanup-receipt.json").write_text(_json.dumps({
                "leader_pid": CHILD_OWNER.pid, "pgid": CHILD_OWNER.pgid,
                "started_ticks": CHILD_OWNER.started_ticks,
                "argv_sha256": CHILD_OWNER.argv_sha256, "group_clear": True}))
            self._stack_retired = self._child_retired = self._final_clear = True
            self.context = None

    row = asyncio.run(run_pick_place_case(spec, "full-01", Owner(), journal))
    assert journal.is_file() and row["status"] == "PASSED"
    assert row["live_evidence_path"] == "" or _Path(row["live_evidence_path"]).is_file()
    if row["live_evidence_sha256"] != "0" * 64:
        assert _hashlib.sha256(_Path(row["live_evidence_path"]).read_bytes()).hexdigest() == \
            row["live_evidence_sha256"]
    journal_row = case_row_to_journal_row(row, identities=identities,
                                          manifest_document_sha256=manifest["manifest_document_sha256"])
    require_case_row_matches_bundle(journal_row, identities=identities,
                                    manifest_document_sha256=manifest["manifest_document_sha256"])


# --- protocol v2 additions (Task 8): the five live-only fields ---------------------------------------------

LIVE_FIELDS = ("grasp_occlusion_window_s", "support_distance_m", "release_stable_s",
               "retreat_distance_m", "placement_stable_s")


def _live_run(index, *, occlusion=0.5, support=0.01, release=1.0, retreat=0.06, placement=1.0,
              session="session-1", policy="d" * 64, matrix="e" * 64):
    return {"run_index": index, "session_id": session, "contact_policy_fingerprint": policy,
            "phase_camera_matrix_sha256": matrix,
            "grasp_occlusion_window_s": occlusion, "cup_support_distance_m": support,
            "release_stable_s": release, "retreat_distance_m": retreat,
            "placement_stable_s": placement,
            "sample_path": f"runs/{index}/live.json", "sample_sha256": "f" * 64}


def test_the_five_live_fields_take_the_documented_extrema_across_five_runs():
    from so101_demo.act.task8_live_qualification import derive_live_measurements

    runs = [_live_run(0, occlusion=0.30, support=0.02, release=1.5, retreat=0.08, placement=2.0),
            _live_run(1, occlusion=0.55, support=0.05, release=0.9, retreat=0.05, placement=1.2),
            _live_run(2, occlusion=0.40, support=0.01, release=1.1, retreat=0.09, placement=1.8),
            _live_run(3, occlusion=0.10, support=0.03, release=1.3, retreat=0.04, placement=2.4),
            _live_run(4, occlusion=0.25, support=0.04, release=1.0, retreat=0.07, placement=1.5)]
    derived = derive_live_measurements(runs, {})
    assert set(derived) == set(LIVE_FIELDS)
    # occlusion and support distance take the maximum; the three stability/distance fields take the minimum
    assert derived["grasp_occlusion_window_s"]["value"] == pytest.approx(0.55)
    assert derived["support_distance_m"]["value"] == pytest.approx(0.05)
    assert derived["release_stable_s"]["value"] == pytest.approx(0.9)
    assert derived["retreat_distance_m"]["value"] == pytest.approx(0.04)
    # placement values are 2.0, 1.2, 1.8, 2.4, 1.5 - the minimum is 1.2, not the fixture default
    assert derived["placement_stable_s"]["value"] == pytest.approx(1.2)


@pytest.mark.parametrize("runs,reason", [
    ([_live_run(0), _live_run(1), _live_run(2), _live_run(3)], "FIVE_RUNS_REQUIRED"),
    ([_live_run(0), _live_run(1, policy="c" * 64), _live_run(2), _live_run(3), _live_run(4)],
     "IDENTITY_MISMATCH"),
    ([_live_run(0), _live_run(1, matrix="c" * 64), _live_run(2), _live_run(3), _live_run(4)],
     "IDENTITY_MISMATCH"),
    ([_live_run(0), _live_run(1, session="other"), _live_run(2), _live_run(3), _live_run(4)],
     "IDENTITY_MISMATCH"),
])
def test_derivation_refuses_fewer_than_five_runs_or_a_mixed_identity(runs, reason):
    from so101_demo.act.task8_live_qualification import derive_live_measurements

    with pytest.raises(ValueError, match=reason):
        derive_live_measurements(runs, {})


def test_a_summary_without_a_sealed_sample_is_refused():
    from so101_demo.act.task8_live_qualification import derive_live_measurements

    runs = [_live_run(index) for index in range(5)]
    runs[2] = {key: value for key, value in runs[2].items() if key != "sample_sha256"}
    runs[2]["summary"] = "support distance measured"
    with pytest.raises(ValueError, match="SEALED_SAMPLE_REQUIRED"):
        derive_live_measurements(runs, {})


def test_qualified_measurements_copy_by_value_and_add_exactly_five():
    from so101_demo.act.task8_live_qualification import (LIVE_ONLY_FIELDS, build_qualified_measurements,
                                                         derive_live_measurements)

    ready = {f"ready_field_{index}": {"value": float(index), "unit": "rad"} for index in range(28)}
    snapshot = json.loads(json.dumps(ready))
    runs = [_live_run(index) for index in range(5)]
    merged = build_qualified_measurements(ready, runs, {})

    assert set(merged) - set(ready) == set(LIVE_ONLY_FIELDS), "exactly the five live-only fields are added"
    assert len(merged) == 33
    assert ready == snapshot, "the ready report is never mutated"
    derived = derive_live_measurements(runs, {})
    for field in LIVE_ONLY_FIELDS:
        assert merged[field]["value"] == pytest.approx(derived[field]["value"])
        assert merged[field]["unit"] == derived[field]["unit"]


def test_a_ready_field_that_is_already_live_only_is_refused():
    from so101_demo.act.task8_live_qualification import build_qualified_measurements

    ready = {"grasp_occlusion_window_s": {"value": 0.1, "unit": "s"}}
    with pytest.raises(ValueError, match="LIVE_FIELD_ALREADY_PRESENT"):
        build_qualified_measurements(ready, [_live_run(index) for index in range(5)], {})


def _sample_row(phase, sim_time, *, position=(0.0, 0.0, 0.1), stable=True):
    return {"phase": phase, "sim_time_s": sim_time, "end_effector_position_m": list(position),
            "placement_stable": stable}


def test_retreat_distance_is_radial_from_the_cup_at_the_first_qualifying_readback():
    from so101_demo.act.task8_live_qualification import retreat_distance_m

    def frame(stamp, effector, *, clearing=False):
        return {"phase": "RADIAL_RETREAT", "source_stamp": stamp, "cup_position_m": [0.0, 0.0, 0.1],
                "end_effector_position_m": list(effector), "clearing": clearing}

    frames = [frame(0.0, (0.0, 0.0, 0.1)), frame(0.1, (0.03, 0.04, 0.1), clearing=True),
              frame(0.2, (0.06, 0.08, 0.1))]
    # the radial distance grows from 0 to 0.05 at the first qualifying readback, not to 0.10 at the last
    assert retreat_distance_m(frames, qualifying=lambda f: f["clearing"]) == pytest.approx(0.05)
    with pytest.raises(ValueError, match="RETREAT_QUALIFYING_READBACK_REQUIRED"):
        retreat_distance_m(frames, qualifying=lambda f: False)
    # the refusal is for a run with no retreat frame at all; a single qualifying frame legitimately reports zero
    with pytest.raises(ValueError, match="RETREAT_SAMPLES_REQUIRED"):
        retreat_distance_m([], qualifying=lambda f: True)
    assert retreat_distance_m([frame(0.0, (0.0, 0.0, 0.1))], qualifying=lambda f: True) == pytest.approx(0.0)


def test_placement_stability_is_the_longest_contiguous_final_check_span():
    from so101_demo.act.task8_live_qualification import placement_stable_s

    def frame(stamp, *, settled):
        return {"phase": "FINAL_CHECK", "source_stamp": stamp, "settled": settled}

    frames = [frame(0.0, settled=True), frame(0.1, settled=True), frame(0.2, settled=False),
              frame(0.3, settled=True)]
    assert placement_stable_s(frames, stable=lambda f: f["settled"]) == pytest.approx(0.1)
    # a break ends the span rather than failing the run, and a phase with no frames at all is refused
    gapped = [frame(0.0, settled=True), frame(0.25, settled=True)]
    assert placement_stable_s(gapped, stable=lambda f: f["settled"]) == 0.0
    with pytest.raises(ValueError, match="SPAN_FRAMES_REQUIRED"):
        placement_stable_s([frame(0.0, settled=True)][:0], stable=lambda f: f["settled"])










def _contact_pair(geom_a, geom_b, distance):
    return {"geom1": geom_a, "geom2": geom_b, "signed_distance_m": distance}


def test_support_distance_needs_the_exact_pair_in_every_pre_open_frame():
    from so101_demo.act.task8_live_qualification import support_distance_from_frames

    def frame(stamp, contacts, before=True):
        return {"phase": "RELEASE", "release_epoch": 7, "before_first_open": before,
                "source_stamp": stamp, "contacts": contacts}

    good = [frame(1.0, [_contact_pair("cup_a_bottom_collision", "table_collision", -0.002)]),
            frame(1.1, [_contact_pair("cup_a_bottom_collision", "table_collision", 0.004)]),
            frame(1.2, [_contact_pair("cup_a_bottom_collision", "table_collision", 0.001)])]
    assert support_distance_from_frames(good, cup_collision_geom="cup_a_bottom_collision") == pytest.approx(0.004)
    # a run for the b cup names its own single collision geom and is found just as the a cup's is
    b_cup = [frame(1.0, [_contact_pair("cup_b_collision", "table_collision", 0.003)]),
             frame(1.1, [_contact_pair("cup_b_collision", "table_collision", 0.005)]),
             frame(1.2, [_contact_pair("cup_b_collision", "table_collision", 0.004)])]
    assert support_distance_from_frames(b_cup, cup_collision_geom="cup_b_collision") == pytest.approx(0.005)
    # naming a geom the frames do not carry fails the run rather than passing on a missing pair
    with pytest.raises(ValueError, match="SUPPORT_CONTACT_REQUIRED"):
        support_distance_from_frames(good, cup_collision_geom="cup_b_collision")
    with pytest.raises(ValueError, match="CUP_COLLISION_GEOM_REQUIRED"):
        support_distance_from_frames(good, cup_collision_geom="")
    # a negative signed distance is floored at zero, and a gap in the stamps is refused
    floored = [frame(1.0, [_contact_pair("cup_a_bottom_collision", "table_collision", -0.5)]),
               frame(1.1, [_contact_pair("cup_a_bottom_collision", "table_collision", -0.4)]),
               frame(1.2, [_contact_pair("cup_a_bottom_collision", "table_collision", -0.3)])]
    assert support_distance_from_frames(floored, cup_collision_geom="cup_a_bottom_collision") == 0.0
    with pytest.raises(ValueError, match="SUPPORT_FRAMES_NOT_CONSECUTIVE"):
        support_distance_from_frames([good[0], good[1], frame(1.35, good[2]["contacts"])],
                                     cup_collision_geom="cup_a_bottom_collision")


def test_longest_contiguous_span_ends_at_a_break_and_can_refuse_one():
    from so101_demo.act.task8_live_qualification import longest_contiguous_span_s

    frames = [{"phase": "RELEASE", "source_stamp": stamp, "ok": ok}
              for stamp, ok in ((0.0, True), (0.1, True), (0.2, True), (0.3, False), (0.4, True), (0.5, True))]
    # the longest run of stable frames is 0.0..0.2, i.e. a 0.2 s span; the tail contributes only 0.1 s
    assert longest_contiguous_span_s(frames, predicate=lambda f: f["ok"], phase="RELEASE") == pytest.approx(0.2)
    with pytest.raises(ValueError, match="SPAN_FRAMES_REQUIRED"):
        longest_contiguous_span_s(frames, predicate=lambda f: f["ok"], phase="FINAL_CHECK")
    gapped = [{"phase": "RELEASE", "source_stamp": 0.0, "ok": True},
              {"phase": "RELEASE", "source_stamp": 0.25, "ok": True}]
    assert longest_contiguous_span_s(gapped, predicate=lambda f: f["ok"], phase="RELEASE") == 0.0
    with pytest.raises(ValueError, match="SPAN_FRAME_BREAK"):
        longest_contiguous_span_s(gapped, predicate=lambda f: f["ok"], phase="RELEASE", strict_breaks=True)


def test_release_stability_and_occlusion_window_use_the_span_structure():
    from so101_demo.act.task8_live_qualification import grasp_occlusion_window_s, release_stable_s

    release = [{"phase": "RELEASE", "source_stamp": stamp, "steady": steady}
               for stamp, steady in ((0.0, False), (0.1, True), (0.2, True), (0.3, False))]
    assert release_stable_s(release, stable=lambda f: f["steady"]) == pytest.approx(0.1)

    close_to_release = [{"phase": "CLOSE", "source_stamp": 0.0, "occluded": True},
                        {"phase": "CLOSE", "source_stamp": 0.1, "occluded": True},
                        {"phase": "CLOSE", "source_stamp": 0.2, "occluded": True},
                        {"phase": "RELEASE", "source_stamp": 0.3, "occluded": False}]
    assert grasp_occlusion_window_s(close_to_release, occluded=lambda f: f["occluded"]) == pytest.approx(0.2)
    # the occlusion row, unlike the stability rows, fails the run on a frame break
    gapped = [close_to_release[0], {"phase": "CLOSE", "source_stamp": 0.25, "occluded": True}]
    with pytest.raises(ValueError, match="SPAN_FRAME_BREAK"):
        grasp_occlusion_window_s(gapped, occluded=lambda f: f["occluded"])


def _sealed_artifact(tmp_path, index, *, digest_matches=True):
    import hashlib
    payload = json.dumps({"identity": {"case_id": f"full-{index:02d}", "session_id": "session-1"},
                          "sample_count": 1,
                          "samples": [{"phase": "RELEASE", "source_stamp": 0.0, "sim_time_s": 0.0}]}).encode()
    target = tmp_path / f"full-{index:02d}.json"
    target.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest() if digest_matches else "0" * 64
    return {"path": str(target), "sha256": digest, "schema_version": 1}


def test_collect_live_runs_reads_five_sealed_full_rows_and_refuses_anything_else(tmp_path):
    from so101_demo.act.task8_live_qualification import LIVE_ONLY_FIELDS, collect_live_runs

    extractors = {field: (lambda samples, document: 0.5) for field in LIVE_ONLY_FIELDS}
    rows = []
    for index in range(5):
        artifact = _sealed_artifact(tmp_path, index)
        rows.append({"live_evidence_path": artifact["path"], "live_evidence_sha256": artifact["sha256"]})
    rows.append({"live_evidence_path": "", "live_evidence_sha256": ""})   # the nine prefix rows carry none
    runs = collect_live_runs(rows, identities={"contact_policy_fingerprint": "d" * 64,
                                               "phase_camera_matrix_sha256": "e" * 64},
                             extractors=extractors)
    assert len(runs) == 5
    assert all(run["contact_policy_fingerprint"] == "d" * 64 for run in runs)
    assert runs[0]["sample_sha256"] and Path(runs[0]["sample_path"]).is_file()

    # a mismatched digest, a missing extractor and fewer than five full rows are each refused
    bad = []
    for index in range(5):
        artifact = _sealed_artifact(tmp_path, index, digest_matches=False)
        bad.append({"live_evidence_path": artifact["path"], "live_evidence_sha256": artifact["sha256"]})
    with pytest.raises(ValueError, match="SEALED_SAMPLE_DIGEST_MISMATCH"):
        collect_live_runs(bad, identities={}, extractors=extractors)
    with pytest.raises(ValueError, match="LIVE_EXTRACTOR_REQUIRED"):
        collect_live_runs(rows, identities={}, extractors={})
    with pytest.raises(ValueError, match="FIVE_FULL_RUNS_REQUIRED"):
        collect_live_runs(rows[:4], identities={}, extractors=extractors)


def test_the_raw_reader_resolves_only_indexed_records_with_matching_digests(tmp_path):
    import hashlib
    import json as _json

    from so101_demo.act.task8_live_qualification import make_raw_reader

    (tmp_path / "raw").mkdir()
    payload = _json.dumps({"pairs": [{"geom1": "cup_a_bottom_collision", "geom2": "table_collision",
                                      "signed_distance_m": 0.002}]}).encode()
    (tmp_path / "raw" / "contact.json").write_bytes(payload)
    artifact = tmp_path / "full-00.json"
    artifact.write_bytes(b"{}")
    reader = make_raw_reader(artifact)
    sample = {"raw_records": {"contact": {"relative_path": "raw/contact.json",
                                          "sha256": hashlib.sha256(payload).hexdigest()}}}
    assert reader(sample, "contact")["pairs"][0]["signed_distance_m"] == pytest.approx(0.002)

    with pytest.raises(ValueError, match="RAW_RECORD_REQUIRED"):
        reader(sample, "wrist")
    with pytest.raises(ValueError, match="RAW_RECORD_PATH_INVALID"):
        reader({"raw_records": {"contact": {"relative_path": "../escape.json", "sha256": "a" * 64}}}, "contact")
    with pytest.raises(ValueError, match="RAW_RECORD_MISSING"):
        reader({"raw_records": {"contact": {"relative_path": "raw/absent.json", "sha256": "a" * 64}}}, "contact")
    with pytest.raises(ValueError, match="RAW_RECORD_DIGEST_MISMATCH"):
        reader({"raw_records": {"contact": {"relative_path": "raw/contact.json", "sha256": "b" * 64}}}, "contact")


def test_live_extractors_bind_each_rule_to_its_supplied_evidence():
    from so101_demo.act.task8_live_qualification import LIVE_ONLY_FIELDS, live_extractors

    extractors = live_extractors(occluded=lambda f: f.get("occluded") is True,
                                release_stable=lambda f: f.get("steady") is True,
                                placement_stable=lambda f: f.get("settled") is True,
                                retreat_qualifying=lambda f: f.get("clear") is True,
                                cup_collision_geom="cup_a_bottom_collision")
    assert set(extractors) == set(LIVE_ONLY_FIELDS)

    samples = [{"phase": "CLOSE", "source_stamp": 0.0, "occluded": True},
               {"phase": "CLOSE", "source_stamp": 0.1, "occluded": True},
               {"phase": "RELEASE", "source_stamp": 0.2, "steady": True},
               {"phase": "RELEASE", "source_stamp": 0.3, "steady": True},
               {"phase": "FINAL_CHECK", "source_stamp": 0.4, "settled": True},
               {"phase": "FINAL_CHECK", "source_stamp": 0.5, "settled": True},
               # the retreat starts at the cup and moves away, so the qualifying frame is the later one
               {"phase": "RADIAL_RETREAT", "source_stamp": 0.6, "clear": False,
                "cup_position_m": [0.0, 0.0, 0.1], "end_effector_position_m": [0.0, 0.0, 0.1]},
               {"phase": "RADIAL_RETREAT", "source_stamp": 0.7, "clear": True,
                "cup_position_m": [0.0, 0.0, 0.1], "end_effector_position_m": [0.03, 0.04, 0.1]}]
    assert extractors["grasp_occlusion_window_s"](samples, {}) == pytest.approx(0.1)
    assert extractors["release_stable_s"](samples, {}) == pytest.approx(0.1)
    assert extractors["placement_stable_s"](samples, {}) == pytest.approx(0.1)
    # the retreat value is read at the first qualifying frame, i.e. 0.05 m from the cup at 0.6 s
    assert extractors["retreat_distance_m"](samples, {}) == pytest.approx(0.05)
    # the support rule refuses before the contact check when its three pre-open frames are absent, which is the
    # correct order: no window, no distance
    with pytest.raises(ValueError, match="SUPPORT_FRAMES_REQUIRED"):
        extractors["support_distance_m"](samples, {})
    with pytest.raises(ValueError, match="CUP_COLLISION_GEOM_REQUIRED"):
        live_extractors(occluded=lambda f: True, release_stable=lambda f: True,
                        placement_stable=lambda f: True, retreat_qualifying=lambda f: True,
                        cup_collision_geom="")


def test_the_world_distance_fallback_is_opt_in_and_not_the_default():
    from so101_demo.act.task8_live_qualification import support_distance_from_frames

    def frame(stamp, *, distance=None, contacts=()):
        entry = {"phase": "RELEASE", "release_epoch": 7, "before_first_open": True, "source_stamp": stamp,
                 "contacts": list(contacts)}
        if distance is not None:
            entry["cup_support_distance_m"] = distance
        return entry

    world_only = [frame(1.0, distance=0.002), frame(1.1, distance=0.004), frame(1.2, distance=0.001)]
    # without the opt-in the rule still insists on real contact, exactly as the design's row states
    with pytest.raises(ValueError, match="SUPPORT_CONTACT_REQUIRED"):
        support_distance_from_frames(world_only, cup_collision_geom="cup_a_bottom_collision")
    assert support_distance_from_frames(world_only, cup_collision_geom="cup_a_bottom_collision",
                                        allow_world_distance=True) == pytest.approx(0.004)


def _r580_fixture(tmp_path):
    """One artifact whose samples reference a real contact record and a real wrist record."""

    import hashlib
    import json as _json

    root = tmp_path / "records"
    (root / "raw").mkdir(parents=True)
    contact_payload = _json.dumps({"pairs": [{"geom1": "cup_a_bottom_collision", "geom2": "table_collision",
                                              "signed_distance_m": 0.002}], "stable": True,
                                   "clear": True}).encode()
    wrist_payload = _json.dumps({"occluded": True}).encode()
    (root / "raw" / "contact.json").write_bytes(contact_payload)
    (root / "raw" / "wrist.json").write_bytes(wrist_payload)
    refs = {"contact": {"relative_path": "raw/contact.json",
                        "sha256": hashlib.sha256(contact_payload).hexdigest()},
            "wrist": {"relative_path": "raw/wrist.json",
                      "sha256": hashlib.sha256(wrist_payload).hexdigest()}}
    def frame(phase, sim_time, *, before=None, effector_x=0.0):
        entry = {"phase": phase, "sim_time_s": sim_time, "raw_records": refs, "release_epoch": 7,
                 "cup_position_m": [0.0, 0.0, 0.1], "end_effector_position_m": [effector_x, 0.0, 0.1]}
        if before is not None:
            entry["before_first_open"] = before
        return entry

    samples = [frame("RELEASE", 1.0 + 0.1 * index, before=index < 3) for index in range(4)]
    samples += [frame("FINAL_CHECK", 1.4 + 0.1 * index) for index in range(3)]
    # the retreat starts at the cup and moves away, so the first clear frame is the later one
    samples += [frame("RADIAL_RETREAT", 1.7, effector_x=0.0), frame("RADIAL_RETREAT", 1.8, effector_x=0.01)]
    artifact = root / "full-00.json"
    artifact.write_bytes(_json.dumps({"identity": {"session_id": "session-1"},
                                      "samples": samples}).encode())
    return artifact, samples


def test_record_extractors_bind_the_rules_to_the_records(tmp_path):
    from so101_demo.act.task8_live_qualification import LIVE_ONLY_FIELDS, record_live_extractors

    artifact, samples = _r580_fixture(tmp_path)
    # the occlusion rule applies no phase filter of its own - the caller's predicate owns the phase and owner
    # conditions - so this one counts occlusion only in CLOSE..RELEASE, exactly as the design's row describes
    def occluded_from_record(record):
        return record["occluded"]

    extractors = record_live_extractors(artifact_path=artifact, cup_collision_geom="cup_a_bottom_collision",
                                        pair_key="pairs", occluded_from_record=occluded_from_record)
    assert set(extractors) == set(LIVE_ONLY_FIELDS)
    # three consecutive pre-open frames each carry the exact pair, so the support distance is the max of max(0, d)
    assert extractors["support_distance_m"](samples, {}) == pytest.approx(0.002)
    # the rule applies the row's own CLOSE..RELEASE phase range, so the ten-frame fixture yields the release span
    assert extractors["grasp_occlusion_window_s"](samples, {}) == pytest.approx(0.3)
    assert extractors["release_stable_s"](samples, {}) == pytest.approx(0.3)
    assert extractors["placement_stable_s"](samples, {}) == pytest.approx(0.2)
    # this fixture's contact record reports clear in every frame, so the first retreat frame already qualifies and
    # the radial displacement it reports is zero - the qualifier is what moves the reading to the later frame
    assert extractors["retreat_distance_m"](samples, {}) == pytest.approx(0.0)
    later_only = record_live_extractors(
        artifact_path=artifact, cup_collision_geom="cup_a_bottom_collision", pair_key="pairs",
        occluded_from_record=occluded_from_record,
        retreat_qualifying=lambda sample: sample.get("phase") == "RADIAL_RETREAT"
        and abs(sample["end_effector_position_m"][0]) > 0.005)
    assert later_only["retreat_distance_m"](samples, {}) == pytest.approx(0.01)

    # a record list under the wrong key is refused rather than silently producing an empty pair list
    wrong = record_live_extractors(artifact_path=artifact, cup_collision_geom="cup_a_bottom_collision",
                                   pair_key="collisions", occluded_from_record=lambda record: record["occluded"])
    with pytest.raises(ValueError, match="RAW_PAIR_KEY_REQUIRED"):
        wrong["support_distance_m"](samples, {})
