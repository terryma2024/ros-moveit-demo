"""B2 (plan R3 + R9.10 + re-review E): the label stream is the controller's own `controller_state`, gaps are counted.

* the subscription is RELIABLE, KEEP_LAST, depth 1000;
* the buffer holds at least 2 s by stamp and its age is measured from the stamp, not from the receipt;
* a gap is any consecutive per-controller stamp step other than one controller period (2 ms at update_rate 500);
* the Recorder counts and seals the gaps, QC requires zero arm/gripper gaps in the label-relevant window
  (first grid instant through the last grid target, last instant + 0.1 s); neck gaps are diagnostic.
"""
from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.controller_reference_observer import ControllerReferenceObserver
from so101_demo.act.offline import sources as module
from test_act_episode_recorder_sources import RecordingNode

PERIOD_NS = 2_000_000
ARM = ("1", "2", "3", "4", "5")


def frame(stamp_ns, names=ARM):
    return SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=stamp_ns // 10**9, nanosec=stamp_ns % 10**9)),
        joint_names=list(names), reference=SimpleNamespace(positions=[0.0] * len(names), velocities=[0.0] * len(names)))


def feed(observer, kind, stamps, names=ARM):
    for stamp in stamps:
        observer.accept(kind, frame(stamp, names), received_monotonic_s=stamp / 1e9 + 0.001)


# ---- subscription -----------------------------------------------------------------------------------------------

def test_the_three_controller_state_subscriptions_are_reliable_keep_last_1000():
    from rclpy.qos import QoSHistoryPolicy, QoSReliabilityPolicy

    seen = []

    class Node(RecordingNode):
        def create_subscription(self, message_type, topic, callback, qos, *args, **kwargs):
            seen.append((topic, qos))
            return super().create_subscription(message_type, topic, callback, qos)

    port = module.ControllerReferencePort(Node(), session_id="s", reset_epoch=1)
    assert [topic for topic, _ in seen] == [f"/{kind}_controller/controller_state" for kind in ("arm", "gripper", "neck")]
    for _topic, qos in seen:
        assert qos.reliability == QoSReliabilityPolicy.RELIABLE
        assert qos.history == QoSHistoryPolicy.KEEP_LAST and qos.depth == 1000
    port.close()


# ---- buffer, age from the stamp ---------------------------------------------------------------------------------

def test_the_buffer_holds_at_least_two_seconds_of_500_hz_frames_by_stamp():
    node = RecordingNode()
    port = module.ControllerReferencePort(node, session_id="s", reset_epoch=1)
    start = node.clock_ns + 1_000_000
    stamps = [start + index * PERIOD_NS for index in range(1250)]  # 2.5 s
    node.clock_ns = stamps[-1]
    feed(port.observer, "arm", stamps)
    _identity, frames = port.recent("arm")
    assert len(frames) >= 1000, len(frames)
    assert frames[0]["sim_stamp_ns"] >= stamps[-1] - 2_000_000_000


def test_age_is_measured_from_the_stamp_not_from_the_receipt():
    node = RecordingNode()
    port = module.ControllerReferencePort(node, session_id="s", reset_epoch=1)
    stamp = node.clock_ns + 1_000_000
    for kind, names in (("arm", ARM), ("gripper", ("6",))):
        port.observer.accept(kind, frame(stamp, names), received_monotonic_s=1.0)
    node.clock_ns = stamp + 1_500_000_000  # 1.5 s of simulation time later, still inside the 2 s window
    record = port.read(stamp / 1e9)
    assert record["accepted"] is True
    node.clock_ns = stamp + 2_500_000_000  # older than 2 s by stamp
    with pytest.raises(RuntimeError, match="REFERENCE_HISTORY_UNAVAILABLE"):
        port.read(stamp / 1e9)


# ---- gap counting -----------------------------------------------------------------------------------------------

def test_a_stamp_step_other_than_one_period_is_a_counted_gap_per_controller():
    observer = ControllerReferenceObserver(max_frames=2048)
    observer.reset("s", 1, source_floor_ns=1_000_000_000)
    base = 1_100_000_000
    feed(observer, "arm", [base, base + 2 * PERIOD_NS // 2, base + 2 * PERIOD_NS, base + 4 * PERIOD_NS])  # 2,2,4 ms
    feed(observer, "gripper", [base + index * PERIOD_NS for index in range(5)], names=("6",))
    feed(observer, "neck", [base, base + 3_000_000], names=("neck_yaw_joint",))
    report = observer.gap_report()
    assert report["period_ns"] == PERIOD_NS
    assert report["kinds"]["arm"]["gaps"] == 1 and report["kinds"]["arm"]["steps"] == [[base + 2 * PERIOD_NS, base + 4 * PERIOD_NS]]
    assert report["kinds"]["gripper"]["gaps"] == 0 and report["kinds"]["gripper"]["frames"] == 5
    assert report["kinds"]["neck"]["gaps"] == 1
    assert (report["session_id"], report["reset_epoch"]) == ("s", 1)


# ---- QC rule ----------------------------------------------------------------------------------------------------

def report(*, arm=(), gripper=(), neck=(), overflow=0):
    def block(steps):
        return {"frames": 100, "gaps": len(steps) + overflow, "steps": [list(step) for step in steps]}
    return {"schema_version": 2, "period_ns": PERIOD_NS, "session_id": "s", "reset_epoch": 1,
            "kinds": {"arm": block(arm), "gripper": block(gripper), "neck": block(neck)}}


IDENTITY = {"session_id": "s", "reset_epoch": 1}
WINDOW = {"collection_start_s": 1.0, "label_cutoff_s": 3.0}  # label window 1.0 s through 3.1 s


def continuity(value, window=WINDOW, identity=IDENTITY):
    from so101_demo.act.episode_qc import verify_reference_continuity
    return verify_reference_continuity(value, identity=identity, window=window)


def test_zero_gaps_in_the_label_window_passes():
    assert continuity(report())["gaps_in_window"] == 0


@pytest.mark.parametrize("kind", ["arm", "gripper"])
def test_an_arm_or_gripper_gap_inside_the_window_is_invalid(kind):
    with pytest.raises(ValueError, match="REFERENCE_GAP_IN_LABEL_WINDOW"):
        continuity(report(**{kind: [(2_000_000_000, 2_004_000_000)]}))


def test_gaps_outside_the_window_and_neck_gaps_are_diagnostic_only():
    value = report(arm=[(500_000_000, 504_000_000), (3_200_000_000, 3_204_000_000)],
                   neck=[(2_000_000_000, 2_004_000_000)])
    assert continuity(value)["gaps_in_window"] == 0 and continuity(value)["neck_gaps"] == 1


def test_a_gap_at_a_label_instant_is_invalid_and_so_is_a_gap_in_the_frames_around_it():
    """CP-3439: the reference must be continuous at every row's t + 0.1 s: the frame there and one period either side."""
    for gap in ((1_098_000_000, 1_102_000_000),    # the frame at the label instant 1.100 is missing
                (1_100_000_000, 1_104_000_000),    # the frame after it (1.102) is missing
                (1_096_000_000, 1_100_000_000),    # the frame before it (1.098) is missing
                (3_098_000_000, 3_104_000_000)):   # the last label instant 3.100
        with pytest.raises(ValueError, match="REFERENCE_GAP_IN_LABEL_WINDOW"):
            continuity(report(arm=[gap]))
        with pytest.raises(ValueError, match="REFERENCE_GAP_IN_LABEL_WINDOW"):
            continuity(report(gripper=[gap]))


def test_a_gap_that_touches_no_label_instant_is_only_counted():
    # label instants are 1.1, 1.2 ... 3.1 s; each needs the frames at -2 ms, 0 and +2 ms
    value = report(arm=[(1_100_000_000 + 4_000_000, 1_100_000_000 + 8_000_000),   # frame 1.106 missing: no label near
                        (998_000_000, 1_004_000_000)],                             # at the window edge but before the first label
                   gripper=[(2_150_000_000, 2_154_000_000)], neck=[(1_100_000_000, 1_104_000_000)])
    result = continuity(value)
    assert result["gaps_in_window"] == 0 and result["diagnostic_gaps"] == 3 and result["neck_gaps"] == 1
    assert result["label_instants"] == 21


def test_the_four_gaps_of_the_pilot_bag_touch_no_label_instant():
    """Pilot bag 031b82c6 (arm 31.512 gripper, 67.388, 86.160, 92.020 arm; labels 4.904 + 0.1 k): all four gaps are off-label."""
    window = {"collection_start_s": 4.803999999, "label_cutoff_s": 104.803999999}
    value = report(arm=[(67_388_000_000, 67_392_000_000), (86_160_000_000, 86_164_000_000), (92_020_000_000, 92_024_000_000)],
                   gripper=[(31_512_000_000, 31_516_000_000), (86_160_000_000, 86_164_000_000)])
    result = continuity(value, window=window)
    assert result["gaps_in_window"] == 0 and result["diagnostic_gaps"] == 5


def test_a_label_instant_one_nanosecond_off_the_grid_needs_the_grid_frames_around_it():
    window = {"collection_start_s": 4.803999999, "label_cutoff_s": 5.003999999}   # labels 4.903999999, 5.003999999, 5.103999999
    with pytest.raises(ValueError, match="REFERENCE_GAP_IN_LABEL_WINDOW"):
        continuity(report(arm=[(4_902_000_000, 4_906_000_000)]), window=window)   # frame 4.904 (the label's frame) missing
    with pytest.raises(ValueError, match="REFERENCE_GAP_IN_LABEL_WINDOW"):
        continuity(report(arm=[(4_904_000_000, 4_908_000_000)]), window=window)   # frame 4.906 missing


def test_a_gap_list_that_overflowed_cannot_prove_the_window_is_clean():
    with pytest.raises(ValueError, match="REFERENCE_GAP_LIST_INCOMPLETE"):
        continuity(report(overflow=3))


def test_a_cross_reset_report_is_invalid():
    with pytest.raises(ValueError, match="REFERENCE_EPOCH_MISMATCH"):
        continuity(report(), identity={"session_id": "s", "reset_epoch": 2})


def test_a_missing_report_is_invalid():
    with pytest.raises(ValueError, match="REFERENCE_CONTINUITY_MISSING"):
        continuity(None)


def test_labels_before_the_verified_reset_boundary_are_a_cross_reset_frame():
    from so101_demo.act.episode_qc import verify_reference_epoch
    rows = [{"frames": {"arm": {"sim_stamp_ns": 1_000_000_000}, "gripper": {"sim_stamp_ns": 1_000_000_000}}},
            {"frames": {"arm": {"sim_stamp_ns": 1_100_000_000}, "gripper": {"sim_stamp_ns": 1_100_000_000}}}]
    assert verify_reference_epoch(rows, reset_sim_time_ns=1_000_000_000) == 2
    with pytest.raises(ValueError, match="REFERENCE_CROSS_RESET_FRAME"):
        verify_reference_epoch(rows, reset_sim_time_ns=1_050_000_000)
