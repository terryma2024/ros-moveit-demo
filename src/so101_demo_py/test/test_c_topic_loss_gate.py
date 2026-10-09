"""Phase C: the per-topic transport-loss gate.

A message lost inside the episode window on a topic the episode uses makes the data INVALID (`OFFLINE_TOPIC_LOSS:<topic>`). A loss
outside the window, or on a topic the episode does not use, is recorded and never fatal. The recorder's aggregate "messages lost on
the transport layer" must be accounted for by what the topics show (otherwise it fails closed), and the gate result is part of the QC
verdict (rule version `act_data_qc_v4`, check `topic_loss_gate`).

The synthetic bag has its Teacher timeline at 1.05 s (first command) to 1.5 s (terminal), the verified reset at 1.0 s, and every topic
from 0.9 s to 1.75 s: a message lost before 1.0 s is outside the window.
"""

import copy
import json
from pathlib import Path

import pytest
from offline_synthetic_bag import build_bag
from so101_demo.act import episode_qc, qc_memo, topic_loss
from so101_demo.act.offline.scan import scan_bag

JOINT = "/joint_states"
SCENE = "/so101/simulation/scene_state"
CLOCK = "/clock"
HEAD = "/head_camera/color"
IN_WINDOW, BEFORE_WINDOW = 15, 3          # joint_states: 1.05 s and 0.93 s


def scan(tmp_path, name="raw", *, transport_lost=0, drop=(), omit=()):
    bag = build_bag(tmp_path / name, drop=drop, omit_topics=omit, transport_lost=transport_lost)
    return scan_bag(bag, transport_lost=transport_lost, scene_reads_expected=1)


def loss_reasons(report):
    return [r for r in report["reasons"] if r.startswith(("OFFLINE_TOPIC_LOSS", "OFFLINE_TRANSPORT_LOSS"))]


def test_a_complete_bag_has_no_loss_and_the_gate_document_passes(tmp_path):
    report = scan(tmp_path)
    assert report["reasons"] == [], report["reasons"]
    facts = report["topic_loss"]
    assert facts["transport_lost"] == {"reported": 0, "attributed": 0, "unattributed": 0}
    assert all(item["missing_in_window"] == 0 and item["missing_outside_window"] == 0 for item in facts["topics"].values())
    assert {JOINT, SCENE, CLOCK, HEAD, "/wrist_camera/color", "/so101/raw/planning_scene_reads"} <= set(facts["topics"])


def test_a_joint_state_lost_inside_the_window_is_a_topic_loss(tmp_path):
    report = scan(tmp_path, drop=[(JOINT, IN_WINDOW)], transport_lost=1)
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{JOINT} ") for r in report["reasons"]), report["reasons"]
    item = report["topic_loss"]["topics"][JOINT]
    assert item["missing_in_window"] == 1 and item["first_missing"] == [[1_040_000_000, 1_060_000_000]]


def test_a_scene_state_transition_lost_inside_the_window_is_a_topic_loss(tmp_path):
    report = scan(tmp_path, drop=[(SCENE, 10)], transport_lost=1)         # the world record at 1.020 s has no scene state
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{SCENE} ") for r in report["reasons"]), report["reasons"]
    assert report["topic_loss"]["topics"][SCENE]["first_missing"] == [[510, 1_020_000_000]]


def test_a_clock_message_lost_inside_the_window_is_a_topic_loss(tmp_path):
    report = scan(tmp_path, drop=[(CLOCK, 100)], transport_lost=1)         # 1.100 s
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{CLOCK} ") for r in report["reasons"]), report["reasons"]


def test_an_image_lost_while_its_camera_info_arrived_is_a_topic_loss(tmp_path):
    report = scan(tmp_path, drop=[(HEAD, 2)], transport_lost=1)           # 1.200 s: between the reset and the normal stop
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{HEAD} ") for r in report["reasons"]), report["reasons"]


def test_planning_scene_reads_fewer_in_the_bag_than_the_sidecar_made_are_a_topic_loss(tmp_path):
    bag = build_bag(tmp_path / "raw")
    report = scan_bag(bag, transport_lost=0, scene_reads_expected=2)
    assert any(r.startswith("OFFLINE_TOPIC_LOSS:/so101/raw/planning_scene_reads") for r in report["reasons"])


def test_scene_reads_made_before_the_window_are_recorded_but_do_not_count(tmp_path):
    """CP-3489: the sidecar can start reading before the bag recorder has matched its subscription (T03, T06 of the first v2 round:
    the first 5 and 3 reads, at sim time 0, are in the sidecar and not in the bag). Reads before the window are never used by a row."""
    bag = build_bag(tmp_path / "raw")
    bag_read_ns = 950_000_000
    old = scan_bag(bag, transport_lost=0, scene_reads_expected=4)                                    # the count rule alone
    assert any(r.startswith("OFFLINE_TOPIC_LOSS:/so101/raw/planning_scene_reads") for r in old["reasons"])
    window_begin = old["timeline"]["window_begin_sim_ns"] if "window_begin_sim_ns" in old.get("timeline", {}) else None
    report = scan_bag(bag, transport_lost=0, scene_reads_expected=4, scene_read_sidecar_stamps=[0, 0, 0, bag_read_ns])
    item = report["topic_loss"]["topics"]["/so101/raw/planning_scene_reads"]
    if bag_read_ns < report["topic_loss"]["window"]["begin_sim_ns"]:
        assert loss_reasons(report) == [], report["reasons"]
        assert item["missing_in_window"] == 0 and item["missing_outside_window"] == 3
        assert "inside the window" in item["rule"]
    # a read missing from the bag INSIDE the window is still a loss, whatever happened before it
    inside = report["topic_loss"]["window"]["begin_sim_ns"] + 10_000_000
    lost = scan_bag(bag, transport_lost=0, scene_reads_expected=5, scene_read_sidecar_stamps=[0, 0, 0, bag_read_ns, inside])
    assert any(r.startswith("OFFLINE_TOPIC_LOSS:/so101/raw/planning_scene_reads missing=1") for r in lost["reasons"]), lost["reasons"]
    # a sidecar list that does not match the sidecar's own count is not trusted: the whole-bag count rule applies
    mismatch = scan_bag(bag, transport_lost=0, scene_reads_expected=4, scene_read_sidecar_stamps=[0])
    assert any(r.startswith("OFFLINE_TOPIC_LOSS:/so101/raw/planning_scene_reads") for r in mismatch["reasons"])


def test_a_loss_outside_the_window_is_recorded_not_fatal(tmp_path):
    report = scan(tmp_path, drop=[(JOINT, BEFORE_WINDOW), (SCENE, 1)], transport_lost=2)
    assert loss_reasons(report) == [], report["reasons"]
    facts = report["topic_loss"]
    assert facts["topics"][JOINT]["missing_outside_window"] == 1 and facts["topics"][JOINT]["missing_in_window"] == 0
    assert facts["topics"][SCENE]["missing_outside_window"] == 1
    assert facts["transport_lost"] == {"reported": 2, "attributed": 2, "unattributed": 0}


def test_a_transport_loss_that_no_topic_accounts_for_fails_closed(tmp_path):
    report = scan(tmp_path, transport_lost=3)
    assert "OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 3 of 3" in report["reasons"], report["reasons"]
    partial = scan(tmp_path, name="partial", transport_lost=3, drop=[(JOINT, BEFORE_WINDOW)])
    assert "OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 2 of 3" in partial["reasons"], partial["reasons"]


def test_an_unknown_transport_loss_count_fails_closed(tmp_path):
    bag = build_bag(tmp_path / "raw")
    report = scan_bag(bag, transport_lost=None, scene_reads_expected=1)
    assert "OFFLINE_TRANSPORT_LOSS_UNKNOWN" in report["reasons"]


def test_a_gap_that_overlaps_a_clock_gap_is_a_producer_stall_not_a_message_loss(tmp_path):
    # the clock itself skipped 1.100 s: nothing was published at that cycle, so the joint state of that instant is a stall too. The
    # stall is judged once, on the clock (it is the clock rule's verdict); it is not counted as a lost joint state
    report = scan(tmp_path, drop=[(CLOCK, 100), (JOINT, 20)], transport_lost=0)
    topics = report["topic_loss"]["topics"]
    assert topics[CLOCK]["missing_in_window"] == 1
    assert topics[JOINT]["stalls"] == 1 and topics[JOINT]["missing_in_window"] == 0
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{CLOCK}") for r in report["reasons"])
    assert not any(r.startswith(f"OFFLINE_TOPIC_LOSS:{JOINT}") for r in report["reasons"])


# ---- the processor: the verdict and the document -----------------------------------------------------------------------------

def test_the_processor_makes_the_data_invalid_and_writes_the_gate_document(tmp_path):
    from test_p2_offline_processor import run

    bag = build_bag(tmp_path / "raw", drop=[(JOINT, IN_WINDOW)], transport_lost=1)
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "INVALID" and any(r.startswith(f"OFFLINE_TOPIC_LOSS:{JOINT}") for r in report["reasons"])
    document = json.loads((out / topic_loss.DOCUMENT_NAME).read_bytes())
    assert document["status"] == "FAIL" and document["lost_in_window"] >= 1
    assert report["topic_loss"]["status"] == "FAIL" and report["qc"] == {"status": "NOT_RUN"}


def test_the_processor_keeps_a_valid_bag_valid_and_binds_the_gate_document(tmp_path):
    from test_p2_offline_processor import run

    bag = build_bag(tmp_path / "raw")
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "VALID", report["reasons"]
    document = json.loads((out / topic_loss.DOCUMENT_NAME).read_bytes())
    assert document["status"] == "PASS" and report["topic_loss"]["sha256"] == __import__("hashlib").sha256(
        (out / topic_loss.DOCUMENT_NAME).read_bytes()).hexdigest()


def test_the_loss_facts_come_from_the_stats_or_from_the_recorders_log(tmp_path):
    from so101_demo.act.offline.processor import load_loss_facts

    (tmp_path / "raw").mkdir()
    stats = tmp_path / "raw" / "record-stats.json"
    stats.write_text(json.dumps({"transport_lost": 7, "scene_reads": {"count": 5, "errors": 0}}))
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats) == {"transport_lost": 7, "scene_reads_expected": 5,
                                                                                   "transport_lost_by_topic": None,
                                                                                   "transport_lost_events": None,
                                                                                   "scene_read_sidecar_stamps": None}
    stats.write_text(json.dumps({"scene_reads": {"count": 5, "errors": 0}}))
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost"] is None
    (tmp_path / "raw" / "bag-record.log").write_text(
        "[WARN] [so101_raw_recorder]: Recording stopped\n[WARN] [so101_raw_recorder]: Number of messages lost on the transport layer: 6\n")
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost"] == 6
    (tmp_path / "raw" / "bag-record.log").write_text("[INFO] [so101_raw_recorder]: Recording stopped\n")
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost"] == 0
    stats.write_text(json.dumps({"transport_lost": 3, "transport_lost_by_topic": {"/clock": 3}}))
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost_by_topic"] == {"/clock": 3}


# ---- C5: the recorder's per-topic breakdown ----------------------------------------------------------------------------------

EVENTS = "/so101/teacher/events"
READS = "/so101/raw/planning_scene_reads"
JOINTS_UNUSED = "/so101/simulation/joints"


def scan_by_topic(tmp_path, by_topic, *, name="raw", transport_lost=None, drop=(), reads=1, events=None):
    total = sum(by_topic.values()) if transport_lost is None else transport_lost
    bag = build_bag(tmp_path / name, drop=drop, transport_lost=total, transport_lost_by_topic=by_topic,
                    transport_lost_events=events)
    return scan_bag(bag, transport_lost=total, scene_reads_expected=reads, transport_lost_by_topic=by_topic,
                    transport_lost_events=events)


def test_a_breakdown_with_no_loss_passes_and_is_recorded_in_the_document(tmp_path):
    report = scan_by_topic(tmp_path, {})
    assert report["reasons"] == [], report["reasons"]
    assert report["topic_loss"]["transport_lost"] == {"reported": 0, "attributed": 0, "unattributed": 0, "by_topic": {}}


def test_a_reported_loss_that_the_topics_own_rule_shows_outside_the_window_is_recorded_not_fatal(tmp_path):
    report = scan_by_topic(tmp_path, {JOINT: 1}, drop=[(JOINT, BEFORE_WINDOW)])
    assert loss_reasons(report) == [], report["reasons"]
    assert report["topic_loss"]["transport_lost"] == {"reported": 1, "attributed": 1, "unattributed": 0, "by_topic": {JOINT: 1}}
    assert report["topic_loss"]["topics"][JOINT]["reported"] == 1 and report["topic_loss"]["topics"][JOINT]["detected"] == 1


def test_a_reported_loss_on_a_used_topic_with_no_gap_to_show_for_it_is_invalid_and_names_the_topic(tmp_path):
    # the shape of the L2 residual: the recorder says the topic lost messages, the bag shows none
    report = scan_by_topic(tmp_path, {JOINT: 3})
    assert f"OFFLINE_TOPIC_LOSS:{JOINT} reported_in_window=3 detected=0" in report["reasons"], report["reasons"]
    assert report["topic_loss"]["transport_lost"]["unattributed"] == 3


def test_a_reported_loss_on_an_unused_topic_is_recorded_only(tmp_path):
    report = scan_by_topic(tmp_path, {JOINTS_UNUSED: 3, "/neck_controller/controller_state": 2})
    assert loss_reasons(report) == [], report["reasons"]
    facts = report["topic_loss"]
    assert facts["transport_lost"] == {"reported": 5, "attributed": 5, "unattributed": 0,
                                       "by_topic": {"/neck_controller/controller_state": 2, JOINTS_UNUSED: 3}}
    assert facts["topics"][JOINTS_UNUSED]["reported"] == 3 and facts["topics"][JOINTS_UNUSED]["used"] is False


def test_per_topic_numbers_that_do_not_add_up_to_the_aggregate_fail_closed(tmp_path):
    report = scan_by_topic(tmp_path, {JOINTS_UNUSED: 1}, transport_lost=4)
    assert any(r.startswith("OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 3 of 4") for r in report["reasons"]), report["reasons"]
    over = scan_by_topic(tmp_path, {JOINTS_UNUSED: 5}, name="over", transport_lost=4)
    assert any(r.startswith("OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 1 of 4") for r in over["reasons"]), over["reasons"]


def test_a_loss_named_on_a_topic_the_recorder_does_not_subscribe_to_fails_closed(tmp_path):
    report = scan_by_topic(tmp_path, {"/not/a/recorded/topic": 2})
    assert any(r.startswith("OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 2 of 2") for r in report["reasons"]), report["reasons"]


def test_a_gap_inside_the_window_stays_invalid_with_the_breakdown_too(tmp_path):
    report = scan_by_topic(tmp_path, {JOINT: 1}, drop=[(JOINT, IN_WINDOW)])
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{JOINT} gaps=1") for r in report["reasons"]), report["reasons"]
    assert not any("reported_in_window=" in r for r in report["reasons"])


def test_a_loss_on_the_events_topic_after_a_whole_sequence_is_after_the_terminal_event(tmp_path):
    report = scan_by_topic(tmp_path, {EVENTS: 2})
    assert loss_reasons(report) == [], report["reasons"]
    assert report["topic_loss"]["topics"][EVENTS]["reported"] == 2


def test_a_planning_scene_read_the_sidecar_made_and_the_bag_lacks_is_explained_by_its_span_rule(tmp_path):
    report = scan_by_topic(tmp_path, {READS: 1}, reads=2)
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{READS} missing=1") for r in report["reasons"]), report["reasons"]
    assert not any("reported_in_window=" in r for r in report["reasons"])
    over = scan_by_topic(tmp_path, {READS: 2}, name="over", reads=1)
    assert f"OFFLINE_TOPIC_LOSS:{READS} reported_in_window=2 detected=0" in over["reasons"], over["reasons"]


def test_the_contact_step_span_is_read_only_when_the_recorder_reported_a_loss_on_it(tmp_path, monkeypatch):
    from so101_demo.act.offline import scan as scan_module

    calls = []
    monkeypatch.setattr(scan_module, "_contact_step_gaps", lambda bag: calls.append(bag) or 2)
    clean = scan_by_topic(tmp_path, {})
    assert calls == [] and loss_reasons(clean) == []
    lossy = scan_by_topic(tmp_path, {"/so101/simulation/robot_contacts": 2}, name="lossy")
    assert len(calls) == 1 and lossy["topic_loss"]["topics"]["/so101/simulation/robot_contacts"]["detected"] == 2
    assert loss_reasons(lossy) == []


def test_a_bag_recorded_without_the_breakdown_keeps_the_aggregate_rule(tmp_path):
    report = scan(tmp_path, transport_lost=3)
    assert "OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 3 of 3" in report["reasons"]
    assert report["topic_loss"]["transport_lost"] == {"reported": 3, "attributed": 0, "unattributed": 3}


def test_the_per_topic_lines_of_the_recorders_debug_log_are_parsed_to_the_last_cumulative_total():
    from so101_demo.act.offline.raw_recorder import (
        RECORDER_LOG_LEVEL,
        transport_lost_by_topic_from_log,
    )

    log = ("[DEBUG] [1.0] [so101_raw_recorder]: Messages lost on transport layer for topic '/clock'. Total lost: 1\n"
           "[DEBUG] [2.0] [so101_raw_recorder]: Messages lost on transport layer for topic '/a/b'. Total lost: 4\n"
           "[DEBUG] [3.0] [so101_raw_recorder]: Messages lost on transport layer for topic '/clock'. Total lost: 2\n"
           "[WARN] [4.0] [so101_raw_recorder]: Number of messages lost on the transport layer: 6\n")
    assert RECORDER_LOG_LEVEL == "debug"
    assert transport_lost_by_topic_from_log(log) == {"/a/b": 4, "/clock": 2}
    assert transport_lost_by_topic_from_log("[INFO] nothing lost\n") == {}


def test_the_processor_reads_the_breakdown_and_makes_an_unexplained_used_topic_loss_invalid(tmp_path):
    from test_p2_offline_processor import run

    bag = build_bag(tmp_path / "raw", transport_lost=3, transport_lost_by_topic={JOINT: 3})
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "INVALID" and f"OFFLINE_TOPIC_LOSS:{JOINT} reported_in_window=3 detected=0" in report["reasons"]
    assert json.loads((out / topic_loss.DOCUMENT_NAME).read_bytes())["transport_lost"]["by_topic"] == {JOINT: 3}
    unused = build_bag(tmp_path / "raw2", transport_lost=3, transport_lost_by_topic={JOINTS_UNUSED: 3})
    kept, _ = run(tmp_path, unused, name="sealed2")
    assert kept["verdict"] == "VALID", kept["reasons"]


# ---- CP-3394: the log time of a per-topic loss says whether it lies before the window ------------------------------------------

CLOCK_TOPIC = "/clock"
SEC = 1_000_000_000


def window_wall_ns(tmp_path):
    """The wall time (bag stamp) of the window's first /clock message in the synthetic bag."""
    return scan_by_topic(tmp_path, {}, name="probe")["topic_loss"]["window"]["begin_wall_ns"]


def event(topic, when, total=1):
    return {"topic": topic, "total": total, "log_time_ns": when}


def test_start_of_stream_losses_logged_before_the_window_are_recorded_and_the_data_stays_valid(tmp_path):
    wall = window_wall_ns(tmp_path)
    events = [event(CLOCK_TOPIC, wall - 3 * SEC), event(JOINT, wall - 3 * SEC), event(SCENE, wall - 2 * SEC)]
    report = scan_by_topic(tmp_path, {CLOCK_TOPIC: 1, JOINT: 1, SCENE: 1}, events=events)
    assert loss_reasons(report) == [], report["reasons"]
    facts = report["topic_loss"]
    assert facts["transport_lost"]["unattributed"] == 0 and facts["transport_lost"]["attributed"] == 3
    assert facts["topics"][JOINT]["reported_outside_window"] == 1 and facts["topics"][JOINT]["reported_in_window"] == 0


def test_one_loss_logged_inside_the_window_with_no_detected_gap_is_invalid(tmp_path):
    wall = window_wall_ns(tmp_path)
    report = scan_by_topic(tmp_path, {JOINT: 1}, events=[event(JOINT, wall + SEC)])
    assert f"OFFLINE_TOPIC_LOSS:{JOINT} reported_in_window=1 detected=0" in report["reasons"], report["reasons"]


def test_a_loss_logged_inside_the_window_that_a_gap_outside_it_matches_is_valid(tmp_path):
    wall = window_wall_ns(tmp_path)
    report = scan_by_topic(tmp_path, {JOINT: 1}, drop=[(JOINT, BEFORE_WINDOW)], events=[event(JOINT, wall + SEC)])
    assert loss_reasons(report) == [], report["reasons"]
    assert report["topic_loss"]["topics"][JOINT]["detected"] == 1


def test_one_detected_gap_cannot_account_for_two_losses(tmp_path):
    wall = window_wall_ns(tmp_path)
    events = [event(JOINT, wall + SEC, 1), event(JOINT, wall + 2 * SEC, 2)]
    report = scan_by_topic(tmp_path, {JOINT: 2}, drop=[(JOINT, BEFORE_WINDOW)], events=events)
    assert f"OFFLINE_TOPIC_LOSS:{JOINT} reported_in_window=2 detected=1" in report["reasons"], report["reasons"]
    mixed = [event(JOINT, wall - 3 * SEC, 1), event(JOINT, wall + SEC, 2)]
    ok = scan_by_topic(tmp_path, {JOINT: 2}, name="mixed", drop=[(JOINT, BEFORE_WINDOW)], events=mixed)
    assert loss_reasons(ok) == [], "the start-of-stream loss needs no gap, so the one gap matches the one in-window loss"


@pytest.mark.parametrize("when", [None, "never", float("nan"), 1.5])
def test_a_log_time_that_cannot_be_mapped_is_treated_as_inside_the_window(tmp_path, when):
    report = scan_by_topic(tmp_path, {JOINT: 1}, events=[event(JOINT, when)])
    assert f"OFFLINE_TOPIC_LOSS:{JOINT} reported_in_window=1 detected=0" in report["reasons"], report["reasons"]


def test_losses_the_log_lines_do_not_account_for_and_a_line_just_before_the_window_are_inside(tmp_path):
    wall = window_wall_ns(tmp_path)
    short = scan_by_topic(tmp_path, {JOINT: 2}, name="short", events=[event(JOINT, wall - 3 * SEC, 1)])
    assert f"OFFLINE_TOPIC_LOSS:{JOINT} reported_in_window=1 detected=0" in short["reasons"], short["reasons"]
    edge = scan_by_topic(tmp_path, {JOINT: 1}, name="edge", events=[event(JOINT, wall - 10_000_000)])    # inside the 100 ms margin
    assert f"OFFLINE_TOPIC_LOSS:{JOINT} reported_in_window=1 detected=0" in edge["reasons"], edge["reasons"]
    over = scan_by_topic(tmp_path, {JOINT: 1}, name="over", events=[event(JOINT, wall - 3 * SEC, 5)])
    assert "reported_in_window=1" in " ".join(over["reasons"]), "lines that claim more than the recorder reported are not trusted"


def test_an_unused_topic_loss_inside_the_window_is_recorded_only(tmp_path):
    wall = window_wall_ns(tmp_path)
    report = scan_by_topic(tmp_path, {JOINTS_UNUSED: 1}, events=[event(JOINTS_UNUSED, wall + SEC)])
    assert loss_reasons(report) == [], report["reasons"]


def test_the_aggregate_must_still_equal_the_sum_of_the_last_per_topic_totals(tmp_path):
    wall = window_wall_ns(tmp_path)
    report = scan_by_topic(tmp_path, {JOINT: 1}, transport_lost=3, events=[event(JOINT, wall - 3 * SEC)])
    assert any(r.startswith("OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 2 of 3") for r in report["reasons"]), report["reasons"]


def test_the_log_lines_become_events_with_their_exact_times():
    from so101_demo.act.offline.raw_recorder import transport_lost_events_from_log

    log = ("[DEBUG] [1791468693.120143303] [so101_raw_recorder]: Messages lost on transport layer for topic '/clock'. Total lost: 1\n"
           "[DEBUG] [1791468693.1] [so101_raw_recorder]: Messages lost on transport layer for topic '/a/b'. Total lost: 4\n"
           "[WARN] [1791468782.424240667] [so101_raw_recorder]: Number of messages lost on the transport layer: 5\n")
    assert transport_lost_events_from_log(log) == [
        {"topic": "/clock", "total": 1, "log_time_ns": 1791468693120143303},
        {"topic": "/a/b", "total": 4, "log_time_ns": 1791468693100000000}]


def test_the_loss_facts_carry_the_events_from_the_stats_or_from_the_log_beside_them(tmp_path):
    from so101_demo.act.offline.processor import load_loss_facts

    (tmp_path / "raw").mkdir()
    stats = tmp_path / "raw" / "record-stats.json"
    line = "[DEBUG] [1791468693.120143303] [r]: Messages lost on transport layer for topic '/clock'. Total lost: 1\n"
    stats.write_text(json.dumps({"transport_lost": 1, "transport_lost_by_topic": {"/clock": 1}}))
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost_events"] is None      # no log, no events
    (tmp_path / "raw" / "bag-record.log").write_text(line)
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost_events"] == [
        {"topic": "/clock", "total": 1, "log_time_ns": 1791468693120143303}]
    (tmp_path / "raw" / "bag-record.log").write_text(line.replace("Total lost: 1", "Total lost: 2"))
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost_events"] is None, "totals must agree with the stats"
    stats.write_text(json.dumps({"transport_lost": 1, "transport_lost_by_topic": {"/clock": 1},
                                 "transport_lost_events": [{"topic": "/clock", "total": 1, "log_time_ns": 5}]}))
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost_events"][0]["log_time_ns"] == 5


def test_the_processor_keeps_a_bag_with_start_of_stream_losses_valid_and_a_loss_inside_the_window_invalid(tmp_path):
    from test_p2_offline_processor import run

    wall = window_wall_ns(tmp_path)
    start = build_bag(tmp_path / "raw1", transport_lost=2, transport_lost_by_topic={CLOCK_TOPIC: 1, JOINT: 1},
                      transport_lost_events=[event(CLOCK_TOPIC, wall - 3 * SEC), event(JOINT, wall - 3 * SEC)])
    kept, out = run(tmp_path, start, name="sealed1")
    assert kept["verdict"] == "VALID", kept["reasons"]
    assert json.loads((out / topic_loss.DOCUMENT_NAME).read_bytes())["rule_version"] == "topic_loss_v2"
    inside = build_bag(tmp_path / "raw2", transport_lost=1, transport_lost_by_topic={JOINT: 1},
                       transport_lost_events=[event(JOINT, wall + SEC)])
    lost, _ = run(tmp_path, inside, name="sealed2")
    assert lost["verdict"] == "INVALID" and f"OFFLINE_TOPIC_LOSS:{JOINT} reported_in_window=1 detected=0" in lost["reasons"]


# ---- the QC check and the rule version ---------------------------------------------------------------------------------------

IDENTITY = {"session_id": "session-1", "reset_epoch": 2, "attempt_id": "attempt-1", "lease": {}}


def write_document(root, **changes):
    topics = {JOINT: {"rule": "x", "used": True, "messages": 1, "gaps": 0, "stalls": 0, "missing_in_window": 0,
                      "missing_outside_window": 0, "diagnostic_in_window": 0, "first_missing": []}}
    document = topic_loss.build_document(identity={k: IDENTITY[k] for k in ("session_id", "reset_epoch", "attempt_id")},
                                         window={}, transport_lost={"reported": 0, "attributed": 0, "unattributed": 0},
                                         topics=topics, reasons=[])
    document.update(changes)
    path = topic_loss.document_path(root / "episode")
    path.write_bytes(topic_loss.canonical(document))
    return path


def test_the_qc_check_passes_a_clean_document_and_names_it_by_digest(tmp_path):
    path = write_document(tmp_path)
    check = topic_loss.qc_check(tmp_path / "episode", identity=IDENTITY)
    assert check["status"] == "PASS" and check["rule_version"] == "topic_loss_v2" and check["lost_in_window"] == 0
    assert check["document_sha256"] == __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    topic_loss.validate_check(check)


@pytest.mark.parametrize("change", ["missing", "garbage", "other_attempt", "old_rule", "noncanonical"])
def test_the_qc_check_refuses_an_absent_foreign_or_old_document(tmp_path, change):
    path = write_document(tmp_path)
    if change == "missing":
        path.unlink()
    elif change == "garbage":
        path.write_text("{")
    elif change == "other_attempt":
        write_document(tmp_path, identity={"session_id": "session-1", "reset_epoch": 2, "attempt_id": "other"})
    elif change == "old_rule":
        write_document(tmp_path, rule_version="topic_loss_v0")
    else:
        path.write_text(json.dumps(json.loads(path.read_text()), indent=2))
    with pytest.raises(ValueError, match="NATIVE_QC_TOPIC_LOSS"):
        topic_loss.qc_check(tmp_path / "episode", identity=IDENTITY)


def test_a_failed_document_fails_the_check_with_its_first_reason(tmp_path):
    write_document(tmp_path, status="FAIL", lost_in_window=1, reasons=["OFFLINE_TOPIC_LOSS:/joint_states missing=1"])
    check = topic_loss.qc_check(tmp_path / "episode", identity=IDENTITY)
    assert check["status"] == "FAIL" and check["reason"].startswith("OFFLINE_TOPIC_LOSS:/joint_states")


def test_the_qc_rule_version_changed_so_older_reports_and_memos_are_refused():
    assert episode_qc.QC_RULE_VERSION == "act_data_qc_v4" and episode_qc.TOPIC_LOSS_CHECK == "topic_loss_gate"
    from test_act_qc_report_publication import report

    document = report()
    assert episode_qc.validate_qc_report(document) == document
    old = copy.deepcopy(document)
    old["rule_version"] = "act_data_qc_v3"
    del old["checks"]["topic_loss_gate"]
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.validate_qc_report(old)
    missing = copy.deepcopy(document)
    del missing["checks"]["topic_loss_gate"]
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.validate_qc_report(missing)
    failing = copy.deepcopy(document)
    failing["checks"]["topic_loss_gate"].update(status="FAIL", reason="OFFLINE_TOPIC_LOSS:/joint_states", lost_in_window=1)
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.validate_qc_report(failing)           # a failed gate with a PASS verdict is inconsistent
    failing.update(status="FAIL", reason="OFFLINE_TOPIC_LOSS:/joint_states")
    assert episode_qc.validate_qc_report(failing)["status"] == "FAIL"


def test_the_memo_fingerprint_covers_the_gate_document(tmp_path):
    root = tmp_path / "attempt"
    (root / "episode").mkdir(parents=True)
    (root / "episode" / "seal.json").write_text("{}")
    scope, inputs = root / "scope.json", root / "inputs.json"
    scope.write_text("s")
    inputs.write_text("i")
    write_document(root)
    one = qc_memo.fingerprint(episode_root=root / "episode", scope=scope, inputs_manifest=inputs)
    write_document(root, lost_in_window=0, reasons=[], window={"changed": 1})
    assert qc_memo.fingerprint(episode_root=root / "episode", scope=scope, inputs_manifest=inputs) != one
    assert "topic_loss" in qc_memo.CODE_MODULES


def test_a_scan_level_loss_leaves_a_sealed_failed_record_not_a_second_seal_failure(tmp_path):
    """P1(b): a reason the scan latches before the replay (here an unattributed transport loss) used to stop the engine from
    retaining the Teacher events, so the capture saw rows but never the first command and the window it claimed (`complete`, no first
    command) could not be sealed: RECORDER_SEAL_FAILED: AUDIT_WINDOW_INVALID, and the retained record stayed unsealed."""
    from test_p2_offline_processor import run

    bag = build_bag(tmp_path / "raw", transport_lost=3)
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "INVALID"
    assert "OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 3 of 3" in report["reasons"], report["reasons"]
    assert not any(r.startswith("RECORDER_SEAL_FAILED") for r in report["reasons"]), report["reasons"]
    seal = json.loads((Path(out) / "episode" / "seal.json").read_bytes())
    assert seal["status"] == "FAILED" and seal["reason"].startswith("RECORDER_DATA_INVALID: OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED"), seal
