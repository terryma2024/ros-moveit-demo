"""A `normal_stop` after the terminal event is refused."""

import json


# ---- a normal_stop after the terminal event is refused ---------------------------------------------------------------------

def _event(seq, kind, sim_ns, **payload):
    return {"seq": seq, "type": kind, "sim_time_ns": sim_ns, "session_id": "s", "reset_epoch": 1, "attempt_id": "a",
            "payload": payload}


def test_a_normal_stop_after_the_terminal_event_is_counted_and_never_becomes_the_episodes_stop():
    from so101_demo.act.offline.scan import timeline

    events = [_event(1, "reset_complete", 1_000, simulation_time_s=1e-6), _event(2, "phase_begin", 2_000, goal_sent=True),
              _event(3, "normal_stop", 5_000), _event(4, "terminal", 6_000), _event(5, "normal_stop", 9_000)]
    facts = timeline(events)
    assert facts["normal_stop_after_terminal"] == 1
    assert facts["normal_stop_sim_ns"] == 5_000 and facts["final_normal_stop_seq"] == 3 and facts["normal_stop_count"] == 1
    clean = timeline(events[:4])
    assert clean["normal_stop_after_terminal"] == 0 and clean["normal_stop_sim_ns"] == 5_000


def test_the_scan_names_a_stop_after_the_terminal_as_a_reason(tmp_path):
    from std_msgs.msg import String

    from so101_demo.act.offline.bag_io import BagWriter
    from so101_demo.act.offline.raw_recorder import EVENTS_TOPIC
    from so101_demo.act.offline.scan import scan_bag

    def scan(events):
        bag = tmp_path / f"bag{len(events)}"
        writer = BagWriter(bag)
        try:
            writer.create(EVENTS_TOPIC, "std_msgs/msg/String")
            for index, event in enumerate(events):
                writer.write(EVENTS_TOPIC, String(data=json.dumps(event)), index + 1)
        finally:
            writer.close()
        return scan_bag(bag)["reasons"]

    base = [_event(1, "reset_complete", 1_000, simulation_time_s=1e-6), _event(2, "phase_begin", 2_000, goal_sent=True),
            _event(3, "normal_stop", 5_000), _event(4, "terminal", 6_000)]
    assert not any(reason.startswith("OFFLINE_NORMAL_STOP_AFTER_TERMINAL") for reason in scan(base))
    assert "OFFLINE_NORMAL_STOP_AFTER_TERMINAL: 1" in scan(base + [_event(5, "normal_stop", 9_000)])
