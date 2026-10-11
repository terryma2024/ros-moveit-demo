"""Registered leases, event kinds and sources, and the ratified window schema."""

from __future__ import annotations

import hashlib
import json

from act_episode_audit_support import (
    ZERO,
    _arm_evaluation,
    _formal_writer,
    _lease,
    _ratified_reference,
    _resign,
    _window,
    complete_audit,
    identity,
    scope,
)
import pytest

from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.episode_audit.checks import (
    FORMAL_PHASES,  # F5: the prescribed lifecycle
    MANIFEST_KIND,
)
from so101_demo.act.episode_audit.verification import verify_audit_manifest
from so101_demo.act.episode_audit.writer import EpisodeAuditWriter
from so101_demo.act.joints import ARM_JOINTS  # F5: the ratified joint order


def test_a_formal_audit_requires_the_registered_lease_contract(tmp_path):
    """The plan's formal scope needs the full lease; the contract already exists, so reuse it."""

    formal = dict(scope(), mode="formal")
    formal_identity = {**identity(), "lease": _lease()}
    writer = EpisodeAuditWriter(tmp_path / "ok", formal, formal_identity, {"inputs_sha256": "a" * 64})
    assert writer.identity["lease"]["batch_id"] == "batch-1"

    with pytest.raises(ValueError, match="AUDIT_IDENTITY_INVALID"):
        EpisodeAuditWriter(tmp_path / "no-lease", formal, identity(), {"inputs_sha256": "a" * 64})
    for broken in (_lease(lease_deadline_monotonic_s=100.0), _lease(worker_generation=0),
                   _lease(attempt_id="other-attempt"), _lease(batch_id="")):
        with pytest.raises(ValueError, match="AUDIT_IDENTITY_INVALID"):
            EpisodeAuditWriter(tmp_path / "broken", formal, {**identity(), "lease": broken},
                               {"inputs_sha256": "a" * 64})
    # a diagnostic audit stays admissible without a lease, keeping the modes distinct
    EpisodeAuditWriter(tmp_path / "diagnostic", scope(), identity(), {"inputs_sha256": "a" * 64})


@pytest.mark.parametrize("kind, payload", [
    ("dispatch", {"owner": "worker-1", "permit_id": "permit-1"}),
    ("accept", {"permit_id": "permit-1"}),
    ("revoke", {"permit_id": "permit-1", "reason": "deadline"}),
    ("stop", {"reason": "PICK_PLACE_VALIDATION_ABORT", "stopped_confirmed": True}),
    ("contact", {"left_contacts": 2, "right_contacts": 2, "table_contact": True}),
    # a release event describes the epoch its own identity claims
    ("release", {"release_epoch": 1, "supported": True, "no_fingertip_contact": True}),
    ("final_check", {"placement_stable": True, "retreat_stable": True}),
])
def test_the_required_event_kinds_are_accepted_and_refuse_a_wrong_payload(tmp_path, kind, payload):
    writer = EpisodeAuditWriter(tmp_path / "episode", scope(), identity(),
                                {"inputs_sha256": "a" * 64})
    writer.append_source("events", {"kind": kind, "identity": identity(), "sim_time_s": 1.0,
                                    "monotonic_ns": 1000, "payload": payload})
    # a boolean where a count belongs and an extra key are both refused for a declared kind
    for broken in ({**payload, "extra": 1},
                   {**payload, **({"left_contacts": True} if kind == "contact"
                                  else {"reason": True} if "reason" in payload
                                  else {"permit_id": 1} if "permit_id" in payload
                                  else {"stopped_confirmed": 1} if kind == "stop"
                                  else {"release_epoch": True} if kind == "release"
                                  else {"placement_stable": "yes"} if kind == "final_check"
                                  else {"owner": 1})}):
        other = EpisodeAuditWriter(tmp_path / f"bad-{len(broken)}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("events", {"kind": kind, "identity": identity(), "sim_time_s": 1.0,
                                           "monotonic_ns": 1000, "payload": broken})


def test_the_physics_observation_must_follow_the_source_contract(tmp_path):
    """The raw block is typed against what the MuJoCo source actually publishes (T3-F1)."""

    good = {"simulation_time_s": 1.1, "simulation_step": 11, "left_contact_count": 2,
            "right_contact_count": 2, "table_contact": True, "maximum_normal_force_n": 0.5,
            "cup_position_world_m": [0.02, -0.28, 0.165], "other_contact_geoms": ["table_collision"]}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("physics", {"kind": "contact", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": good})
    for broken in ({**good, "extra": 1}, {**good, "left_contact_count": True},
                   {**good, "table_contact": 1}, {**good, "maximum_normal_force_n": -0.1},
                   {**good, "cup_position_world_m": [0.0, 0.0]},
                   {**good, "cup_position_world_m": [0.0, 0.0, float("inf")]},
                   {key: value for key, value in good.items() if key != "simulation_time_s"}):
        other = EpisodeAuditWriter(tmp_path / f"bad-{len(str(broken))}-{id(broken) % 97}", scope(),
                                   identity(), {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("physics", {"kind": "contact", "sim_time_s": 1.1,
                                            "release_epoch": 1, "observation": broken})


def test_a_reference_record_may_preserve_the_observer_raw_frame(tmp_path):
    """The audit must be able to hold the raw history the observer keeps (T3-F1)."""

    raw = {"joint_names": ["shoulder_pan", "shoulder_lift"], "sim_stamp_ns": 1100000000,
           "received_monotonic_ns": 900000, "velocities": [0.0, 0.0]}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": True, **raw})
    for broken in ({"joint_names": []}, {"sim_stamp_ns": 0}, {"received_monotonic_ns": -1},
                   {"velocities": [0.0]}, {"velocities": ["x", "y"]}):
        other = EpisodeAuditWriter(tmp_path / f"bad-{sorted(broken)[0]}-{len(str(broken))}", scope(),
                                   identity(), {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("references", {"reference_time_s": 1.1,
                                               "source": "CONTROLLER_REFERENCE",
                                               "positions": [0.1] * 6, "accepted": True, **broken})
    # a partial raw group is refused: all four fields or none
    third = EpisodeAuditWriter(tmp_path / "partial", scope(), identity(), {"inputs_sha256": "a" * 64})
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        third.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                           "positions": [0.1] * 6, "accepted": True,
                                           "joint_names": ["a", "b"]})


def test_readback_refuses_a_resigned_partial_raw_reference(tmp_path):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    lines = (path.parent / "references.jsonl").read_text().splitlines()
    row = json.loads(lines[0])
    row["joint_names"] = ["a", "b"]
    payload = ("\n".join([json.dumps(row, sort_keys=True, separators=(",", ":"))]) + "\n").encode()
    _resign(writer, path, "references.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_REFERENCE_INVALID"):
        verify_audit_manifest(path)


def test_a_registered_source_document_is_admitted_and_a_time_only_block_is_not(tmp_path):
    """The real evidence_dict document must pass; a timestamp alone must not (T3-F1)."""

    document = {"publisher_sequence": 7, "simulation_time_s": 1.1, "simulation_step": 11,
                "reset_epoch": 1, "paused": False, "left_contact_count": 2, "right_contact_count": 2,
                "table_contact": True, "other_contact_geoms": ["table_collision"],
                "maximum_normal_force_n": 0.5, "cup_position_world_m": [0.02, -0.28, 0.165],
                "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
                "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
                "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0]}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("physics", {"kind": "contact", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": document})
    for kind, observation in (
            ("contact", {"simulation_time_s": 1.1, "simulation_step": 11}),
            ("pose", {"simulation_time_s": 1.1, "simulation_step": 11}),
            ("retract", {"simulation_time_s": 1.1, "simulation_step": 11, "table_contact": True}),
            ("support", {"simulation_time_s": 1.1, "simulation_step": 11, "supported": True}),
            ("contact", {**document, "other_contact_geoms": [1, 2]})):
        other = EpisodeAuditWriter(tmp_path / f"bad-{kind}-{len(observation)}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("physics", {"kind": kind, "sim_time_s": 1.1, "release_epoch": 1,
                                            "observation": observation})


def test_readback_requires_exact_types_and_correlated_clocks(tmp_path):
    """Sequences are integers, clocks agree, and an event identity is the episode's (T3-F3)."""

    # a boolean or float sequence is refused at admission, so the writer cannot record one
    writer = EpisodeAuditWriter(tmp_path / "seq", scope(), identity(), {"inputs_sha256": "a" * 64})
    with pytest.raises(ValueError, match="AUDIT_ROW_INVALID"):
        writer.bind_row(0, 1.0, "a", "b", True)
    # a physics envelope clock must be finite and equal the observation clock
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                         "observation": {"simulation_time_s": 1.2,
                                                         "simulation_step": 1,
                                                         "cup_position_world_m": [0.0, 0.0, 0.0]}})
    # an event identity must be the episode's, and its release epoch cannot go backwards
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("events", {"kind": "phase_start",
                                        "identity": {**identity(), "reset_epoch": 9},
                                        "sim_time_s": 1.0, "monotonic_ns": 1,
                                        "payload": {"phase": "SEARCH"}})
    writer.append_source("events", {"kind": "phase_start",
                                    "identity": {**identity(), "release_epoch": 1},
                                    "sim_time_s": 1.0, "monotonic_ns": 1,
                                    "payload": {"phase": "SEARCH"}})
    # a backwards release epoch is refused, and an identity from another attempt is not the episode's; the
    # lease clause applies to an episode that names one, so it is exercised by its own unit control
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("events", {"kind": "phase_start",
                                        "identity": {**identity(), "release_epoch": 0},
                                        "sim_time_s": 1.0, "monotonic_ns": 2,
                                        "payload": {"phase": "SEARCH"}})
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("events", {"kind": "phase_start",
                                        "identity": {**identity(), "attempt_id": "other"},
                                        "sim_time_s": 1.0, "monotonic_ns": 3,
                                        "payload": {"phase": "SEARCH"}})
    # readback repeats the clock correlation on a re-signed stream of its own
    case = tmp_path / "sealed"
    case.mkdir(parents=True, exist_ok=True)
    sealed, window = complete_audit(case)
    path = sealed.seal(window)
    row = json.loads((path.parent / "physics.jsonl").read_text().splitlines()[0])
    row["sim_time_s"] = None
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _resign(sealed, path, "physics.jsonl", payload)
    with pytest.raises(ValueError, match="AUDIT_PHYSICS_INVALID"):
        verify_audit_manifest(path)


def test_the_ratified_window_schema_is_enforced_for_a_formal_audit(tmp_path):
    """Proposal B: the window's fields and per-outcome ordering are ratified and enforced."""

    # the writer carries full source coverage first, so each attempt below fails on the window alone
    writer = _formal_writer(tmp_path / "window")
    writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                        "positions": [0.1] * 6, "accepted": True,
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
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window() | {"extra": 1})
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(label_cutoff_s=1.5))                    # outside the physics window
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(first_command_s=1.5))                   # after the physics end
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(source_schedule={"head": [1.1, 1.0], "wrist": [1.0, 1.1]}))
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(permitted_gaps_s=[[0.5, 0.6]]))         # outside the collection window
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(source_schedule={"head": [0.9, 1.0], "wrist": [1.0, 1.1]}))
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(streams_required=[], source_schedule={}))   # nothing required, nothing seen
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(outcome="no_command"))                  # must null both instants
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        writer.seal(_window(outcome="interrupted_diagnostic"))      # never formal evidence
    # a diagnostic audit may record a legacy window, but one that opts into the ratified shape is held
    # to it: an interrupted diagnostic window is legal, a complete one without a cutoff is not
    interrupted = EpisodeAuditWriter(tmp_path / "interrupted", scope(), identity(),
                                     {"inputs_sha256": "a" * 64})
    # An interrupted capture still names original acquired frames, never an invented inventory.
    minter = AcquisitionMinter()
    for camera in ("head", "wrist"):
        for stamp in (1., 1.1, 1.2):
            interrupted.append_acquisition(minter.mint(camera, session_id="s", reset_epoch=1,
                stamp_s=stamp, received_monotonic_ns=round(stamp * 1e9) + 1, pixels=ZERO))
    assert interrupted.seal(_window(outcome="interrupted_diagnostic", label_cutoff_s=None)).is_file()
    bad_diagnostic = EpisodeAuditWriter(tmp_path / "bad-diagnostic", scope(), identity(),
                                        {"inputs_sha256": "a" * 64})
    with pytest.raises(ValueError, match="AUDIT_WINDOW_INVALID"):
        bad_diagnostic.seal(_window(label_cutoff_s=None))

    # the writer creates its own root, so only its parent must exist
    diagnostic = EpisodeAuditWriter(tmp_path / "legacy", scope(), identity(),
                                    {"inputs_sha256": "a" * 64})
    assert diagnostic.seal({"start_s": 1.0}).is_file()               # the diagnostic path is unchanged


def test_a_formal_audit_may_not_seal_without_source_coverage(tmp_path):
    """A formal seal must carry physics, references, events and a release (T3-F5)."""

    empty = _formal_writer(tmp_path / "empty")
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        empty.seal({**_window(), "first_command_s": 1.1, "physics_end_s": 1.1})

    partial = _formal_writer(tmp_path / "partial")
    partial.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                      "observation": {"simulation_time_s": 1.1,
                                                      "simulation_step": 1,
                                                      "cup_position_world_m": [0.0, 0.0, 0.0]}})
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        partial.seal({**_window(), "first_command_s": 1.1, "physics_end_s": 1.1})

    complete = _formal_writer(tmp_path / "complete")
    complete.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                          "positions": [0.1] * 6, "accepted": True,
                                        # F5: coverage needs one complete raw group, not a bare
                                        # projection, so the legacy flat group travels with it
                                        "joint_names": list(ARM_JOINTS),
                                        "sim_stamp_ns": 1_100_000_000,
                                        "received_monotonic_ns": 1_100_000_001,
                                        "velocities": [0.0] * 6})
    complete.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                       "observation": {"simulation_time_s": 1.1,
                                                       "simulation_step": 1,
                                                       "cup_position_world_m": [0.0, 0.0, 0.0]}})
    complete.append_source("physics", {"kind": "support", "sim_time_s": 1.1,
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
    complete.append_source("physics", {"kind": "pose", "sim_time_s": 1.1,
                                              "release_epoch": 1,
                                              "observation": {"simulation_time_s": 1.1, "simulation_step": 1,
                                                             "cup_position_world_m": [0.0, 0.0, 0.0],
                                                             "planning_scene_observation": _scene,
                                                             "controller_feedback": _feedback}})
    complete.append_source("physics", {"kind": "contact", "sim_time_s": 1.1,
                                              "release_epoch": 1,
                                              "observation": {"simulation_time_s": 1.1, "simulation_step": 1, "left_contact_count": 0,
                                                     "right_contact_count": 0, "table_contact": True}})
    complete.append_source("physics", {"kind": "retract", "sim_time_s": 1.1,
                                              "release_epoch": 1,
                                              "observation": {"simulation_time_s": 1.1, "simulation_step": 1, "cup_position_world_m": [0.0, 0.0, 0.0]}})
    for kind, payload in ([*[("phase_complete", {"phase": phase, "physics_step": 1})
                             for phase in FORMAL_PHASES],
                            ("release", {"release_epoch": 1, "supported": True,
                                         "no_fingertip_contact": True})]):
        complete.append_source("events", {"kind": kind, "identity": {**identity(), "lease": _lease()},
                                          "sim_time_s": 1.1, "monotonic_ns": 1, "payload": payload})
    # this formal audit has coverage but no bound row, so its window says exactly that (T3-F11); it must
    # also hold the acquisitions its schedule declares, which is the rule the matcher enforces
    minter = AcquisitionMinter()
    for camera in ("head", "wrist"):
        for stamp in (1.0, 1.1, 1.2):
            complete.append_acquisition(minter.mint(
                camera, session_id="s", reset_epoch=1, stamp_s=stamp,
                received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO))
    # this sub-case's rows all sit at 1.1, so its window states that rather than borrowing the shared literal
    assert complete.seal(_window(outcome="no_label", label_cutoff_s=None,
                                 physics_end_s=1.1)).is_file()
    # the diagnostic mode keeps its previous behaviour, which is what the plan separates
    diagnostic = EpisodeAuditWriter(tmp_path / "diagnostic", scope(), identity(),
                                    {"inputs_sha256": "a" * 64})
    assert diagnostic.seal({"start_s": 1.0}).is_file()


def test_the_ratified_reference_frames_are_accepted_and_validated(tmp_path):
    """Proposal A: per-kind frames with their clocks, an evaluation and a checked map."""

    base = {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
            "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("references", {**base, **_ratified_reference()})

    def broken(**changes):
        document = json.loads(json.dumps(_ratified_reference()))
        for key, value in changes.items():
            if value is None:
                document.pop(key, None)
            else:
                document[key] = value
        return document

    frames = _ratified_reference()["frames"]
    cases = [broken(frames={**frames, "arm": {**frames["arm"], "evaluation": {
                 **_arm_evaluation(), "basis": "published", "goal_id": "g", "accepted_sim_s": 1.0}}}),
             broken(frames={**frames, "arm": {**frames["arm"], "evaluation": {
                 **_arm_evaluation(), "goal_id": None, "accepted_sim_s": None}}}),
             broken(projection_map=[["arm", 0], ["arm", 1], ["arm", 2], ["arm", 3], ["arm", 4],
                                    ["gripper", 3]]),
             broken(projected_positions=[0.9, 0.2, 0.3, 0.4, 0.5, 0.6]),
             broken(frames={**frames, "arm": {**frames["arm"], "velocities": [0.0] * 4}}),
             broken(frames={"arm": frames["arm"]}),
             broken(frames={**frames, "base": frames["gripper"]}),
             # the provenance checks the fifth verdict named as independent of A.1
             broken(frames={**frames, "gripper": {**frames["gripper"], "evaluation": {
                 **_arm_evaluation(), "requested_sim_time_s": 1.3}}}),
             broken(frames={**frames, "gripper": {**frames["gripper"], "evaluation": {
                 **_arm_evaluation(), "accepted_sim_s": 1.2}}}),
             broken(frames={**frames, "gripper": {**frames["gripper"], "evaluation": {
                 **_arm_evaluation(), "revoked_sim_s": 1.0}}}),
             broken(projection_map=[["arm", 0]] * 6),
             broken(frames={**frames, "arm": {**frames["arm"], "joint_names": ["a"] * 4,
                                              "published_positions": [0.1] * 4,
                                              "published_velocities": [0.0] * 4,
                                              "evaluated_positions": [0.1] * 4,
                                              "evaluated_velocities": [0.0] * 4}}),
             broken(frames={**frames, "gripper": {**frames["gripper"],
                                                  "joint_names": ["g", "h"],
                                                  "published_positions": [0.6, 0.7],
                                                  "published_velocities": [0.0, 0.0],
                                                  "evaluated_positions": [0.6, 0.7],
                                                  "evaluated_velocities": [0.0, 0.0]}})]
    for index, document in enumerate(cases):
        other = EpisodeAuditWriter(tmp_path / f"bad-{index}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("references", {**base, **document})
    mixed = EpisodeAuditWriter(tmp_path / "mixed", scope(), identity(), {"inputs_sha256": "a" * 64})
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        mixed.append_source("references", {**base, **_ratified_reference(),
                                           "joint_names": ["a"], "sim_stamp_ns": 1,
                                           "received_monotonic_ns": 1, "velocities": [0.0]})


@pytest.mark.parametrize("change", ["positive", "wrong_target", "evaluated_position",
                                   "evaluated_velocity", "future_outside_tolerance"])
def test_sealed_readback_checks_published_reference_causality(tmp_path, change):
    writer, window = complete_audit(tmp_path)
    path = writer.seal(window)
    row = json.loads(writer.files.references.read_text().splitlines()[0])
    row.update(_ratified_reference())
    for frame in row["frames"].values():
        frame["evaluation"].update(basis="published", goal_id=None, accepted_sim_s=None)
    arm = row["frames"]["arm"]
    if change == "wrong_target":
        arm["sim_stamp_ns"] -= 10_000_000
    elif change == "future_outside_tolerance":
        arm["sim_stamp_ns"] += 1001
    elif change == "evaluated_position":
        arm["evaluated_positions"][0] = 0.9
        row["projected_positions"][0] = row["positions"][0] = 0.9
    elif change == "evaluated_velocity":
        arm["evaluated_velocities"][0] = 0.02
    _resign(writer, path, "references.jsonl",
            (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())
    if change == "positive":
        assert verify_audit_manifest(path)["kind"] == MANIFEST_KIND
    else:
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            verify_audit_manifest(path)


def test_the_planning_scene_and_feedback_records_are_validated(tmp_path):
    """Proposal C's two records: accepted and typified, so a gate can be derived from them."""

    scene = {"scene_revision": 3, "attached_objects": ["plastic_cup"],
             "world_object_ids": ["plastic_cup", "table"], "is_diff": False, "sim_time_s": 1.1,
             "source": "search_boundary"}
    feedback = [{"controller": "arm", "joint_names": ["1", "2", "3", "4", "5"],
                 "commanded_positions": [0.1, 0.2, 0.0, 0.0, 0.0],
                 "measured_positions": [0.1, 0.2, 0.0, 0.0, 0.0],
                 "measured_velocities": [0.0, 0.0, 0.0, 0.0, 0.0],
                 "status_sequence": 4, "sim_time_s": 1.1, "source_sim_time_s": 1.1},
                {"controller": "gripper", "joint_names": ["6"],
                 "commanded_positions": [0.6], "measured_positions": [0.6],
                 "measured_velocities": [0.0], "status_sequence": 4, "sim_time_s": 1.1, "source_sim_time_s": 1.1}]
    pose = {"simulation_time_s": 1.1, "simulation_step": 11, "cup_position_world_m": [0.0, 0.0, 0.0]}
    writer = EpisodeAuditWriter(tmp_path / "ok", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                     "observation": {**pose, "planning_scene_observation": scene,
                                                     "controller_feedback": feedback}})
    for index, broken in enumerate(({**scene, "sim_time_s": 1.2},
                                    {**scene, "attached_objects": ["b", "a"]},
                                    {**scene, "scene_revision": -1},
                                    {**scene, "extra": 1},
                                    {**scene, "source": ""})):
        other = EpisodeAuditWriter(tmp_path / f"bad-scene-{index}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                            "observation": {**pose,
                                                            "planning_scene_observation": broken}})
    for index, broken_feedback in enumerate(([{**feedback[0], "sim_time_s": 1.2}],
                                             [{**feedback[0], "measured_positions": [0.1]}],
                                             [{**feedback[0], "controller": "neck"}],
                                             [{**feedback[0], "status_sequence": 0}],
                                             [{**feedback[0], "joint_names": []}])):
        other = EpisodeAuditWriter(tmp_path / f"bad-fb-{index}", scope(), identity(),
                                   {"inputs_sha256": "a" * 64})
        with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
            other.append_source("physics", {"kind": "pose", "sim_time_s": 1.1, "release_epoch": 1,
                                            "observation": {**pose,
                                                            "controller_feedback": broken_feedback}})


def test_the_per_kind_history_must_keep_its_ordering_across_the_stream(tmp_path):
    """A second packed reference may not rewind its kind's stamps, receipts or sequence (T3-F1)."""

    base = {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
            "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True}
    writer = EpisodeAuditWriter(tmp_path / "ordered", scope(), identity(), {"inputs_sha256": "a" * 64})
    writer.append_source("references", {**base, **_ratified_reference()})
    later = json.loads(json.dumps(_ratified_reference()))
    later["frames"]["arm"]["evaluation"]["requested_sim_time_s"] = 1.2
    later["frames"]["gripper"]["evaluation"]["requested_sim_time_s"] = 1.2
    later["frames"]["arm"]["sim_stamp_ns"] = 1200000000
    later["frames"]["arm"]["received_monotonic_ns"] = 901000
    later["frames"]["arm"]["observer_sequence"] = 8
    later["frames"]["gripper"] = {**later["frames"]["gripper"], "sim_stamp_ns": 1200000000,
                                  "received_monotonic_ns": 901100, "observer_sequence": 8}
    writer.append_source("references", {**base, "reference_time_s": 1.2, **later})
    rewind = json.loads(json.dumps(later))
    rewind["frames"]["arm"]["evaluation"]["requested_sim_time_s"] = 1.3
    rewind["frames"]["gripper"]["evaluation"]["requested_sim_time_s"] = 1.3
    rewind["frames"]["arm"]["sim_stamp_ns"] = 1100000000
    with pytest.raises(ValueError, match="AUDIT_SCHEMA_INVALID"):
        writer.append_source("references", {**base, "reference_time_s": 1.3, **rewind})


def test_readback_refuses_a_formal_stream_that_steps_without_a_release(tmp_path):
    """T3-F3: a re-signed formal stream may not advance its release epoch without a release event naming it."""

    (tmp_path / "case").mkdir(parents=True, exist_ok=True)
    writer, window = complete_audit(tmp_path / "case")
    path = writer.seal(window)
    audit = path.parent
    source = json.dumps(dict(scope(), mode="formal"), sort_keys=True,
                        separators=(",", ":")).encode()
    audit.joinpath("source.json").write_bytes(source)
    document = json.loads(path.read_bytes())
    document["files"]["source.json"] = {"path": "source.json", "size": len(source),
                                        "sha256": hashlib.sha256(source).hexdigest()}
    document["scope_sha256"] = hashlib.sha256(source).hexdigest()
    document["window"] = _window()
    identity_bytes = json.dumps({**identity(), "lease": _lease()}, sort_keys=True,
                                separators=(",", ":")).encode()
    audit.joinpath("episode.json").write_bytes(identity_bytes)
    document["files"]["episode.json"] = {"path": "episode.json", "size": len(identity_bytes),
                                         "sha256": hashlib.sha256(identity_bytes).hexdigest()}
    document["identity"] = {**identity(), "lease": _lease()}
    # the stream steps to epoch 2 - later than the episode's declared initial 1 - and no release event names it,
    # because the declared initial epoch is exempt from transition naming (T3-F3, eighth verdict)
    events_lines = (audit / "events.jsonl").read_text().splitlines()
    events_bytes = ("\n".join(json.dumps({**json.loads(line),
                                           "identity": {**json.loads(line)["identity"], "lease": _lease(),
                                                        "release_epoch": 2}},
                                          sort_keys=True, separators=(",", ":"))
                               for line in events_lines) + "\n").encode()
    audit.joinpath("events.jsonl").write_bytes(events_bytes)
    document["files"]["events.jsonl"] = {"path": "events.jsonl", "size": len(events_bytes),
                                         "sha256": hashlib.sha256(events_bytes).hexdigest()}
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="AUDIT_EVENT_INVALID"):
        verify_audit_manifest(path)


def test_readback_reapplies_the_formal_coverage_gate(tmp_path):
    """T3-F5: an audit relabelled formal without coverage must not verify."""

    (tmp_path / "case").mkdir(parents=True, exist_ok=True)
    writer, window = complete_audit(tmp_path / "case")
    path = writer.seal(window)
    audit = path.parent
    # relabel the scope as formal and give it a ratified window, so only coverage can fail
    source = json.dumps(dict(scope(), mode="formal"), sort_keys=True,
                        separators=(",", ":")).encode()
    audit.joinpath("source.json").write_bytes(source)
    document = json.loads(path.read_bytes())
    document["files"]["source.json"] = {"path": "source.json", "size": len(source),
                                        "sha256": hashlib.sha256(source).hexdigest()}
    document["scope_sha256"] = hashlib.sha256(source).hexdigest()
    document["window"] = _window()
    # a formal audit also names the registered lease, so the identity is rewritten to match
    identity_bytes = json.dumps({**identity(), "lease": _lease()}, sort_keys=True,
                                separators=(",", ":")).encode()
    audit.joinpath("episode.json").write_bytes(identity_bytes)
    document["files"]["episode.json"] = {"path": "episode.json", "size": len(identity_bytes),
                                         "sha256": hashlib.sha256(identity_bytes).hexdigest()}
    document["identity"] = {**identity(), "lease": _lease()}
    # its events must carry the same lease too, or the identity rule refuses before the coverage gate does;
    # the rewrite is recorded in this same manifest document, the way the two above are
    events_lines = (audit / "events.jsonl").read_text().splitlines()
    # T3-F3(a)+seal tie: the stream must model a complete episode, so a release event is appended at the
    # identity's own epoch with the next sequence number, which the per-row admission requires
    _first, _last = json.loads(events_lines[0]), json.loads(events_lines[-1])
    events_lines.append(json.dumps({**_first, "sequence": _last["sequence"] + 1, "kind": "release",
                                    "identity": {**_first["identity"], "lease": _lease(),
                                                 "release_epoch": 1},
                                    "payload": {"release_epoch": 1, "supported": True,
                                                "no_fingertip_contact": True}},
                                   sort_keys=True, separators=(",", ":")))
    # the stream is kept at its initial epoch: this control is about coverage, and a step no release names
    # would be refused by the tie before that gate is reached
    events_bytes = ("\n".join(json.dumps({**json.loads(line),
                                           "identity": {**json.loads(line)["identity"], "lease": _lease(),
                                                        "release_epoch": 1}},
                                           sort_keys=True, separators=(",", ":"))
                               for line in events_lines) + "\n").encode()
    audit.joinpath("events.jsonl").write_bytes(events_bytes)
    document["files"]["events.jsonl"] = {"path": "events.jsonl", "size": len(events_bytes),
                                         "sha256": hashlib.sha256(events_bytes).hexdigest()}
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="AUDIT_FORMAL_COVERAGE_INCOMPLETE"):
        verify_audit_manifest(path)
