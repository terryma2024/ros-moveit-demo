"""Formal coverage, sealing and the minimal window form."""

from __future__ import annotations

import json

from act_episode_audit_support import (
    _ratified_reference,
    _resign,
    complete_audit,
)
import pytest

from so101_demo.act.episode_audit.verification import verify_audit_manifest
from teacher_formal_audit import TeacherEpisode
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)


def _self_consistent_formal(tmp_path, frozen_scene):
    """A formal Teacher episode whose window is derived from the rows and frames it actually holds."""

    return TeacherEpisode(frozen_scene).write(tmp_path / "formal")


def test_a_self_consistent_formal_window_seals(tmp_path, frozen_scene):
    """The positive case of T3-F11: derived from the audit's own rows and frames."""

    writer, window = _self_consistent_formal(tmp_path, frozen_scene)
    assert writer.seal(window).is_file()


@pytest.mark.parametrize("overrides", [
    {"label_cutoff_s": 0.2},                                          # not the bound row's instant
    {"source_schedule": {"head": [0.1, 0.2, 0.25], "wrist": [0.1, 0.2]}},  # an instant never published
    {"streams_required": ["head", "wrist", "neck"]},                  # a required stream with no schedule
    {"outcome": "no_label", "label_cutoff_s": None},                  # labelled rows under a non-complete outcome
])
def test_the_formal_window_must_describe_the_rows_and_frames(tmp_path, frozen_scene, overrides):
    """T3-F11's controls: a window that does not describe this audit's rows and frames cannot be sealed."""

    writer, window = _self_consistent_formal(tmp_path, frozen_scene)
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


def test_readback_refuses_a_window_naming_an_instant_no_acquisition_holds(tmp_path, frozen_scene):
    """T3-F11: the reader repeats the seal's window predicate, so an invented in-range instant is refused."""

    writer, window = _self_consistent_formal(tmp_path / "case", frozen_scene)
    path = writer.seal(window)
    document = json.loads(path.read_bytes())
    head = list(document["window"]["source_schedule"]["head"])
    document["window"]["source_schedule"]["head"] = sorted([*head, 0.15])   # in range, no acquisition
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        verify_audit_manifest(path)


def test_a_schedule_naming_no_instant_is_refused_at_seal(tmp_path, frozen_scene):
    """T3-F11: an empty stream schedule is vacuous, so a seal may not accept one."""

    writer, window = _self_consistent_formal(tmp_path / "seal", frozen_scene)
    emptied = {**window, "source_schedule": {**window["source_schedule"], "head": []}}
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(emptied)


def test_a_sealed_schedule_naming_no_instant_is_refused_on_readback(tmp_path, frozen_scene):
    """T3-F11: a sealed manifest carrying the same emptied schedule is refused, at the manifest gate.

    The readback reaches `_window_ok` before the shared predicate, so the refusal it reports is
    `AUDIT_MANIFEST_INVALID`; what matters is that the vacuous schedule cannot survive readback at all.
    """

    sealed, window = _self_consistent_formal(tmp_path / "read", frozen_scene)
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


def test_a_window_naming_an_unacquired_instant_is_refused_as_a_window(tmp_path, frozen_scene):
    """K1=B: a window whose schedule names an instant no acquisition holds must report the window error."""

    writer, window = _self_consistent_formal(tmp_path / "win", frozen_scene)
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal({**window, "source_schedule": {"head": [0.1, 0.15, 0.3], "wrist": [0.1, 0.2, 0.3]}})


def test_the_minimal_window_form_seals_and_verifies_by_recomputation(tmp_path):
    """T3-F5: the suite's own sealable fixture seals and verifies, with the minimal window form."""

    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    print("SEALED", path.is_file())
    manifest = verify_audit_manifest(path)
    print("VERIFY kind:", manifest["kind"], "| files:", len(manifest["files"]))
    print("WINDOW", window)
