"""Read-only scan of a raw bag before it is replayed (P2).

The record-only process cannot know whether it recorded everything: it only writes. This scan is where a bag that lost data is
named. It checks what the bag itself can prove, independent of the engine that replays it later:

* every topic the episode needs has messages, and the bag's metadata counts equal what is read back from it;
* the Teacher event sequence is whole (seq 1..N);
* inside the episode window [first command, terminal + 0.1 s] every ordered source is gap-free: the three `controller_state`
  topics on their 2 ms stamp grid, the physics chunks by chunk sequence and step, and the world evidence by publisher sequence;
* the bag covers that window at both ends.

Messages outside the window (before the Teacher's first command, after the end) are never judged here: only data the episode
uses can invalidate it.
"""

from __future__ import annotations

import json
from collections import defaultdict

from .raw_recorder import CORE_TOPICS, EVENTS_TOPIC

CONTROLLER_STATE_TOPICS = ("/arm_controller/controller_state", "/gripper_controller/controller_state",
                           "/neck_controller/controller_state")
CHUNK_TOPIC = "/so101/simulation/physics_step_chunks"
WORLD_TOPIC = "/so101/simulation/evidence"
STATE_PERIOD_NS = 2_000_000
STATE_TAIL_NS = 100_000_000
#: topics whose messages are decoded in the scan (the images are large, and only counted from the bag's own metadata)
CAMERA_INFO_TOPICS = ("/head_camera/camera_info", "/wrist_camera/camera_info")   # same stamps as the images, and small
CAMERA_PERIOD_NS = 100_000_000
_DECODED = (EVENTS_TOPIC, CHUNK_TOPIC, WORLD_TOPIC, *CONTROLLER_STATE_TOPICS, *CAMERA_INFO_TOPICS)
_NS = 1_000_000_000


def required_topics() -> tuple:
    return tuple(dict.fromkeys((*CORE_TOPICS, EVENTS_TOPIC)))


def parse_events(texts) -> list:
    events = []
    for text in texts:
        events.append(json.loads(text))
    return events


def timeline(events) -> dict:
    """The Teacher's own account of the run: identity and the instants that bound the episode window."""
    facts = {"identity": None, "reset_complete_sim_s": None, "first_command_sim_ns": None, "normal_stop_sim_ns": None,
             "terminal_sim_ns": None, "terminal": None, "reset_epoch": None, "final_normal_stop_seq": None,
             "normal_stop_count": 0, "normal_stop_after_terminal": 0}
    for event in events:
        if facts["identity"] is None:
            facts["identity"] = {"session_id": event.get("session_id"), "reset_epoch": event.get("reset_epoch"),
                                 "attempt_id": event.get("attempt_id")}
        kind, payload = event.get("type"), event.get("payload") or {}
        if kind == "reset_complete" and facts["reset_complete_sim_s"] is None:
            facts["reset_complete_sim_s"] = payload.get("simulation_time_s")
        elif kind == "phase_begin" and payload.get("goal_sent") is True and facts["first_command_sim_ns"] is None:
            facts["first_command_sim_ns"] = int(event["sim_time_ns"])
        elif kind == "normal_stop" and facts["terminal_sim_ns"] is not None:
            # CP-3457: a stop confirmed after the terminal event has no place in the episode; it is refused, not taken as the last one
            facts["normal_stop_after_terminal"] += 1
        elif kind == "normal_stop":
            # the Teacher confirms a stop at each release step and once more after its sequence: the episode's is the last
            facts["normal_stop_sim_ns"] = int(event["sim_time_ns"])
            facts["final_normal_stop_seq"] = event.get("seq")
            facts["normal_stop_count"] += 1
        elif kind == "terminal":
            facts["terminal_sim_ns"] = int(event["sim_time_ns"])
            facts["terminal"] = payload
    identity = facts["identity"]
    facts["reset_epoch"] = None if identity is None else identity["reset_epoch"]
    return facts


def _stamp_ns(stamp) -> int:
    return int(stamp.sec) * _NS + int(stamp.nanosec)


def scan_bag(bag, *, info=None) -> dict:
    """{"reasons": [...], "timeline": {...}, "continuity": {...}, "counts": {...}} for the bag at `bag`."""
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    from .bag_io import bag_info, read_messages

    info = bag_info(bag) if info is None else info
    counts = {topic: item["count"] for topic, item in sorted(info["topics"].items())}
    reasons = [f"OFFLINE_BAG_TOPIC_MISSING: {topic}" for topic in required_topics() if counts.get(topic, 0) == 0]
    types: dict = {}
    events_text, states, chunks, worlds, cameras = [], defaultdict(list), [], [], defaultdict(list)
    read_counts: dict = defaultdict(int)
    for topic, type_name, bag_stamp, data in read_messages(bag, topics=[t for t in _DECODED if t in counts]):
        read_counts[topic] += 1
        if type_name not in types:
            types[type_name] = get_message(type_name)
        message = deserialize_message(data, types[type_name])
        if topic == EVENTS_TOPIC:
            events_text.append(message.data)
        elif topic in CONTROLLER_STATE_TOPICS:
            states[topic].append(_stamp_ns(message.header.stamp))
        elif topic in CAMERA_INFO_TOPICS:
            cameras[topic].append(_stamp_ns(message.header.stamp))
        elif topic == CHUNK_TOPIC:
            chunks.append((int(message.chunk_sequence), int(message.first_physics_step), int(message.last_physics_step),
                           round(message.first_simulation_time_s * _NS), round(message.last_simulation_time_s * _NS),
                           int(message.reset_epoch)))
        else:
            worlds.append((int(message.publisher_sequence), _stamp_ns(message.header.stamp), int(message.reset_epoch),
                           bool(message.paused), int(bag_stamp)))
    for topic, count in read_counts.items():
        if count != counts[topic]:
            reasons.append(f"OFFLINE_BAG_READBACK_COUNT_MISMATCH: {topic} read={count} metadata={counts[topic]}")
    try:
        events = parse_events(events_text)
    except ValueError as error:
        events, reasons = [], reasons + [f"OFFLINE_TEACHER_EVENT_UNREADABLE: {error}"[:300]]
    facts = timeline(events)
    if facts["normal_stop_after_terminal"]:
        reasons.append(f"OFFLINE_NORMAL_STOP_AFTER_TERMINAL: {facts['normal_stop_after_terminal']}")
    sequence = [event.get("seq") for event in events]
    if sequence != list(range(1, len(sequence) + 1)):
        reasons.append("OFFLINE_TEACHER_EVENT_SEQUENCE_GAP")
    report = {"counts": counts, "timeline": facts, "continuity": {}, "reasons": reasons, "events": len(events)}
    begin, end = facts["first_command_sim_ns"], facts["terminal_sim_ns"]
    if begin is None or end is None or facts["identity"] is None:
        reasons.append("OFFLINE_TEACHER_TIMELINE_INCOMPLETE")
        return report
    end += STATE_TAIL_NS
    epoch = facts["reset_epoch"]
    continuity = report["continuity"]

    def verdict(topic, selected, gaps, first, last, diagnostic=False):
        covered = first is not None and first <= begin and last is not None and last >= end
        continuity[topic] = {"in_window": len(selected), "gap_count": len(gaps), "first_gaps": gaps[:10],
                             "covers_window": covered, "diagnostic": diagnostic}
        if gaps and not diagnostic:
            reasons.append(f"OFFLINE_SOURCE_GAP: {topic} gaps={len(gaps)}")
        if not selected or not covered:
            reasons.append(f"OFFLINE_WINDOW_NOT_COVERED: {topic}")

    # ---- cameras: the grid is the camera cadence, so the frames must sit on it (a +2 ms frame or a missing frame leaves a row
    # without a causal new acquisition: NO_NEW_ACQUISITION). Judged from reset_complete to the normal stop, where rows are minted.
    reset_ns = None if facts["reset_complete_sim_s"] is None else round(facts["reset_complete_sim_s"] * _NS)
    stop_ns = facts["normal_stop_sim_ns"]
    labels = []
    if reset_ns is not None and stop_ns is not None:
        head = [s for s in cameras.get("/head_camera/camera_info", []) if reset_ns <= s <= stop_ns]
        wrist = [s for s in cameras.get("/wrist_camera/camera_info", []) if reset_ns <= s <= stop_ns]
        off_grid = [[a, b] for a, b in zip(head, head[1:]) if b - a != CAMERA_PERIOD_NS]
        report["camera_grid"] = {"frames": len(head), "off_grid_count": len(off_grid), "first_off_grid": off_grid[:10],
                                     "head_wrist_equal": head == wrist}
        if off_grid:
            reasons.append(f"OFFLINE_CAMERA_GRID: {len(off_grid)} intervals other than 100 ms (a +2 ms frame or a missing frame)")
        if head != wrist:
            reasons.append("OFFLINE_CAMERA_PAIR_STAMPS_DIFFER")
        labels = [s + CAMERA_PERIOD_NS for s in head]

    # ---- controller_state: continuous at every label instant (arm, gripper); other gaps are diagnostic (episode_qc rule)
    from ..episode_qc import reference_frames_needed_ns
    needed = sorted({frame for instant in labels for frame in reference_frames_needed_ns(instant, STATE_PERIOD_NS)})
    import bisect
    for topic in CONTROLLER_STATE_TOPICS:
        stamps = states.get(topic, [])
        selected = [s for s in stamps if begin <= s <= end]
        every_gap = [[a, b] for a, b in zip(stamps, stamps[1:]) if b - a != STATE_PERIOD_NS]
        window_gaps = [gap for gap in every_gap if gap[1] > begin and gap[0] < end]
        touching = [gap for gap in window_gaps
                    if (lambda i: i < len(needed) and needed[i] < gap[1])(bisect.bisect_right(needed, gap[0]))]
        neck = topic.startswith("/neck_")
        verdict(topic, selected, [] if neck else touching, stamps[0] if stamps else None, stamps[-1] if stamps else None,
                diagnostic=neck)
        continuity[topic]["gaps_in_window"] = len(window_gaps)
        continuity[topic]["gaps_touching_a_label"] = len(touching)
        continuity[topic]["diagnostic_gaps"] = len(window_gaps) - (0 if neck else len(touching))
        continuity[topic]["first_diagnostic_gaps"] = [g for g in window_gaps if g not in touching][:10]
    inside = [c for c in chunks if c[5] == epoch]
    selected = [c for c in inside if c[4] >= begin and c[3] <= end]
    gaps = [[a[:3], b[:3]] for a, b in zip(selected, selected[1:]) if b[0] != a[0] + 1 or b[1] != a[2] + 1]
    verdict(CHUNK_TOPIC, selected, gaps, inside[0][3] if inside else None, inside[-1][4] if inside else None)
    inside = [w for w in worlds if w[2] == epoch]
    # ---- the episode window starts after the worker's last pre-Teacher pause (CP-3440 A): the worker freezes the simulation for
    # the inference snapshot after the Recorder has started, and a paused world record is not a legal source. The window begins
    # at the first UNPAUSED world record after the last paused record up to the verified reset; a paused record inside the
    # window stays INVALID.
    report["window_start"] = None
    reset_sim_ns = reset_ns if reset_ns is not None else begin
    paused_before = [index for index, w in enumerate(worlds) if w[3] and w[1] <= reset_sim_ns and w[2] == epoch]
    if paused_before:
        after = next((w for w in worlds[paused_before[-1] + 1:] if not w[3] and w[2] == epoch), None)
        if after is not None:
            report["window_start"] = {"publisher_sequence": after[0], "sim_time_ns": after[1], "bag_stamp_ns": after[4],
                                      "last_paused_sim_time_ns": worlds[paused_before[-1]][1],
                                      "paused_records_before": len(paused_before)}
    start_sim = begin if report["window_start"] is None else report["window_start"]["sim_time_ns"]
    paused_inside = [w for w in inside if w[3] and w[1] >= start_sim and w[1] <= end]
    report["paused_world_records_in_window"] = len(paused_inside)
    if paused_inside:
        reasons.append(f"OFFLINE_PAUSED_WORLD_IN_WINDOW: {len(paused_inside)} first at {paused_inside[0][1]}")
    selected = [w for w in inside if begin <= w[1] <= end]
    gaps = [[a[0], b[0]] for a, b in zip(selected, selected[1:]) if b[0] != a[0] + 1]
    verdict(WORLD_TOPIC, selected, gaps, inside[0][1] if inside else None, inside[-1][1] if inside else None)
    return report
