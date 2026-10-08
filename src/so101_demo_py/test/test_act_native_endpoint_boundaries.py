"""Original-source FIRST logic, controlled records only; not live endpoint proof."""

import copy
import pytest

from test_act_native_world_history import source_record
from test_act_scene_association import frozen_scene


def _world_sources(frozen_scene):
    """The world sources and the clock of one stop (no broker message: the V2 boundary names none)."""
    first, raw = source_record(frozen_scene)
    world = first["physics"]
    stamp_ns = round(world["simulation_time_s"] * 1e9)
    confirmed = first["scene_received_monotonic_ns"] + 1
    boundary = {
        "epoch": {"session_id": world["simulation_session_id"], "reset_epoch": world["reset_epoch"],
            "simulation_step": world["simulation_step"], "publisher_sequence": world["publisher_sequence"],
            "simulation_time_s": world["simulation_time_s"], "received_wall_s": first["received_monotonic_ns"] / 1e9},
        "source_clock": {"sim_time_ns": stamp_ns, "begin_monotonic_ns": confirmed, "end_monotonic_ns": confirmed},
        "confirmed_monotonic_ns": confirmed}
    later = copy.deepcopy(first)
    later["physics"].update(publisher_sequence=world["publisher_sequence"] + 1,
        simulation_step=world["simulation_step"] + 1, simulation_time_s=world["simulation_time_s"] + .002)
    later["native_reference"]["simulation_step"] = later["physics"]["simulation_step"]
    later["scene_state"].update(simulation_step=later["physics"]["simulation_step"],
        simulation_time_s=later["physics"]["simulation_time_s"],
        clock_interval_begin_monotonic_ns=confirmed + 4, clock_interval_end_monotonic_ns=confirmed + 5)
    later["received_monotonic_ns"], later["scene_received_monotonic_ns"] = confirmed + 6, confirmed + 7
    sample = copy.deepcopy(raw[0])
    sample.update(physics_step=later["physics"]["simulation_step"], simulation_time_s=later["physics"]["simulation_time_s"],
        clock_interval_begin_monotonic_ns=confirmed + 1, clock_interval_end_monotonic_ns=confirmed + 2)
    raw.append(sample)
    capture = {"sim_time_ns": round(later["physics"]["simulation_time_s"] * 1e9),
        "begin_monotonic_ns": confirmed + 8, "end_monotonic_ns": confirmed + 9}
    return [first, later], boundary, capture, raw


def final_boundary(frozen_scene):
    """The V2 normal-stop boundary (successful result, joint stop proof) with the same world sources and raw steps."""
    sources, old, capture, raw = _world_sources(frozen_scene)
    clock = old["source_clock"]
    stop = {"kind": "ACT_NORMAL_STOP_BOUNDARY", "schema_version": 2, "epoch": old["epoch"], "source_clock": clock,
            "confirmed_monotonic_ns": old["confirmed_monotonic_ns"],
            "stop_confirmed_wall_s": (clock["begin_monotonic_ns"] - 1000) / 1e9, "trajectory_result": "SUCCEEDED",
            "joint_positions": {name: 0.0 for name in "123456"},
            "joint_velocities": {name: 0.0 for name in "123456"}}
    return sources, stop, capture, raw


def test_online_initial_candidate_needs_no_fabricated_future_dispatch(frozen_scene):
    from so101_demo.act import native_endpoints
    sources,reset,capture,raw=final_boundary(frozen_scene)
    select=getattr(native_endpoints,'first_world_after_capture_start',None)
    assert callable(select), 'initial capture requires a fabricated future dispatch clock'
    identity={'session_id':'alignment-session','reset_epoch':1}
    kwargs=dict(identity=identity,reset_clock=reset['source_clock'],capture_start_clock=reset['source_clock'],
        capture_clock=capture,raw_steps=raw)
    assert select(sources,**kwargs)==sources[1]
    with pytest.raises(ValueError):select(sources[1:],**kwargs)


@pytest.mark.parametrize('stage',['initial_capture','final_capture'])
@pytest.mark.parametrize('fault',[None,'scope','clock','future','extra'])
def test_original_endpoint_capture_has_closed_clock_and_source(stage,fault,frozen_scene):
    from so101_demo.act.collection_boundaries import validate_collection_boundary
    sources,_,capture,_=final_boundary(frozen_scene)
    value=dict(source_clock=capture,world_source=sources[1])
    document=dict(kind='ACT_COLLECTION_BOUNDARY',schema_version=2,stage=stage,value=value)
    identity=dict(session_id='alignment-session',reset_epoch=1)
    if fault=='scope':value['world_source']['physics']['reset_epoch']+=1
    if fault=='clock':value['source_clock']['end_monotonic_ns']=True
    if fault=='future':value['source_clock']['sim_time_ns']-=1
    if fault=='extra':value['success']=True
    if fault is None:assert validate_collection_boundary(document,identity=identity)==document
    else:
        with pytest.raises(ValueError):validate_collection_boundary(document,identity=identity)


@pytest.mark.parametrize('fault',[None,'unretained','changed'])
def test_endpoint_boundary_requires_same_previously_retained_world_original(fault,frozen_scene):
    import hashlib
    from so101_demo.act.collection_boundaries import claim_collection_boundary
    from so101_demo.act.scene_association import canonical
    sources,_,clock,_=final_boundary(frozen_scene)
    source=sources[1]
    known={source['physics']['publisher_sequence']:hashlib.sha256(canonical(source)).hexdigest()}
    event=dict(sim_time_s=clock['sim_time_ns']/1e9,monotonic_ns=clock['end_monotonic_ns'],
        payload={'collection_boundary':dict(kind='ACT_COLLECTION_BOUNDARY',schema_version=2,
            stage='initial_capture',value=dict(source_clock=clock,world_source=source))})
    if fault=='unretained':known={}
    if fault=='changed':source['physics']['object_state']['position_world'][0]+=.01
    kwargs=dict(identity=dict(session_id='alignment-session',reset_epoch=1),seen=set(),world_hashes=known)
    if fault is None:assert claim_collection_boundary(event,**kwargs)['value']['world_source']==source
    else:
        with pytest.raises(ValueError,match='COLLECTION_ENDPOINT_ORIGINAL_REQUIRED'):claim_collection_boundary(event,**kwargs)


@pytest.mark.parametrize("change", [None, "late_owner_epoch", "missing_predecessor", "gap", "prestop_generation",
    "foreign_world", "wrong_bound_step", "boolean_clock", "future_source", "stale_capture", "epoch_time_mismatch",
    "missing_native", "native_scope", "native_pre_stop", "native_pose", "equal_stamp_later", "equal_stamp_not_later", "moving_arm", "result_not_success"])
def test_first_final_source_uses_original_stop_mapping_and_complete_publisher_prefix(frozen_scene, change):
    from so101_demo.act.native_endpoints import first_world_after_stop
    sources, boundary, capture, raw = final_boundary(frozen_scene)
    identity = {"session_id": "alignment-session", "reset_epoch": 1}
    if change == "late_owner_epoch":
        # A separate later RPC observation is deliberately not an input to FIRST.
        unused_later_epoch = dict(boundary["epoch"], simulation_step=999)
        assert unused_later_epoch["simulation_step"] > sources[-1]["physics"]["simulation_step"]
    elif change == "missing_predecessor":
        sources = sources[1:]
    elif change == "gap":
        sources[-1]["physics"]["publisher_sequence"] += 1
    elif change == "prestop_generation":
        sources[-1]["scene_state"]["clock_interval_begin_monotonic_ns"] = boundary["confirmed_monotonic_ns"] - 1
    elif change == "foreign_world":
        boundary["epoch"]["session_id"] = "foreign"
    elif change == "wrong_bound_step":
        boundary["epoch"]["simulation_step"] += 1
    elif change == "boolean_clock":
        boundary["source_clock"]["sim_time_ns"] = True
    elif change == "future_source":
        capture["sim_time_ns"] -= 1
    elif change == "stale_capture":
        capture["sim_time_ns"] += 100000001
    elif change == "epoch_time_mismatch":
        boundary["epoch"]["simulation_time_s"] += .01
    elif change == "missing_native":
        raw.pop()
    elif change == "native_scope":
        raw[-1]["reset_epoch"] += 1
    elif change == "native_pre_stop":
        raw[-1].update(clock_interval_begin_monotonic_ns=boundary["confirmed_monotonic_ns"] - 2,
            clock_interval_end_monotonic_ns=boundary["confirmed_monotonic_ns"] - 1)
    elif change == "native_pose":
        raw[-1]["object_pose_world"]["position"]["x"] += .01
    elif change == "equal_stamp_later":
        boundary["source_clock"]["sim_time_ns"] = capture["sim_time_ns"]
    elif change == "equal_stamp_not_later":
        boundary["source_clock"]["sim_time_ns"] = capture["sim_time_ns"]
        raw[-1].update(clock_interval_begin_monotonic_ns=boundary["confirmed_monotonic_ns"] - 2,
            clock_interval_end_monotonic_ns=boundary["confirmed_monotonic_ns"] - 1)
    elif change == "moving_arm":
        boundary["joint_velocities"]["2"] = .01
    elif change == "result_not_success":
        boundary["trajectory_result"] = "TIMED_OUT"
    if change in (None, "late_owner_epoch", "equal_stamp_later"):
        assert first_world_after_stop(sources, boundary, identity=identity, capture_clock=capture, raw_steps=raw) == sources[-1]
    else:
        with pytest.raises(ValueError):
            first_world_after_stop(sources, boundary, identity=identity, capture_clock=capture, raw_steps=raw)


def test_first_final_source_does_not_select_later_better_quality(frozen_scene):
    from so101_demo.act.native_endpoints import first_world_after_stop
    sources, boundary, capture, raw = final_boundary(frozen_scene)
    later = copy.deepcopy(sources[-1])
    later["physics"].update(publisher_sequence=later["physics"]["publisher_sequence"] + 1,
        simulation_step=later["physics"]["simulation_step"] + 1,
        simulation_time_s=later["physics"]["simulation_time_s"] + .002)
    later["physics"]["object_state"]["position_world"][0] += .01
    later["native_reference"]["simulation_step"] = later["physics"]["simulation_step"]
    later["scene_state"].update(simulation_step=later["physics"]["simulation_step"],
        simulation_time_s=later["physics"]["simulation_time_s"])
    sample = copy.deepcopy(raw[-1])
    sample.update(physics_step=later["physics"]["simulation_step"], simulation_time_s=later["physics"]["simulation_time_s"])
    sample["object_pose_world"]["position"]["x"] += .01
    raw.append(sample)
    sources.append(later)
    assert first_world_after_stop(sources, boundary, identity={"session_id": "alignment-session", "reset_epoch": 1},
        capture_clock=capture, raw_steps=raw) == sources[1]


@pytest.mark.parametrize("change", [None, "equal_dispatch", "capture_before_receipt", "missing_predecessor",
    "gap", "pre_capture_native", "future_capture", "stale_capture", "missing_native", "foreign_scope",
    "wrong_native_pose", "reset_after_start", "late_capture", "later_better", "capture_after_dispatch"])
def test_initial_first_source_is_after_real_start_and_before_first_dispatch(frozen_scene, change):
    from so101_demo.act.native_endpoints import first_world_after_start
    sources, stop, capture, raw = final_boundary(frozen_scene)
    reset_clock = copy.deepcopy(stop["source_clock"])
    start_clock = copy.deepcopy(reset_clock)
    dispatch = {"sim_time_ns": capture["sim_time_ns"] + 2_000_000,
        "begin_monotonic_ns": capture["end_monotonic_ns"] + 1,
        "end_monotonic_ns": capture["end_monotonic_ns"] + 2}
    selected = copy.deepcopy(sources[1])
    if change == "equal_dispatch":
        dispatch["sim_time_ns"] = capture["sim_time_ns"]
    elif change == "capture_before_receipt":
        capture["begin_monotonic_ns"] = sources[1]["scene_received_monotonic_ns"] - 1
    elif change == "missing_predecessor":
        sources = sources[1:]
    elif change == "gap":
        sources[1]["physics"]["publisher_sequence"] += 1
    elif change == "pre_capture_native":
        raw[-1]["clock_interval_begin_monotonic_ns"] = start_clock["end_monotonic_ns"] - 1
    elif change == "future_capture":
        capture["sim_time_ns"] -= 1
    elif change == "stale_capture":
        capture["sim_time_ns"] += 100_000_001
    elif change == "missing_native":
        raw.pop()
    elif change == "foreign_scope":
        sources[-1]["physics"]["reset_epoch"] += 1
    elif change == "wrong_native_pose":
        raw[-1]["object_pose_world"]["position"]["x"] += .01
    elif change == "reset_after_start":
        reset_clock["sim_time_ns"] += 2_000_000
    elif change == "late_capture":
        capture["end_monotonic_ns"] = dispatch["end_monotonic_ns"] + 1
    elif change == "capture_after_dispatch":
        capture["sim_time_ns"] = dispatch["sim_time_ns"] + 1
    elif change == "later_better":
        later = copy.deepcopy(sources[1])
        later["physics"].update(publisher_sequence=later["physics"]["publisher_sequence"] + 1,
            simulation_step=later["physics"]["simulation_step"] + 1,
            simulation_time_s=later["physics"]["simulation_time_s"] + .002)
        later["native_reference"]["simulation_step"] += 1
        later["scene_state"].update(simulation_step=later["physics"]["simulation_step"],
            simulation_time_s=later["physics"]["simulation_time_s"])
        sample = copy.deepcopy(raw[-1])
        sample.update(physics_step=later["physics"]["simulation_step"], simulation_time_s=later["physics"]["simulation_time_s"])
        sources.append(later)
        raw.append(sample)
        dispatch["sim_time_ns"] += 2_000_000
    args = dict(identity={"session_id": "alignment-session", "reset_epoch": 1}, reset_clock=reset_clock,
                capture_start_clock=start_clock, first_dispatch_clock=dispatch, capture_clock=capture, raw_steps=raw)
    if change in (None, "later_better"):
        assert first_world_after_start(sources, **args) == selected
    else:
        with pytest.raises(ValueError):
            first_world_after_start(sources, **args)
