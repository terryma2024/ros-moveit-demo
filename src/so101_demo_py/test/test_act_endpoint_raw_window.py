"""Endpoint capture compares world sources only inside the retained raw window (W3, D20).

The boundary code lives in `RecorderDataSide` (moved out of the Teacher's execution in A4c)."""

import ast
import copy
import pathlib
import threading
from types import SimpleNamespace

import pytest

from test_act_scene_association import frozen_scene
from test_act_native_endpoint_boundaries import final_boundary
from test_act_raw_physics_chunks import _chunk


class WindowAdapter:
    """Fake bounded raw lookup: retained_step_range plus filter-before-copy original_durable_steps."""

    def __init__(self, raw, pending=None):
        self.raw = raw
        self.pending = [] if pending is None else pending

    def received_max_step(self):
        steps = [sample['physics_step'] for sample in self.raw + self.pending]
        return max(steps) if steps else None

    def drain(self):
        self.raw.extend(self.pending)
        self.pending.clear()

    def retained_step_range(self):
        steps = [sample['physics_step'] for sample in self.raw]
        return (min(steps), max(steps)) if steps else None

    def history_summary(self):
        return {'pending': len(self.pending)}

    def original_durable_steps(self, min_physics_step=None):
        return [copy.deepcopy(sample) for sample in self.raw
                if min_physics_step is None or sample['physics_step'] >= min_physics_step]


def shifted(source, delta):
    value = copy.deepcopy(source)
    physics = value['physics']
    physics['simulation_step'] += delta
    physics['publisher_sequence'] += delta
    physics['simulation_time_s'] += .002 * delta
    value['native_reference']['simulation_step'] = physics['simulation_step']
    value['scene_state'].update(simulation_step=physics['simulation_step'],
        simulation_time_s=physics['simulation_time_s'])
    return value


def older(first, count=70):
    return [shifted(first, -k) for k in range(count, 0, -1)]


def drive_initial(runtime):
    """The data side's passes: one non-waiting step per progress call until the boundary is selected or refused."""
    for _ in range(50):
        selected = runtime._capture_native_initial_step()
        if selected is not None:
            return selected
        runtime._progress()
    raise AssertionError('the initial boundary was never selected')


def finish_data(runtime):
    import time
    return runtime._finish_native_collection(time.monotonic() + 60.)


def initial_runtime(frozen_scene, monkeypatch, sources, raw, boundary, capture):
    from so101_demo.ros.recorder_data_side import RecorderDataSide
    from so101_demo.act.episode_assembly import PointEpisode
    from so101_demo.act.collection_boundaries import validate_collection_boundary
    from so101_demo.act.scene_association import canonical
    from test_act_collection_boundaries import original_reset
    owned = dict(session_id='alignment-session', attempt_id='a', reset_epoch=1,
        lease={'lease_deadline_monotonic_s': capture['end_monotonic_ns'] / 1e9 + 120.})
    episode = PointEpisode.__new__(PointEpisode)
    episode.identity = owned
    retained = []

    def append(stage, value):
        document = dict(kind='ACT_COLLECTION_BOUNDARY', schema_version=2, stage=stage, value=value)
        validate_collection_boundary(document, identity=owned)
        retained.append(copy.deepcopy(document))
    episode.capture = SimpleNamespace(started=True, check_health=lambda: None,
        audit=SimpleNamespace(identity=owned, append_collection_boundary=append))
    reset = original_reset(owned)
    reset['source_clock'] = copy.deepcopy(boundary['source_clock'])
    reset['physical_source'].update(simulation_time_s=reset['source_clock']['sim_time_ns'] / 1e9,
        received_wall_s=reset['source_clock']['begin_monotonic_ns'] / 1e9)
    runtime = RecorderDataSide.__new__(RecorderDataSide)
    runtime._invalid_latched_callable = lambda: False
    runtime.episode_recorder = episode
    # The data side holds the retained reset original itself; no phase port, recorder binding or stash is involved.
    runtime._data_verified_reset = canonical(reset)
    runtime._collection_capture_start_clock = copy.deepcopy(boundary['source_clock'])
    runtime._node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=capture['sim_time_ns'])))
    runtime._scene_source_binding = SimpleNamespace(physics_adapter=WindowAdapter(raw))
    runtime.original_collection_worlds = lambda: copy.deepcopy(sources)
    runtime._progress = lambda: pytest.fail('a refused or selected endpoint was retried')
    monkeypatch.setattr('so101_demo.ros.recorder_data_side.time.monotonic_ns',
        lambda: capture['end_monotonic_ns'])
    return runtime, retained


def final_runtime(frozen_scene, monkeypatch, sources, raw, boundary, final_clock):
    from so101_demo.ros.recorder_data_side import RecorderDataSide
    from so101_demo.act.episode_assembly import PointEpisode
    owned = dict(session_id='alignment-session', attempt_id='a', reset_epoch=1,
        lease={'lease_deadline_monotonic_s': final_clock['end_monotonic_ns'] / 1e9 + 120.})
    boundaries = []
    episode = PointEpisode.__new__(PointEpisode)
    episode.identity = owned
    episode.capture = SimpleNamespace(started=True, ingress_lock=threading.RLock(), check_health=lambda: None,
        on_normal_motion_end=lambda clock: None,
        audit=SimpleNamespace(identity=owned,
            append_collection_boundary=lambda stage, value: boundaries.append((stage, copy.deepcopy(value)))),
        _frames={role: [SimpleNamespace(session_id='alignment-session', reset_epoch=1,
            stamp_s=final_clock['sim_time_ns'] / 1e9)] for role in ('head', 'wrist')})
    runtime = RecorderDataSide.__new__(RecorderDataSide)
    runtime._invalid_latched_callable = lambda: False
    runtime.episode_recorder = episode
    runtime._collection_initial_capture = {'explicit_fixture': 'retained elsewhere'}
    current = [dict(sim_time_ns=boundary['source_clock']['sim_time_ns'],
        begin_monotonic_ns=boundary['source_clock']['begin_monotonic_ns'] - 1,
        end_monotonic_ns=boundary['source_clock']['begin_monotonic_ns'] - 1)]
    # The first command (the goal-sending phase_begin) and the normal_stop event were consumed before the finish: the
    # data side holds the first-command clock and the V2 stop boundary, and the finish asks nobody for either.
    runtime._data_first_command_clock = copy.deepcopy(current[0])
    runtime._data_normal_stop = copy.deepcopy(boundary)
    runtime._node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=current[0]['sim_time_ns'])))
    monkeypatch.setattr('so101_demo.ros.recorder_data_side.time.monotonic_ns',
        lambda: current[0]['end_monotonic_ns'])

    def stop():
        current[0] = copy.deepcopy(final_clock)
        return copy.deepcopy(boundary)
    runtime._retained_normal_stop = stop
    runtime._scene_source_binding = SimpleNamespace(physics_adapter=WindowAdapter(raw))
    runtime.original_collection_worlds = lambda: copy.deepcopy(sources)
    runtime._progress = lambda: pytest.fail('a refused or selected endpoint was retried')
    runtime._drain_collection = lambda: None
    return runtime, boundaries


def facts_lines(capsys):
    return [line for line in capsys.readouterr().err.splitlines() if 'ENDPOINT_NATIVE_SOURCE_FACTS' in line]


def test_initial_capture_ignores_world_sources_older_than_retained_raw_window(frozen_scene, monkeypatch):
    sources, boundary, capture, raw = final_boundary(frozen_scene)
    full = initial_runtime(frozen_scene, monkeypatch, copy.deepcopy(sources), copy.deepcopy(raw), boundary, capture)[0]
    expected = drive_initial(full)['world_source']
    runtime, retained = initial_runtime(frozen_scene, monkeypatch, older(sources[0]) + sources, raw, boundary, capture)
    selected = drive_initial(runtime)
    assert selected['world_source'] == expected == sources[1]
    assert len(retained) == 1 and retained[0]['value'] == selected


def test_initial_gap_inside_window_still_refuses_and_prints_one_facts_line(frozen_scene, monkeypatch, capsys):
    sources, boundary, capture, raw = final_boundary(frozen_scene)
    tail = copy.deepcopy(raw[-1])
    tail['physics_step'] += 4
    raw.append(tail)
    gap = shifted(sources[1], 2)
    runtime, retained = initial_runtime(frozen_scene, monkeypatch, older(sources[0]) + sources + [gap], raw, boundary, capture)
    with pytest.raises(ValueError, match='ENDPOINT_NATIVE_SOURCE_INVALID'):
        drive_initial(runtime)
    assert retained == []
    lines = facts_lines(capsys)
    assert len(lines) == 1
    step = gap['physics']['simulation_step']
    assert 'site=initial' in lines[0] and 'sources_count=3' in lines[0]
    assert 'raw_count=3' in lines[0] and f'missing_steps_first10=[{step}]' in lines[0]


def test_initial_predecessor_before_window_still_refuses(frozen_scene, monkeypatch):
    sources, boundary, capture, raw = final_boundary(frozen_scene)
    runtime, retained = initial_runtime(frozen_scene, monkeypatch, older(sources[0]) + sources, raw[1:], boundary, capture)
    with pytest.raises(ValueError, match='ENDPOINT_INITIAL_PREDECESSOR_REQUIRED'):
        drive_initial(runtime)
    assert retained == []


def test_final_anchor_before_window_still_refuses(frozen_scene, monkeypatch):
    sources, boundary, final_clock, raw = final_boundary(frozen_scene)
    runtime, boundaries = final_runtime(frozen_scene, monkeypatch, sources, raw[1:], boundary, final_clock)
    # The anchor sample is outside the window, so the native-stop proof is also absent: closed refusal.
    with pytest.raises(ValueError, match='ENDPOINT_STOP_NATIVE_REQUIRED'):
        finish_data(runtime)
    assert [stage for stage, _ in boundaries] == ['normal_stop']


def test_final_gap_inside_window_still_refuses_and_prints_one_facts_line(frozen_scene, monkeypatch, capsys):
    sources, boundary, final_clock, raw = final_boundary(frozen_scene)
    tail = copy.deepcopy(raw[-1])
    tail['physics_step'] += 4
    raw.append(tail)
    gap = shifted(sources[1], 2)
    runtime, boundaries = final_runtime(frozen_scene, monkeypatch, sources + [gap], raw, boundary, final_clock)
    with pytest.raises(ValueError, match='ENDPOINT_NATIVE_SOURCE_INVALID'):
        finish_data(runtime)
    lines = facts_lines(capsys)
    assert len(lines) == 1 and 'site=final' in lines[0]


def _real_adapter(history_capacity=256, now=None):
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    retained = []
    node = SimpleNamespace(create_subscription=lambda *args: 'owned', destroy_subscription=lambda value: None)
    adapter = RosEpisodePhysicsAdapter(node, session_id='live-source', reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=lambda value: retained.append(copy.deepcopy(value))),
        clock_ns=lambda: (now or [10_000_000_000])[0], history_capacity=history_capacity)
    return adapter


def test_retained_step_range_is_none_when_empty_and_tracks_the_bounded_history():
    now = [10_000_000_000]
    adapter = _real_adapter(history_capacity=7, now=now)
    try:
        assert adapter.retained_step_range() is None
        adapter.accept_message(_chunk())
        adapter.drain()
        assert adapter.retained_step_range() == (101, 105)
        now[0] += 10_000_000
        adapter.accept_message(_chunk(sequence=8, first=106, receipt=now[0]))
        adapter.drain()
        assert adapter.retained_step_range() == (104, 110)
        adapter.hazard = 'PHYSICS_RAW_CONTINUITY_INVALID'
        with pytest.raises(ValueError, match='PHYSICS_RAW_CONTINUITY_INVALID'):
            adapter.retained_step_range()
    finally:
        adapter.hazard = None
        adapter.close()


def test_original_durable_steps_default_filter_copy_and_validation(monkeypatch):
    from so101_demo.adapters.act import ros_episode_physics as module
    adapter = _real_adapter()
    try:
        adapter.accept_message(_chunk())
        adapter.drain()
        everything = adapter.original_durable_steps()
        assert [s['physics_step'] for s in everything] == [101, 102, 103, 104, 105]
        assert [s['physics_step'] for s in adapter.original_durable_steps(min_physics_step=103)] == [103, 104, 105]
        assert adapter.original_durable_steps(min_physics_step=106) == []
        copies = []
        real = copy.deepcopy
        monkeypatch.setattr(module, 'copy', SimpleNamespace(deepcopy=lambda value: (copies.append(1), real(value))[1]))
        assert len(adapter.original_durable_steps(min_physics_step=105)) == 1
        assert len(copies) == 1
        monkeypatch.undo()
        for invalid in (True, -1, 1.5, '3'):
            with pytest.raises(ValueError, match='PHYSICS_RAW_QUERY_INVALID'):
                adapter.original_durable_steps(min_physics_step=invalid)
    finally:
        adapter.close()


def test_recording_path_constructs_the_raw_adapter_with_4096_history():
    import so101_demo.ros.data_source_binding as runtime
    tree = ast.parse(pathlib.Path(runtime.__file__).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and getattr(node.func, 'id', None) == 'RosEpisodePhysicsAdapter']
    assert len(calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
    assert isinstance(keywords['history_capacity'], ast.Constant) and keywords['history_capacity'].value == 4096


OLD_NS = 150_000_000


def _delay_clock(monkeypatch, offset_ns):
    """Make the monotonic clock read offset_ns later, as when a slow drain delays the endpoint check."""
    from so101_demo.ros import recorder_data_side as module
    base = module.time.monotonic_ns
    offset = [offset_ns]
    monkeypatch.setattr(module.time, 'monotonic_ns', lambda: base() + offset[0])
    return offset


def _split_tail(runtime, raw, pending_received):
    """Take the newest raw sample out of the durable raw: pending (received) or arriving only on progress."""
    tail = raw.pop()
    adapter = runtime._scene_source_binding.physics_adapter
    if pending_received:
        adapter.pending.append(tail)
    calls = []

    def progress():
        calls.append(1)
        adapter.drain()
        if not pending_received:
            adapter.raw.append(tail)
    runtime._progress = progress
    return calls


def expired_lines(capsys):
    return [line for line in capsys.readouterr().err.splitlines() if 'ENDPOINT_NATIVE_SOURCE_EXPIRED_FACTS' in line]


def _initial_case(frozen_scene, monkeypatch, pending_received, age):
    sources, boundary, capture, raw = final_boundary(frozen_scene)
    expected = copy.deepcopy(sources[1])
    runtime, retained = initial_runtime(frozen_scene, monkeypatch, sources, raw, boundary, capture)
    _delay_clock(monkeypatch, OLD_NS if age else 0)
    return runtime, retained, _split_tail(runtime, raw, pending_received), expected


def _final_case(frozen_scene, monkeypatch, pending_received, age):
    sources, boundary, final_clock, raw = final_boundary(frozen_scene)
    expected = copy.deepcopy(sources[1])
    runtime, boundaries = final_runtime(frozen_scene, monkeypatch, sources, raw, boundary, final_clock)
    offset = _delay_clock(monkeypatch, 0)
    stop = runtime._retained_normal_stop

    def delayed_stop():
        proof = stop()
        offset[0] = OLD_NS if age else 0
        return proof
    runtime._retained_normal_stop = delayed_stop
    return runtime, boundaries, _split_tail(runtime, raw, pending_received), expected


def test_initial_received_pending_raw_is_not_expired_by_drain_latency(frozen_scene, monkeypatch):
    runtime, retained, calls, expected = _initial_case(frozen_scene, monkeypatch, True, True)
    selected = drive_initial(runtime)
    assert selected['world_source']['physics'] == expected['physics']
    assert calls == [1] and len(retained) == 1


def test_initial_unreceived_raw_older_than_bound_still_expires_with_one_facts_line(frozen_scene, monkeypatch, capsys):
    runtime, retained, calls, expected = _initial_case(frozen_scene, monkeypatch, False, True)
    with pytest.raises(RuntimeError, match='DYNAMIC_INITIAL_NATIVE_SOURCE_EXPIRED'):
        drive_initial(runtime)
    assert calls == [] and retained == []
    lines = expired_lines(capsys)
    assert len(lines) == 1 and '"site":"initial"' in lines[0]
    assert f'"expired_steps_first10":[{expected["physics"]["simulation_step"]}]' in lines[0]


def test_initial_unreceived_raw_younger_than_bound_progresses(frozen_scene, monkeypatch):
    runtime, retained, calls, expected = _initial_case(frozen_scene, monkeypatch, False, False)
    selected = drive_initial(runtime)
    assert selected['world_source']['physics'] == expected['physics']
    assert calls == [1] and len(retained) == 1


def test_final_received_pending_raw_is_not_expired_by_drain_latency(frozen_scene, monkeypatch):
    runtime, boundaries, calls, expected = _final_case(frozen_scene, monkeypatch, True, True)
    finish_data(runtime)
    assert calls == [1]
    assert [stage for stage, _ in boundaries] == ['normal_stop', 'final_capture']
    assert boundaries[-1][1]['world_source']['physics'] == expected['physics']


def test_final_unreceived_raw_older_than_bound_still_expires_with_one_facts_line(frozen_scene, monkeypatch, capsys):
    runtime, boundaries, calls, expected = _final_case(frozen_scene, monkeypatch, False, True)
    with pytest.raises(RuntimeError, match='DYNAMIC_FINAL_NATIVE_SOURCE_EXPIRED'):
        finish_data(runtime)
    assert calls == [] and [stage for stage, _ in boundaries] == ['normal_stop']
    lines = expired_lines(capsys)
    assert len(lines) == 1 and '"site":"final"' in lines[0]


def test_final_unreceived_raw_younger_than_bound_progresses(frozen_scene, monkeypatch):
    runtime, boundaries, calls, expected = _final_case(frozen_scene, monkeypatch, False, False)
    finish_data(runtime)
    assert calls == [1]
    assert [stage for stage, _ in boundaries] == ['normal_stop', 'final_capture']


def test_received_max_step_is_none_when_empty_tracks_pending_and_raises_on_hazard():
    now = [10_000_000_000]
    adapter = _real_adapter(now=now)
    try:
        assert adapter.received_max_step() is None
        adapter.accept_message(_chunk())
        assert adapter.original_durable_steps() == []
        assert adapter.received_max_step() == 105
        adapter.drain()
        assert adapter.received_max_step() == 105
        now[0] += 10_000_000
        adapter.accept_message(_chunk(sequence=8, first=106, receipt=now[0]))
        assert adapter.received_max_step() == 110
        adapter.hazard = 'PHYSICS_RAW_CONTINUITY_INVALID'
        with pytest.raises(ValueError, match='PHYSICS_RAW_CONTINUITY_INVALID'):
            adapter.received_max_step()
    finally:
        adapter.hazard = None
        adapter.close()


FACTS_FIELDS = {'site', 'capture_sim_ns', 'capture_begin_ns', 'selected_step', 'selected_stamp_ns', 'delta_sim_ms',
    'selected_received_ns', 'selected_scene_received_ns', 'capture_start_sim_ns', 'capture_start_end_ns',
    'raw_received_max_step', 'raw_durable_max_step', 'pending_count', 'loop_iterations', 'loop_elapsed_ms'}
LATE_NS = 200_000_000


def capture_facts_lines(capsys):
    import json
    return [json.loads(line.split(' ', 1)[1]) for line in capsys.readouterr().err.splitlines()
        if line.startswith('ENDPOINT_INITIAL_CAPTURE_FACTS ')]


def test_initial_capture_refusal_prints_one_d29_facts_line_and_reraises_unchanged(frozen_scene, monkeypatch, capsys):
    sources, boundary, capture, raw = final_boundary(frozen_scene)
    late = dict(capture, sim_time_ns=capture['sim_time_ns'] + LATE_NS)
    runtime, retained = initial_runtime(frozen_scene, monkeypatch, sources, raw, boundary, late)
    with pytest.raises(ValueError) as caught:
        drive_initial(runtime)
    assert caught.value.args == ('ENDPOINT_INITIAL_CAPTURE_INVALID',)
    assert retained == []
    lines = capture_facts_lines(capsys)
    assert len(lines) == 1 and set(lines[0]) == FACTS_FIELDS and lines[0]['site'] == 'initial'
    fact = lines[0]
    selected = sources[1]['physics']
    assert fact['selected_step'] == selected['simulation_step']
    assert fact['capture_sim_ns'] == late['sim_time_ns'] and fact['capture_begin_ns'] == late['end_monotonic_ns']
    assert fact['selected_stamp_ns'] == round(selected['simulation_time_s'] * 1e9)
    assert fact['delta_sim_ms'] == (fact['capture_sim_ns'] - fact['selected_stamp_ns']) / 1e6 > 100
    assert fact['capture_start_sim_ns'] == boundary['source_clock']['sim_time_ns']
    assert fact['capture_start_end_ns'] == boundary['source_clock']['end_monotonic_ns']
    assert fact['raw_durable_max_step'] == max(sample['physics_step'] for sample in raw)
    assert fact['raw_received_max_step'] == fact['raw_durable_max_step'] and fact['pending_count'] == 0
    assert fact['loop_iterations'] == 1 and fact['loop_elapsed_ms'] == 0


def test_initial_capture_success_prints_no_d29_facts_line(frozen_scene, monkeypatch, capsys):
    sources, boundary, capture, raw = final_boundary(frozen_scene)
    runtime, retained = initial_runtime(frozen_scene, monkeypatch, sources, raw, boundary, capture)
    drive_initial(runtime)
    assert capture_facts_lines(capsys) == [] and len(retained) == 1


def test_final_capture_refusal_prints_one_d29_facts_line_and_reraises_unchanged(frozen_scene, monkeypatch, capsys):
    sources, boundary, final_clock, raw = final_boundary(frozen_scene)
    runtime, boundaries = final_runtime(frozen_scene, monkeypatch, sources, raw, boundary, final_clock)
    stop = runtime._retained_normal_stop

    def late_stop():
        proof = stop()
        runtime._node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
            now=lambda: SimpleNamespace(nanoseconds=final_clock['sim_time_ns'] + LATE_NS)))
        return proof
    runtime._retained_normal_stop = late_stop
    with pytest.raises(ValueError) as caught:
        finish_data(runtime)
    assert caught.value.args == ('ENDPOINT_CAPTURE_CLOCK_INVALID',)
    assert [stage for stage, _ in boundaries] == ['normal_stop']
    lines = capture_facts_lines(capsys)
    assert len(lines) == 1 and set(lines[0]) == FACTS_FIELDS and lines[0]['site'] == 'final'
    assert lines[0]['capture_sim_ns'] == final_clock['sim_time_ns'] + LATE_NS
    assert lines[0]['delta_sim_ms'] > 100 and lines[0]['loop_iterations'] == 1


def test_final_capture_success_prints_no_d29_facts_line(frozen_scene, monkeypatch, capsys):
    sources, boundary, final_clock, raw = final_boundary(frozen_scene)
    runtime, boundaries = final_runtime(frozen_scene, monkeypatch, sources, raw, boundary, final_clock)
    finish_data(runtime)
    assert capture_facts_lines(capsys) == [] and [stage for stage, _ in boundaries] == ['normal_stop', 'final_capture']


def _drain_adapter(adapter, monkeypatch):
    from so101_demo.adapters.act import ros_episode_physics as module
    real = copy.deepcopy
    sample_copies = []

    def spy(value):
        if isinstance(value, dict) and 'physics_step' in value:
            sample_copies.append(value['physics_step'])
        return real(value)
    monkeypatch.setattr(module, 'copy', SimpleNamespace(deepcopy=spy))
    adapter.accept_message(_chunk())
    adapter.drain()
    monkeypatch.undo()
    return sample_copies


def test_drain_makes_no_deepcopy_of_samples(monkeypatch):
    adapter = _real_adapter()
    try:
        assert _drain_adapter(adapter, monkeypatch) == []
        assert [s['physics_step'] for s in adapter.original_durable_steps()] == [101, 102, 103, 104, 105]
    finally:
        adapter.close()


def test_returned_history_samples_are_isolated_from_the_retained_history():
    adapter = _real_adapter()
    try:
        adapter.accept_message(_chunk())
        adapter.drain()
        expected = adapter.original_durable_steps()
        returned = adapter.original_durable_steps()
        for sample in returned:
            sample['physics_step'] = -1
            sample['model_qpos'].append(9.)
        assert adapter.original_durable_steps() == expected
        record = adapter.source_at(expected[-1]['simulation_time_s'], physics_step=105)
        assert record['sample'] == expected[-1]
        record['sample']['physics_step'] = -1
        record['sample']['model_qpos'].append(9.)
        assert adapter.original_durable_steps() == expected
        assert adapter.source_at(expected[-1]['simulation_time_s'], physics_step=105)['sample'] == expected[-1]
        assert adapter.retained_step_range() == (101, 105)
    finally:
        adapter.close()


def test_first_state_entry_is_marked_once_around_the_runner_first_perform(monkeypatch):
    from so101_demo.ros import dynamic_runtime
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    marks = []
    monkeypatch.setattr(dynamic_runtime, '_ACTIVE_PHASE_TIMER', SimpleNamespace(mark=marks.append))
    runtime = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    calls = []
    runtime._perform_state = lambda state, target: calls.append(state) or 'result'
    assert runtime.perform('s1', None) == 'result' and runtime.perform('s2', None) == 'result'
    assert calls == ['s1', 's2']
    assert marks == ['runner.first_state.begin', 'runner.first_state.end']


def _first_state_runtime(monkeypatch, events):
    from so101_demo.ros import dynamic_runtime
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    monkeypatch.setattr(dynamic_runtime, '_ACTIVE_PHASE_TIMER', SimpleNamespace(mark=events.append))
    runtime = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    # V2 phase events go to the stream; there is no phase port any more
    runtime._stream_emit = lambda kind, payload: events.append(kind)
    runtime._initial = object()
    runtime._document = {}
    runtime._write = lambda: None
    runtime._command_gripper = lambda *args: events.append('action')
    runtime._progress = lambda: events.append('progress')
    return runtime


def test_the_first_state_begins_motion_and_runs_no_data_step_at_all(monkeypatch):
    from so101_demo.core.domain import State, ActionStatus
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    events = []
    runtime = _first_state_runtime(monkeypatch, events)
    # The Teacher has no data side (A4c) and the Recorder never writes the planning scene (A4b): nothing is attempted
    # in the first state but the Teacher's own scene states and motion.
    runtime._apply_scene = SimpleNamespace(call_async=lambda *a: pytest.fail('the first state applied a scene'))
    runtime._get_scene = SimpleNamespace(call_async=lambda *a: pytest.fail('the first state queried the scene'))
    result = runtime.perform(State.PREPARE_OPEN_GRIPPER, None)
    assert result.status is ActionStatus.SUCCEEDED
    # a goal-sending state begins at its goal send; this state's action is stubbed, so the begin is published at the finish
    assert events == ['runner.first_state.begin', 'action', 'phase_begin', 'phase_finish', 'runner.first_state.end']
    assert not hasattr(RosDynamicMujocoExecution, '_initial_world_sync_best_effort')
    assert not hasattr(RosDynamicMujocoExecution, '_sync_collection_world')
    assert not hasattr(RosDynamicMujocoExecution, '_capture_native_initial_step')


# ---- C3b: a bounded single-sample accessor for the source alignment raw lookup ------------------------------------------------

def _tail_adapter(count=4096, first=1000):
    adapter = _real_adapter()
    adapter._history = __import__('collections').deque(maxlen=4096)
    for index in range(count):
        step = first + index
        adapter._history.append({'sample': {'physics_step': step, 'model_qpos': [float(step)] * 14,
                                            'contacts': [{'f': 1.0}] * 4}, 'received_monotonic_ns': step,
                                 'chunk_sequence': step // 50})
    return adapter


def test_c3b_first_durable_step_is_identical_to_the_old_path_on_a_4096_sample_tail():
    adapter = _tail_adapter()
    try:
        for step in (0, 1000, 1001, 3000, 5095, 5096, 99999):
            old = adapter.original_durable_steps(min_physics_step=step)[:1]
            new = adapter.first_original_durable_step(step)
            assert (old[0] if old else None) == new
        # a copy: mutating it never reaches the retained history
        sample = adapter.first_original_durable_step(2000)
        sample['model_qpos'][0] = -1.0
        assert adapter.first_original_durable_step(2000)['model_qpos'][0] == 2000.0
        # same errors
        for invalid in (True, -1, 1.5, '3', None):
            with pytest.raises(ValueError, match='PHYSICS_RAW_QUERY_INVALID'):
                adapter.first_original_durable_step(invalid)
        adapter.hazard = 'PHYSICS_RAW_SOURCE_HAZARD'
        with pytest.raises(ValueError, match='PHYSICS_RAW_SOURCE_HAZARD'):
            adapter.first_original_durable_step(2000)
        with pytest.raises(ValueError, match='PHYSICS_RAW_SOURCE_HAZARD'):
            adapter.original_durable_steps(min_physics_step=2000)
    finally:
        adapter.hazard = None
        adapter.close()


def test_c3b_first_durable_step_copies_at_most_one_sample(monkeypatch):
    from so101_demo.adapters.act import ros_episode_physics as module
    adapter = _tail_adapter()
    try:
        copies = []
        real = copy.deepcopy
        monkeypatch.setattr(module, 'copy', SimpleNamespace(deepcopy=lambda value: (copies.append(1), real(value))[1]))
        assert adapter.first_original_durable_step(1500)['physics_step'] == 1500
        assert len(copies) == 1
        assert adapter.first_original_durable_step(99999) is None and len(copies) == 1
        copies.clear()
        assert len(adapter.original_durable_steps(min_physics_step=1500)) == 3596 and len(copies) == 3596
        monkeypatch.undo()
    finally:
        adapter.close()


def test_c3b_the_alignment_raw_lookup_uses_the_bounded_accessor():
    from so101_demo.act.offline.sources import OfflineRosSources
    adapter = _tail_adapter()
    try:
        adapter.original_durable_steps = lambda *a, **k: pytest.fail('whole-tail copy')
        holder = SimpleNamespace(binding=SimpleNamespace(physics_adapter=adapter))
        assert OfflineRosSources._raw_lookup(holder, 1500)['sample']['physics_step'] == 1500
        assert OfflineRosSources._raw_lookup(holder, 99999) is None
    finally:
        adapter.close()
