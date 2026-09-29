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
from types import SimpleNamespace
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
        # the port reads the reset generation from the verified receipt when it stamps a document or seals a case, so a
        # double without `reset` is refused by name rather than silently given epoch zero
        self.reset = SimpleNamespace(receipt=SimpleNamespace(new_epoch=4))

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


def _records_root():
    """The raw-records root the evidence attachment must carry, per the port's own contract."""

    import tempfile
    from pathlib import Path as _Path

    return _Path(tempfile.mkdtemp())


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
    # the port forwards the canonical sample AND the grid sample it builds for the phase, so the assertion is that the
    # sample it was given is among what the recorder received - the exact list is the port's business, not this test's
    assert sample_document in double.appended, double.appended
    # a caller that STATES the case's epochs must be right: the seal refuses a disagreement by name rather than
    # ignoring it (CP-1583), and a case that ends after FINAL_CHECK carries the incremented release epoch
    artifact = port.seal_live_evidence({"scenario_id": "full-01", "session_id": "session-1",
                                        "attempt_id": "attempt-1", "reset_epoch": 4,
                                        "release_epoch": 1})
    assert artifact["sha256"] == "a" * 64
    # the seal happens after FINAL_CHECK, so the release epoch is the incremented one - the same value the runner
    # verifies RELEASE and everything after it with (CP-1555)
    assert double.sealed == [{"case_id": "full-01", "session_id": "session-1",
                              "attempt_id": "attempt-1", "reset_epoch": 4, "release_epoch": 1}]


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


def test_campaign_journal_plan_covers_all_fourteen_cases_before_anything_runs(tmp_path):
    from so101_demo.act.task8_live_evidence import plan_campaign_journals

    plan = plan_campaign_journals(tmp_path, _manifest())
    assert [case_id for case_id, _ in plan] == [f"prefix-{i:02d}" for i in range(1, 10)] + \
        [f"full-{i:02d}" for i in range(1, 6)]
    assert len({path for _, path in plan}) == 14
    assert all(path.parent == tmp_path / "task8-live" / "cases" for _, path in plan)
    assert all(not path.exists() for _, path in plan)
    # a conflicting existing journal stops the run before it starts
    plan[0][1].write_text("{}")
    with pytest.raises(ValueError, match="TASK8_JOURNAL_EXISTS"):
        plan_campaign_journals(tmp_path, _manifest())
    # an invalid bundle root is refused outright
    with pytest.raises(ValueError, match="TASK8_CAMPAIGN_BUNDLE_ROOT_INVALID"):
        plan_campaign_journals(tmp_path / "missing", _manifest())


def test_journal_row_must_belong_to_the_bundle_that_produced_it():
    from so101_demo.act.task8_live_evidence import require_case_row_matches_bundle

    identities = {"source_provenance_sha256": "e" * 64, "runtime_config_sha256": "f" * 64,
                  "contact_policy_fingerprint": "a" * 64}
    row = _journal_row()
    assert require_case_row_matches_bundle(
        row, identities=identities, manifest_document_sha256="9" * 64)["case_id"] == "full-01"
    for key in ("source_provenance_sha256", "runtime_config_sha256",
                "contact_policy_fingerprint"):
        with pytest.raises(ValueError, match="TASK8_JOURNAL_IDENTITY_MISMATCH"):
            require_case_row_matches_bundle(_journal_row(**{key: "7" * 64}),
                                            identities=identities,
                                            manifest_document_sha256="9" * 64)
    with pytest.raises(ValueError, match="TASK8_JOURNAL_IDENTITY_MISMATCH"):
        require_case_row_matches_bundle(row, identities=identities,
                                        manifest_document_sha256="8" * 64)
    with pytest.raises(ValueError, match="TASK8_JOURNAL_IDENTITY_MISMATCH"):
        require_case_row_matches_bundle(row, identities={"source_provenance_sha256": "e" * 64},
                                        manifest_document_sha256="9" * 64)


class _Contact:
    def __init__(self, body1="left_finger", body2="cup"):
        self.body1, self.body2 = body1, body2


class _ObjectState:
    def __init__(self, position=(0.0, 0.0, 0.1), orientation=(0.0, 0.0, 0.0, 1.0)):
        self.position_world, self.orientation_xyzw = position, orientation


class _Evidence:
    """The readback's per-step physics evidence (SimulationEvidence-shaped)."""

    def __init__(self, *, left=(), right=(), other=(), minimum_signed_distance_m=0.0,
                 position=(0.0, 0.0, 0.1), orientation=(0.0, 0.0, 0.0, 1.0),
                 simulation_step=0, simulation_time_s=0.0):
        self.simulation_step = simulation_step
        self.simulation_time_s = simulation_time_s
        self.left_fingertip_contacts = tuple(left)
        self.right_fingertip_contacts = tuple(right)
        self.other_object_contacts = tuple(other)
        self.minimum_signed_distance_m = minimum_signed_distance_m
        self.object_state = _ObjectState(position, orientation)


def test_frame_aggregates_follow_the_contact_evidence_not_a_label():
    from so101_demo.act.task8_live_evidence import derive_frame_aggregates

    held = derive_frame_aggregates(_Evidence(left=[_Contact()], right=[_Contact()],
                                            minimum_signed_distance_m=0.02),
                                   support_distance_max_m=0.005)
    assert held["bilateral_contact"] is True
    assert held["no_fingertip_contact"] is False
    assert held["cup_supported"] is False          # airborne on both pads: not resting on support
    assert held["holding_state"] == "HOLDING"
    assert held["cup_support_distance_m"] == 0.02
    assert held["cup_position_m"] == [0.0, 0.0, 0.1]

    resting = derive_frame_aggregates(_Evidence(other=[_Contact(body2="table")],
                                                minimum_signed_distance_m=0.001),
                                      support_distance_max_m=0.005)
    assert resting["bilateral_contact"] is False
    assert resting["no_fingertip_contact"] is True
    assert resting["cup_supported"] is True        # in contact with the support
    assert resting["holding_state"] == "EMPTY"

    single = derive_frame_aggregates(_Evidence(left=[_Contact()], minimum_signed_distance_m=0.02),
                                     support_distance_max_m=0.005)
    assert single["bilateral_contact"] is False    # one pad is not a grasp
    assert single["holding_state"] == "APPROACHING"


def test_capture_evidence_fields_compose_a_canonical_sample(recorder):
    """The readback's per-frame fields plus the phase bits make a recorder-accepted sample."""

    from so101_demo.act.task8_live_evidence import build_live_evidence_sample
    from so101_demo.adapters.act.pick_place_readback import PickPlacePhysicalReadback

    rec, root = recorder
    canonical = sample(root, step=0)
    evidence = _Evidence(left=[_Contact()], right=[_Contact()], minimum_signed_distance_m=0.02)
    # the adapter reads the scene's clock bound and both documents' own time, and requires the three physics stamps to
    # agree - so they carry the world's own value rather than a third opinion
    captured = {"world": evidence,
                "scene": {"clock_interval_end_monotonic_ns": 12_500_000_000,
                          "simulation_time_s": evidence.simulation_time_s},
                "contact": {"simulation_time_s": evidence.simulation_time_s},
                "observation": {}, "reference": {},
                "source_stamps_s": canonical["source_stamps_s"],
                "source_received_wall_s": canonical["source_received_monotonic_s"]}
    adapter = object.__new__(PickPlacePhysicalReadback)
    fields = adapter.capture_evidence_fields(captured, support_distance_max_m=0.005,
                                             raw_records=canonical["raw_records"],
                                             # the end-effector position is MuJoCo output: the caller holding the model supplies it, and the
                                             # recorder refuses a frame without it rather than recording one that never had it
                                             end_effector_position_m=[0.0, 0.0, 0.1])
    assert type(fields["physics_step"]) is int and fields["sim_time_s"] >= 0
    built = build_live_evidence_sample(
        identity={"case_id": "full-01", "session_id": "session-1", "attempt_id": "attempt-1",
                  "reset_epoch": 4, "release_epoch": 0},
        phase="TRANSPORT", physics_step=fields["physics_step"], sim_time_s=fields["sim_time_s"],
        source_stamps_s=fields["source_stamps_s"],
        source_received_monotonic_s=fields["source_received_monotonic_s"],
        raw_records=fields["raw_records"], holding_state=fields["holding_state"],
        frame={"wrist_frame_valid": True, "wrist_target_visible": True},
        contact={"observation_valid": True, "bilateral_contact": fields["bilateral_contact"],
                 "no_fingertip_contact": fields["no_fingertip_contact"],
                 "cup_supported": fields["cup_supported"], "released": False,
                 "placement_stable": False},
        measurements={"cup_support_distance_m": fields["cup_support_distance_m"],
                      "end_effector_position_m": [0.0, 0.0, 0.1],
                      "cup_position_m": fields["cup_position_m"],
                      "cup_orientation_xyzw": fields["cup_orientation_xyzw"]})
    assert set(built) == set(canonical)
    rec.append(built)                      # the recorder accepts the composed sample
    with pytest.raises(Exception):
        adapter.capture_evidence_fields({"world": evidence}, support_distance_max_m=0.005,
                                        raw_records={})


def _window_sample(recorder_root, time_s, phase, step):
    document = sample(recorder_root, step=step)
    document["sim_time_s"] = time_s
    document["phase"] = phase
    return document


def test_window_opens_at_search_and_enforces_the_frozen_grid(recorder):
    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow

    rec, root = recorder
    reference = sample(root, step=0)
    identity = {key: reference[key] for key in
                ("case_id", "session_id", "attempt_id", "reset_epoch", "release_epoch")}
    window = LiveEvidenceWindow(rec, identity=identity)
    window.bind_reset_epoch((identity)["reset_epoch"])
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_WINDOW_NOT_OPEN"):
        window.add_grid(_window_sample(root, 0.0, "IDLE", 0))
    window.add_grid(_window_sample(root, 0.0, "SEARCH", 0))
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_GRID_GAP"):
        window.add_grid(_window_sample(root, 0.3, "MICRO_LIFT", 1))
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_GRID_REGRESSION"):
        window.add_grid(_window_sample(root, 0.0, "MICRO_LIFT", 1))
    window.add_grid(_window_sample(root, 0.1, "MICRO_LIFT", 1))
    window.add_event(_window_sample(root, 0.15, "CONTACT_EDGE", 1))
    assert window.grid_count == 2 and window.event_count == 1
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_WINDOW_INCOMPLETE"):
        window.seal()                       # the run has not reached FINAL_CHECK yet


def test_window_seals_only_after_final_check_and_then_refuses_more_samples(recorder):
    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow

    rec, root = recorder
    reference = sample(root, step=0)
    identity = {key: reference[key] for key in
                ("case_id", "session_id", "attempt_id", "reset_epoch", "release_epoch")}
    window = LiveEvidenceWindow(rec, identity=identity)
    window.bind_reset_epoch((identity)["reset_epoch"])
    for index, phase in enumerate(LiveEvidenceWindow.REQUIRED_PHASES):
        window.add_grid(_window_sample(root, index * 0.1, phase, index))
    artifact = window.seal()
    assert set(artifact) == {"path", "sha256", "schema_version"}
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_WINDOW_SEALED"):
        window.add_grid(_window_sample(root, 0.7, "FINAL_CHECK", 7))


def test_case_driver_reaches_the_window_and_seals_into_the_case_directory(tmp_path):
    from so101_demo.act.task8_live_evidence import (
        CaseEvidenceDriver, LiveEvidenceWindow,
    )

    driver = CaseEvidenceDriver(case_id="full-01", staging_root=tmp_path, session_id="session-1",
                                attempt_id="attempt-1", reset_epoch=4)
    driver.bind_reset_epoch(4)
    assert driver.case_root == tmp_path / "full-01" and driver.case_root.is_dir()
    reference = sample(tmp_path, step=0)
    # the recorder resolves each raw record against ITS evidence root, so materialise them there
    for record in reference["raw_records"].values():
        relative = record if isinstance(record, str) else (
            record.get("path") or record.get("relative_path") or record.get("file"))
        assert isinstance(relative, str), f"unexpected raw record shape: {type(record)}"
        target = driver.case_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source = tmp_path / relative            # the fixture wrote the real record there
        payload = source.read_bytes() if source.is_file() else b"raw"
        if not target.exists():
            target.write_bytes(payload)         # same bytes, so the recorded digest still holds
    fields = {"physics_step": 0, "sim_time_s": 0.0,
              "source_stamps_s": reference["source_stamps_s"],
              "source_received_monotonic_s": reference["source_received_monotonic_s"],
              "raw_records": reference["raw_records"], "holding_state": "HOLDING"}
    frame = {"wrist_frame_valid": True, "wrist_target_visible": True}
    contact = {"observation_valid": True, "bilateral_contact": True,
               "no_fingertip_contact": False, "cup_supported": False, "released": False,
               "placement_stable": False}
    measurements = {"cup_support_distance_m": 0.02, "end_effector_position_m": [0.0, 0.0, 0.1],
                    "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]}
    # a grid sample before CLOSE is refused, exactly as the window requires
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_WINDOW_NOT_OPEN"):
        driver.observe(fields, phase="IDLE", frame=frame, contact=contact,
                       measurements=measurements)
    # CLOSE is the first GRID point (that is what opens the window); an edge event is an addition
    for index, phase in enumerate(LiveEvidenceWindow.REQUIRED_PHASES):
        present = dict(fields, physics_step=index, sim_time_s=index * 0.1)
        driver.observe(present, phase=phase, frame=frame, contact=contact,
                       measurements=measurements)
    driver.observe(dict(fields, physics_step=99, sim_time_s=6.05), phase="RELEASE_EPOCH_EDGE",
                   frame=frame, contact=contact, measurements=measurements, event=True)
    artifact = driver.seal()
    assert set(artifact) == {"path", "sha256", "schema_version"}
    assert driver.window.grid_count == len(LiveEvidenceWindow.REQUIRED_PHASES)
    assert driver.window.event_count == 1


def test_driver_observe_capture_composes_from_a_readback_capture(tmp_path):
    """One call takes a readback capture through the driver to the frozen grid."""

    from so101_demo.act.task8_live_evidence import CaseEvidenceDriver, LiveEvidenceWindow
    from so101_demo.adapters.act.pick_place_readback import PickPlacePhysicalReadback

    driver = CaseEvidenceDriver(case_id="full-02", staging_root=tmp_path, session_id="session-1",
                                attempt_id="attempt-2", reset_epoch=7)
    driver.bind_reset_epoch(7)
    reference = sample(tmp_path, step=0)
    for record in reference["raw_records"].values():
        relative = record if isinstance(record, str) else (
            record.get("path") or record.get("relative_path") or record.get("file"))
        target = driver.case_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source = tmp_path / relative
        if not target.exists():
            target.write_bytes(source.read_bytes() if source.is_file() else b"raw")
    adapter = object.__new__(PickPlacePhysicalReadback)
    identity = {"case_id": "full-02", "session_id": "session-1", "attempt_id": "attempt-2",
                "reset_epoch": 7, "release_epoch": 0}
    document = sample(tmp_path, step=0)
    document.update(identity)
    evidence = _Evidence(left=[_Contact()], right=[_Contact()], simulation_step=0,
                         simulation_time_s=0.0, minimum_signed_distance_m=0.02)
    frame = {"wrist_frame_valid": True, "wrist_target_visible": True}
    contact = {"observation_valid": True, "bilateral_contact": True,
               "no_fingertip_contact": False, "cup_supported": False, "released": False,
               "placement_stable": False}
    measurements = {"cup_support_distance_m": 0.02, "end_effector_position_m": [0.0, 0.0, 0.1],
                    "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]}
    for index, phase in enumerate(LiveEvidenceWindow.REQUIRED_PHASES):
        captured = {"world": _Evidence(left=[_Contact()], right=[_Contact()],
                                       simulation_step=index, simulation_time_s=index * 0.1,
                                       minimum_signed_distance_m=0.02),
                    "scene": {"clock_interval_end_monotonic_ns": 12_500_000_000 + index * 100_000_000,
                      "simulation_time_s": index * 0.1,
                              "simulation_time_s": index * 0.1},
                    "contact": {"simulation_time_s": index * 0.1}, "observation": {}, "reference": {},
                    "source_stamps_s": document["source_stamps_s"],
                    "source_received_wall_s": document["source_received_monotonic_s"]}
        driver.observe_capture(adapter, captured, phase=phase, frame=frame, contact=contact,
                               measurements=measurements, raw_records=document["raw_records"],
                               support_distance_max_m=0.005)
    assert driver.window.grid_count == len(LiveEvidenceWindow.REQUIRED_PHASES)
    assert set(driver.seal()) == {"path", "sha256", "schema_version"}


def _published_row(**overrides):
    row = {"case_id": "full-01", "mode": "full", "status": "PASSED",
           "live_evidence_path": "/run/full-01/live.json", "live_evidence_sha256": "b" * 64,
           "child_retirement_receipt_path": "/run/full-01-child.json",
           "child_receipt_sha256": "c" * 64,
           "stack_retirement_receipt_path": "/run/full-01-stack.json",
           "stack_receipt_sha256": "d" * 64,
           "anchor": "default", "stop_after": None, "campaign_id": "campaign-1",
           "session_id": "session-1", "manifest_sha256": "9" * 64, "completed_phases": [],
           "stopped_confirmed": True, "full_restart_retired": True,
           "eligible_for_formal_collection": False}
    row.update(overrides)
    return row


def test_published_case_row_translates_into_the_journal_row_shape():
    from so101_demo.act.task8_live_evidence import case_row_to_journal_row

    identities = {"source_provenance_sha256": "e" * 64, "runtime_config_sha256": "f" * 64,
                  "contact_policy_fingerprint": "a" * 64}
    journal = case_row_to_journal_row(_published_row(), identities=identities,
                                      manifest_document_sha256="9" * 64)
    assert journal["child_retirement_receipt_sha256"] == "c" * 64
    assert journal["stack_retirement_receipt_sha256"] == "d" * 64
    assert journal["source_provenance_sha256"] == "e" * 64
    # the producer's extra fields do not leak into the closed journal shape
    assert "anchor" not in journal and "campaign_id" not in journal
    # a prefix row must not claim a live-evidence artifact, and the rule is re-applied here
    with pytest.raises(ValueError, match="TASK8_PREFIX_EVIDENCE_FORBIDDEN"):
        case_row_to_journal_row(_published_row(case_id="prefix-01", mode="phase_prefix"),
                                identities=identities, manifest_document_sha256="9" * 64)
    with pytest.raises(ValueError, match="TASK8_CASE_ROW_INVALID"):
        case_row_to_journal_row({"case_id": "full-01"}, identities=identities,
                                manifest_document_sha256="9" * 64)


# --- protocol v2 additions (Task 7): nine phases, row provenance, release correlation ----------------------

V2_PHASES = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE", "RADIAL_RETREAT",
             "FINAL_CHECK")
V2_ROW_KEYS = {"head_rgb_ref", "wrist_rgb_ref", "head_camera_info_ref", "wrist_camera_info_ref",
               "head_segmentation_ref", "wrist_segmentation_ref", "head_depth_ref", "wrist_depth_ref",
               "joint_receipt", "tf_receipt", "reference_receipt", "physics_receipt",
               "session_id", "reset_epoch", "attempt_id", "phase", "source_stamp", "receive_monotonic_s",
               "digests"}


def test_the_window_requires_exactly_the_designs_nine_phases():
    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow

    assert LiveEvidenceWindow.REQUIRED_PHASES == V2_PHASES


def _v2_sample(**overrides):
    """Call the real builder with the real keyword-only interface."""

    from so101_demo.act.task8_live_evidence import build_live_evidence_sample

    refs = {"head_rgb": "raw/head.png", "wrist_rgb": "raw/wrist.png",
            "head_camera_info": "raw/head.json", "wrist_camera_info": "raw/wrist.json",
            "head_segmentation": "raw/head-seg.png", "wrist_segmentation": "raw/wrist-seg.png",
            "head_depth": "raw/head.npy", "wrist_depth": "raw/wrist.npy"}
    arguments = {"identity": {"case_id": "c", "session_id": "s", "attempt_id": "a",
                              "reset_epoch": 1, "release_epoch": 1},
                 "phase": "SEARCH", "physics_step": 0, "sim_time_s": 0.0,
                 "source_stamps_s": {name: 0.0 for name in refs},
                 "source_received_monotonic_s": {name: 0.0 for name in refs},
                 "raw_records": dict(refs), "holding_state": "EMPTY",
                 "frame": {"wrist_frame_valid": True, "wrist_target_visible": True},
                 # the builder requires these exact shapes, read from its own validation
                 "contact": {"observation_valid": True, "bilateral_contact": False,
                             "no_fingertip_contact": False, "cup_supported": True,
                             "released": False, "placement_stable": False},
                 "measurements": {"cup_support_distance_m": 0.01, "end_effector_position_m": [0.0, 0.0, 0.1],
                                  "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]}}
    arguments.update(overrides)
    return build_live_evidence_sample(**arguments)


def test_every_ten_hz_row_cites_its_raw_records_and_identity():
    row = _v2_sample()
    text = json.dumps(row, sort_keys=True)
    for name in ("raw/head.png", "raw/wrist.png", "raw/head.json", "raw/wrist.json",
                 "raw/head-seg.png", "raw/wrist-seg.png", "raw/head.npy", "raw/wrist.npy"):
        assert name in text, name
    assert row["phase"] == "SEARCH"
    assert "task_camera" not in text, "the audit camera may not appear in ACT observations"


def test_the_task_camera_is_not_an_observation_source():
    with pytest.raises(ValueError, match="TASK_CAMERA_NOT_AN_OBSERVATION"):
        _v2_sample(raw_records={"task_camera": "raw/task.png"})


def _release_fixture(rows_suffix=0):
    return [{"phase": "RELEASE", "source_stamp": 1.0 + 0.1 * index, "receive_monotonic_s": 1.0 + 0.1 * index,
             "release_epoch": 7, "cup_pose": [0.1, 0.2, 0.3], "cup_velocity": [0.0, 0.0, 0.0]}
            for index in range(4)]


def test_release_correlation_needs_three_consecutive_preceding_rows_and_a_same_epoch_open():
    from so101_demo.act.task8_live_evidence import correlate_release_open

    rows = _release_fixture()
    open_event = {"operation": "gripper_open", "release_epoch": 7, "source_stamp": 1.45,
                  "command_ref": "raw/controller/open.json"}
    result = correlate_release_open(rows, open_event, period_s=0.1)
    assert result["support_rows"] == 3 and result["verdict"] == "PASS"
    with pytest.raises(ValueError, match="RELEASE_EPOCH_MISMATCH"):
        correlate_release_open(rows, {**open_event, "release_epoch": 8}, period_s=0.1)
    with pytest.raises(ValueError, match="RAW_REF_REQUIRED"):
        correlate_release_open(rows, {**open_event, "command_ref": None}, period_s=0.1)


def test_release_correlation_refuses_a_gap_a_summary_and_an_unindexed_mask():
    from so101_demo.act.task8_live_evidence import correlate_release_open

    gapped = _release_fixture()
    gapped[1]["source_stamp"] = 1.35                       # not consecutive at 10 Hz
    with pytest.raises(ValueError, match="SUPPORT_ROWS_NOT_CONSECUTIVE"):
        correlate_release_open(gapped, {"operation": "gripper_open", "release_epoch": 7, "source_stamp": 1.45,
                                        "command_ref": "raw/open.json"}, period_s=0.1)
    with pytest.raises(ValueError, match="SUMMARY_ONLY_SUBSTITUTE"):
        correlate_release_open(_release_fixture(), {"operation": "gripper_open", "release_epoch": 7,
                                                    "source_stamp": 1.45, "command_ref": "raw/open.json",
                                                    "summary": "opened"}, period_s=0.1)
    with pytest.raises(ValueError, match="UNINDEXED_REF"):
        correlate_release_open(_release_fixture(), {"operation": "gripper_open", "release_epoch": 7,
                                                    "source_stamp": 1.45,
                                                    "command_ref": "raw/open.json",
                                                    "mask_ref": "raw/mask.png"},
                               period_s=0.1, indexed=("raw/open.json",))


def test_a_failed_run_invalid_seals_its_window_instead_of_sealing_evidence(recorder):
    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow

    rec, root = recorder
    reference = sample(root, step=0)
    identity = {key: reference[key] for key in
                ("case_id", "session_id", "attempt_id", "reset_epoch", "release_epoch")}
    window = LiveEvidenceWindow(rec, identity=identity)
    window.bind_reset_epoch((identity)["reset_epoch"])
    window.add_grid(_window_sample(root, 0.0, "SEARCH", 0))
    # a run that never reached FINAL_CHECK must not seal as evidence
    result = window.invalidate("TASK8_ABORT")
    assert result["status"] == "INVALID" and result["reason"] == "TASK8_ABORT"
    assert result["grid_count"] == 1 and result["event_count"] == 0
    assert window.invalidate("TASK8_ABORT") == result          # idempotent
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_INVALID_REASON_REQUIRED"):
        window.invalidate("")



def test_the_port_binds_one_evidence_window_and_refuses_a_second():
    """The bind is one-shot and refused once recording has begun, mirroring the startup receipt."""

    from so101_demo.adapters.act.pick_place_search_port import (PickPlaceSearchPhasePort,
                                                               PickPlaceSearchPortError)

    class Window:
        def __init__(self):
            self.sealed = False

        def seal(self):
            self.sealed = True
            return {"status": "SEALED"}

    port = PickPlaceSearchPhasePort(_Boundary())
    window = Window()
    port.bind_live_evidence(window, support_distance_max_m=0.02,
                            raw_records_root=_records_root())
    assert port.live_evidence_window is window
    with pytest.raises(PickPlaceSearchPortError, match="TASK8_LIVE_EVIDENCE_ALREADY_BOUND"):
        # the fields travel with the call, so the guard that refuses this one is the already-bound rule and not the
        # field check that now runs first
        port.bind_live_evidence(Window(), support_distance_max_m=0.02, raw_records_root=_records_root())
    with pytest.raises(PickPlaceSearchPortError, match="TASK8_LIVE_EVIDENCE_WINDOW_INVALID"):
        PickPlaceSearchPhasePort(_Boundary()).bind_live_evidence(
            object(), support_distance_max_m=0.02, raw_records_root=_records_root())



def test_a_window_refuses_observation_until_the_reset_epoch_is_bound(recorder):
    """The epoch is unknown until the reset receipt is verified, so an unbound window must not record or seal."""

    from so101_demo.act.task8_live_evidence import UNBOUND_RESET_EPOCH, LiveEvidenceWindow

    rec, root = recorder
    reference = sample(root, step=0)
    identity = {key: reference[key] for key in
                ("case_id", "session_id", "attempt_id", "release_epoch")}
    identity["reset_epoch"] = None
    window = LiveEvidenceWindow(rec, identity=identity)
    assert window.reset_epoch is UNBOUND_RESET_EPOCH
    with pytest.raises(ValueError, match="TASK8_RESET_EPOCH_UNBOUND"):
        window.add_grid(_window_sample(root, 0.0, "SEARCH", 0))
    with pytest.raises(ValueError, match="TASK8_RESET_EPOCH_UNBOUND"):
        window.add_event(_window_sample(root, 0.0, "SEARCH", 0))
    with pytest.raises(ValueError, match="TASK8_RESET_EPOCH_UNBOUND"):
        window.seal()


def test_the_reset_epoch_binds_once_and_reaches_the_identity(recorder):
    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow

    rec, root = recorder
    reference = sample(root, step=0)
    identity = {key: reference[key] for key in
                ("case_id", "session_id", "attempt_id", "release_epoch")}
    identity["reset_epoch"] = None
    window = LiveEvidenceWindow(rec, identity=identity)
    window.bind_reset_epoch(7)
    assert window.reset_epoch == 7 and window.identity["reset_epoch"] == 7
    with pytest.raises(ValueError, match="TASK8_RESET_EPOCH_ALREADY_BOUND"):
        window.bind_reset_epoch(8)
    for bad in (True, -1, None, "7"):
        with pytest.raises(ValueError, match="TASK8_RESET_EPOCH_INVALID"):
            LiveEvidenceWindow(rec, identity=dict(identity)).bind_reset_epoch(bad)
    # an unbound window cannot open at all, so "bound after opening" is unreachable by construction; the reachable
    # too-late case is a window invalidated by the retirement path before its epoch ever arrived
    window.add_grid(_window_sample(root, 0.0, "SEARCH", 0))
    with pytest.raises(ValueError, match="TASK8_RESET_EPOCH_ALREADY_BOUND"):
        window.bind_reset_epoch(9)
    other = LiveEvidenceWindow(rec, identity=dict(identity))
    other.invalidate("OWNER_RETIRE")
    with pytest.raises(ValueError, match="TASK8_RESET_EPOCH_BOUND_TOO_LATE"):
        other.bind_reset_epoch(9)


def test_the_port_gives_its_attached_window_the_verified_reset_epoch():
    """The epoch only exists once the reset receipt is verified, so the port passes it on and refuses a window that cannot take it."""

    from so101_demo.adapters.act.pick_place_search_port import (PickPlaceSearchPhasePort,
                                                               PickPlaceSearchPortError)

    class Window:
        def __init__(self):
            self.bound = []

        def seal(self):
            return {"status": "SEALED"}

        def bind_reset_epoch(self, epoch):
            self.bound.append(epoch)

    port = PickPlaceSearchPhasePort(_Boundary())
    window = Window()
    port.bind_live_evidence(window, support_distance_max_m=0.02,
                            raw_records_root=_records_root())
    port._bind_case_epoch({"reset_epoch": 7})
    assert window.bound == [7]
    port._bind_case_epoch({"reset_epoch": 7})       # the window's own one-shot rule is what refuses a repeat

    class NoBind:
        def seal(self):
            return {"status": "SEALED"}

    other = PickPlaceSearchPhasePort(_Boundary())
    other.bind_live_evidence(NoBind(), support_distance_max_m=0.02, raw_records_root=_records_root())
    with pytest.raises(PickPlaceSearchPortError, match="TASK8_LIVE_EVIDENCE_WINDOW_INVALID"):
        other._bind_case_epoch({"reset_epoch": 7})
    PickPlaceSearchPhasePort(_Boundary())._bind_case_epoch({"reset_epoch": 7})   # no window, nothing to bind
