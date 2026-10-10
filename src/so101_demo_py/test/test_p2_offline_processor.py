"""P2: the offline episode processor over a small synthetic MCAP written with the real message types.

The bag is `offline_synthetic_bag`; the sources are `BagSyntheticSources` (real physics adapter, real controller reference port,
real episode/lossless writer/engine/seal). The production sources (`OfflineRosSources`) are exercised on the pilot bag.
"""

import filecmp
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from so101_demo.act.offline import processor, replay
from offline_synthetic_bag import (ATTEMPT, EPOCH, SESSION, BagSyntheticSources, arm_reference, build_bag, mono_of,
                                   system_of)
from test_act_episode_recorder import POLICY_FILE, make_episode
from paths import PACKAGE_ROOT, SUPPORT_DIR, TEST_ROOT

LEASE = dict(batch_id="batch-1", coordinator_epoch=1, worker_id="w00", worker_generation=1, point_id="point-1",
             attempt_id=ATTEMPT, lease_generation=1, lease_issued_monotonic_s=1.0, lease_deadline_monotonic_s=9_999_999.0)

QC_CODE = """
import json, sys
from pathlib import Path
from test_act_episode_recorder import readback
seal, manifest, references = readback(Path(sys.argv[1]))
print(json.dumps({"status": references["status"], "reason": references.get("reason", ""),
                  "seal": seal["status"], "records": seal["record_count"]}))
"""


def synthetic_qc(episode_root, **_):
    """A fresh interpreter re-reads the sealed files: seal, audit manifest, the Teacher-reference cross-check."""
    # the child imports a test-directory module: hand it this directory explicitly (the gate runs from another cwd and path)
    here = [str(TEST_ROOT), str(SUPPORT_DIR)]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [*here, os.environ.get("PYTHONPATH", "")])))
    completed = subprocess.run([sys.executable, "-c", QC_CODE, str(Path(episode_root).parent)], capture_output=True, text=True,
                               env=env, timeout=300)
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


def run(tmp_path, bag, name="sealed", **overrides):
    from so101_demo.act.offline.policy import load_recorder_policy

    out = tmp_path / name
    policy = dict(load_recorder_policy(POLICY_FILE), poll_s=0.005)
    arguments = dict(inputs_manifest=tmp_path / "inputs-manifest.json", lease=LEASE, scope=tmp_path / "scope.json", policy=policy,
                     episode_factory=lambda options: make_episode(out),
                     sources_factory=lambda node, episode, options, policy: BagSyntheticSources(
                         node, episode, options, policy),
                     qc_runner=synthetic_qc)
    arguments.update(overrides)
    return processor.process_bag(bag, out, **arguments), out


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


# ---- the happy path ------------------------------------------------------------------------------------------------

def test_a_complete_bag_gives_a_valid_sealed_episode_and_a_passing_fresh_process_qc(tmp_path):
    bag = build_bag(tmp_path / "raw")
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "VALID" and report["rc"] == 0 and report["reasons"] == [], report
    assert report["engine"]["status"] == "VALID" and report["qc"]["status"] == "PASS"
    assert report["scan_reasons"] == [] and report["clock"]["map_source"] == "anchors"
    assert report["clock"]["max_residual_ns"] == 0
    result = json.loads((out / "recorder-result.json").read_bytes())
    assert result["status"] == "VALID" and result["pid"] == 0 and result["event_stream"]["accepted"] == 7
    assert (out / "episode" / "seal.json").is_file()
    for topic, item in report["continuity"].items():
        assert item["gap_count"] == 0 and item["covers_window"] and item["in_window"] > 0, topic


# ---- determinism ---------------------------------------------------------------------------------------------------------

def test_two_runs_over_the_same_bag_are_byte_identical(tmp_path):
    bag = build_bag(tmp_path / "raw")
    first_report, out = run(tmp_path, bag)
    assert first_report["verdict"] == "VALID"
    first = tmp_path / "first"
    out.rename(first)
    time.sleep(0.05)   # wall time differs between the runs
    second_report, out = run(tmp_path, bag)
    assert second_report["verdict"] == "VALID"
    first_tree, second_tree = tree(first), tree(out)
    assert first_tree.keys() == second_tree.keys()
    differing = [name for name in first_tree if first_tree[name] != second_tree[name]]
    assert differing == [], differing
    for key in ("engine", "continuity", "timeline", "clock"):
        assert first_report[key] == second_report[key]


# ---- INVALID: missing topic, sequence gap -----------------------------------------------------------------------------

@pytest.mark.parametrize("topic", ["/gripper_controller/controller_state", "/so101/simulation/physics_step_chunks",
                                   "/head_camera/color", "/so101/raw/planning_scene_reads"])
def test_a_missing_topic_is_invalid_and_named(tmp_path, topic):
    bag = build_bag(tmp_path / "raw", omit_topics=(topic,))
    report, _ = run(tmp_path, bag)
    assert report["verdict"] == "INVALID" and report["rc"] == 3
    assert f"OFFLINE_BAG_TOPIC_MISSING: {topic}" in report["scan_reasons"]
    assert any(f"OFFLINE_BAG_TOPIC_MISSING: {topic}" in reason for reason in report["reasons"])


@pytest.mark.parametrize("topic,index,code", [
    ("/arm_controller/controller_state", 200, "OFFLINE_SOURCE_GAP: /arm_controller/controller_state"),
    ("/so101/simulation/physics_step_chunks", 3, "OFFLINE_SOURCE_GAP: /so101/simulation/physics_step_chunks"),
    ("/so101/simulation/evidence", 40, "OFFLINE_SOURCE_GAP: /so101/simulation/evidence"),
    ("/so101/teacher/events", 3, "OFFLINE_TEACHER_EVENT_SEQUENCE_GAP")])
def test_a_sequence_gap_inside_the_window_is_invalid(tmp_path, topic, index, code):
    bag = build_bag(tmp_path / "raw", drop=((topic, index),))
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "INVALID" and report["rc"] == 3, report["reasons"]
    assert any(code in reason for reason in report["scan_reasons"]), report["scan_reasons"]
    assert report["qc"]["status"] == "NOT_RUN"
    assert (out / "recorder-result.json").is_file(), "the record of an invalid episode is retained"


def test_data_outside_the_episode_window_is_ignored(tmp_path):
    """Gaps before the first command and after the end (+0.1 s) are not the episode's: a window that is whole is VALID."""
    bag = build_bag(tmp_path / "raw", drop=(("/arm_controller/controller_state", 10), ("/arm_controller/controller_state", 11),
                                            ("/so101/simulation/evidence", 3), ("/so101/simulation/evidence", 70),
                                            ("/arm_controller/controller_state", 420)))
    report, _ = run(tmp_path, bag)
    assert report["scan_reasons"] == [], report["scan_reasons"]
    assert report["verdict"] == "VALID", report["reasons"]


def test_a_controller_gap_that_touches_no_label_instant_is_only_a_diagnostic_count(tmp_path):
    """CP-3439: labels are at 1.1, 1.2, 1.3 and 1.4 s; the arm frame at 1.220 s is missing, 20 ms from the nearest label."""
    bag = build_bag(tmp_path / "raw", drop=(("/arm_controller/controller_state", 160),))
    report, _ = run(tmp_path, bag)
    arm = report["continuity"]["/arm_controller/controller_state"]
    assert report["scan_reasons"] == [] and report["verdict"] == "VALID", report["reasons"]
    assert arm["gaps_in_window"] == 1 and arm["gaps_touching_a_label"] == 0 and arm["diagnostic_gaps"] == 1


@pytest.mark.parametrize("index", [150, 149, 151])   # frames 1.200 (the label's frame) and the ones either side
def test_a_gripper_gap_at_or_next_to_a_label_instant_is_invalid(tmp_path, index):
    bag = build_bag(tmp_path / "raw", drop=(("/gripper_controller/controller_state", index),))
    report, _ = run(tmp_path, bag)
    assert report["verdict"] == "INVALID"
    assert "OFFLINE_SOURCE_GAP: /gripper_controller/controller_state gaps=1" in report["scan_reasons"]


#: a camera frame that is really missing: the camera_info and the image of both cameras at one stamp (a camera_info lost on one
#: camera with both images present is a diagnostic only, CP-3494)
MISSING_CAMERA_FRAME = tuple((topic, 2) for topic in ("/head_camera/camera_info", "/wrist_camera/camera_info",
                                                       "/head_camera/color", "/wrist_camera/color"))


def test_a_camera_frame_missing_or_off_the_100_ms_grid_is_named_by_the_scan(tmp_path):
    bag = build_bag(tmp_path / "raw", drop=MISSING_CAMERA_FRAME)
    report, _ = run(tmp_path, bag)
    assert report["verdict"] == "INVALID"
    assert any(reason.startswith("OFFLINE_CAMERA_GRID") for reason in report["scan_reasons"])
    assert report["camera_grid"]["off_grid_count"] >= 1


def test_a_bag_that_does_not_reach_the_end_of_the_window_is_invalid(tmp_path):
    bag = build_bag(tmp_path / "raw", drop=tuple(("/neck_controller/controller_state", index) for index in range(330, 426)))
    report, _ = run(tmp_path, bag)
    assert report["verdict"] == "INVALID"
    assert "OFFLINE_WINDOW_NOT_COVERED: /neck_controller/controller_state" in report["scan_reasons"]


# ---- QC event order and the label --------------------------------------------------------------------------------------

def test_the_events_are_in_the_qc_order_on_sim_time(tmp_path):
    bag = build_bag(tmp_path / "raw")
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "VALID"
    timeline = report["timeline"]
    reset = round(timeline["reset_complete_sim_s"] * 1e9)
    assert reset <= timeline["first_command_sim_ns"] <= timeline["normal_stop_sim_ns"] <= timeline["terminal_sim_ns"]
    from so101_demo.act.episode_assembly import episode_audit_pair
    from so101_demo.act.episode_audit import verify_audit_manifest
    audit_manifest, _ = episode_audit_pair(out / "episode")
    window = verify_audit_manifest(audit_manifest)["window"]
    assert reset / 1e9 <= window["collection_start_s"] <= window["first_command_s"] <= window["collection_end_s"]
    assert window["first_command_s"] == pytest.approx(1.05)
    rows = [json.loads(line) for line in (out / "episode" / "audit" / "events.jsonl").read_text().splitlines()]
    stamps = [row["monotonic_ns"] for row in rows]
    assert stamps == sorted(stamps) and [row["sequence"] for row in rows] == list(range(1, len(rows) + 1))
    assert window["physics_end_s"] == pytest.approx(1.3) and window["first_command_s"] < window["physics_end_s"]


def test_every_label_is_the_controller_reference_at_t_plus_0_1(tmp_path):
    bag = build_bag(tmp_path / "raw")
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "VALID"
    rows = [json.loads(line) for line in (out / "episode" / "records.jsonl").read_text().splitlines()]
    assert len(rows) >= 2
    for row in rows:
        t = row["observation"]["sim_time_s"] if "observation" in row else row["sim_time_s"]
        arm, gripper = arm_reference(round(t + 0.1, 6))
        action = row["action"]
        assert action == pytest.approx([*arm, *gripper], abs=1e-6), (t, action)
    references = [json.loads(line) for line in (out / "episode" / "audit" / "references.jsonl").read_text().splitlines()]
    assert all(item["source"] == "CONTROLLER_REFERENCE" for item in references) or references


# ---- the replay layer -------------------------------------------------------------------------------------------------------

def test_the_clock_map_is_exact_between_anchors_and_linear_for_a_drifting_clock():
    exact = replay.ClockMap([{"system_ns": 1_000, "monotonic_ns": 400}])
    assert exact.monotonic_ns(2_000) == 1_400 and exact.system_ns(1_400) == 2_000
    drift = replay.ClockMap([{"system_ns": 0, "monotonic_ns": 100}, {"system_ns": 1_000_000_000, "monotonic_ns": 1_000_001_100}])
    assert drift.monotonic_ns(500_000_000) == 500_000_600 and drift.drift_ppm == pytest.approx(1.0)
    with pytest.raises(ValueError, match="OFFLINE_CLOCK_ANCHORS_MISSING"):
        replay.ClockMap([])


def test_virtual_time_replaces_the_clock_functions_and_the_defaults_bound_at_import():
    from so101_demo.act.synchronizer import RgbObservationSynchronizer

    clock = replay.VirtualClock(replay.ClockMap([{"system_ns": 5_000_000_000, "monotonic_ns": 1_000_000_000}]), 7_000_000_000)
    real = time.monotonic
    with replay.virtual_time(clock):
        assert time.monotonic() == 7.0 and time.monotonic_ns() == 7_000_000_000 and time.time_ns() == 11_000_000_000
        time.sleep(0.5)
        assert time.monotonic() == 7.5
        synchronizer = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1)
        assert synchronizer.monotonic() == 7.5, "the `monotonic=time.monotonic` default follows the virtual clock"
        clock.set(1)   # never goes back
        assert time.monotonic() == 7.5
    assert time.monotonic is real
    assert abs(RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1).monotonic() - real()) < 5.0


def test_a_message_is_delivered_at_its_receipt_instant_and_the_node_clock_follows_clock(tmp_path):
    from std_msgs.msg import String

    bag = build_bag(tmp_path / "raw")
    clock_map, _ = processor.load_clock_map(bag)
    stream = replay.BagStream(bag, clock_map)
    clock = replay.VirtualClock(clock_map, stream.peek().monotonic_ns)
    node = replay.ReplayNode(stream, clock)
    seen = []
    node.create_subscription(String, "/so101/teacher/events", lambda m: seen.append(clock.now_ns), 10)
    node.deliver_due(mono_of(1.0))
    assert seen == [] and node.sim_ns == pytest.approx(1.0e9, abs=0.01e9)
    node.deliver_due(mono_of(1.0) + 6_000_000)
    assert len(seen) == 2 and seen[0] == mono_of(1.0) + 6_000_000   # receipt = the bag stamp on the monotonic clock
    assert node.get_clock().now().nanoseconds == node.sim_ns
    clock_before = clock.now_ns
    node.deliver_due(mono_of(0.1))   # the past
    assert clock.now_ns == clock_before


def test_a_callback_that_raises_is_reported_not_propagated(tmp_path):
    from std_msgs.msg import String

    bag = build_bag(tmp_path / "raw")
    clock_map, _ = processor.load_clock_map(bag)
    stream = replay.BagStream(bag, clock_map)
    node = replay.ReplayNode(stream, replay.VirtualClock(clock_map, stream.peek().monotonic_ns))

    def boom(_):
        raise ValueError("boom")

    node.create_subscription(String, "/so101/teacher/events", boom, 10)
    node.deliver_due(mono_of(1.6))
    assert any("boom" in item for item in node.take_callback_errors()) and node.take_callback_errors() == []


def test_the_clock_map_falls_back_to_the_scene_reads_and_refuses_an_unmappable_bag(tmp_path):
    bag = build_bag(tmp_path / "raw")
    (tmp_path / "raw" / "record-stats.json").unlink()
    clock_map, facts = processor.load_clock_map(bag)
    assert facts["map_source"] == "scene_reads" and facts["max_residual_ns"] == 0
    bag = build_bag(tmp_path / "raw2", omit_topics=("/so101/raw/planning_scene_reads",))
    (tmp_path / "raw2" / "record-stats.json").unlink()
    with pytest.raises(processor.OfflineRefused, match="OFFLINE_CLOCK_ANCHORS_MISSING"):
        processor.load_clock_map(bag)


# ---- the command line --------------------------------------------------------------------------------------------------------

def test_the_command_refuses_a_missing_argument_with_rc2_and_an_existing_output_with_rc2(tmp_path, capsys):
    assert processor.main([]) == 2
    bag = build_bag(tmp_path / "raw")
    (tmp_path / "out" / "episode").mkdir(parents=True)
    lease = tmp_path / "lease.json"
    lease.write_text(json.dumps(LEASE))
    assert processor.main(["--bag", str(bag), "--inputs", str(tmp_path / "m.json"), "--out", str(tmp_path / "out"),
                           "--lease", str(lease)]) == 2


def test_the_lease_can_be_read_from_an_episode_document(tmp_path):
    path = tmp_path / "episode.json"
    path.write_text(json.dumps({"attempt_id": ATTEMPT, "lease": LEASE, "mode": "x"}))
    assert processor.read_lease(path) == LEASE
    path.write_text(json.dumps({"lease": {"batch_id": "b"}}))
    with pytest.raises(processor.OfflineRefused, match="OFFLINE_LEASE_INCOMPLETE"):
        processor.read_lease(path)


def test_setup_py_declares_the_act_offline_episode_console_entry_and_it_resolves_to_a_callable():
    text = (PACKAGE_ROOT / "setup.py").read_text()
    assert '"act_offline_episode = so101_demo.cli.act_offline_episode:main"' in text
    from so101_demo.cli import act_offline_episode
    assert callable(act_offline_episode.main)


def _stamped_bag(root, *, joint_stamp_ms, joint_receipt_ms, clock_until_ms=40):
    """/clock every 2 ms and one JointState stamped `joint_stamp_ms`, received at `joint_receipt_ms` (bag order = receipt order)."""
    from builtin_interfaces.msg import Time
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import JointState
    from so101_demo.act.offline.bag_io import BagWriter

    writer = BagWriter(root / "bag")
    base = 1_000_000_000_000
    plan = [("/clock", "rosgraph_msgs/msg/Clock", ms, Clock(clock=Time(sec=0, nanosec=ms * 1_000_000)))
            for ms in range(0, clock_until_ms + 1, 2)]
    joint = JointState()
    joint.header.stamp.nanosec = joint_stamp_ms * 1_000_000
    plan.append(("/joint_states", "sensor_msgs/msg/JointState", joint_receipt_ms, joint))
    for topic, type_name, ms, message in sorted(plan, key=lambda item: (item[2], item[0] != "/clock")):
        writer.create(topic, type_name)
        writer.write(topic, message, base + ms * 1_000_000)
    writer.close()
    return root / "bag", replay.ClockMap([{"system_ns": base, "monotonic_ns": base}])


def _play(bag, clock_map, until_ms):
    from sensor_msgs.msg import JointState

    stream = replay.BagStream(bag, clock_map)
    clock = replay.VirtualClock(clock_map, stream.peek().monotonic_ns)
    node = replay.ReplayNode(stream, clock)
    seen = []
    node.create_subscription(JointState, "/joint_states", lambda m: seen.append((clock.now_ns - 1_000_000_000_000, node.sim_ns)), 10)
    node.deliver_due(1_000_000_000_000 + until_ms * 1_000_000)
    return seen, node


def test_a_message_stamped_ahead_of_the_recorded_clock_waits_for_the_clock_to_reach_its_stamp(tmp_path):
    """Pilot bag 031b82c6: 32 joint_states carried a stamp up to 4 ms past the latest /clock the bag had received (the two topics
    are separate subscriptions); the sources' INPUT_TIMESTAMP_FUTURE rule then refused a correct stream."""
    bag, clock_map = _stamped_bag(tmp_path, joint_stamp_ms=20, joint_receipt_ms=16)
    seen, node = _play(bag, clock_map, 30)
    assert len(seen) == 1
    received_ns, sim_ns = seen[0]
    assert sim_ns == 20_000_000, "the clock had reached the stamp when the message was received"
    assert received_ns == 20_000_000, "received when /clock reached 20 ms, not at its earlier bag receipt"


def test_a_stamp_the_clock_never_reaches_is_delivered_after_the_hold_and_left_to_the_sources_rule(tmp_path):
    bag, clock_map = _stamped_bag(tmp_path, joint_stamp_ms=500, joint_receipt_ms=10)
    seen, node = _play(bag, clock_map, 30)
    assert seen == [], "still held inside the 50 ms hold"
    seen, node = _play(bag, clock_map, 80)
    assert len(seen) == 1 and seen[0][0] == 10_000_000 + replay.HOLD_NS and seen[0][1] == 40_000_000
    assert node.exhausted


def test_a_message_the_clock_has_already_reached_is_delivered_at_its_receipt(tmp_path):
    bag, clock_map = _stamped_bag(tmp_path, joint_stamp_ms=10, joint_receipt_ms=16)
    seen, _ = _play(bag, clock_map, 30)
    assert seen == [(16_000_000, 16_000_000)]


def test_the_diagnostic_camera_repair_snaps_and_fills_and_counts_what_it_changed():
    from sensor_msgs.msg import Image

    def frame(stamp_ms):
        image = Image()
        image.header.stamp.sec, image.header.stamp.nanosec = divmod(stamp_ms * 1_000_000, 1_000_000_000)
        return image

    repair = replay.CameraGridRepair()
    stamps = []
    # the camera's own grid, a +2 ms frame whose phase then STAYS moved (as in the bag), then a 300 ms interval
    for ms in (4704, 4804, 4906, 5006, 5106, 5406):
        for image in repair.apply("/head_camera/color", frame(ms)):
            stamps.append(image.header.stamp.sec * 1000 + image.header.stamp.nanosec // 1_000_000)
    assert stamps == [4704, 4804, 4904, 5004, 5104, 5204, 5304, 5404]
    assert (repair.snapped, repair.inserted) == (1, 2)


def test_a_diagnostic_run_is_never_a_valid_result_and_never_exit_code_0_or_3(tmp_path):
    bag = build_bag(tmp_path / "raw", drop=MISSING_CAMERA_FRAME)
    report, _ = run(tmp_path, bag, camera_repair=True)
    assert report["verdict"].startswith("DIAGNOSTIC_") and report["rc"] == 5
    assert set(report["diagnostic"]["camera_grid_repair"]) == {"snapped", "inserted"}
    assert any(reason.startswith("OFFLINE_CAMERA_GRID") for reason in report["scan_reasons"]), "the scan still names the defect"


# ---- the episode window starts after the worker's last pre-Teacher pause (CP-3440 A) ------------------------------------------

def test_the_window_starts_at_the_first_unpaused_world_record_after_the_last_pause_before_the_reset(tmp_path):
    # world records every 12 ms from 0.900 s: index 3 is 0.936 s and 8 is 0.996 s (the verified reset is 1.0 s)
    bag = build_bag(tmp_path / "raw", paused_worlds=(3, 8))
    from so101_demo.act.offline.scan import scan_bag

    scan = scan_bag(bag)
    window = scan["window_start"]
    assert window["last_paused_sim_time_ns"] == 996_000_000 and window["sim_time_ns"] == 1_008_000_000
    assert window["paused_records_before"] == 2 and scan["paused_world_records_in_window"] == 0
    assert not any(reason.startswith("OFFLINE_PAUSED") for reason in scan["reasons"])


def test_without_a_pause_the_window_is_the_whole_bag(tmp_path):
    from so101_demo.act.offline.scan import scan_bag

    scan = scan_bag(build_bag(tmp_path / "raw"))
    assert scan["window_start"] is None and scan["paused_world_records_in_window"] == 0


def test_a_paused_world_record_inside_the_window_stays_invalid(tmp_path):
    bag = build_bag(tmp_path / "raw", paused_worlds=(40,))     # 1.380 s: after the reset, inside the episode
    report, _ = run(tmp_path, bag)
    assert report["verdict"] == "INVALID" and report["window_start"] is None
    assert any(reason.startswith("OFFLINE_PAUSED_WORLD_IN_WINDOW") for reason in report["reasons"]), report["reasons"]


def test_the_replay_withholds_only_the_world_evidence_recorded_before_the_window(tmp_path):
    from sensor_msgs.msg import JointState
    from so101_mujoco_support.msg import SimulationEvidence
    from std_msgs.msg import String

    bag = build_bag(tmp_path / "raw")
    clock_map, _ = processor.load_clock_map(bag)
    start_stamp = system_of(mono_of(1.0)) + 50_000_000          # bag stamp: 1.050 s
    stream = replay.BagStream(bag, clock_map)
    node = replay.ReplayNode(stream, replay.VirtualClock(clock_map, stream.peek().monotonic_ns), start_at_stamp_ns=start_stamp)
    worlds, joints, events = [], [], []
    node.create_subscription(SimulationEvidence, "/so101/simulation/evidence", lambda m: worlds.append(m.header.stamp.sec + m.header.stamp.nanosec / 1e9), 10)
    node.create_subscription(JointState, "/joint_states", lambda m: joints.append(m.header.stamp.sec + m.header.stamp.nanosec / 1e9), 10)
    node.create_subscription(String, "/so101/teacher/events", lambda m: events.append(m.data), 10)
    node.deliver_due(mono_of(1.7))
    assert worlds and min(worlds) >= 1.044, "world evidence recorded before the window start is withheld"
    assert min(joints) == 0.9, "every other source is delivered from the beginning of the bag"
    assert len(events) == 7, "every Teacher event is delivered whatever the window"


def test_the_diagnostic_teacher_clock_repair_only_moves_a_lagging_reading_and_counts_it():
    import json

    repair = replay.TeacherClockRepair(threshold_ns=30_000_000)
    for mono, sim in ((1_000, 100_000_000), (2_000, 200_000_000), (3_000, 300_000_000)):
        repair.observe(mono, sim)
    lagging = {"type": "scene_operation", "seq": 1, "payload": {"operation": "apply", "request_ros_clock": {
        "begin_monotonic_ns": 3_000, "sim_time_ns": 100_000_000}, "response_ros_clock": {
        "begin_monotonic_ns": 3_000, "sim_time_ns": 290_000_000}}}
    repaired = json.loads(repair.apply(json.dumps(lagging)))
    assert repaired["payload"]["request_ros_clock"]["sim_time_ns"] == 300_000_000
    assert repaired["payload"]["response_ros_clock"]["sim_time_ns"] == 290_000_000, "10 ms is not a lag"
    assert [item["clock"] for item in repair.repaired] == ["request_ros_clock"]
    stop = {"type": "normal_stop", "seq": 2, "payload": {"proof": {"source_clock": {"begin_monotonic_ns": 3_000,
                                                                                    "sim_time_ns": 298_000_000}}}}
    assert json.loads(repair.apply(json.dumps(stop)))["payload"]["proof"]["source_clock"]["sim_time_ns"] == 300_000_000
    untouched = json.dumps({"type": "phase_begin", "seq": 3, "payload": {}})
    assert repair.apply(untouched) == untouched
