"""The offline sources' ROS wiring (Phase A4a, cleanup step 2): shared logic is reused, nothing here can command, the gaps are named.

These tests use a fake node (no DDS): they prove the composition, the reuse of the existing data-side code, parity of the
controller reference record with the command broker's, and that the sources subscribe only.
"""

import copy
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.offline import sources as module
from so101_demo.act.teacher_event_stream import StreamIdentity, TeacherEventStream, decode_event
from so101_demo.ros.recorder_data_side import RecorderDataSide
from test_act_collection_boundaries import original_reset


class RecordingNode:
    """A node that records every kind of entity created on it: the Recorder may only create subscriptions."""

    def __init__(self):
        self.calls = []
        self.clock_ns = 5_000_000_000

    def create_subscription(self, message_type, topic, callback, qos, *args, **kwargs):
        self.calls.append(("subscription", topic))
        return SimpleNamespace(topic=topic, callback=callback)

    def destroy_subscription(self, subscription):
        self.calls.append(("destroy_subscription", subscription.topic))

    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=self.clock_ns))

    def deliver_due(self):
        return 0

    def take_callback_errors(self):
        return []

    def __getattr__(self, name):
        if name.startswith(("create_", "call_")) or "client" in name or "action" in name or "publisher" in name:
            def forbidden(*args, **kwargs):
                self.calls.append(("FORBIDDEN", name))
                raise AssertionError(f"the Recorder used {name}")
            return forbidden
        raise AttributeError(name)


# ---- reuse -----------------------------------------------------------------------------------------------------

def test_the_sources_own_a_recorder_data_side_and_the_teacher_execution_holds_none_of_its_code():
    """REPLACED_BY (A4c): the borrowed-from-the-execution parity test. The functions now live in `RecorderDataSide`; the
    Recorder no longer imports the Teacher's execution module at all."""
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    sources, _, _, _ = _prepared()
    assert type(sources.host) is RecorderDataSide
    moved = [name for name in vars(RecorderDataSide) if name.startswith("_data_") or name in (
        "_consume_teacher_event", "_capture_native_initial_step", "_finish_native_collection",
        "original_collection_worlds", "_drain_world_sources", "_step_data_initial_boundary")]
    assert moved and [name for name in moved if hasattr(RosDynamicMujocoExecution, name)] == []


def test_the_data_side_carries_no_teacher_control_or_planning_function():
    forbidden = ("_motion", "_command_gripper", "_attach", "_detach_or_sync", "_open_supported_gripper", "_call",
                 "_set_touch_collision", "_plan_candidate_set", "_sync_collection_world",
                 "_scene_transaction", "_perform_state", "perform", "finish", "_collection_port")
    assert [name for name in forbidden if hasattr(RecorderDataSide, name)] == []


def test_the_offline_sources_provide_every_method_the_engine_calls():
    for name in ("prepare", "pump", "try_start", "collect", "on_teacher_event", "tail_ready", "end_time_s", "physics_steps",
                 "final_issues", "source_counts", "start_gate_summary", "close"):
        assert callable(getattr(module.OfflineRosSources, name)), name


# ---- controller reference parity with the command broker -----------------------------------------------------------

def _frames(kind, stamps):
    return [{"sim_stamp_ns": stamp, "received_monotonic_ns": stamp + 5, "joint_names": ("a", "b"),
             "positions": (0.1 * index, 0.2), "velocities": (0.0, 0.0), "observer_sequence": index + 1,
             "original_message": {"header": {"stamp": {"sec": 0, "nanosec": stamp}}, "kind": kind}}
            for index, stamp in enumerate(stamps)]


@pytest.mark.parametrize("fault,code", [("none_published", "COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE"),
                                        ("two_published", "COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE"),
                                        ("epoch", "REFERENCE_HISTORY_EPOCH_INVALID")])
def test_a_missing_ambiguous_or_foreign_reference_is_refused_never_replaced_by_a_nearby_value(fault, code):
    histories = {"arm": _frames("arm", [1_000_000_000, 1_200_000_000] if fault == "none_published" else
                                [1_000_000_000, 1_100_000_000]),
                 "gripper": _frames("gripper", [1_000_000_000, 1_100_000_000])}
    identities = {"arm": ("session-1", 2), "gripper": ("session-1", 3 if fault == "epoch" else 2)}
    if fault == "two_published":
        histories["arm"] = _frames("arm", [1_100_000_000, 1_100_000_000])
    with pytest.raises(RuntimeError, match=code):
        module.build_collection_reference(1.1, lambda kind: (identities[kind], histories[kind]))


def test_the_reference_port_subscribes_to_the_three_controller_states_and_creates_nothing_else():
    node = RecordingNode()
    port = module.ControllerReferencePort(node, session_id="session-1", reset_epoch=2)
    topics = [topic for kind, topic in node.calls if kind == "subscription"]
    assert topics == ["/arm_controller/controller_state", "/gripper_controller/controller_state",
                      "/neck_controller/controller_state"]
    assert not [call for call in node.calls if call[0] == "FORBIDDEN"]
    port.close()


def test_the_reference_port_turns_real_controller_messages_into_the_accepted_reference_record():
    from control_msgs.msg import JointTrajectoryControllerState

    node = RecordingNode()
    clock = [100.0]
    port = module.ControllerReferencePort(node, session_id="session-1", reset_epoch=2, monotonic=lambda: clock[0])
    node.clock_ns = 6_000_000_000   # the simulation clock reaches the frames' stamps
    def publish(kind, names, stamp_ns, positions):
        message = JointTrajectoryControllerState()
        message.header.stamp.sec, message.header.stamp.nanosec = divmod(stamp_ns, 1_000_000_000)
        message.joint_names = list(names)
        message.reference.positions = list(positions)
        message.reference.velocities = [0.0] * len(positions)
        port.observer.accept(kind, message, received_monotonic_s=clock[0])

    from so101_demo.act.joints import ARM_JOINTS
    publish("arm", ARM_JOINTS[:5], 6_000_000_000, [0.1, 0.2, 0.3, 0.4, 0.5])
    publish("gripper", ARM_JOINTS[5:], 6_000_000_000, [0.6])
    record = port.read(6.0)
    assert record["accepted"] is True and record["source"] == "CONTROLLER_REFERENCE"
    assert record["positions"] == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    with pytest.raises(RuntimeError, match="COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE"):
        port.read(6.5)
    node.clock_ns += 5_000_000_000   # by stamp the publications became stale (age is from the stamp): no value is invented
    with pytest.raises(RuntimeError, match="REFERENCE_HISTORY_UNAVAILABLE"):
        port.read(6.0)


# ---- preparation and the named gap --------------------------------------------------------------------------------

def _options():
    return SimpleNamespace(session_id="session-1", expected_reset_epoch=2)


def _episode(boundaries=None, *, started=True):
    audit = SimpleNamespace(
        inputs={"execution_snapshot": {"path": "execution"}}, identity=None,
        append_collection_boundary=lambda stage, value: boundaries.append((stage, copy.deepcopy(value))),
        append_teacher_event=lambda event: boundaries.append(("event", event["type"])),
        append_teacher_event_summary=lambda summary: boundaries.append(("event_summary", summary["accepted"])),
        append_reference_continuity=lambda report: boundaries.append(("reference_continuity", report["reset_epoch"])))
    from dataclasses import asdict

    from so101_demo.parallel_batch.contracts import LeaseIdentity
    lease = LeaseIdentity(batch_id="batch-1", coordinator_epoch=1, worker_id="w00", worker_generation=1,
                          point_id="point-1", attempt_id="attempt-1", lease_generation=1,
                          lease_issued_monotonic_s=1.0, lease_deadline_monotonic_s=time.monotonic() + 600.)
    identity = dict(session_id="session-1", attempt_id="attempt-1", reset_epoch=2, release_epoch=0,
                    scene_id="default", seed=0, mode="preselected_target_diagnostic", lease=asdict(lease))
    audit.identity = identity
    capture = SimpleNamespace(started=started, audit=audit, on_event=lambda event: boundaries.append(("event", event)),
                              _first_command_s=None, on_acquisition=lambda frame, pixels: None,
                              window={"collection_end_s": 9.0})
    return SimpleNamespace(identity=identity, capture=capture, frozen_inputs_manifest="/frozen/inputs-manifest.json",
                           execution_inputs={"scene_path": "scene.xml"}, bind_physical_provider=lambda provider: None,
                           start=lambda start_s: None)


def _binding():
    return SimpleNamespace(observer=SimpleNamespace(original_frames_with_receipts=lambda: [1, 2]),
                           model=object(), model_identity={"model_sha256": "a" * 64},
                           physics_adapter=SimpleNamespace(
                               receipt_diagnostics=lambda: {"chunk_count": 7}, original_durable_steps=lambda **kw: [],
                               source_at=lambda at, **kw: None),
                           observation_adapter=SimpleNamespace(), hazards=[], drain_sources=lambda: 0,
                           close=lambda: None)


def _engine(latched):
    return SimpleNamespace(on_event_text=lambda text: None, latch=lambda reason, **facts: latched.append(reason),
                           invalid=latched, policy={"finish_budget_s": 1.0}, end_obs=None,
                           event_summary=lambda: {"schema": "SO101_TEACHER_EVENT_V2", "accepted": 0, "last_seq": 0,
                                                  "types": {}})


def _prepared(provider=None, *, boundaries=None, bind=None):
    node, latched = RecordingNode(), []
    sources = module.OfflineRosSources(
        node, _episode(boundaries if boundaries is not None else []), _options(),
        bind=bind or (lambda *args, **kwargs: _binding()),
        world_observer_factory=lambda node, session: SimpleNamespace(callback_count=11),
        reference_port_factory=lambda node, **kwargs: SimpleNamespace(read=lambda when: {}, close=lambda: None),
        physical_provider=provider)
    engine = _engine(latched)
    sources.prepare(engine)
    return sources, node, engine, latched


def test_prepare_subscribes_to_the_event_stream_first_and_only_subscribes():
    sources, node, _, _ = _prepared()
    assert node.calls[0] == ("subscription", "/so101/teacher/events"), "seq 1 must not be missed"
    assert ("subscription", "/joint_states") in node.calls
    assert not [call for call in node.calls if call[0] == "FORBIDDEN"]


def test_the_prepared_host_provides_everything_the_data_side_functions_use_on_self():
    """Every `self.<name>` the data-side functions read or call must exist on the host (state they only assign, or read
    through a getattr default, is theirs to create)."""
    import ast
    import inspect
    import textwrap

    sources, _, _, _ = _prepared()
    host = sources.host
    used, assigned = set(), set()
    for name, function in vars(RecorderDataSide).items():
        function = getattr(function, "__func__", function)
        if not inspect.isfunction(function) or name.startswith("__"):
            continue
        for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(function)))):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
                (assigned if isinstance(node.ctx, ast.Store) else used).add(node.attr)
    missing = sorted(name for name in used - assigned if not hasattr(host, name))
    assert missing == [], f"the data-side code uses {missing} on a host that does not provide them"


def test_preparation_binds_the_real_physical_audit_provider_and_no_placeholder_refusal_remains():
    from so101_demo.act.live_physical_audit import LivePhysicalAuditProvider
    bound = []
    node, latched = RecordingNode(), []
    episode = _episode([])
    episode.bind_physical_provider = bound.append
    sources = module.OfflineRosSources(
        node, episode, _options(), bind=lambda *a, **k: _binding(),
        world_observer_factory=lambda node, session: SimpleNamespace(callback_count=1),
        reference_port_factory=lambda node, **kwargs: SimpleNamespace(read=lambda when: {}, close=lambda: None))
    sources.prepare(_engine(latched))
    assert latched == [] and len(bound) == 1 and type(bound[0]) is LivePhysicalAuditProvider
    assert "RECORDER_PLANNING_SCENE_SOURCE_UNAVAILABLE" not in open(module.__file__).read()


def test_a_supplied_physical_provider_is_bound_before_the_capture_starts_and_nothing_is_latched():
    bound = []
    provider = object()
    node, latched = RecordingNode(), []
    episode = _episode([])
    episode.bind_physical_provider = bound.append
    sources = module.OfflineRosSources(
        node, episode, _options(), bind=lambda *a, **k: _binding(),
        world_observer_factory=lambda node, session: SimpleNamespace(callback_count=1),
        reference_port_factory=lambda node, **kwargs: SimpleNamespace(read=lambda when: {}, close=lambda: None),
        physical_provider=provider)
    sources.prepare(_engine(latched))
    assert bound == [provider] and latched == []


def test_the_binder_is_given_the_frozen_model_and_the_recorders_own_episode():
    calls = []

    def bind(node, **kwargs):
        calls.append(kwargs)
        return _binding()

    _prepared(bind=bind)
    assert calls[0]["session_id"] == "session-1" and calls[0]["reset_epoch"] == 2
    assert str(calls[0]["model_path"]) == "/frozen/execution/scene.xml"
    assert calls[0]["expected_model"] == {"scene_path": "scene.xml"} and calls[0]["max_age_s"] == .1
    assert calls[0]["episode_recorder"] is not None


# ---- events reach the existing retention code ---------------------------------------------------------------------

def _stream_event(kind, payload, *, seq=1):
    published = []
    stream = TeacherEventStream(StreamIdentity("session-1", 2, "attempt-1"), clock_ns=lambda: 1,
                                publish=published.append, start=False)
    for _ in range(seq - 1):
        stream.offer("phase_finish", {})
    stream.offer(kind, payload)
    stream.pump()
    return decode_event(published[-1])


def _reset_payload(**changes):
    reset = original_reset(dict(session_id="session-1", attempt_id="attempt-1", reset_epoch=2))
    value = dict(session_id="session-1", reset_epoch=2, simulation_time_s=0.0, simulation_step=0, publisher_sequence=1,
                 received_monotonic_ns=reset["source_clock"]["end_monotonic_ns"])
    value.update(changes)
    return reset, value


def _epoch_boundary(**changes):
    now = time.monotonic_ns()
    value = dict(kind="ACT_VERIFIED_RESET_BOUNDARY", schema_version=3, session_id="session-1", attempt_id="attempt-1",
                 reset_epoch=2, source_clock=dict(sim_time_ns=0, begin_monotonic_ns=now - 2_000_000, end_monotonic_ns=now - 1_000_000),
                 physical_source=dict(session_id="session-1", reset_epoch=2, simulation_step=0, publisher_sequence=0,
                                      simulation_time_s=0.0, received_wall_s=(now - 500_000) / 1e9))
    value.update(changes)
    return value


def test_the_verified_reset_is_retained_once_at_the_capture_start_and_the_reset_event_is_checked_against_it():
    boundaries = []
    sources, _, engine, _ = _prepared(boundaries=boundaries)
    sources.host.retain_epoch_boundary(sources.episode, _epoch_boundary())
    _reset, payload = _reset_payload()
    sources.on_teacher_event(engine, _stream_event("reset_complete", payload))
    sources.on_teacher_event(engine, _stream_event("reset_complete", payload, seq=2))
    assert [item[0] for item in boundaries].count("verified_reset") == 1
    assert [item[1] for item in boundaries if item[0] == "verified_reset"][0]["schema_version"] == 3


def test_a_reset_event_older_than_the_recorders_own_evidence_is_refused_and_surfaces_as_an_exception():
    boundaries = []
    sources, _, engine, _ = _prepared(boundaries=boundaries)
    sources.host.retain_epoch_boundary(sources.episode, _epoch_boundary(
        physical_source=dict(session_id="session-1", reset_epoch=2, simulation_step=0, publisher_sequence=50,
                             simulation_time_s=0.0, received_wall_s=(time.monotonic_ns() - 500_000) / 1e9)))
    _reset, payload = _reset_payload()
    with pytest.raises(PermissionError, match="TEACHER_RESET_EVENT_INCONSISTENT"):
        sources.on_teacher_event(engine, _stream_event("reset_complete", dict(payload, publisher_sequence=2)))


def _stop_proof(clock_ns):
    clock = dict(sim_time_ns=3_000_000_000, begin_monotonic_ns=clock_ns, end_monotonic_ns=clock_ns)
    return dict(kind="TEACHER_NORMAL_STOP", trajectory_result="SUCCEEDED", stop_confirmed_wall_s=(clock_ns - 10) / 1e9,
                source_clock=clock, simulation_step=1500, publisher_sequence=900, sim_stamp_s=3.0,
                received_wall_s=clock_ns / 1e9, joint_positions={n: 0.0 for n in "123456"},
                joint_velocities={n: 0.0 for n in "123456"})


def test_the_normal_stop_event_is_the_v2_stop_boundary_the_final_boundary_will_use():
    sources, _, engine, _ = _prepared()
    proof = _stop_proof(time.monotonic_ns() - 1_000_000)
    sources.on_teacher_event(engine, _stream_event("normal_stop", {"proof": proof}))
    stop = sources.host._retained_normal_stop()
    assert stop["schema_version"] == 2 and stop["source_clock"] == proof["source_clock"]
    assert stop["epoch"]["publisher_sequence"] == 900


def test_a_second_normal_stop_is_still_refused_and_a_marked_non_boundary_stop_is_audited_only():
    """CP-3440: the Teacher publishes a `normal_stop` for every confirmed stop (three on the pilot bag). The Recorder takes exactly one
    boundary; a repeat stays an error. The offline processor, which sees the whole bag, marks the stops that are not the final one."""
    sources, _, engine, latched = _prepared()
    host = sources.host
    host._data_skip_normal_stop_boundary = True
    sources.on_teacher_event(engine, _stream_event("normal_stop", {"proof": _stop_proof(time.monotonic_ns() - 3_000_000)}, seq=1))
    assert host._retained_normal_stop() is None and host._data_skip_normal_stop_boundary is False
    sources.on_teacher_event(engine, _stream_event("normal_stop", {"proof": _stop_proof(time.monotonic_ns() - 2_000_000)}, seq=2))
    assert host._retained_normal_stop() is not None
    with pytest.raises(RuntimeError, match="TEACHER_NORMAL_STOP_REPEATED"):
        sources.on_teacher_event(engine, _stream_event("normal_stop", {"proof": _stop_proof(time.monotonic_ns() - 1_000_000)}, seq=3))


def test_the_normal_stop_ends_the_capture_when_it_arrives_not_at_the_tail(monkeypatch):
    """Applied at the tail only, the capture kept labelling rows through the Teacher's end observation (0.5 s after the final stop on
    the pilot bag) and then revoked them: CAPTURE_LABEL_REVOKED."""
    from so101_demo.act import episode_assembly

    sources, _, engine, _ = _prepared()
    host, episode = sources.host, sources.episode
    monkeypatch.setattr(episode_assembly, "PointEpisode", type(episode))
    seen = []
    episode.capture.on_normal_motion_end = lambda clock: seen.append(clock["sim_time_ns"])
    host._collection_initial_capture = {"stage": "initial_capture"}
    host._data_first_command_clock = dict(sim_time_ns=1_000_000_000, begin_monotonic_ns=1, end_monotonic_ns=2)
    sources.on_teacher_event(engine, _stream_event("normal_stop", {"proof": _stop_proof(time.monotonic_ns() - 1_000_000)}, seq=1))
    assert seen == [3_000_000_000] and host._collection_normal_end_clock["sim_time_ns"] == 3_000_000_000


def test_the_reference_check_reads_every_raw_sample_of_the_episode_not_only_the_adapters_last_8_seconds(tmp_path):
    """The engine checks the Teacher's start and end references against the episode's raw physics samples before it seals. The
    adapter keeps 4096 samples (8.2 s): on a 100 s episode the start reference's step was long gone and the check failed
    TEACHER_REFERENCE_PHYSICS_STEP_ABSENT. The audit holds every chunk."""
    import json

    sources, _, engine, _ = _prepared()
    audit = tmp_path / "audit"
    audit.mkdir()
    rows = [{"kind": "physics_chunk_v1", "payload": {"raw_chunk": {"chunk": {"samples": [{"physics_step": step} for step in chunk]}}}}
            for chunk in ((1, 2), (3, 4))]
    rows.append({"kind": "world_source_v1", "payload": {}})
    (audit / "events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    sources.episode.capture.recorder = SimpleNamespace(root=tmp_path)
    sources.binding.physics_adapter.original_durable_steps = lambda **kw: [{"physics_step": 4}]    # the adapter remembers the tail
    assert [sample["physics_step"] for sample in sources.physics_steps(engine)] == [1, 2, 3, 4]


def test_no_world_source_is_retained_after_the_final_capture():
    """A world record drained after the final capture has no raw sample yet when the episode is sealed (the chunk follows the record by
    up to 100 ms): the seal then failed WORLD_SOURCE_NATIVE_REQUIRED. The episode's sources end with the final boundary."""
    from so101_demo.ros.recorder_data_side import RecorderDataSide

    host = RecorderDataSide.__new__(RecorderDataSide)
    host.episode_recorder = object()
    host._world_record_cursor = 5
    host._collection_final_capture = {"source_clock": {}, "world_source": {}}
    host.observer = SimpleNamespace(original_records_after=lambda cursor: pytest.fail("the world observer must not be read"))
    assert host._drain_world_sources() == 0


def test_events_without_a_retention_obligation_are_retained_as_events_and_touch_no_boundary():
    boundaries = []
    sources, _, engine, _ = _prepared(boundaries=boundaries)
    for seq, (kind, payload) in enumerate((("teacher_start_observation", {"observation": {}}),
                                           ("phase_finish", {"state": "X", "status": "SUCCEEDED"}),
                                           ("teacher_end_observation", {"observation": None}),
                                           ("terminal", {})), start=1):
        sources.on_teacher_event(engine, _stream_event(kind, payload, seq=seq))
    assert [item for item in boundaries if item[0] != "event"] == []
    assert [item[1] for item in boundaries] == ["teacher_start_observation", "phase_finish",
                                                "teacher_end_observation", "terminal"]


# ---- source health ------------------------------------------------------------------------------------------------

def test_source_counts_name_every_required_source_including_the_world_and_scene_state():
    sources, _, _, _ = _prepared()
    sources._counts.update(head=3, wrist=3)
    counts = sources.source_counts(None)
    assert counts == {"head": 3, "wrist": 3, "joint_states": 0, "physics": 7, "scene_state": 2, "world": 11}


def test_acquisitions_are_counted_as_the_capture_takes_them():
    sources, _, _, _ = _prepared()
    capture = sources.episode.capture
    capture.on_acquisition(SimpleNamespace(camera="head"), None)
    capture.on_acquisition(SimpleNamespace(camera="wrist"), None)
    capture.on_acquisition(SimpleNamespace(camera="head"), None)
    assert (sources._counts["head"], sources._counts["wrist"]) == (2, 1)


def test_a_hazard_reported_by_a_data_adapter_becomes_an_invalid_verdict_never_an_exception():
    sources, _, engine, latched = _prepared()
    del latched[:]
    sources.binding.hazards.append({"reason": "DATA_SOURCE_CALLBACK_FAILED: /so101/simulation/scene_state: x"})
    sources.pump(engine)
    assert latched == ["DATA_SOURCE_CALLBACK_FAILED: /so101/simulation/scene_state: x"]
    sources.pump(engine)
    assert len(latched) == 1, "a hazard is reported once"


def test_close_releases_every_subscription_it_created():
    sources, node, _, _ = _prepared()
    sources.close()
    destroyed = [call[1] for call in node.calls if call[0] == "destroy_subscription"]
    assert "/so101/teacher/events" in destroyed and "/joint_states" in destroyed


# ---- the shared final-boundary code, run on the Recorder's host over stream events -------------------------------

from test_act_scene_association import frozen_scene  # noqa: E402,F401  (pytest fixture)


def test_the_final_boundary_runs_on_the_recorder_host_from_stream_events_with_the_shared_code(frozen_scene, monkeypatch):
    import threading

    from so101_demo.act.episode_assembly import PointEpisode
    from test_act_endpoint_raw_window import WindowAdapter
    from test_act_native_endpoint_boundaries import final_boundary

    world_sources, boundary, final_clock, raw = final_boundary(frozen_scene)
    owned = dict(session_id="alignment-session", attempt_id="a", reset_epoch=1,
                 lease={"lease_deadline_monotonic_s": final_clock["end_monotonic_ns"] / 1e9 + 120.})
    boundaries, ends = [], []
    episode = PointEpisode.__new__(PointEpisode)
    episode.identity = owned
    episode.capture = SimpleNamespace(
        started=True, ingress_lock=threading.RLock(), check_health=lambda: None,
        on_normal_motion_end=lambda clock: ends.append(copy.deepcopy(clock)),
        audit=SimpleNamespace(identity=owned, inputs={"execution_snapshot": {"path": "execution"}},
                              append_collection_boundary=lambda stage, value: boundaries.append(stage),
                              append_teacher_event_summary=lambda summary: boundaries.append(("event_summary", 0)),
                              append_reference_continuity=lambda report: boundaries.append(("reference_continuity", 1))),
        _frames={role: [SimpleNamespace(session_id="alignment-session", reset_epoch=1,
                                        stamp_s=final_clock["sim_time_ns"] / 1e9)] for role in ("head", "wrist")},
        window={"collection_end_s": 99.}, on_acquisition=lambda frame, pixels: None)
    episode.frozen_inputs_manifest = "/frozen/inputs-manifest.json"
    episode.execution_inputs = {"scene_path": "scene.xml"}
    episode.bind_physical_provider = lambda provider: None
    current = [dict(sim_time_ns=boundary["source_clock"]["sim_time_ns"],
                    begin_monotonic_ns=boundary["source_clock"]["begin_monotonic_ns"] - 1,
                    end_monotonic_ns=boundary["source_clock"]["begin_monotonic_ns"] - 1)]
    monkeypatch.setattr("so101_demo.ros.recorder_data_side.time.monotonic_ns",
                        lambda: current[0]["end_monotonic_ns"])
    node = RecordingNode()
    node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=current[0]["sim_time_ns"]))
    latched = []
    engine = _engine(latched)
    engine.policy = {"finish_budget_s": 60.}
    sources = module.OfflineRosSources(
        node, episode, _options(),
        bind=lambda *args, **kwargs: SimpleNamespace(
            observer=SimpleNamespace(original_frames_with_receipts=lambda: []), physics_adapter=WindowAdapter(raw),
            observation_adapter=SimpleNamespace(), hazards=[], drain_sources=lambda: 0, close=lambda: None),
        world_observer_factory=lambda node, session: SimpleNamespace(callback_count=1),
        reference_port_factory=lambda node, **kwargs: SimpleNamespace(read=lambda when: {}, close=lambda: None,
                                                                      continuity_report=lambda: {"reset_epoch": 1}),
        physical_provider=object())
    sources.prepare(engine)
    host = sources.host
    host.original_collection_worlds = lambda: copy.deepcopy(world_sources)
    host._collection_initial_capture = {"explicit_fixture": "retained elsewhere"}
    host._progress = lambda: pytest.fail("a selected endpoint was retried")
    host._drain_collection = lambda: None
    # The Teacher's own events, as they arrive from the stream: the first goal-sending phase_begin, then the stop.
    first = copy.deepcopy(current[0])
    first["end_monotonic_ns"] = first["begin_monotonic_ns"] = first["begin_monotonic_ns"] - 5
    host._data_first_command_clock = first
    host._data_normal_stop = copy.deepcopy(boundary)

    def stop():
        current[0] = copy.deepcopy(final_clock)
        return copy.deepcopy(boundary)
    host._retained_normal_stop = stop
    assert sources.tail_ready(engine) is True
    assert [item for item in boundaries if isinstance(item, str)] == ["normal_stop", "final_capture"]
    assert ("event_summary", 0) in boundaries and ("reference_continuity", 1) in boundaries
    assert ends == [boundary["source_clock"]] and host._collection_normal_end_clock == boundary["source_clock"]
    assert sources.end_time_s(engine) == boundary["source_clock"]["sim_time_ns"] / 1e9
    assert latched == []
