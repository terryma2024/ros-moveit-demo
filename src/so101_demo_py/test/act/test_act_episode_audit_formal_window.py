"""Formal coverage, sealing and the minimal window form."""

from __future__ import annotations

import hashlib
import json

from act_episode_audit_support import (
    ZERO,
    _formal_writer,
    _lease,
    _ratified_reference,
    _resign,
    _window,
    complete_audit,
    identity,
)
import pytest

from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.episode_audit.checks import (
    FORMAL_PHASES,  # F5: the prescribed lifecycle
    )
from so101_demo.act.episode_audit.verification import verify_audit_manifest
from so101_demo.act.joints import ARM_JOINTS  # F5: the ratified joint order


def _self_consistent_formal(tmp_path):
    """A formal episode whose window is derived from the rows and frames it actually holds."""

    writer = _formal_writer(tmp_path / "formal")
    minter = AcquisitionMinter()
    frames = {}
    for camera in ("head", "wrist"):
        for stamp in (1.0, 1.1, 1.2):
            frame = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO)
            writer.append_acquisition(frame)
            frames[(camera, stamp)] = frame
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True,
                                        # F5: coverage needs one complete raw group, not a bare
                                        # projection, so the legacy flat group travels with it
                                        "joint_names": list(ARM_JOINTS),
                                        "sim_stamp_ns": 1_100_000_000,
                                        "received_monotonic_ns": 1_100_000_001,
                                        "velocities": [0.0] * 6})
    writer.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": {"simulation_time_s": 1.1, "simulation_step": 1,
                                                     "cup_position_world_m": [0.0, 0.0, 0.0]}})
    writer.append_source("physics", {"kind": "support", "sim_time_s": 1.1,
                                              "release_epoch": 1,
                                              "observation": {"simulation_time_s": 1.1, "simulation_step": 1, "table_contact": True, "supported": True}})
    # F5: the ratified observations are retained with this writer, joined by the row's own instant
    _scene = {"scene_revision": 1, "attached_objects": [], "world_object_ids": [], "is_diff": False,
              "sim_time_s": 1.1, "source": "scene_port"}
    _feedback = [{"controller": "arm", "joint_names": ["1", "2", "3", "4", "5"], "commanded_positions": [0.0, 0.0, 0.0, 0.0, 0.0],
                  "measured_positions": [0.0, 0.0, 0.0, 0.0, 0.0], "measured_velocities": [0.0, 0.0, 0.0, 0.0, 0.0],
                  "status_sequence": 1, "sim_time_s": 1.1, "source_sim_time_s": 1.1},
                 # T3-F13: the action has two controllers, so the collection carries one record for each
                 {"controller": "gripper", "joint_names": ["6"], "commanded_positions": [0.0],
                  "measured_positions": [0.0], "measured_velocities": [0.0],
                  "status_sequence": 1, "sim_time_s": 1.1, "source_sim_time_s": 1.1}]
    writer.append_source("physics", {"kind": "pose", "sim_time_s": 1.1,
                                              "release_epoch": 1,
                                              "observation": {"simulation_time_s": 1.1, "simulation_step": 1,
                                                             "cup_position_world_m": [0.0, 0.0, 0.0],
                                                             "planning_scene_observation": _scene,
                                                             "controller_feedback": _feedback}})
    writer.append_source("physics", {"kind": "contact", "sim_time_s": 1.1,
                                              "release_epoch": 1,
                                              "observation": {"simulation_time_s": 1.1, "simulation_step": 1, "left_contact_count": 0,
                                                     "right_contact_count": 0, "table_contact": True}})
    writer.append_source("physics", {"kind": "retract", "sim_time_s": 1.1,
                                              "release_epoch": 1,
                                              "observation": {"simulation_time_s": 1.1, "simulation_step": 1, "cup_position_world_m": [0.0, 0.0, 0.0]}})
    for kind, payload in ([*[("phase_complete", {"phase": phase, "physics_step": 1})
                             for phase in FORMAL_PHASES],
                            ("release", {"release_epoch": 1, "supported": True,
                                         "no_fingertip_contact": True})]):
        writer.append_source("events", {"kind": kind, "identity": {**identity(), "lease": _lease()}, "sim_time_s": 1.1,
                                        "monotonic_ns": 1, "payload": payload})
    writer.bind_row(0, 1.0, frames[("head", 1.0)].acquisition_id,
                    frames[("wrist", 1.0)].acquisition_id, 1)
    # T3-F11: this fixture's five physics rows all sit at 1.1, so its window states those endpoints rather than
    # borrowing the shared helper's, which describes the relabelled-coverage fixture's rows (1.1 to 1.2)
    return writer, {**_window(), "first_command_s": 1.1, "physics_end_s": 1.1}


def test_a_self_consistent_formal_window_seals(tmp_path):
    """The positive case of T3-F11: derived from the audit's own rows and frames."""

    writer, window = _self_consistent_formal(tmp_path)
    assert writer.seal(window).is_file()


@pytest.mark.parametrize("overrides", [
    {"label_cutoff_s": 1.1},                                          # not the bound row's instant
    {"source_schedule": {"head": [1.0, 1.1, 1.15], "wrist": [1.0, 1.1]}},  # an instant never published
    {"streams_required": ["head", "wrist", "neck"]},                  # a required stream with no schedule
    {"outcome": "no_label", "label_cutoff_s": None},                  # labelled rows under a non-complete outcome
])
def test_the_formal_window_must_describe_the_rows_and_frames(tmp_path, overrides):
    """T3-F11's controls: a window that does not describe this audit's rows and frames cannot be sealed."""

    writer, window = _self_consistent_formal(tmp_path)
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal({**window, **overrides})


def test_each_complete_raw_reference_alternative_round_trips(tmp_path):
    """T3-F3's positive controls: either exclusive group alone verifies after re-sealing."""

    (tmp_path / "packed").mkdir(parents=True, exist_ok=True)
    writer, window = complete_audit(tmp_path / "packed")
    path = writer.seal(window)
    audit = path.parent
    row = json.loads((audit / "references.jsonl").read_text().splitlines()[0])
    for key in ("joint_names", "sim_stamp_ns", "received_monotonic_ns", "velocities"):
        row.pop(key, None)
    row.update(_ratified_reference())
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _resign(writer, path, "references.jsonl", payload)
    assert verify_audit_manifest(path)["kind"] == "ACT_EPISODE_AUDIT"

    (tmp_path / "legacy").mkdir(parents=True, exist_ok=True)
    writer, window = complete_audit(tmp_path / "legacy")
    path = writer.seal(window)
    audit = path.parent
    row = json.loads((audit / "references.jsonl").read_text().splitlines()[0])
    for key in ("frames", "projected_positions", "projection_map"):
        row.pop(key, None)
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _resign(writer, path, "references.jsonl", payload)
    assert verify_audit_manifest(path)["kind"] == "ACT_EPISODE_AUDIT"


def test_the_audit_names_the_runner_s_phases():
    """The audit's declared lifecycle is the runner's, and the test is what keeps it so."""

    from so101_demo.act.episode_audit.checks import FORMAL_PHASES
    from so101_demo.act.pick_place_runner import PickPlaceRunner

    assert tuple(FORMAL_PHASES) == tuple(PickPlaceRunner.PHASES)


def test_a_registered_live_sample_reaches_the_audit_and_reads_back(tmp_path):
    """T3-F1: the thirteen-key shape act/contact_live.py publishes is admitted and survives readback."""

    (tmp_path / "sample").mkdir(parents=True, exist_ok=True)
    writer, window = complete_audit(tmp_path / "sample")
    contact = {"robot_geom": "g", "object_body": "b", "normal_force_n": 0.0, "signed_distance_m": -0.001}
    writer.append_source("physics", {
        "kind": "contact", "sim_time_s": 1.1, "release_epoch": 1,
        "observation": {
            "simulation_session_id": "session-1", "reset_epoch": 1, "physics_step": 1,
            "simulation_time_s": 1.1, "model_qpos": [0.0] * 6, "model_qvel": [0.0] * 6,
            "cup_position_m": [0.0, 0.0, 0.0], "cup_velocity_m_s": [0.0, 0.0, 0.0],
            "left_contacts": [contact], "right_contacts": [contact], "other_contacts": [],
            "truncated": False, "diagnostic_hazard_breached": False}})
    path = writer.seal(window)
    assert verify_audit_manifest(path)["kind"] == "ACT_EPISODE_AUDIT"


def test_the_expert_carries_the_ratified_group_into_the_audit(tmp_path):
    """T3-F1: port -> expert -> writer -> readback with the A.1 packed group present."""

    from so101_demo.act.expert import MoveItExpertActionTap

    projected = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]

    def frame(kind, when):
        size = 5 if kind == "arm" else 1
        evaluated = projected[:5] if kind == "arm" else projected[5:]
        return {"joint_names": ([f"{index + 1}" for index in range(size)]
                                  if kind == "arm" else ["6"]),
                "published_positions": list(evaluated), "published_velocities": [0.0] * size,
                "evaluated_positions": list(evaluated), "evaluated_velocities": [0.0] * size,
                "evaluation": {"requested_sim_time_s": when, "basis": "published",
                               "goal_id": None, "accepted_sim_s": None, "revoked_sim_s": None},
                "sim_stamp_ns": int(when * 1e9), "received_monotonic_ns": 1, "observer_sequence": 1}

    class Port:
        def reference_state(self, at_s):
            return {"requested_sim_time_s": at_s, "source": "CONTROLLER_REFERENCE",
                    "positions": list(projected), "joint_names": ["1"], "sim_stamp_ns": 1,
                    "received_monotonic_ns": 1, "velocities": [0.0]}

        def reference_frames(self, kind, at_s):
            return frame(kind, at_s)

    record = MoveItExpertActionTap(Port()).reference(1.0)
    assert record["projection_map"] == [["arm", index] for index in range(5)] + [["gripper", 0]]
    assert list(record["positions"]) == list(record["projected_positions"])

    (tmp_path / "chain").mkdir(parents=True, exist_ok=True)
    writer, window = complete_audit(tmp_path / "chain")
    writer.append_source("references", {
        **{key: value for key, value in record.items() if key != "requested_sim_time_s"},
        "reference_time_s": record["requested_sim_time_s"], "accepted": True})
    path = writer.seal(window)
    assert verify_audit_manifest(path)["kind"] == "ACT_EPISODE_AUDIT"


def test_readback_refuses_a_window_naming_an_instant_no_acquisition_holds(tmp_path):
    """T3-F11: the reader repeats the seal's window predicate, so an invented in-range instant is refused."""

    writer, window = _self_consistent_formal(tmp_path / "case")
    path = writer.seal(window)
    document = json.loads(path.read_bytes())
    head = list(document["window"]["source_schedule"]["head"])
    document["window"]["source_schedule"]["head"] = sorted([*head, 1.05])   # in range, no acquisition
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        verify_audit_manifest(path)


def test_a_schedule_naming_no_instant_is_refused_at_seal(tmp_path):
    """T3-F11: an empty stream schedule is vacuous, so a seal may not accept one."""

    writer, window = _self_consistent_formal(tmp_path / "seal")
    emptied = {**window, "source_schedule": {**window["source_schedule"], "head": []}}
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(emptied)


def test_a_sealed_schedule_naming_no_instant_is_refused_on_readback(tmp_path):
    """T3-F11: a sealed manifest carrying the same emptied schedule is refused, at the manifest gate.

    The readback reaches `_window_ok` before the shared predicate, so the refusal it reports is
    `AUDIT_MANIFEST_INVALID`; what matters is that the vacuous schedule cannot survive readback at all.
    """

    sealed, window = _self_consistent_formal(tmp_path / "read")
    path = sealed.seal(window)
    document = json.loads(path.read_bytes())
    document["window"]["source_schedule"]["head"] = []
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    # an emptied schedule fails _window_ok, which the manifest gate runs before the shared predicate
    with pytest.raises(ValueError, match="AUDIT_MANIFEST_INVALID"):
        verify_audit_manifest(path)


def test_the_capture_preserves_the_packed_reference_the_tap_supplies(tmp_path):
    """T3-F1: the adapter/tap/capture path by name — the capture keeps the shape its tap produced."""

    from so101_demo.act.expert import CausalEpisodeCapture, MoveItExpertActionTap

    projected = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]

    def frame(kind, when):
        size = 5 if kind == "arm" else 1
        evaluated = projected[:5] if kind == "arm" else projected[5:]
        return {"joint_names": ([f"{index + 1}" for index in range(size)]
                                  if kind == "arm" else ["6"]),
                "published_positions": [0.0] * size, "published_velocities": [0.0] * size,
                "evaluated_positions": list(evaluated), "evaluated_velocities": [0.0] * size,
                "evaluation": {"requested_sim_time_s": when, "basis": "published",
                               "goal_id": None, "accepted_sim_s": None, "revoked_sim_s": None},
                "sim_stamp_ns": int(when * 1e9), "received_monotonic_ns": 1, "observer_sequence": 1}

    class Port:
        def reference_state(self, at_s):
            return {"requested_sim_time_s": at_s, "source": "CONTROLLER_REFERENCE",
                    "positions": list(projected), "joint_names": ["1"], "sim_stamp_ns": 1,
                    "received_monotonic_ns": 1, "velocities": [0.0]}

        def reference_frames(self, kind, at_s):
            return frame(kind, at_s)

    class Recorder:
        def __init__(self):
            self.calls = []

        def append(self, observation, positions, audit):
            self.calls.append((observation, positions, audit))

    recorder = Recorder()
    capture = CausalEpisodeCapture(recorder, MoveItExpertActionTap(Port()))
    label = capture.append({"sim_time_s": 1.0}, {"phase": "SEARCH"})
    assert list(label) == projected
    assert recorder.calls and recorder.calls[0][1] == tuple(label)
    assert set(capture.raw_reference) == {"frames", "projected_positions", "projection_map"}
    assert capture.raw_reference["projected_positions"] == projected


def test_coverage_owns_a_missing_record_while_the_window_stays_valid(tmp_path):
    """K1=B: with the camera window legal, removing a required record must reach the coverage gate."""

    (tmp_path / "cov").mkdir(parents=True, exist_ok=True)
    writer, window = _self_consistent_formal(tmp_path / "cov")
    # the window is derived from this audit's own rows and acquisitions and is sealed first, so the audit is legal
    path = writer.seal(window)
    assert verify_audit_manifest(path)
    # now remove the physics history - the camera schedule and the window it supports are untouched, and coverage
    # is checked before both the window and the row bindings, so this reaches the coverage gate specifically
    audit = path.parent
    payload = b""
    (audit / "physics.jsonl").write_bytes(payload)
    document = json.loads(path.read_bytes())
    document["files"]["physics.jsonl"] = {"path": "physics.jsonl", "size": len(payload),
                                          "sha256": hashlib.sha256(payload).hexdigest()}
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        verify_audit_manifest(path)


def test_a_window_naming_an_unacquired_instant_is_refused_as_a_window(tmp_path):
    """K1=B: a window whose schedule names an instant no acquisition holds must report the window error."""

    (tmp_path / "win").mkdir(parents=True, exist_ok=True)
    writer, window = _self_consistent_formal(tmp_path / "win")
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal({**window, "source_schedule": {"head": [1.0, 1.15, 1.2], "wrist": [1.0, 1.1, 1.2]}})


def test_the_minimal_window_form_seals_and_verifies_by_recomputation(tmp_path):
    """T3-F5: the suite's own sealable fixture seals and verifies, with the minimal window form."""

    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    print("SEALED", path.is_file())
    manifest = verify_audit_manifest(path)
    print("VERIFY kind:", manifest["kind"], "| files:", len(manifest["files"]))
    print("WINDOW", window)
