"""Recorder round 3 (CP-3405): the controller_state topics (3 x 500 Hz = 1500 messages/s) are received, validated, stamped and
gap-counted in their own process; the Recorder keeps the frames it needs for the exact t+0.1 references.

L2 rerun evidence: the Recorder process was CPU/GIL-saturated (events appended up to 1.2 s behind their receipt, p99 1.0 s; world
delivery latency p99 108 ms; probe lateness up to 230 ms). Benchmarked on this machine the controller topics alone cost the receiver
thread ~215 us per frame = 0.32 s of the GIL per second, before any other source. Nothing about the rule changes: every frame is
validated by the same `ControllerReferenceObserver`, the gap report is the observer's own, the reference lookup is the exact
stamp +- 1 us within the 2 s window of the sim clock.
"""
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.controller_reference_observer import ControllerReferenceObserver
from test_b2_controller_reference import ARM, PERIOD_NS, frame

BASE = 1_000_000_000_000


def observer_with(stamps_by_kind):
    observer = ControllerReferenceObserver(max_frames=2048)
    observer.reset("s", 1, source_floor_ns=1_000)
    names = {"arm": ARM, "gripper": ("6",), "neck": ("neck_yaw_joint",)}
    for kind, stamps in stamps_by_kind.items():
        for stamp in stamps:
            observer.accept(kind, frame(stamp, names[kind]), received_monotonic_s=stamp / 1e9 + 0.001)
    return observer


def record_of(observer, kind, stamp):
    """What the spooler writes for one accepted frame: the observer's own retained record."""
    return next(item for item in observer._frames[kind] if item["sim_stamp_ns"] == stamp)


def test_frames_round_trip_with_their_kind_stamp_and_receipt(tmp_path):
    from so101_demo.act.controller_spool import SpoolFrameReader, SpoolFrameWriter
    writer, reader = SpoolFrameWriter(tmp_path, max_bytes=1 << 20), SpoolFrameReader(tmp_path)
    writer.write("arm", 111, 222, b'{"a":1}')
    writer.write("gripper", 333, 444, b"x" * 50_000)
    assert reader.read() == [("arm", 111, 222, b'{"a":1}'), ("gripper", 333, 444, b"x" * 50_000)]
    assert reader.read() == []
    with open(tmp_path / "controller.spool", "ab", buffering=0) as stream:       # a frame still being written
        stream.write(b"CST1" + bytes([2]) + (5).to_bytes(8, "little") + (6).to_bytes(8, "little") + (4).to_bytes(4, "little") + b"ab")
        assert reader.read() == []
        stream.write(b"cd")
    assert reader.read() == [("neck", 5, 6, b"abcd")]


def test_overflow_is_marked_and_never_blocks(tmp_path):
    from so101_demo.act.controller_spool import SpoolFrameReader, SpoolFrameWriter
    writer, reader = SpoolFrameWriter(tmp_path, max_bytes=100), SpoolFrameReader(tmp_path)
    assert writer.write("arm", 1, 1, b"y" * 40) is True
    assert writer.write("arm", 2, 2, b"y" * 80) is False
    assert reader.overflowed() is True and len(reader.read()) == 1


def loaded_view(tmp_path, observer, kinds=("arm", "gripper", "neck")):
    from so101_demo.act.controller_spool import ControllerSpoolView, SpoolFrameWriter
    writer = SpoolFrameWriter(tmp_path, max_bytes=1 << 26)
    for kind in kinds:
        for item in sorted(observer._frames[kind], key=lambda value: value["sim_stamp_ns"]):
            body = {key: (list(value) if isinstance(value, tuple) else value) for key, value in item.items()
                    if key not in ("sim_stamp_ns", "received_monotonic_ns")}
            writer.write(kind, item["sim_stamp_ns"], item["received_monotonic_ns"], json.dumps(body).encode())
    view = ControllerSpoolView(tmp_path, identity=("s", 1), capacity=2048)
    view.pull()
    return view


def test_the_view_answers_exactly_like_the_observers_window_read(tmp_path):
    stamps = [BASE + index * PERIOD_NS for index in range(800)]
    observer = observer_with({"arm": stamps, "gripper": stamps})
    view = loaded_view(tmp_path, observer, kinds=("arm", "gripper"))
    now = stamps[-1] + 1_000_000
    for kind in ("arm", "gripper"):
        for index in (3, 400, 799):
            expected = observer.matching_by_stamp(kind, now_sim_ns=now, window_ns=2_000_000_000,
                                                  target_ns=stamps[index], tolerance_ns=1000)
            got = view.matching_by_stamp(kind, now_sim_ns=now, window_ns=2_000_000_000, target_ns=stamps[index],
                                         tolerance_ns=1000)
            assert got[0] == expected[0]
            assert [dict(frame_, joint_names=list(frame_["joint_names"]), positions=list(frame_["positions"]),
                         velocities=list(frame_["velocities"])) for frame_ in expected[1]] == list(got[1])


def test_the_view_refuses_a_stale_window_and_answers_a_missing_instant_with_nothing(tmp_path):
    stamps = [BASE + index * PERIOD_NS for index in range(300) if index != 150]
    observer = observer_with({"arm": stamps})
    view = loaded_view(tmp_path, observer, kinds=("arm",))
    assert view.matching_by_stamp("arm", now_sim_ns=stamps[-1], window_ns=2_000_000_000,
                                  target_ns=BASE + 150 * PERIOD_NS, tolerance_ns=1000)[1] == ()
    with pytest.raises(ValueError, match="CONTROLLER_REFERENCE_HISTORY_INVALID"):
        view.matching_by_stamp("arm", now_sim_ns=stamps[-1] + 5_000_000_000, window_ns=2_000_000_000,
                               target_ns=stamps[10], tolerance_ns=1000)


def test_received_through_is_the_older_of_arm_and_gripper(tmp_path):
    observer = observer_with({"arm": [BASE + i * PERIOD_NS for i in range(100)],
                              "gripper": [BASE + i * PERIOD_NS for i in range(60)]})
    view = loaded_view(tmp_path, observer, kinds=("arm", "gripper"))
    assert view.latest_stamp_ns("arm") == BASE + 99 * PERIOD_NS and view.latest_stamp_ns("neck") is None


# ---- the real process -------------------------------------------------------------------------------------------

rclpy = pytest.importorskip("rclpy")


def busy(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        sum(range(200))


class Publishers:
    def __init__(self, context):
        from control_msgs.msg import JointTrajectoryControllerState
        self.cls = JointTrajectoryControllerState
        self.node = rclpy.create_node("rec3_pub", context=context)
        self.names = {"arm": ARM, "gripper": ("6",), "neck": ("neck_yaw_joint",)}
        self.pubs = {kind: self.node.create_publisher(self.cls, f"/{kind}_controller/controller_state", 1000)
                     for kind in self.names}

    def subscriptions(self):
        return min(pub.get_subscription_count() for pub in self.pubs.values())

    def publish(self, kind, stamp_ns, names=None):
        message = self.cls()
        message.joint_names = list(names or self.names[kind])
        message.header.stamp.sec, message.header.stamp.nanosec = divmod(stamp_ns, 10**9)
        count = len(message.joint_names)
        for field in ("reference", "feedback", "error", "output"):
            getattr(message, field).positions = [0.1] * count
            getattr(message, field).velocities = [0.0] * count
        self.pubs[kind].publish(message)


@pytest.fixture
def ros(isolated_ros_domain):
    context = rclpy.context.Context()
    rclpy.init(context=context)
    publishers = Publishers(context)
    yield publishers
    publishers.node.destroy_node()
    rclpy.shutdown(context=context)


def start_process(tmp_path, floor_ns):
    from so101_demo.act.controller_spool import ControllerSpoolProcess
    process = ControllerSpoolProcess(tmp_path, session_id="s", reset_epoch=1, floor_ns=floor_ns, max_bytes=1 << 26)
    process.start()
    assert process.wait_ready(20.0)
    return process


def test_a_real_spooler_stamps_at_delivery_validates_and_counts_gaps_while_the_main_thread_is_busy(tmp_path, ros):
    process = start_process(tmp_path, floor_ns=1)
    try:
        deadline = time.monotonic() + 10
        while ros.subscriptions() < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        base, published, stop = time.time_ns() // 2_000_000 * 2_000_000 + 1_000_000_000, {}, threading.Event()
        steps = [0]
        gap_at = [None]

        def publisher():
            t0, step = time.monotonic(), 0
            while not stop.is_set():
                due = int((time.monotonic() - t0) / 0.002)
                while step < due:
                    for kind in ("arm", "gripper", "neck"):
                        if not (kind == "arm" and gap_at[0] is not None and step == gap_at[0]):    # one missing arm publication
                            ros.publish(kind, base + step * PERIOD_NS)
                            # stamped after the call returned: this (test) thread is itself starved while the loop is busy
                            published[(kind, base + step * PERIOD_NS)] = time.monotonic_ns()
                    step += 1
                    steps[0] = step
                time.sleep(0.0005)

        thread = threading.Thread(target=publisher)
        thread.start()
        # Warm-up (a test artefact): the first reliable samples after a match wait for the discovery handshake (270-330 ms
        # seen in the gate). Measure only after delivery is steady: the newest frame is fresh.
        probe_view = process.view(identity=("s", 1))
        warm_end, end = None, time.monotonic() + 15.0
        while time.monotonic() < end and warm_end is None:
            time.sleep(0.05)
            probe_view.pull()
            newest = probe_view.latest_stamp_ns("gripper")
            if newest is not None and ("gripper", newest) in published and steps[0] > 300:
                frame_ = probe_view.matching_by_stamp("gripper", now_sim_ns=newest, window_ns=10_000_000_000,
                                                      target_ns=newest, tolerance_ns=1000)[1]
                if frame_ and (frame_[0]["received_monotonic_ns"] - published[("gripper", newest)]) / 1e6 < 30.0:
                    warm_end = steps[0]
        assert warm_end is not None, "delivery never became steady"
        gap_at[0] = steps[0] + 100                                              # a gap AFTER delivery is established
        busy(0.16)                                                              # the loop is busy; the spooler must not care
        time.sleep(1.0)
        stop.set()
        thread.join()
        step = steps[0]
        report = process.report()
        assert report["status"]["gap_report"]["kinds"]["arm"]["gaps"] == 1
        assert report["status"]["gap_report"]["kinds"]["gripper"]["gaps"] == 0 and report["status"]["hazard"] is None
        assert report["status"]["off_grid_frames"] == {"arm": 0, "gripper": 0, "neck": 0}     # the 2 ms grid is observed
        reader = process.view(identity=("s", 1))
        reader.pull()
        got = reader.matching_by_stamp("gripper", now_sim_ns=base + (step - 1) * PERIOD_NS + 1000, window_ns=10_000_000_000,
                                       target_ns=base + 200 * PERIOD_NS, tolerance_ns=1000)
        assert len(got[1]) == 1 and got[1][0]["observer_sequence"] == 201
        assert got[1][0]["original_message"]["joint_names"] == ["6"]
        delays = [(frame_["received_monotonic_ns"] - published[("gripper", frame_["sim_stamp_ns"])]) / 1e6
                  for frame_ in (reader.matching_by_stamp("gripper", now_sim_ns=base + (step - 1) * PERIOD_NS,
                                                          window_ns=10_000_000_000, target_ns=base + index * PERIOD_NS,
                                                          tolerance_ns=1000)[1][0] for index in range(warm_end + 20, step - 150, 7))]
        ordered = sorted(delays)
        # the 160 ms busy loop is invisible; a lone sample can still wait for a DDS reliable retransmission (transport)
        assert ordered[len(ordered) // 2] < 5.0 and ordered[int(len(ordered) * 0.9)] < 20.0, ordered[-5:]
    finally:
        process.close()
    assert process.child.poll() is not None


def test_an_invalid_frame_is_a_hazard_reported_by_the_process(tmp_path, ros):
    process = start_process(tmp_path, floor_ns=1)
    try:
        deadline = time.monotonic() + 10
        while ros.subscriptions() < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        base, step = time.time_ns() + 1_000_000_000, 0
        end = time.monotonic() + 15.0
        while process.report()["status"].get("frames", 0) < 5 and time.monotonic() < end:     # delivery is established first
            ros.publish("arm", base + step * PERIOD_NS)
            step += 1
            time.sleep(0.01)
        assert process.report()["status"]["frames"] >= 5 and process.report()["status"]["hazard"] is None
        ros.publish("arm", base + step * PERIOD_NS, names=("9", "9", "9", "9", "9"))
        end = time.monotonic() + 5
        while process.report()["status"]["hazard"] is None and time.monotonic() < end:
            time.sleep(0.05)
        assert process.report()["status"]["hazard"] == "CONTROLLER_REFERENCE_FRAME_INVALID"
    finally:
        process.close()


def test_the_spooled_port_reads_the_exact_reference_reports_continuity_and_surfaces_failures(tmp_path, ros):
    from test_act_episode_recorder_sources import RecordingNode
    from so101_demo.ros.episode_recorder_sources import SpooledControllerReferencePort
    node = RecordingNode()
    node.clock_ns = 1_000
    port = SpooledControllerReferencePort(node, session_id="s", reset_epoch=1, directory=tmp_path / "spool")
    try:
        deadline = time.monotonic() + 10
        while ros.subscriptions() < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        base = time.time_ns() + 1_000_000_000
        warm = 0
        end = time.monotonic() + 15.0
        while port.received_through_s() is None and time.monotonic() < end:                    # delivery established first
            for kind in ("arm", "gripper", "neck"):
                ros.publish(kind, base + warm * PERIOD_NS)
            warm += 1
            time.sleep(0.01)
        assert port.received_through_s() is not None
        first = warm                                                  # the measured stream continues the warm-up's, gap-free
        for step in range(first, first + 400):
            for kind in ("arm", "gripper", "neck"):
                if not (kind == "gripper" and step == first + 100):
                    ros.publish(kind, base + step * PERIOD_NS)
            time.sleep(0.0005)
        end = time.monotonic() + 5
        while (port.received_through_s() or 0) < (base + (first + 390) * PERIOD_NS) / 1e9 and time.monotonic() < end:
            time.sleep(0.01)
        node.clock_ns = base + (first + 399) * PERIOD_NS
        record = port.read((base + (first + 50) * PERIOD_NS) / 1e9)
        assert record["accepted"] is True and record["frames"]["arm"]["sim_stamp_ns"] == base + (first + 50) * PERIOD_NS
        assert record["frames"]["gripper"]["observer_sequence"] >= 51
        with pytest.raises(RuntimeError, match="COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE"):
            port.read((base + (first + 100) * PERIOD_NS) / 1e9)                      # the one missing gripper publication
        report = port.continuity_report()
        assert report["kinds"]["gripper"]["gaps"] == 1 and report["kinds"]["arm"]["gaps"] == 0
        assert port.failure() is None
        ros.publish("arm", base + (first + 401) * PERIOD_NS, names=("9", "9", "9", "9", "9"))
        end = time.monotonic() + 5
        while port.failure() is None and time.monotonic() < end:
            time.sleep(0.05)
        assert port.failure() == "CONTROLLER_REFERENCE_FRAME_INVALID"
    finally:
        port.close()
    assert not (tmp_path / "spool").exists() and port.facts()["frames"] > 0


def test_a_stamp_off_the_two_millisecond_grid_is_counted_by_the_process(tmp_path, ros):
    process = start_process(tmp_path, floor_ns=1)
    try:
        deadline = time.monotonic() + 10
        while ros.subscriptions() < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        base, step = time.time_ns() // 2_000_000 * 2_000_000 + 1_000_000_000, 0
        end = time.monotonic() + 15.0
        while process.report()["status"].get("frames", 0) < 5 and time.monotonic() < end:
            ros.publish("gripper", base + step * PERIOD_NS)
            step += 1
            time.sleep(0.01)
        ros.publish("gripper", base + step * PERIOD_NS + 1_000_000)             # 1 ms off the grid
        end = time.monotonic() + 5
        while process.report()["status"]["off_grid_frames"]["gripper"] == 0 and time.monotonic() < end:
            time.sleep(0.05)
        assert process.report()["status"]["off_grid_frames"] == {"arm": 0, "gripper": 1, "neck": 0}
    finally:
        process.close()
