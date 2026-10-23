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

from ..rig_profile import DEFAULT_RIG
from .raw_recorder import EVENTS_TOPIC, NECK_STATE_TOPIC, core_topics_for


def controller_state_topics_for(rig) -> tuple:
    """The controller_state topics the episode judges: arm and gripper, and the neck's only for a rig that has one."""
    return ("/arm_controller/controller_state", "/gripper_controller/controller_state",
            *((NECK_STATE_TOPIC,) if rig.has_neck else ()))


CONTROLLER_STATE_TOPICS = controller_state_topics_for(DEFAULT_RIG)
CHUNK_TOPIC = "/so101/simulation/physics_step_chunks"
WORLD_TOPIC = "/so101/simulation/evidence"
STATE_PERIOD_NS = 2_000_000
STATE_TAIL_NS = 100_000_000
#: topics whose messages are decoded in the scan (the images are large, and only counted from the bag's own metadata)
CAMERA_INFO_TOPICS = DEFAULT_RIG.info_topics   # same stamps as the images, and small; a rig names its own via `rig.info_topics`
CAMERA_PERIOD_NS = 100_000_000
CLOCK_TOPIC = "/clock"
JOINT_STATES_TOPIC = "/joint_states"
SCENE_STATE_TOPIC = "/so101/simulation/scene_state"
CONTACTS_TOPIC = "/so101/simulation/robot_contacts"
SCENE_READS_TOPIC = "/so101/raw/planning_scene_reads"
COLOR_TOPICS = DEFAULT_RIG.color_topics
CLOCK_PERIOD_NS = 2_000_000
JOINT_STATES_PERIOD_NS = 10_000_000


def _decoded_for(rig) -> tuple:
    return (EVENTS_TOPIC, CHUNK_TOPIC, WORLD_TOPIC, *controller_state_topics_for(rig), *rig.info_topics, CLOCK_TOPIC,
            JOINT_STATES_TOPIC, SCENE_STATE_TOPIC, SCENE_READS_TOPIC, *rig.color_topics)


_DECODED = _decoded_for(DEFAULT_RIG)
_NS = 1_000_000_000


def required_topics(rig=DEFAULT_RIG) -> tuple:
    return tuple(dict.fromkeys((*core_topics_for(rig), EVENTS_TOPIC)))


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
            # A stop confirmed after the terminal event has no place in the episode; it is refused, not taken as the last one
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


def _starts_with_header(message_class) -> bool:
    """True if the first member of the message is `std_msgs/Header header`."""
    fields = message_class.get_fields_and_field_types()
    return next(iter(fields.items()), None) == ("header", "std_msgs/Header")


def _header_stamp_ns(data):
    """`header.stamp` in ns of a CDR-serialised message whose first member is a header, or None when the body is not plain
    little-endian XCDR1 (representation id 0x0001): the 4-byte encapsulation header, then int32 sec and uint32 nanosec."""
    if len(data) < 12 or data[0] != 0 or data[1] != 1:
        return None
    return int.from_bytes(data[4:8], "little", signed=True) * _NS + int.from_bytes(data[8:12], "little")


def _missing(first, second, period) -> int:
    """How many messages of a `period` grid are absent between two consecutive stamps that are not one period apart."""
    return max(round((second - first) / period) - 1, 0)


def _grid_gaps(stamps, period) -> list:
    return [[a, b] for a, b in zip(stamps, stamps[1:]) if b - a != period]


def _overlaps(gap, intervals) -> bool:
    return any(gap[0] < b and a < gap[1] for a, b in intervals)


def scan_bag(bag, *, info=None, transport_lost=None, scene_reads_expected=None, transport_lost_by_topic=None,
             transport_lost_events=None, scene_read_sidecar_stamps=None, rig=DEFAULT_RIG) -> dict:
    """{"reasons": [...], "timeline": {...}, "continuity": {...}, "counts": {...}, "topic_loss": {...}} for the bag at `bag`.

    `transport_lost` is the number of messages the recorder reported lost on the transport layer (None when unknown, which fails
    closed), `scene_reads_expected` the number of planning-scene reads the sidecar made (its own count), `transport_lost_by_topic`
    the recorder's per-topic breakdown of that total ({} when it ran with debug logging and lost nothing; None for a bag recorded
    without the breakdown, which keeps the aggregate rule), `transport_lost_events` its per-event log times (see `_with_breakdown`), `scene_read_sidecar_stamps` the simulation time (ns) of
    every read the sidecar made (None when its file is not there: the count rule then applies to the whole bag)."""
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    from .bag_io import bag_info, read_messages

    info = bag_info(bag) if info is None else info
    counts = {topic: item["count"] for topic, item in sorted(info["topics"].items())}
    reasons = [f"OFFLINE_BAG_TOPIC_MISSING: {topic}" for topic in required_topics(rig) if counts.get(topic, 0) == 0]
    controller_topics, camera_info_topics, color_topics = controller_state_topics_for(rig), rig.info_topics, rig.color_topics
    types: dict = {}
    events_text, states, chunks, worlds, cameras = [], defaultdict(list), [], [], defaultdict(list)
    clock_stamps, joint_stamps, scene_states, color_stamps = [], [], [], defaultdict(list)
    clock_marks = []        # (simulation ns, bag stamp ns) of every /clock message: the map between the two clocks
    read_counts: dict = defaultdict(int)
    read_stamps: list = []  # simulation time (ns) of every planning-scene read in the bag (None for one that cannot be read)
    # Topics of which the scan keeps only `header.stamp`: the stamp is read from the first eight bytes of the CDR body (the header is the
    # first member), without building the message. Anything that is not a little-endian XCDR1 body takes the full deserialization.
    stamp_only = {topic: states for topic in controller_topics}
    stamp_only.update({topic: cameras for topic in camera_info_topics})
    stamp_only.update({topic: color_stamps for topic in color_topics})
    stamp_only[JOINT_STATES_TOPIC] = None
    header_first: dict = {}
    for topic, type_name, bag_stamp, data in read_messages(bag, topics=[t for t in _decoded_for(rig) if t in counts]):
        read_counts[topic] += 1
        if topic in stamp_only:
            if type_name not in header_first:
                header_first[type_name] = _starts_with_header(get_message(type_name))
            stamp = _header_stamp_ns(data) if header_first[type_name] else None
            if stamp is not None:
                (joint_stamps if topic == JOINT_STATES_TOPIC else stamp_only[topic][topic]).append(stamp)
                continue
        if type_name not in types:
            types[type_name] = get_message(type_name)
        message = deserialize_message(data, types[type_name])
        if topic == EVENTS_TOPIC:
            events_text.append(message.data)
        elif topic in controller_topics:
            states[topic].append(_stamp_ns(message.header.stamp))
        elif topic in camera_info_topics:
            cameras[topic].append(_stamp_ns(message.header.stamp))
        elif topic == CLOCK_TOPIC:
            clock_stamps.append(int(message.clock.sec) * _NS + int(message.clock.nanosec))
            clock_marks.append((clock_stamps[-1], int(bag_stamp)))
        elif topic == JOINT_STATES_TOPIC:
            joint_stamps.append(_stamp_ns(message.header.stamp))
        elif topic == SCENE_STATE_TOPIC:
            scene_states.append((int(message.reset_epoch), int(message.simulation_step), _stamp_ns(message.header.stamp)))
        elif topic in color_topics:
            color_stamps[topic].append(_stamp_ns(message.header.stamp))
        elif topic == SCENE_READS_TOPIC:
            read_stamps.append(_read_sim_ns(message.data))
        elif topic == CHUNK_TOPIC:
            chunks.append((int(message.chunk_sequence), int(message.first_physics_step), int(message.last_physics_step),
                           round(message.first_simulation_time_s * _NS), round(message.last_simulation_time_s * _NS),
                           int(message.reset_epoch)))
        else:
            worlds.append((int(message.publisher_sequence), _stamp_ns(message.header.stamp), int(message.reset_epoch),
                           bool(message.paused), int(bag_stamp), int(message.simulation_step)))
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
        names = rig.camera_names
        infos = {name: [s for s in cameras.get(rig.camera(name).info_topic, []) if reset_ns <= s <= stop_ns] for name in names}
        images = {name: [s for s in color_stamps.get(rig.camera(name).image_topic, []) if reset_ns <= s <= stop_ns]
                  for name in names}
        # All the rig's cameras share one grid. They are judged on the IMAGE stamps (the frames the rows use). A camera_info lost on
        # one camera while all the images are present is a transport loss the topic-loss gate already reports (diagnostic): the
        # camera grid is then the union of the cameras' infos. Without images in the bag the camera_info stamps decide, as before.
        first = names[0]
        infos_equal = all(infos[name] == infos[first] for name in names[1:])
        if any(images.values()):
            pair_equal = all(images[name] == images[first] for name in names[1:])
            grid = sorted(set().union(*infos.values())) if pair_equal else infos[first]
        else:
            pair_equal = infos_equal
            grid = infos[first]
        off_grid = [[a, b] for a, b in zip(grid, grid[1:]) if b - a != CAMERA_PERIOD_NS]
        report["camera_grid"] = {"frames": len(grid), "off_grid_count": len(off_grid), "first_off_grid": off_grid[:10],
                                 "_".join(names) + "_equal": pair_equal,
                                 "paired_on": "images" if any(images.values()) else "camera_info",
                                 "camera_info_pair_equal": infos_equal}
        if off_grid:
            reasons.append(f"OFFLINE_CAMERA_GRID: {len(off_grid)} intervals other than 100 ms (a +2 ms frame or a missing frame)")
        if not pair_equal:
            reasons.append("OFFLINE_CAMERA_PAIR_STAMPS_DIFFER")
        labels = [s + CAMERA_PERIOD_NS for s in grid]

    # ---- controller_state: continuous at every label instant (arm, gripper); other gaps are diagnostic (episode_qc rule)
    from ..episode_qc import reference_frames_needed_ns
    needed = sorted({frame for instant in labels for frame in reference_frames_needed_ns(instant, STATE_PERIOD_NS)})
    import bisect
    for topic in controller_topics:
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
    # ---- the episode window starts after the worker's last pre-Teacher pause: the worker freezes the simulation for
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
    contact_missing = None
    if transport_lost_by_topic and transport_lost_by_topic.get(CONTACTS_TOPIC, 0) > 0 and CONTACTS_TOPIC in counts:
        contact_missing = _contact_step_gaps(bag)       # decoded only when the recorder reported a loss on it
    report["topic_loss"] = _topic_loss(
        report, facts, counts, reasons, begin=begin, end=end, reset_ns=reset_ns, stop_ns=stop_ns, epoch=epoch, states=states,
        chunks=chunks, worlds=worlds, cameras=cameras, clock_stamps=clock_stamps, joint_stamps=joint_stamps,
        scene_states=scene_states, color_stamps=color_stamps, transport_lost=transport_lost,
        scene_reads_expected=scene_reads_expected, start_sim=start_sim, transport_lost_by_topic=transport_lost_by_topic,
        scene_read_stamps=read_stamps, scene_read_sidecar_stamps=scene_read_sidecar_stamps,
        contact_missing=contact_missing, event_sequence=sequence, transport_lost_events=transport_lost_events,
        clock_marks=clock_marks, rig=rig)
    return report


def _contact_step_gaps(bag) -> int:
    """The robot-contact samples missing between consecutive physics steps of one reset epoch (the topic has one per step)."""
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    from .bag_io import read_messages

    message_type, previous, missing = None, None, 0
    for _topic, type_name, _stamp, data in read_messages(bag, topics=[CONTACTS_TOPIC]):
        message_type = message_type or get_message(type_name)
        message = deserialize_message(data, message_type)
        key = (int(message.reset_epoch), int(message.physics_step))
        if previous is not None and key[0] == previous[0] and key[1] > previous[1]:
            missing += key[1] - previous[1] - 1
        previous = key
    return missing


def _read_sim_ns(text):
    """The simulation time (ns) at which a planning-scene read answered, from its sidecar line; None when the line is unreadable."""
    try:
        value = json.loads(text)["payload"]["response_ros_clock"]["sim_time_ns"]
    except (ValueError, KeyError, TypeError):
        return None
    return value if type(value) is int else None


def _sequence_missing(values) -> int:
    """How many numbers are absent between consecutive values of an increasing publisher sequence."""
    return sum(max(b - a - 1, 0) for a, b in zip(values, values[1:]))


def _topic_loss(report, facts, counts, reasons, *, begin, end, reset_ns, stop_ns, epoch, states, chunks, worlds, cameras,
                clock_stamps, joint_stamps, scene_states, color_stamps, transport_lost, scene_reads_expected, start_sim,
                transport_lost_by_topic=None, contact_missing=None, event_sequence=(), transport_lost_events=None,
                clock_marks=(), scene_read_stamps=(), scene_read_sidecar_stamps=None, rig=DEFAULT_RIG) -> dict:
    """Phase C: every topic the episode uses is judged on its own continuity over the window, and the recorder's aggregate
    transport loss is reconciled with what the topics show. Adds reasons to `reasons`; returns the facts for the gate document.

    The window is [the start of the retained world (or the verified reset), the Teacher's terminal + 0.1 s]: wider than the
    window of the older sequence rules, because rows are minted from the capture start. A message lost outside it is recorded,
    never fatal.
    """
    lo = start_sim if report.get("window_start") is not None else (reset_ns if reset_ns is not None else begin)
    lo = min(lo, begin)
    topics: dict = {}
    clock_gaps = _grid_gaps(clock_stamps, CLOCK_PERIOD_NS)
    attributed = 0
    detected: dict = {}      # topic -> messages its own rule shows missing anywhere in the bag (a stall gap included)

    def record(topic, *, rule, used, messages, gaps, period, window_lo=lo, window_hi=end, judged=True, reason=True):
        """One gridded topic: gaps (stamp pairs) -> missing counts inside and outside the window; stalls (a gap that overlaps a
        /clock gap: the producer's cycle was skipped, nothing was published) are not message losses."""
        nonlocal attributed
        stall = [g for g in gaps if topic != CLOCK_TOPIC and _overlaps(g, clock_gaps)]
        lost = [g for g in gaps if g not in stall]
        inside = [g for g in lost if g[1] > window_lo and g[0] < window_hi]
        outside = [g for g in lost if g not in inside]
        missing_in = sum(_missing(a, b, period) or 1 for a, b in inside)
        missing_out = sum(_missing(a, b, period) or 1 for a, b in outside)
        detected[topic] = sum(_missing(a, b, period) or 1 for a, b in gaps)
        topics[topic] = {"rule": rule, "used": used, "messages": messages, "gaps": len(gaps), "stalls": len(stall),
                         "missing_in_window": missing_in if judged else 0, "missing_outside_window": missing_out,
                         "diagnostic_in_window": 0 if judged else missing_in,
                         "first_missing": [g for g in lost][:10]}
        if topic != CLOCK_TOPIC:       # a /clock gap is what defines a producer stall: it is judged, but it explains no lost message
            attributed += missing_in + missing_out
        if inside and used and judged and reason:
            reasons.append(f"OFFLINE_TOPIC_LOSS:{topic} gaps={len(inside)} missing={missing_in}")

    # existing sequence rules: their verdict stands, their facts join the document
    for topic in controller_state_topics_for(rig):
        item = report["continuity"].get(topic, {})
        gaps = _grid_gaps(states.get(topic, []), STATE_PERIOD_NS)
        neck = topic.startswith("/neck_")
        record(topic, rule="2 ms stamp grid; a gap judged where a label instant needs the frame (OFFLINE_SOURCE_GAP)",
               used=not neck, messages=len(states.get(topic, [])), gaps=gaps, period=STATE_PERIOD_NS, judged=False, reason=False)
        topics[topic]["missing_in_window"] = 0 if neck else item.get("gap_count", 0)
        topics[topic]["diagnostic_in_window"] = item.get("diagnostic_gaps", 0) if not neck else item.get("gaps_in_window", 0)
    for topic in rig.info_topics:
        gaps = _grid_gaps(cameras.get(topic, []), CAMERA_PERIOD_NS)
        record(topic, rule=f"100 ms stamp grid, {' equals '.join(rig.camera_names)} (OFFLINE_CAMERA_GRID)", used=True,
               messages=len(cameras.get(topic, [])), gaps=gaps, period=CAMERA_PERIOD_NS,
               window_lo=reset_ns if reset_ns is not None else lo, window_hi=stop_ns if stop_ns is not None else end,
               judged=False, reason=False)
        topics[topic]["missing_in_window"] = report.get("camera_grid", {}).get("off_grid_count", 0) if topic == rig.info_topics[0] else 0

    # new rules (C2)
    record(CLOCK_TOPIC, rule="2 ms stamp grid", used=True, messages=len(clock_stamps), gaps=clock_gaps, period=CLOCK_PERIOD_NS)
    record(JOINT_STATES_TOPIC, rule="10 ms header-stamp grid", used=True, messages=len(joint_stamps),
           gaps=_grid_gaps(joint_stamps, JOINT_STATES_PERIOD_NS), period=JOINT_STATES_PERIOD_NS)
    # the colour images: the camera_info of the same frame is the witness that the frame existed
    rows_lo = reset_ns if reset_ns is not None else lo
    rows_hi = stop_ns if stop_ns is not None else end
    for image_topic, info_topic in rig.color_topics.items():
        have = set(color_stamps.get(image_topic, []))
        absent = [s for s in cameras.get(info_topic, []) if s not in have]
        inside = [s for s in absent if rows_lo <= s <= rows_hi]
        topics[image_topic] = {"rule": "every camera_info stamp has its image", "used": True,
                               "messages": len(color_stamps.get(image_topic, [])), "gaps": len(absent), "stalls": 0,
                               "missing_in_window": len(inside), "missing_outside_window": len(absent) - len(inside),
                               "diagnostic_in_window": 0, "first_missing": absent[:10]}
        attributed += len(absent)
        detected[image_topic] = len(absent)
        if inside:
            reasons.append(f"OFFLINE_TOPIC_LOSS:{image_topic} missing={len(inside)}")
    # scene_state is published in the same call as the world record (same snapshot): every world record of the window has its
    # scene_state of the same step and stamp
    have_scene = {(step, stamp) for e, step, stamp in scene_states if e == epoch}
    needed = [(w[5], w[1]) for w in worlds if w[2] == epoch and lo <= w[1] <= end]
    absent = [pair for pair in needed if pair not in have_scene]
    # outside the window only from the first scene_state on (the world topic starts publishing before the scene state does)
    first_scene = min((stamp for e, _step, stamp in scene_states if e == epoch), default=None)
    absent_outside = [] if first_scene is None else [
        (w[5], w[1]) for w in worlds if w[2] == epoch and w[1] >= first_scene and not lo <= w[1] <= end
        and (w[5], w[1]) not in have_scene]
    topics[SCENE_STATE_TOPIC] = {"rule": "every world record of the window has a scene_state of the same step and stamp",
                                 "used": True, "messages": len(scene_states), "gaps": len(absent), "stalls": 0,
                                 "missing_in_window": len(absent), "missing_outside_window": len(absent_outside),
                                 "diagnostic_in_window": 0, "first_missing": [list(pair) for pair in absent[:10]]}
    attributed += len(absent) + len(absent_outside)
    detected[SCENE_STATE_TOPIC] = len(absent) + len(absent_outside)
    if absent:
        reasons.append(f"OFFLINE_TOPIC_LOSS:{SCENE_STATE_TOPIC} missing={len(absent)}")
    # sequenced topics: facts and the numbers that count toward the attribution
    for topic in (CHUNK_TOPIC, WORLD_TOPIC):
        item = report["continuity"].get(topic, {})
        topics[topic] = {"rule": "chunk sequence and step / publisher sequence", "used": True,
                         "messages": counts.get(topic, 0), "gaps": item.get("gap_count", 0), "stalls": 0,
                         "missing_in_window": item.get("gap_count", 0), "missing_outside_window": 0, "diagnostic_in_window": 0,
                         "first_missing": item.get("first_gaps", [])}
        attributed += item.get("gap_count", 0)
    # the outside-window sequence gaps of chunks and world records are not scanned: both are cheap, so count them
    inside_chunks = [c for c in chunks if c[5] == epoch]
    out_chunks = sum(1 for a, b in zip(inside_chunks, inside_chunks[1:]) if b[0] != a[0] + 1 and not (a[4] >= begin and b[3] <= end))
    topics[CHUNK_TOPIC]["missing_outside_window"] = out_chunks
    attributed += out_chunks
    seq = [w[0] for w in worlds if w[2] == epoch]
    out_worlds = sum(1 for a, b in zip(seq, seq[1:]) if b != a + 1) - topics[WORLD_TOPIC]["missing_in_window"]
    topics[WORLD_TOPIC]["missing_outside_window"] = max(out_worlds, 0)
    attributed += max(out_worlds, 0)
    detected[WORLD_TOPIC] = _sequence_missing(seq)
    ordered_chunks = [c[0] for c in inside_chunks]
    detected[CHUNK_TOPIC] = _sequence_missing(ordered_chunks)
    # topics the episode does not use: counted and recorded only
    expected_steps = sum(c[2] - c[1] + 1 for c in chunks)
    topics[CONTACTS_TOPIC] = {"rule": "none (a lost sample is a lost sample of a chunk, which is covered)", "used": False,
                              "messages": counts.get(CONTACTS_TOPIC, 0), "gaps": 0, "stalls": 0, "missing_in_window": 0,
                              "missing_outside_window": 0, "diagnostic_in_window": 0, "first_missing": [],
                              "chunk_steps": expected_steps}
    for topic in ("/so101/simulation/joints", "/so101/simulation/physics_hazard"):
        topics[topic] = {"rule": "none (not used by the episode)", "used": False, "messages": counts.get(topic, 0), "gaps": 0,
                         "stalls": 0, "missing_in_window": 0, "missing_outside_window": 0, "diagnostic_in_window": 0,
                         "first_missing": []}
    reads = counts.get("/so101/raw/planning_scene_reads", 0)
    total_short = 0 if scene_reads_expected is None else max(scene_reads_expected - reads, 0)
    short = total_short
    before_window = 0
    rule = "bag count equals the sidecar's own count of reads"
    if (scene_read_sidecar_stamps is not None and scene_reads_expected is not None
            and len(scene_read_sidecar_stamps) == scene_reads_expected and len(scene_read_stamps) == reads
            and all(type(t) is int for t in (*scene_read_sidecar_stamps, *scene_read_stamps))):
        # The reads made before the window starts (the bag recorder may not have matched its subscription yet; sim time 0)
        # are recorded in the sidecar but no row uses them, so only the reads inside [begin, end] are counted, on both sides
        wanted = sum(1 for t in scene_read_sidecar_stamps if lo <= t <= end)
        found = sum(1 for t in scene_read_stamps if lo <= t <= end)
        short = max(wanted - found, 0)
        before_window = max(total_short - short, 0)
        rule = "bag count equals the sidecar's own count of reads inside the window (earlier reads are recorded, not counted)"
    topics["/so101/raw/planning_scene_reads"] = {
        "rule": rule, "used": True, "messages": reads, "gaps": short, "stalls": 0,
        "missing_in_window": short, "missing_outside_window": before_window, "diagnostic_in_window": 0, "first_missing": [],
        "sidecar_count": scene_reads_expected}
    attributed += short
    detected["/so101/raw/planning_scene_reads"] = short
    if short:
        reasons.append(f"OFFLINE_TOPIC_LOSS:/so101/raw/planning_scene_reads missing={short}")
    topics[EVENTS_TOPIC] = {"rule": "seq 1..N", "used": True, "messages": counts.get(EVENTS_TOPIC, 0), "gaps": 0, "stalls": 0,
                            "missing_in_window": 0, "missing_outside_window": 0, "diagnostic_in_window": 0, "first_missing": []}
    detected[EVENTS_TOPIC] = max(max(event_sequence, default=0) - len(set(event_sequence)), 0) if all(
        type(s) is int for s in event_sequence) else 0
    detected[CONTACTS_TOPIC] = 0 if contact_missing is None else contact_missing
    if transport_lost_by_topic and event_sequence == list(range(1, len(event_sequence) + 1)):
        # the Teacher's terminal event carries no published count, so a loss on this topic after a gap-free sequence that reaches
        # the terminal can only be a message after it (a loss before it would be a gap in seq): outside the episode
        detected[EVENTS_TOPIC] += transport_lost_by_topic.get(EVENTS_TOPIC, 0)
        topics[EVENTS_TOPIC]["rule"] = "seq 1..N up to the terminal event (a loss after it is outside the episode)"
    if transport_lost_by_topic is not None and transport_lost is not None:
        return _with_breakdown(topics, detected, reasons, lo=lo, end=end, rows_lo=rows_lo, rows_hi=rows_hi,
                               transport_lost=transport_lost, by_topic=transport_lost_by_topic, rig=rig,
                               events=transport_lost_events, wall_begin_ns=next((wall for sim, wall in clock_marks if sim >= lo), None))
    # ---- the recorder's aggregate
    unattributed = None if transport_lost is None else max(transport_lost - attributed, 0)
    aggregate = {"reported": transport_lost, "attributed": attributed, "unattributed": 0 if unattributed is None else unattributed}
    if transport_lost is None:
        reasons.append("OFFLINE_TRANSPORT_LOSS_UNKNOWN")
    elif unattributed:
        reasons.append(f"OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: {unattributed} of {transport_lost}")
    return {"window": {"begin_sim_ns": lo, "end_sim_ns": end, "rows_begin_sim_ns": rows_lo, "rows_end_sim_ns": rows_hi},
            "transport_lost": aggregate, "topics": topics}



#: A loss line is stamped when rosbag2 reports the loss, which can lag the message by delivery latency: a line must precede the window's
#: first instant by this much before the loss is called provably outside.
LOSS_LOG_MARGIN_NS = 100_000_000


def _split_events(count, events, wall_begin_ns):
    """(outside, inside): how many of a topic's `count` reported losses were logged before the window began, and how many were not.

    `events` are the topic's log lines with their cumulative totals. A line is outside only when its time is an int that precedes the
    wall time of the window's first `/clock` message by the margin; anything else (no times, no clock, a time that is not a number, a
    total the lines do not account for) is inside: unmappable fails closed."""
    outside = previous = 0
    mapped = wall_begin_ns is not None
    for event in sorted(events, key=lambda e: (e["log_time_ns"] if type(e.get("log_time_ns")) is int else 1 << 62, e.get("total", 0))):
        total, when = event.get("total"), event.get("log_time_ns")
        if type(total) is not int or total <= previous:
            continue
        increment, previous = total - previous, total
        if mapped and type(when) is int and when < wall_begin_ns - LOSS_LOG_MARGIN_NS:
            outside += increment
    if previous > count:             # the lines claim more than the recorder's own figure: nothing can be trusted
        return 0, count
    return outside, count - outside


def _with_breakdown(topics, detected, reasons, *, lo, end, rows_lo, rows_hi, transport_lost, by_topic, events=None,
                    wall_begin_ns=None, rig=DEFAULT_RIG) -> dict:
    """The per-topic reconciliation (C5, rule `topic_loss`), used when the recorder reported its losses topic by topic.

    * the per-topic numbers must sum to the total and name only recorded topics (else OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED);
    * a loss whose log line precedes the window is provably outside it (a line is never earlier than the loss) and is only recorded;
      every other loss on a topic the episode uses must be matched by a gap that topic's own rule shows missing in the bag, each gap
      once, else OFFLINE_TOPIC_LOSS:<topic> reported_in_window=n detected=m (a gap inside the window is itself judged by the rule);
    * on a topic the episode does not use the loss is recorded only.
    """
    from .raw_recorder import topics_for

    TOPICS = topics_for(rig)
    for topic in TOPICS:           # a recorded topic the scan has no rule for is recorded only
        topics.setdefault(topic, {"rule": "none (not used by the episode)", "used": False, "messages": 0, "gaps": 0, "stalls": 0,
                                  "missing_in_window": 0, "missing_outside_window": 0, "diagnostic_in_window": 0,
                                  "first_missing": []})
    topics[CONTACTS_TOPIC]["rule"] = ("none for the episode (a lost sample is a lost sample of a chunk, which is covered); "
                                      "the step span is read when the recorder reports a loss on it")
    named = sum(by_topic.values())
    unknown = sum(count for topic, count in by_topic.items() if topic not in TOPICS)
    unattributed = abs(transport_lost - named) + unknown
    if unattributed:
        reasons.append(f"OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: {unattributed} of {transport_lost} "
                       f"(per-topic sum {named}, unnamed topics {sorted(t for t in by_topic if t not in TOPICS)})")
    by_event: dict = {}
    for event in events or ():
        if type(event) is dict and type(event.get("topic")) is str:
            by_event.setdefault(event["topic"], []).append(event)
    attributed = 0
    for topic, count in sorted(by_topic.items()):
        if topic not in topics:
            continue
        item = topics[topic]
        outside, inside = _split_events(count, by_event.get(topic, ()), wall_begin_ns)
        item["reported"], item["detected"] = count, detected.get(topic, 0)
        item["reported_outside_window"], item["reported_in_window"] = outside, inside
        if not item["used"]:
            attributed += count
        elif inside > item["detected"]:
            unattributed += inside - item["detected"]
            attributed += outside + item["detected"]
            reasons.append(f"OFFLINE_TOPIC_LOSS:{topic} reported_in_window={inside} detected={item['detected']}")
        else:
            attributed += count
    aggregate = {"reported": transport_lost, "attributed": attributed, "unattributed": unattributed,
                 "by_topic": dict(sorted(by_topic.items()))}
    return {"window": {"begin_sim_ns": lo, "end_sim_ns": end, "rows_begin_sim_ns": rows_lo, "rows_end_sim_ns": rows_hi,
                       "begin_wall_ns": wall_begin_ns},
            "transport_lost": aggregate, "topics": topics}
