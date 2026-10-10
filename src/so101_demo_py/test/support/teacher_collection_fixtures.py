"""Complete TEACHER_EVENT_SCHEMA collection originals (no native dispatch, no broker stop proof). Not a test module."""

import copy

TEACHER_EVENT_SCHEMA = "SO101_TEACHER_EVENT"


def envelope(seq, type_, sim_time_ns, monotonic_ns, payload, *, identity):
    return {"schema": TEACHER_EVENT_SCHEMA, "seq": seq, "type": type_, "session_id": identity["session_id"],
            "reset_epoch": identity["reset_epoch"], "attempt_id": identity["attempt_id"],
            "sim_time_ns": sim_time_ns, "monotonic_ns": monotonic_ns, "payload": payload}


def event_row(document, *, monotonic_ns):
    return dict(kind="teacher_event", sim_time_s=document["sim_time_ns"] / 1e9, monotonic_ns=monotonic_ns,
                payload=dict(teacher_event=document))


def summary_row(accepted, last_seq, types, *, monotonic_ns, sim_time_s=None):
    return dict(kind="teacher_event_summary", sim_time_s=sim_time_s, monotonic_ns=monotonic_ns,
                payload=dict(event_summary=dict(schema=TEACHER_EVENT_SCHEMA, accepted=accepted, last_seq=last_seq, types=types)))


def collection_materials(frozen_scene):
    import mujoco
    from so101_demo.act.collection_boundaries import boundary_clock
    from so101_demo.act.joints import ACT_JOINTS
    from test_act_native_endpoint_boundaries import final_boundary

    sources, stop_v1, _, raw = final_boundary(frozen_scene)
    anchor = sources[0]
    base = anchor["scene_state"]["clock_interval_begin_monotonic_ns"]
    sources, samples = [], []
    for index in range(4):
        source, sample = copy.deepcopy(anchor), copy.deepcopy(raw[0])
        step, stamp, begin = index + 1, .002 * (index + 1), base + index * 2_000_000
        source["physics"].update(simulation_step=step, publisher_sequence=7 + index, simulation_time_s=stamp)
        source["native_reference"]["simulation_step"] = step
        source["scene_state"].update(simulation_step=step, simulation_time_s=stamp,
            clock_interval_begin_monotonic_ns=begin, clock_interval_end_monotonic_ns=begin + 10)
        source.update(received_monotonic_ns=begin + 20, scene_received_monotonic_ns=begin + 30)
        sample.update(physics_step=step, simulation_time_s=stamp,
            clock_interval_begin_monotonic_ns=begin - 20, clock_interval_end_monotonic_ns=begin - 10)
        for name in ACT_JOINTS:
            joint = mujoco.mj_name2id(frozen_scene[2], mujoco.mjtObj.mjOBJ_JOINT, name)
            address = int(frozen_scene[2].jnt_dofadr[joint])
            source["scene_state"]["qvel"][address] = sample["model_qvel"][address] = 0.
        sources.append(source)
        samples.append(sample)

    def clock(stamp, offset):
        return dict(sim_time_ns=round(stamp * 1e9), begin_monotonic_ns=base + offset, end_monotonic_ns=base + offset + 10)

    identity = dict(session_id="alignment-session", attempt_id="attempt-1", reset_epoch=1, release_epoch=0,
        lease=dict(batch_id="batch", coordinator_epoch=1, worker_id="worker", worker_generation=1, point_id="point",
            attempt_id="attempt-1", lease_generation=1, lease_issued_monotonic_s=(base - 100_000_000) / 1e9,
            lease_deadline_monotonic_s=(base + 180_000_000_000) / 1e9))
    reset_clock = dict(sim_time_ns=2_000_000, begin_monotonic_ns=base - 2_000_000, end_monotonic_ns=base - 2_000_000)
    reset = dict(kind="ACT_VERIFIED_RESET_BOUNDARY", schema_version=3, session_id="alignment-session",
        attempt_id="attempt-1", reset_epoch=1, source_clock=reset_clock,
        physical_source=dict(session_id="alignment-session", reset_epoch=1, simulation_step=1, publisher_sequence=7,
            simulation_time_s=.002, received_wall_s=(base - 2_000_000) / 1e9))
    stop_clock = clock(.006, 5_000_000)
    stop = dict(kind="ACT_NORMAL_STOP_BOUNDARY", schema_version=2,
        epoch=dict(session_id="alignment-session", reset_epoch=1, simulation_step=3, publisher_sequence=9,
            simulation_time_s=.006, received_wall_s=sources[2]["received_monotonic_ns"] / 1e9),
        source_clock=stop_clock, confirmed_monotonic_ns=stop_clock["end_monotonic_ns"],
        stop_confirmed_wall_s=(stop_clock["begin_monotonic_ns"] - 1000) / 1e9, trajectory_result="SUCCEEDED",
        joint_positions={name: 0.0 for name in "123456"}, joint_velocities={name: 0.0 for name in "123456"})
    first_clock = clock(.005, 3_000_000)
    boundaries = dict(verified_reset=reset, capture_start=clock(.002, 1_000_000),
        initial_capture=dict(source_clock=clock(.004, 2_500_000), world_source=sources[1]),
        normal_stop=stop, final_capture=dict(source_clock=clock(.008, 7_000_000), world_source=sources[3]))
    events = [dict(kind="physics_chunk_v1", payload=dict(raw_chunk=dict(schema_version=1,
        received_monotonic_ns=base + 8_000_000, chunk=dict(chunk_sequence=1, simulation_session_id="alignment-session",
            reset_epoch=1, first_physics_step=1, last_physics_step=4, first_simulation_time_s=.002,
            last_simulation_time_s=.008, failed_publish_attempts=0, handoff_monotonic_ns=0, publish_monotonic_ns=0,
            publish_deferrals_total=0, evidence_loss=False, samples=samples))))]
    events += [dict(kind="world_source_v1", payload=dict(world_source=source)) for source in sources]
    # the two alignments the QC requires of a new episode (CP-3425): the Recorder's pre-SETUP one, the Teacher's SETUP world_sync
    for operation, version, call, field, stamp in (("initial", 3, "request_ros_clock", "query", 1_000_000),
                                                    ("world_sync", 1, "response_ros_clock", "query", 3_000_000)):
        record = {"request_ros_clock": dict(sim_time_ns=stamp, begin_monotonic_ns=base, end_monotonic_ns=base),
                  "response_ros_clock": dict(sim_time_ns=stamp, begin_monotonic_ns=base, end_monotonic_ns=base)}
        events.append(dict(kind="source_alignment_v1", sim_time_s=stamp / 1e9, monotonic_ns=base + 1,
                           payload=dict(association=dict(operation=operation, schema_version=version,
                                                         query=dict(record=record)))))
    teacher = [
        # the Teacher starts after the capture is running and its initial boundary is committed (CP-3425)
        envelope(1, "reset_complete", 4_500_000, base + 2_800_000,
                 dict(session_id="alignment-session", reset_epoch=1, simulation_time_s=.002, simulation_step=1,
                      publisher_sequence=7, received_monotonic_ns=base + 2_700_000), identity=identity),
        envelope(2, "phase_begin", first_clock["sim_time_ns"], first_clock["end_monotonic_ns"],
                 dict(state="PREPARE_OPEN_GRIPPER", sim_time_ns=first_clock["sim_time_ns"],
                      monotonic_ns=first_clock["end_monotonic_ns"], goal_sent=True, goal_kind="gripper"),
                 identity=identity),
        envelope(3, "phase_finish", first_clock["sim_time_ns"] + 1_000_000, first_clock["end_monotonic_ns"] + 100_000,
                 dict(state="PREPARE_OPEN_GRIPPER", status="SUCCEEDED", code=None), identity=identity),
        envelope(4, "normal_stop", stop_clock["sim_time_ns"], stop_clock["end_monotonic_ns"],
                 dict(proof=dict(kind="TEACHER_NORMAL_STOP", trajectory_result="SUCCEEDED",
                     stop_confirmed_wall_s=stop["stop_confirmed_wall_s"], source_clock=stop_clock,
                     simulation_step=3, publisher_sequence=9, sim_stamp_s=.006, received_wall_s=stop["epoch"]["received_wall_s"],
                     joint_positions=stop["joint_positions"], joint_velocities=stop["joint_velocities"])), identity=identity),
        envelope(5, "terminal", stop_clock["sim_time_ns"] + 1_000_000, stop_clock["end_monotonic_ns"] + 500_000,
                 dict(status="DONE", teacher_execution_status="COMPLETED", teacher_task_result="PASS", failure=None),
                 identity=identity)]
    events += [event_row(document, monotonic_ns=base + 8_000_000) for document in teacher]
    events.append(summary_row(5, 5, {"reset_complete": 1, "phase_begin": 1, "phase_finish": 1, "normal_stop": 1,
                                     "terminal": 1}, monotonic_ns=base + 8_000_001))
    for stage, value in boundaries.items():
        doc = dict(kind="ACT_COLLECTION_BOUNDARY", schema_version=2, stage=stage, value=value)
        events.append(dict(kind="collection_boundary_v1", sim_time_s=boundary_clock(doc)["sim_time_ns"] / 1e9,
                           monotonic_ns=base + 8_000_000, payload=dict(collection_boundary=doc)))
    continuity = dict(schema_version=2, period_ns=2_000_000, session_id="alignment-session", reset_epoch=1,
        kinds={kind: dict(frames=500, gaps=0, steps=[]) for kind in ("arm", "gripper", "neck")})
    events.append(dict(kind="controller_reference", sim_time_s=None, monotonic_ns=base + 8_000_002,
                       payload=dict(reference_continuity=continuity)))
    window = dict(first_command_s=.005, physics_end_s=.006, collection_start_s=.002, label_cutoff_s=.004)
    return events, identity, window, boundaries, sources, samples, teacher
