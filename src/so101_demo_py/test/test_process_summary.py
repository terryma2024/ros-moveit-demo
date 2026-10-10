"""CP-3504: `teacher_process_summary_v1` - synthetic streams, incomplete streams and replays of known runs."""

import json
import math
import threading
from types import SimpleNamespace

import pytest

from so101_demo.core import process_summary as ps
from so101_demo.ros.teacher_safety import CupSafetyLimits
from paths import TEST_ROOT

FIXTURES = TEST_ROOT / "process_summary"
LIMITS = CupSafetyLimits(1.8916304473471774, 0.00011928116711427007)


def summary(limits=LIMITS):
    value = ps.ProcessSummary(limits=limits)
    value.phase_begin("LIFT", 10.0)
    value.phase_finish("LIFT", 12.0, "SUCCEEDED")
    value.phase_begin("DESCEND_TO_PLACE", 12.0)
    value.phase_finish("DESCEND_TO_PLACE", 14.0, "SUCCEEDED")
    return value


def test_peaks_margins_and_flags_per_phase_with_a_strict_threshold():
    value = summary()
    for index in range(1000):
        time_s = 10.0 + index * 0.002
        value.offer_step(1000 + index, time_s, 1.5, 9.75e-5)
    value.offer_step(5000, 11.0, 1.8916304473471774, 0.00011928116711427007)        # exactly the thresholds: not an exceedance
    document = value.build()
    lift = document["phases"]["LIFT"]
    assert lift["peak_force_n"] == pytest.approx(1.8916304473471774) and lift["peak_force_step"] == 5000
    assert lift["first_force_exceedance_step"] is None and lift["first_compression_exceedance_step"] is None
    assert lift["oracle_flags"] == [] and document["flags"] == {ps.FLAG_OVERLOAD: [], ps.FLAG_COLLISION: []}
    assert lift["force_margin_n"] == pytest.approx(0.0) and lift["compression_margin_um"] == pytest.approx(0.0, abs=1e-6)
    assert document["phases"]["DESCEND_TO_PLACE"]["steps"] == 0 and document["phases"]["DESCEND_TO_PLACE"]["peak_force_n"] is None
    value.offer_step(5001, 12.5, 1.8916304473471774 + 1e-9, 9e-5)                    # just over, in the next phase
    value.offer_step(5002, 13.0, 1.0, 0.00012)
    document = value.build()
    place = document["phases"]["DESCEND_TO_PLACE"]
    assert place["first_force_exceedance_step"] == 5001 and place["first_compression_exceedance_step"] == 5002
    assert place["oracle_flags"] == [ps.FLAG_OVERLOAD] and document["flags"][ps.FLAG_OVERLOAD] == ["DESCEND_TO_PLACE"]
    assert place["first_compression_exceedance_um"] == pytest.approx(120.0)
    assert document["complete"] is True and document["incomplete_reasons"] == []


def test_collision_pairs_are_recorded_with_step_depth_and_phase_and_flag_the_phase():
    value = summary()
    value.offer_collision(77, 10.5, "gripper", "table_collision", -0.0004, 3.0)
    value.offer_collision(80, 10.6, "table_collision", "gripper", -0.0009, 5.0)
    value.offer_collision(90, 13.0, "jaw", "pedestal", -0.0001, 1.0)
    document = value.build()
    lift, place = document["phases"]["LIFT"], document["phases"]["DESCEND_TO_PLACE"]
    assert lift["collision_pairs"] == [{"pair": ["gripper", "table_collision"], "first_step": 77, "max_depth_mm": pytest.approx(0.9),
                                        "max_force_n": 5.0, "count": 2}]
    assert place["collision_pairs"][0]["pair"] == ["jaw", "pedestal"]
    assert document["flags"][ps.FLAG_COLLISION] == ["LIFT", "DESCEND_TO_PLACE"]


def world(time_s, left, right, *, table=False, force=0.0, linear=0.0, angular=0.0, step=None):
    contacts = [SimpleNamespace(geom2="table_collision", normal_force_n=force)] if table else []
    return SimpleNamespace(
        simulation_time_s=time_s, simulation_step=step if step is not None else round(time_s / 0.002),
        left_fingertip_contacts=[object()] * left, right_fingertip_contacts=[object()] * right, other_object_contacts=contacts,
        object_state=SimpleNamespace(linear_velocity_world=(linear, 0.0, 0.0), angular_velocity_world=(0.0, angular, 0.0)))


def test_bilateral_contact_lost_needs_80_ms_and_only_counts_in_the_holding_phases():
    value = summary()
    for index in range(200):                                    # 100 Hz in LIFT, 10.0-11.99: contact lost 10.5..10.57 (70 ms) and 11.0..11.09 (90 ms)
        time_s = 10.0 + index * 0.01
        lost = 10.5 <= time_s <= 10.575 or 11.0 <= time_s <= 11.09
        value.offer_world(world(time_s, 0 if lost else 2, 0 if lost else 1))
    document = value.build()
    lost = document["phases"]["LIFT"]["bilateral_contact_lost"]
    assert len(lost) == 1 and lost[0]["begin_s"] == pytest.approx(11.0) and lost[0]["duration_s"] >= 0.08
    quiet = ps.ProcessSummary(limits=LIMITS)
    quiet.phase_begin("PREPARE_OPEN_GRIPPER", 0.0)
    quiet.phase_finish("PREPARE_OPEN_GRIPPER", 5.0, "SUCCEEDED")
    for index in range(100):
        quiet.offer_world(world(index * 0.01, 0, 0))
    assert quiet.build()["phases"]["PREPARE_OPEN_GRIPPER"]["bilateral_contact_lost"] == []


def test_table_contact_during_the_carry_and_the_touchdown_step():
    value = summary()
    value.offer_world(world(10.5, 2, 1))
    value.offer_world(world(12.5, 2, 1))
    value.offer_world(world(13.0, 2, 1, table=True, force=0.05, step=6500))
    document = value.build()
    assert document["phases"]["LIFT"]["early_table_contact"] is False
    place = document["phases"]["DESCEND_TO_PLACE"]
    assert place["early_table_contact"] is True and place["first_table_contact_step"] == 6500


def test_slip_release_displacement_and_settle_time():
    value = ps.ProcessSummary(limits=LIMITS)
    for state, begin, finish in (("WAIT_GRASP_STABLE", 1.0, 2.0), ("OPEN_GRIPPER", 20.0, 22.0), ("WAIT_RELEASE_SETTLE", 22.0, 24.0)):
        value.phase_begin(state, begin)
        value.phase_finish(state, finish, "SUCCEEDED")
    identity = (0.0, 0.0, 0.0, 1.0)
    value.note_pose("grasp_stable", time_s=2.0, cup_position=(0.10, 0.0, 0.20), cup_quaternion=identity,
                    tcp_position=(0.10, 0.0, 0.25), tcp_quaternion=identity)
    # the cup moved 3 mm along x and 4 mm along z in the TCP frame and rotated 5 degrees about x between the two instants
    half = math.radians(5.0) / 2.0
    value.note_pose("release_start", time_s=20.0, cup_position=(0.103, 0.0, 0.204), cup_quaternion=(math.sin(half), 0.0, 0.0, math.cos(half)),
                    tcp_position=(0.10, 0.0, 0.25), tcp_quaternion=identity, table_contact=True, table_normal_force_n=0.21,
                    left_contacts=2, right_contacts=1)
    for index in range(150):                                     # the cup sits and settles 0.30 s after the open
        time_s = 22.0 + index * 0.01
        moving = time_s < 22.3
        value.offer_world(world(time_s, 0, 0, table=True, force=0.2, linear=0.01 if moving else 0.0005, angular=0.0))
    end = {"position": [0.103, 0.0, 0.170], "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}
    document = value.build(end_observation=end)
    assert document["slip_in_hand"]["translation_mm"] == pytest.approx(5.0, abs=1e-6)
    assert document["slip_in_hand"]["rotation_deg"] == pytest.approx(5.0, abs=1e-6)
    release = document["release"]
    assert release["table_contact"] is True and release["left_contacts"] == 2 and release["right_contacts"] == 1
    assert release["displacement_mm"] == pytest.approx(34.0, abs=1e-6) and release["displacement_deg"] == pytest.approx(5.0, abs=1e-6)
    assert document["settle_time_s"] == pytest.approx(0.30, abs=0.011)


def test_an_incomplete_stream_marks_the_summary_and_never_raises():
    value = summary()
    value.note_incomplete("PHYSICS_CHUNK_GAP")
    value.note_incomplete("CONTACT_FRAME_TRUNCATED")
    value.note_incomplete("PHYSICS_CHUNK_GAP")
    document = value.build(extra_incomplete=["EVIDENCE_TRUNCATED_REJECTED"])
    assert document["complete"] is False
    assert document["incomplete_reasons"] == ["CONTACT_FRAME_TRUNCATED", "EVIDENCE_TRUNCATED_REJECTED", "PHYSICS_CHUNK_GAP"]
    assert document["completeness"]["reasons"]["PHYSICS_CHUNK_GAP"] == 2
    missing = ps.ProcessSummary(limits=None, limits_error="THRESHOLDS_UNAVAILABLE: r10b did not load").build()
    assert missing["complete"] is False and missing["thresholds"] is None and "THRESHOLDS_UNAVAILABLE: r10b did not load" in missing["incomplete_reasons"]
    empty = ps.ProcessSummary(limits=LIMITS).build()
    assert empty["complete"] is True and empty["phases"] == {} and empty["slip_in_hand"] is None and empty["release"] is None
    assert ps.failure_summary("SUMMARY_FAILED")["complete"] is False


def test_the_capacity_bound_is_recorded_not_raised():
    value = ps.ProcessSummary(limits=LIMITS, capacity=5)
    value.phase_begin("LIFT", 0.0)
    for index in range(20):
        value.offer_step(index, index * 0.002, 1.0, 1e-5)
    document = value.build()
    assert document["complete"] is False and "SUMMARY_CAPACITY_EXCEEDED" in document["incomplete_reasons"]
    assert document["phases"]["LIFT"]["steps"] == 5


def test_the_document_is_json_and_carries_schema_units_and_policy_provenance():
    value = summary()
    value.offer_step(1, 10.5, 1.0, 5e-5)
    policy = {"schema_version": 3, "policy_sha256": "a" * 64, "cup_pose_source": "broker_rgbd", "verdict_source": "sim_truth"}
    document = value.build(policy=policy, place_height={"mode": "fallback_v1", "fallback_reason": "TILT_UNSTABLE"},
                           perception_error={"xy_mm": 1.0, "z_mm": 0.5, "tilt_deg": 0.2})
    assert json.loads(json.dumps(document, allow_nan=False)) == document
    assert document["schema"] == "teacher_process_summary_v1" and document["units"]["compression"] == "um"
    assert document["policy"] == {"execution_policy_schema": 3, "execution_policy_sha256": "a" * 64, "cup_pose_source": "broker_rgbd",
                                  "verdict_source": "sim_truth"}
    assert document["place_height_mode"] == "fallback_v1" and document["place_fallback_reason"] == "TILT_UNSTABLE"
    assert document["perception_error"] == {"xy_mm": 1.0, "z_mm": 0.5, "tilt_deg": 0.2}
    assert document["thresholds"] == {"source": "r10b", "summed_force_n": 1.8916304473471774,
                                      "compression_um": pytest.approx(119.28116711427007), "comparison": "strict >"}


def test_the_aggregation_runs_on_its_own_thread():
    value = summary()
    value.offer_step(1, 10.5, 1.0, 5e-5)
    seen = []
    original = value.build

    def spy(**kwargs):
        seen.append(threading.current_thread())
        return original(**kwargs)

    value.build = spy
    wait = value.compute_in_thread()
    document = wait(5.0)
    assert document is not None and seen and seen[0] is not threading.current_thread()
    value.build = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    failing = value.compute_in_thread()
    assert failing(5.0) is None and "boom" in failing.error()


# ---- replays of known runs (design 10.2) ----------------------------------------------------------------------------------------

def test_replay_of_cp_3480_run_392e7925_peak_force_1940_at_step_41943():
    """The force-stop run: 1.940 N +- 0.005 at step 41943 +- 1 is the first step over the r10b limit in DESCEND_TO_PLACE."""
    data = json.loads((FIXTURES / "replay_392e7925.json").read_text())
    value = ps.ProcessSummary(limits=CupSafetyLimits(**data["limits"]))
    for phase in data["phases"]:
        value.phase_begin(phase["state"], phase["begin_s"])
        value.phase_finish(phase["state"], phase["finish_s"], phase["status"] or "FAILED")
    for step, time_s, force, compression in data["steps"]:
        value.offer_step(step, time_s, force, compression)
    place = value.build()["phases"]["DESCEND_TO_PLACE"]
    assert abs(place["first_force_exceedance_step"] - 41943) <= 1
    assert place["first_force_exceedance_n"] == pytest.approx(1.940, abs=0.005)
    assert place["oracle_flags"] == [ps.FLAG_OVERLOAD]


def test_replay_of_cp_3493_run_008b058f_left_compression_139_um_from_the_manifest_evidence():
    """That run has no bag: the manifest's own contact evidence is replayed through the same metric."""
    data = json.loads((FIXTURES / "replay_008b058f.json").read_text())
    contacts = {group: [SimpleNamespace(**item) for item in items] for group, items in data["monitor_violation"]["contacts"].items()}
    summed, compression = ps.sample_contact_metrics(contacts["left"], contacts["right"], contacts["other"])
    assert compression * 1e6 == pytest.approx(139.0, abs=0.5)
    assert compression > data["limits"]["maximum_compression_distance_m"]
    assert summed == pytest.approx(0.774369, abs=1e-6)
    value = ps.ProcessSummary(limits=CupSafetyLimits(**data["limits"]))
    value.phase_begin("DESCEND_TO_PLACE", 0.0)
    value.phase_finish("DESCEND_TO_PLACE", 10.0, "FAILED")
    value.offer_step(data["monitor_violation"]["sample"]["simulation_step"], 5.0, summed, compression)
    place = value.build()["phases"]["DESCEND_TO_PLACE"]
    assert place["peak_compression_um"] == pytest.approx(139.0, abs=0.5) and place["oracle_flags"] == [ps.FLAG_OVERLOAD]
    assert place["first_compression_exceedance_step"] == data["monitor_violation"]["sample"]["simulation_step"]
    assert place["first_force_exceedance_step"] is None, "the summed force 0.77 N was under its limit: only the compression flags it"


# ---- samples between phases, validation, exclusion ------------------------------------------------------------------------

def test_an_exceedance_between_two_phases_is_attributed_to_the_between_phases_bucket():
    value = ps.ProcessSummary(limits=LIMITS)
    value.phase_begin("MOVE_ABOVE_PLACE", 10.0)
    value.phase_finish("MOVE_ABOVE_PLACE", 12.0, "SUCCEEDED")
    value.phase_begin("DESCEND_TO_PLACE", 13.0)                # the place-height measurement runs in the gap 12.0 - 13.0
    value.phase_finish("DESCEND_TO_PLACE", 14.0, "SUCCEEDED")
    value.offer_step(1, 12.5, 9.0, 1e-5)
    value.offer_collision(2, 12.6, "table_collision", "upper_arm_collision", -1e-4, 0.3)
    value.offer_step(3, 9.0, 99.0, 1e-5)                       # before the first phase: not attributed
    value.offer_step(4, 15.0, 99.0, 1e-5)                      # after the last phase: not attributed
    document = value.build()
    assert document["flags"][ps.FLAG_OVERLOAD] == [ps.BETWEEN_PHASES] and document["flags"][ps.FLAG_COLLISION] == [ps.BETWEEN_PHASES]
    assert document["phases"][ps.BETWEEN_PHASES]["peak_force_n"] == 9.0
    assert ps.oracle_exclusion(document) == (ps.FLAG_OVERLOAD, ps.BETWEEN_PHASES)
    clean = summary().build()
    assert ps.BETWEEN_PHASES not in clean["phases"]


def test_a_built_summary_validates_and_a_tampered_one_does_not():
    document = summary().build()
    ps.validate_summary(document)
    assert ps.oracle_exclusion(document) is None
    for mutate in (lambda d: d.update(schema="other"), lambda d: d.update(complete=False),
                   lambda d: d["flags"][ps.FLAG_COLLISION].append("LIFT"),
                   lambda d: d["phases"]["LIFT"]["oracle_flags"].append(ps.FLAG_OVERLOAD),
                   lambda d: d.pop("flags"), lambda d: d["phases"].update(LIFT=3)):
        broken = json.loads(json.dumps(document))
        mutate(broken)
        with pytest.raises(ValueError, match="PROCESS_SUMMARY"):
            ps.validate_summary(broken)
        assert ps.oracle_exclusion(broken)[0] == "INCOMPLETE"
    with pytest.raises(ValueError):
        ps.validate_summary(None)


def test_the_oracle_exclusion_names_the_flag_and_phase_and_treats_incomplete_as_excluded():
    value = summary()
    value.offer_step(1, 11.0, 9.0, 1e-5)
    value.offer_collision(2, 13.0, "table_collision", "upper_arm_collision", -1e-4, 0.3)
    assert ps.oracle_exclusion(value.build()) == (ps.FLAG_OVERLOAD, "LIFT")
    only_collision = summary()
    only_collision.offer_collision(2, 13.0, "table_collision", "upper_arm_collision", -1e-4, 0.3)
    assert ps.oracle_exclusion(only_collision.build()) == (ps.FLAG_COLLISION, "DESCEND_TO_PLACE")
    incomplete = summary()
    incomplete.note_incomplete("PHYSICS_GAP")
    assert ps.oracle_exclusion(incomplete.build()) == ("INCOMPLETE", "PHYSICS_GAP")
    assert ps.oracle_exclusion(summary(limits=None).build())[0] == "INCOMPLETE"


# ---- half-open phase windows, silent streams, consistent copies ----------------------------------------------------------------

def test_a_sample_on_the_boundary_of_two_phases_is_counted_once_in_the_later_phase():
    value = summary()                                           # LIFT [10, 12), DESCEND_TO_PLACE [12, 14)
    value.offer_step(1, 12.0, 1.0, 1e-5)
    value.offer_step(2, 10.0, 1.0, 1e-5)                        # the first instant of LIFT belongs to LIFT
    document = value.build()
    assert document["phases"]["LIFT"]["steps"] == 1 and document["phases"]["DESCEND_TO_PLACE"]["steps"] == 1
    assert document["phases"]["LIFT"]["peak_force_step"] == 2 and document["phases"]["DESCEND_TO_PLACE"]["peak_force_step"] == 1
    assert ps.BETWEEN_PHASES not in document["phases"]          # the boundary sample is not also a gap sample


def test_a_stream_silent_for_longer_than_the_limit_inside_a_phase_is_incomplete():
    value = summary()
    value.silence_limit_s = 1.0
    value.phase_begin("MOVE_ABOVE_PLACE", 14.0)
    value.note_receipt("physics", 100.0)
    value.note_receipt("physics", 100.9)                        # within the limit
    assert value.build()["complete"] is True
    value.note_receipt("physics", 102.0)                        # 1.1 s of silence with a phase open
    document = value.build()
    assert document["complete"] is False and "PHYSICS_STREAM_SILENT" in document["incomplete_reasons"]


def test_silence_between_phases_is_not_an_incompleteness_and_the_other_stream_is_judged_alone():
    value = ps.ProcessSummary(limits=LIMITS)
    value.silence_limit_s = 1.0
    value.note_receipt("collision", 10.0)
    value.note_receipt("collision", 20.0)                       # no phase open at either end: the arm has not started
    assert value.build()["complete"] is True
    value.phase_begin("LIFT", 1.0)
    value.note_receipt("physics", 30.0)
    value.note_receipt("collision", 30.5)
    assert value.build()["complete"] is False                   # collision: a phase opened at 30.0 and the previous receipt was 20.0
    assert value.build()["incomplete_reasons"] == ["COLLISION_STREAM_SILENT"]


def test_an_expected_stream_that_never_delivered_is_incomplete_and_an_open_phase_at_the_end_with_silence_too():
    value = ps.ProcessSummary(limits=LIMITS)
    value.silence_limit_s = 1.0
    value.check_streams(50.0, ["physics", "collision"])
    assert value.build()["incomplete_reasons"] == ["COLLISION_STREAM_NEVER_RECEIVED", "PHYSICS_STREAM_NEVER_RECEIVED"]
    other = ps.ProcessSummary(limits=LIMITS)
    other.silence_limit_s = 1.0
    other.note_receipt("physics", 10.0)
    other.phase_begin("LIFT", 1.0)                              # still open when the run ends
    other.check_streams(12.0, ["physics"])
    assert other.build()["incomplete_reasons"] == ["PHYSICS_STREAM_SILENT"]
    done = ps.ProcessSummary(limits=LIMITS)
    done.silence_limit_s = 1.0
    done.note_receipt("physics", 10.0)
    done.phase_begin("LIFT", 1.0)
    done.phase_finish("LIFT", 2.0, "SUCCEEDED")
    done.check_streams(99.0, ["physics"])                       # silence after the last phase is not a gap in a phase
    assert done.build()["complete"] is True


def test_building_while_the_feeds_append_never_fails_and_copies_consistently():
    value = summary()
    stop = threading.Event()
    failures = []

    def feed():
        step = 0
        while not stop.is_set():
            step += 1
            value.offer_step(step, 10.0 + (step % 1000) * 0.002, 0.5, 1e-5)
            value.offer_collision(step, 10.0 + (step % 1000) * 0.002, "a", "b", -1e-5, 0.1)

    thread = threading.Thread(target=feed)
    thread.start()
    try:
        for _ in range(40):
            try:
                value.build()
            except Exception as error:  # noqa: BLE001
                failures.append(error)
    finally:
        stop.set()
        thread.join(5)
    assert failures == []
