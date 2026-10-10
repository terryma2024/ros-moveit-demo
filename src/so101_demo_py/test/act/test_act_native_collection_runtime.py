"""Actual default boundary methods with controlled original sources, never live proof (`RecorderDataSide`, A4c)."""

import copy
import json
import threading
from types import SimpleNamespace

import pytest

from test_act_scene_association import frozen_scene
from test_act_native_endpoint_boundaries import final_boundary


@pytest.mark.parametrize('fault',[None,'missing_predecessor','bad_first','foreign','missing_raw','expired'])
def test_actual_initial_capture_uses_original_first_and_never_waits_for_a_command(frozen_scene,monkeypatch,fault):
    from test_act_endpoint_raw_window import initial_runtime
    sources,boundary,capture,raw=final_boundary(frozen_scene)
    runtime,retained=initial_runtime(frozen_scene,monkeypatch,sources,raw,boundary,capture)
    if fault=='missing_predecessor':sources.pop(0)
    if fault=='bad_first':raw[-1]['object_pose_world']['position']['x']+=.01
    if fault=='foreign':sources[-1]['physics']['reset_epoch']+=1
    if fault=='missing_raw':raw.pop(0)
    if fault=='expired':capture['sim_time_ns']+=100_000_001
    method=getattr(runtime,'_capture_native_initial_step',None)
    assert callable(method),'default native runtime never captures actual initial FIRST'
    if fault is None:
        selected=method()
        assert selected['world_source']==sources[1]
        assert retained==[dict(kind='ACT_COLLECTION_BOUNDARY',schema_version=2,stage='initial_capture',value=selected)]
        assert method()==selected and len(retained)==1
    else:
        with pytest.raises((ValueError,RuntimeError)):method()
        assert retained==[]


def test_the_initial_boundary_is_refused_once_the_first_command_went_out_without_it(frozen_scene,monkeypatch):
    from test_act_endpoint_raw_window import initial_runtime
    sources,boundary,capture,raw=final_boundary(frozen_scene)
    runtime,retained=initial_runtime(frozen_scene,monkeypatch,sources,raw,boundary,capture)
    # The first dispatch began before the initial boundary could end: the QC boundary order can no longer hold.
    runtime._data_first_dispatch_begin_ns=capture['begin_monotonic_ns']-1
    with pytest.raises(RuntimeError,match='DYNAMIC_INITIAL_BOUNDARY_AFTER_FIRST_COMMAND'):
        runtime._capture_native_initial_step()
    assert retained==[]


def test_an_unavailable_initial_source_is_attempted_again_and_never_blocks(frozen_scene,monkeypatch):
    from test_act_endpoint_raw_window import initial_runtime
    sources,boundary,capture,raw=final_boundary(frozen_scene)
    pending=[copy.deepcopy(sample) for sample in raw]
    del raw[:]
    runtime,retained=initial_runtime(frozen_scene,monkeypatch,sources,raw,boundary,capture)
    assert runtime._capture_native_initial_step() is None and retained==[]
    raw.extend(pending)
    assert runtime._capture_native_initial_step()['world_source']==sources[1] and len(retained)==1


@pytest.mark.parametrize('fault',[None,'stop_scope','result','sequence_order','final_gap','missing_anchor','camera_scope'])
def test_actual_normal_finish_fixes_stop_then_final_first_and_original_camera_tail(frozen_scene,monkeypatch,fault):
    from test_act_endpoint_raw_window import final_runtime,finish_data
    sources,boundary,final_clock,raw=final_boundary(frozen_scene)
    runtime,boundaries=final_runtime(frozen_scene,monkeypatch,sources,raw,boundary,final_clock)
    episode=runtime.episode_recorder
    events=[];ends=[]
    audit=episode.capture.audit;append=audit.append_collection_boundary
    audit.append_collection_boundary=lambda stage,value:(events.append(stage),append(stage,value))
    episode.capture.on_normal_motion_end=lambda clock:(events.append('motion_end'),ends.append(copy.deepcopy(clock)))
    stop=runtime._retained_normal_stop
    def mutate(proof):
        if fault=='stop_scope':proof['epoch']['reset_epoch']+=1
        if fault=='result':proof['trajectory_result']='TIMED_OUT'
        return proof
    runtime._retained_normal_stop=lambda:(events.append('retained_stop'),mutate(stop()))[1]
    runtime._drain_collection=lambda:events.append('drain_original_tail')
    if fault=='sequence_order':
        # a first command later than the stop cannot precede it: the finish refuses the order
        runtime._data_first_command_clock['end_monotonic_ns']=boundary['source_clock']['begin_monotonic_ns']+1
    if fault=='final_gap':sources[-1]['physics']['publisher_sequence']+=1
    if fault=='missing_anchor':sources.pop(0)
    if fault=='camera_scope':episode.capture._frames['head'][0].reset_epoch+=1
    if fault is None:
        assert finish_data(runtime)==boundary['source_clock']
        assert ends==[boundary['source_clock']]
        assert [stage for stage,_ in boundaries]==['normal_stop','final_capture']
        assert boundaries[-1][1]['world_source']==sources[1]
        # the stop boundary was retained when the Recorder consumed the Teacher's normal_stop event, before the finish
        assert events.index('retained_stop')<events.index('normal_stop')<events.index('motion_end')<events.index('final_capture')<events.index('drain_original_tail')
        assert runtime._collection_normal_end_clock==boundary['source_clock']
    else:
        with pytest.raises((ValueError,PermissionError,RuntimeError)):finish_data(runtime)
