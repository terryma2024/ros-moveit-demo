"""Task 8P3: live evidence is a closed 10 Hz causal record, sealed only when complete.

Canonical sample shape (pinned here):
  case_id/session_id/attempt_id/reset_epoch/release_epoch/physics_step/sim_time_s/phase
  source_stamps_s and source_received_monotonic_s over world/scene/contact/head/wrist/arm/neck
  raw_records: {source: {"relative_path", "sha256"}} inside the same artifact
  holding_state/wrist_frame_valid/wrist_target_visible/contact_observation_valid
  bilateral_contact/no_fingertip_contact/cup_supported/released/placement_stable
  cup_support_distance_m/end_effector_position_m/cup_position_m/cup_orientation_xyzw
Every gap that is not "valid frame and target genuinely not visible" is evidence loss, never a
bounded occlusion: the recorder refuses it instead of degrading.
"""

import hashlib
import json
from pathlib import Path

import pytest

SOURCES = ("world", "scene", "contact", "head", "wrist", "arm", "neck")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sample(root: Path, *, step=0, phase="CLOSE", **overrides):
    raw = {}
    for source in SOURCES:
        payload = f"{source}:{step}".encode()
        path = root / "raw" / f"{source}-{step}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        raw[source] = {"relative_path": path.relative_to(root).as_posix(),
                       "sha256": _sha(payload)}
    document = {
        "case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
        "reset_epoch": 4, "release_epoch": 0, "physics_step": step,
        "sim_time_s": step * 0.1, "phase": phase,
        "source_stamps_s": {source: step * 0.1 for source in SOURCES},
        "source_received_monotonic_s": {source: 100.0 + step * 0.1 for source in SOURCES},
        "raw_records": raw,
        "holding_state": "HOLDING", "wrist_frame_valid": True, "wrist_target_visible": True,
        "contact_observation_valid": True, "bilateral_contact": True,
        "no_fingertip_contact": False, "cup_supported": True, "released": False,
        "placement_stable": True, "cup_support_distance_m": 0.001,
        "end_effector_position_m": [0.0, 0.0, 0.1], "cup_position_m": [0.0, 0.0, 0.1],
        "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
    }
    document.update(overrides)
    return document


@pytest.fixture
def recorder(tmp_path):
    from so101_demo.act.task8_live_evidence import Task8LiveEvidenceRecorder

    root = tmp_path / "case-root"
    root.mkdir()
    return Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=root,
                                     session_id="session-1", attempt_id="attempt-1"), root


def test_sealed_artifact_is_closed_and_lists_every_sample(recorder):
    rec, root = recorder
    for step in range(3):
        rec.append(sample(root, step=step))
    artifact = rec.seal({"case_id": "full-01", "session_id": "session-1",
                         "attempt_id": "attempt-1", "reset_epoch": 4, "release_epoch": 0})
    path = Path(artifact["path"])
    assert path.is_file() and artifact["sha256"] == _sha(path.read_bytes())
    assert artifact["schema_version"] == 1
    index = json.loads(path.read_text())
    assert index["sample_count"] == 3
    assert [entry["physics_step"] for entry in index["samples"]] == [0, 1, 2]
    for entry in index["samples"]:
        assert _sha((root / entry["relative_path"]).read_bytes()) == entry["sha256"]
    with pytest.raises(ValueError):
        rec.seal({"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
                  "reset_epoch": 4, "release_epoch": 0})           # sealed once, never again


@pytest.mark.parametrize("mutation", [
    "missing_phase", "non_finite", "missing_stamp", "raw_hash_wrong", "raw_missing",
    "identity_mismatch", "contact_observation_invalid", "wrist_frame_invalid",
])
def test_incomplete_or_incoherent_evidence_is_refused(recorder, mutation):
    rec, root = recorder
    document = sample(root)
    if mutation == "missing_phase":
        document.pop("phase")
    elif mutation == "non_finite":
        document["cup_support_distance_m"] = float("nan")
    elif mutation == "missing_stamp":
        document["source_stamps_s"].pop("wrist")
    elif mutation == "raw_hash_wrong":
        document["raw_records"]["wrist"]["sha256"] = "0" * 64
    elif mutation == "raw_missing":
        (root / document["raw_records"]["world"]["relative_path"]).unlink()
    elif mutation == "identity_mismatch":
        document["session_id"] = "other-session"
    elif mutation == "contact_observation_invalid":
        document["contact_observation_valid"] = False
    else:
        document["wrist_frame_valid"] = False
    with pytest.raises(ValueError):
        rec.append(document)


def test_occlusion_is_only_timed_for_a_valid_frame_with_hidden_target(recorder):
    rec, root = recorder
    honest = sample(root, step=0, wrist_frame_valid=True, wrist_target_visible=False)
    rec.append(honest)                       # a genuine, bounded visual occlusion is accepted
    artifact = rec.seal({"case_id": "full-01", "session_id": "session-1",
                         "attempt_id": "attempt-1", "reset_epoch": 4, "release_epoch": 0})
    index = json.loads(Path(artifact["path"]).read_text())
    assert index["samples"][0]["wrist_target_visible"] is False


@pytest.mark.parametrize("mutation,code", [
    ("gap", "TASK8_LIVE_EVIDENCE_GRID_GAP"),
    ("duplicate", "TASK8_LIVE_EVIDENCE_GRID_REGRESSION"),
    ("regression", "TASK8_LIVE_EVIDENCE_GRID_REGRESSION"),
])
def test_ten_hertz_grid_rejects_gaps_duplicates_and_regressions(mutation, code):
    """A missing grid point is not occlusion and may not be smoothed over."""

    from so101_demo.act.task8_live_evidence import validate_evidence_grid

    times = [0.0, 0.1, 0.2, 0.3]
    if mutation == "gap":
        times = [0.0, 0.1, 0.3]
    elif mutation == "duplicate":
        times = [0.0, 0.1, 0.1, 0.2]
    else:
        times = [0.0, 0.1, 0.05, 0.2]
    samples = [{"sim_time_s": value} for value in times]
    with pytest.raises(ValueError, match=code):
        validate_evidence_grid(samples, period_s=0.1, tolerance_s=0.01)


def test_grid_accepts_a_complete_causal_sequence_and_reports_its_length():
    from so101_demo.act.task8_live_evidence import validate_evidence_grid

    samples = [{"sim_time_s": index * 0.1} for index in range(5)]
    assert validate_evidence_grid(samples, period_s=0.1, tolerance_s=0.01) == 5
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_GRID_EMPTY"):
        validate_evidence_grid([], period_s=0.1, tolerance_s=0.01)


def test_sample_builder_cannot_drift_from_the_recorder_shape(recorder):
    """The builder and the recorder must agree: a built sample is accepted verbatim."""

    from so101_demo.act.task8_live_evidence import build_live_evidence_sample

    rec, root = recorder
    canonical = sample(root, step=0)
    built = build_live_evidence_sample(
        identity={"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
                  "reset_epoch": 4, "release_epoch": 0},
        phase=canonical["phase"], physics_step=canonical["physics_step"],
        sim_time_s=canonical["sim_time_s"], source_stamps_s=canonical["source_stamps_s"],
        source_received_monotonic_s=canonical["source_received_monotonic_s"],
        raw_records=canonical["raw_records"], holding_state=canonical["holding_state"],
        frame={"wrist_frame_valid": True, "wrist_target_visible": True},
        contact={"observation_valid": True, "bilateral_contact": True,
                 "no_fingertip_contact": False, "cup_supported": True, "released": False,
                 "placement_stable": True},
        measurements={"cup_support_distance_m": 0.001,
                      "end_effector_position_m": [0.0, 0.0, 0.1],
                      "cup_position_m": [0.0, 0.0, 0.1],
                      "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]})
    assert set(built) == set(canonical)
    rec.append(built)                       # the recorder accepts it without adaptation


def test_sample_builder_refuses_incomplete_readback_inputs(recorder):
    from so101_demo.act.task8_live_evidence import build_live_evidence_sample

    rec, root = recorder
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_SAMPLE_INVALID"):
        build_live_evidence_sample(
            identity={"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
                      "reset_epoch": 4, "release_epoch": 0},
            phase="CLOSE", physics_step=0, sim_time_s=0.0, source_stamps_s={},
            source_received_monotonic_s={}, raw_records={}, holding_state="HOLDING",
            frame={"wrist_frame_valid": True},          # missing the visibility flag
            contact={"observation_valid": True, "bilateral_contact": True,
                     "no_fingertip_contact": False, "cup_supported": True, "released": False,
                     "placement_stable": True},
            measurements={"cup_support_distance_m": 0.001,
                          "end_effector_position_m": [0.0, 0.0, 0.1],
                          "cup_position_m": [0.0, 0.0, 0.1],
                          "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]})


class _NeckSweepChecker:
    def check(self, *args, **kwargs):
        return True


class _Boundary:
    """The minimal boundary the search port validates at construction."""

    def __init__(self):
        self.neck_sweep_checker = _NeckSweepChecker()

    def begin(self, *args, **kwargs):
        return {}

    def search(self, *args, **kwargs):
        return {}

    def safe_stop(self, *args, **kwargs):
        return True


class _RecordingRecorder:
    def __init__(self):
        self.appended = []
        self.sealed = []

    def append(self, sample):
        if set(sample) != set(_CANONICAL_KEYS):
            raise ValueError("TASK8_LIVE_EVIDENCE_SAMPLE_INVALID")
        self.appended.append(sample)

    def seal(self, identity):
        self.sealed.append(identity)
        return {"path": "/tmp/live.json", "sha256": "a" * 64, "schema_version": 1}


_CANONICAL_KEYS = (
    "case_id", "session_id", "attempt_id", "reset_epoch", "release_epoch", "physics_step",
    "sim_time_s", "phase", "source_stamps_s", "source_received_monotonic_s", "raw_records",
    "holding_state", "wrist_frame_valid", "wrist_target_visible", "contact_observation_valid",
    "bilateral_contact", "no_fingertip_contact", "cup_supported", "released",
    "placement_stable", "cup_support_distance_m", "end_effector_position_m", "cup_position_m",
    "cup_orientation_xyzw",
)


def test_search_port_without_a_recorder_keeps_its_previous_behaviour():
    from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPhasePort

    port = PickPlaceSearchPhasePort(_Boundary())
    port.record_evidence(None)                       # no recorder attached: a no-op
    with pytest.raises(ValueError, match="LIVE_EVIDENCE_SEAL_UNAVAILABLE"):
        port.seal_live_evidence({"scenario_id": "full-01", "session_id": "s",
                                 "attempt_id": "a", "reset_epoch": 1, "release_epoch": 0})


def test_search_port_forwards_only_complete_samples_and_never_swallows_a_refusal(recorder):
    from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPhasePort

    rec, root = recorder
    double = _RecordingRecorder()
    port = PickPlaceSearchPhasePort(_Boundary(), evidence_recorder=double)
    # a partial sample must be refused loudly, never recorded as if it were complete
    with pytest.raises(ValueError, match="TASK8_SEARCH_PORT_EVIDENCE_INVALID"):
        port.record_evidence({"phase": "SEARCH"})
    assert double.appended == []
    sample_document = sample(root)
    port.record_evidence(sample_document)
    assert double.appended == [sample_document]
    artifact = port.seal_live_evidence({"scenario_id": "full-01", "session_id": "session-1",
                                        "attempt_id": "attempt-1", "reset_epoch": 4,
                                        "release_epoch": 0})
    assert artifact["sha256"] == "a" * 64
    assert double.sealed == [{"case_id": "full-01", "session_id": "session-1",
                              "attempt_id": "attempt-1", "reset_epoch": 4, "release_epoch": 0}]


def test_readback_adapter_emits_canonical_samples_through_one_builder(recorder):
    """The adapter's entry point must produce the same shape the recorder accepts."""

    from so101_demo.adapters.act.pick_place_readback import PickPlacePhysicalReadback

    rec, root = recorder
    canonical = sample(root, step=0)
    adapter = object.__new__(PickPlacePhysicalReadback)      # no model needed for this entry point
    built = adapter.live_evidence_sample(
        identity={"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
                  "reset_epoch": 4, "release_epoch": 0},
        phase=canonical["phase"], physics_step=canonical["physics_step"],
        sim_time_s=canonical["sim_time_s"], source_stamps_s=canonical["source_stamps_s"],
        source_received_monotonic_s=canonical["source_received_monotonic_s"],
        raw_records=canonical["raw_records"], holding_state=canonical["holding_state"],
        frame={"wrist_frame_valid": True, "wrist_target_visible": True},
        contact={"observation_valid": True, "bilateral_contact": True,
                 "no_fingertip_contact": False, "cup_supported": True, "released": False,
                 "placement_stable": True},
        measurements={"cup_support_distance_m": 0.001,
                      "end_effector_position_m": [0.0, 0.0, 0.1],
                      "cup_position_m": [0.0, 0.0, 0.1],
                      "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]})
    assert set(built) == set(canonical)
    rec.append(built)
    with pytest.raises(ValueError):
        adapter.live_evidence_sample(
            identity={"case_id": "full-01"}, phase="CLOSE", physics_step=0, sim_time_s=0.0,
            source_stamps_s={}, source_received_monotonic_s={}, raw_records={},
            holding_state="HOLDING", frame={}, contact={}, measurements={})


def test_case_journal_path_is_strict_and_refuses_reuse(tmp_path):
    from so101_demo.act.task8_live_evidence import resolve_case_journal_path

    run_root = tmp_path / "run"
    run_root.mkdir()
    journal = resolve_case_journal_path(run_root, "prefix-01")
    assert journal == run_root / "task8-live" / "cases" / "prefix-01.json"
    journal.write_text("{}")
    with pytest.raises(ValueError, match="TASK8_JOURNAL_EXISTS"):
        resolve_case_journal_path(run_root, "prefix-01")     # never spliced into a continuation
    (run_root / "task8-live" / "campaign-result.json").write_text("{}")
    with pytest.raises(ValueError, match="TASK8_CAMPAIGN_JOURNAL_EXISTS"):
        resolve_case_journal_path(run_root, "full-01")
    for bad in ("../escape", "prefix-1", "PREFIX-01", "", 7):
        with pytest.raises(ValueError):
            resolve_case_journal_path(tmp_path / "fresh", bad)


def _journal_row(**overrides):
    row = {"case_id": "full-01", "mode": "full", "status": "PASSED",
           "live_evidence_path": "/run/task8-live/cases/full-01-live.json",
           "live_evidence_sha256": "b" * 64,
           "child_retirement_receipt_path": "/run/task8-live/cases/full-01-child.json",
           "child_retirement_receipt_sha256": "c" * 64,
           "stack_retirement_receipt_path": "/run/task8-live/cases/full-01-stack.json",
           "stack_retirement_receipt_sha256": "d" * 64,
           "source_provenance_sha256": "e" * 64, "runtime_config_sha256": "f" * 64,
           "contact_policy_fingerprint": "a" * 64, "manifest_document_sha256": "9" * 64}
    row.update(overrides)
    return row


def test_full_journal_row_requires_evidence_and_both_retirement_receipts():
    from so101_demo.act.task8_live_evidence import require_case_journal_row

    assert require_case_journal_row(_journal_row(), mode="full")["status"] == "PASSED"
    for missing in ("live_evidence_sha256", "child_retirement_receipt_sha256",
                    "stack_retirement_receipt_sha256", "manifest_document_sha256"):
        with pytest.raises(ValueError):
            require_case_journal_row(_journal_row(**{missing: "not-a-digest"}), mode="full")
    with pytest.raises(ValueError, match="TASK8_JOURNAL_MODE_INVALID"):
        require_case_journal_row(_journal_row(), mode="phase_prefix")
    with pytest.raises(ValueError):
        require_case_journal_row(_journal_row(extra=1), mode="full")


def test_prefix_journal_row_may_never_carry_live_evidence():
    from so101_demo.act.task8_live_evidence import require_case_journal_row

    prefix = _journal_row(case_id="prefix-01", mode="phase_prefix", status="PASSED",
                          live_evidence_path="", live_evidence_sha256="0" * 64)
    assert require_case_journal_row(prefix, mode="phase_prefix")["case_id"] == "prefix-01"
    leaky = dict(prefix, live_evidence_sha256="b" * 64)
    with pytest.raises(ValueError, match="TASK8_PREFIX_EVIDENCE_FORBIDDEN"):
        require_case_journal_row(leaky, mode="phase_prefix")


def _manifest(prefixes=9, fulls=5):
    return {"prefix_cases": [{"case_id": f"prefix-{index:02d}"} for index in range(1, prefixes + 1)],
            "full_cases": [{"case_id": f"full-{index:02d}"} for index in range(1, fulls + 1)]}


def test_campaign_case_list_is_exactly_nine_prefixes_then_five_fulls():
    from so101_demo.act.task8_live_evidence import require_campaign_cases

    ids = require_campaign_cases(_manifest())
    assert ids == tuple([f"prefix-{index:02d}" for index in range(1, 10)]
                        + [f"full-{index:02d}" for index in range(1, 6)])
    for broken in ({"prefix_cases": [], "full_cases": [{"case_id": "full-01"}]},
                   {"prefix_cases": [{"case_id": "prefix-01"}] * 9,
                    "full_cases": [{"case_id": f"full-{index:02d}"} for index in range(1, 6)]},
                   {"prefix_cases": [{"case_id": "full-01"}] + [{"case_id": f"prefix-{i:02d}"}
                                                                for i in range(2, 10)],
                    "full_cases": [{"case_id": f"full-{index:02d}"} for index in range(1, 6)]},
                   {"prefix_cases": [{"case_id": "prefix-1"}] * 9, "full_cases": []}):
        with pytest.raises(ValueError):
            require_campaign_cases(broken)
