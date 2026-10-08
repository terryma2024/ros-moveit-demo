"""Actual dynamic orchestration must bind and retire its source clock observer.

The in-child `_progress` data-failure tests that used to sit here (writer failure, reference refusal, raw physics failure,
scene observer hazard) are REPLACED_BY the Recorder engine and sources tests: `test_act_episode_recorder` (a source that
raises, a missing source), `test_act_episode_recorder_sources` (a data adapter hazard becomes an invalid verdict)."""

from types import SimpleNamespace

import pytest

from so101_demo.ros.dynamic_runtime import run_dynamic_execute
from test_dynamic_scene_sync import _runtime, _options, _observation, RecordingTaskScenePort


@pytest.mark.parametrize("fail_runner", [False, True])
def test_execution_gets_bound_source_before_actions_and_owned_subscription_closes(tmp_path, fail_runner):
    events = []
    runtime = _runtime(events, observations=(
        _observation(simulator_x=-.03, moveit_x=.02),
        _observation(simulator_x=-.03), _observation(simulator_x=-.03)), scene=RecordingTaskScenePort(),
                       faults=frozenset({"runner.run"}) if fail_runner else frozenset())
    observer = object()
    binding = SimpleNamespace(observer=observer, close=lambda: events.append("scene_source.close"))
    captured = []
    def bind(*args, **kwargs):
        captured.append(kwargs)
        events.append("scene_source.bind")
        return binding
    runtime.bind_scene_source = bind
    build = runtime.build_actions
    def actions(execution, targets):
        assert execution._scene_source_observer is observer
        assert events.index("scene_source.bind") < events.index("execution.create")
        return build(execution, targets)
    runtime.build_actions = actions
    assert run_dynamic_execute(_options(tmp_path), _runtime=runtime) == int(fail_runner)
    assert captured[0]["session_id"] == "task-5" and captured[0]["reset_epoch"] == 3
    # The Teacher's own scene join runs on the Teacher state age (0.5 s); the data side keeps the ACT 100 ms.
    assert captured[0]["scene_max_age_s"] == 0.5 and captured[0]["max_age_s"] == .1
    assert events.count("scene_source.close") == 1
    assert events.index("scene_source.close") < events.index("node.close")


def test_a_data_callback_that_raises_latches_a_bounded_hazard_and_never_unwinds_the_control_spin():
    from pathlib import Path
    from so101_demo.ros.data_source_binding import _DATA_HAZARD_LIMIT, bind_data_sources
    callbacks = {}
    class Node:
        def create_subscription(self, message_type, topic, callback, qos):
            callbacks[topic] = callback
            return topic
        def destroy_subscription(self, value):
            pass
    path = Path(__file__).parents[1] / "assets/mujoco/act/scene.xml"
    binding = bind_data_sources(Node(), session_id="source-session", reset_epoch=2, model_path=path)
    try:
        for _ in range(_DATA_HAZARD_LIMIT + 4):
            callbacks["/so101/simulation/scene_state"](object())  # a message the adapter cannot even read
        assert len(binding.hazards) == _DATA_HAZARD_LIMIT
        assert all(item["reason"].startswith("DATA_SOURCE_CALLBACK_FAILED: /so101/simulation/scene_state")
                   and len(item["reason"]) <= 300 for item in binding.hazards)
    finally:
        binding.close()


def test_isolated_data_node_catches_callback_failures_and_forwards_everything_else():
    from so101_demo.ros.data_source_binding import IsolatedDataNode
    registered = []
    class Node:
        context = "real-context"
        def create_subscription(self, message_type, topic, callback, qos, **kwargs):
            registered.append((message_type, topic, callback, qos, kwargs))
            return "subscription"
        def destroy_subscription(self, value):
            registered.append(("destroyed", value))
    reasons = []
    view = IsolatedDataNode(Node(), reasons.append)
    assert view.context == "real-context"
    assert view.create_subscription("T", "/topic", lambda message: message * 2, "qos") == "subscription"
    assert registered[0][2]("ab") == "abab"
    def failing(message):
        raise RuntimeError("DATA_CALLBACK_BUG")
    view.create_subscription("T", "/other", failing, "qos")
    assert registered[1][2](object()) is None
    view.create_subscription("T", "/keyword", callback=failing, qos="qos")
    assert registered[2][2](object()) is None
    assert reasons == ["DATA_SOURCE_CALLBACK_FAILED: /other: DATA_CALLBACK_BUG",
                       "DATA_SOURCE_CALLBACK_FAILED: /keyword: DATA_CALLBACK_BUG"]
    view.destroy_subscription("subscription")
    assert registered[-1] == ("destroyed", "subscription")


def _assert_no_control_requests(requests):
    forbidden = {"revoke", "cancel", "pause", "reset", "fence", "stop_teacher"}
    assert not [operation for operation, *_ in requests if operation in forbidden]


def test_a_failure_to_build_the_recording_sources_leaves_the_teachers_scene_observer_and_only_a_data_hazard(tmp_path):
    from pathlib import Path
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    from so101_demo.ros.data_source_binding import bind_data_sources
    created, destroyed = [], []
    class Node:
        def create_subscription(self, cls, topic, callback, qos):
            if topic == "/so101/simulation/physics_step_chunks":
                raise RuntimeError("ACTUAL_CONSTRUCTION_REFUSED")
            created.append(topic)
            return topic
        def destroy_subscription(self, topic):
            destroyed.append(topic)
    episode = SimpleNamespace(synchronizer=RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1),
        capture=SimpleNamespace(audit=SimpleNamespace(append_raw_physics=lambda record: None,
            inputs={"execution_snapshot": {"physics_chunks": {"max_samples": 50, "max_contacts": 128}}})))
    path = Path(__file__).parents[1] / "assets/mujoco/act/scene.xml"
    binding = bind_data_sources(Node(), session_id="live-source", reset_epoch=2, model_path=path,
                                         episode_recorder=episode)
    assert binding.physics_adapter is None and binding.observation_adapter is None
    assert "/so101/simulation/scene_state" in created, "the Teacher's own scene-state subscription is kept"
    assert [item["reason"].split(":")[0] for item in binding.hazards] == ["DATA_SOURCE_CONSTRUCTION_FAILED"]
    assert "ACTUAL_CONSTRUCTION_REFUSED" in binding.hazards[0]["reason"]
    assert destroyed == []
    binding.close()
    assert destroyed == ["/so101/simulation/scene_state"]


def test_real_factory_owns_one_raw_chunk_subscription_and_drains_before_close(tmp_path):
    import time
    import mujoco
    from pathlib import Path
    from so101_demo.ros.data_source_binding import bind_data_sources
    from test_act_raw_physics_chunks import _chunk
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    callbacks, destroyed, retained = {}, [], []
    class Node:
        def create_subscription(self, cls, topic, callback, qos):
            assert topic not in callbacks
            callbacks[topic] = callback
            return topic

        def destroy_subscription(self, subscription):
            destroyed.append(subscription)

    episode = SimpleNamespace(synchronizer=RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1),
        capture=SimpleNamespace(audit=SimpleNamespace(
        append_raw_physics=lambda record: retained.append(record),
        inputs={"execution_snapshot": {"physics_chunks": {"max_samples": 50, "max_contacts": 128}}})))
    path = Path(__file__).parents[1] / "assets/mujoco/act/scene.xml"
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    binding = bind_data_sources(Node(), session_id="live-source", reset_epoch=2,
        model_path=path, episode_recorder=episode)
    before = time.monotonic_ns()
    message = _chunk(receipt=before)
    for step in message.samples:
        step.model_qpos = data.qpos.tolist()
        step.model_qvel = data.qvel.tolist()
    callbacks["/so101/simulation/physics_step_chunks"](message)
    assert binding.physics_adapter.hazard is None
    assert retained == []
    assert binding.drain_sources() == 1
    assert before <= retained[0]["received_monotonic_ns"] <= time.monotonic_ns()
    assert len(retained[0]["chunk"]["samples"][0]["model_qpos"]) == model.nq
    binding.close()
    binding.close()
    assert set(callbacks) == {"/so101/simulation/physics_step_chunks", "/so101/simulation/scene_state",
                              "/head_camera/color", "/wrist_camera/color", "/joint_states"}
    assert sorted(destroyed) == sorted(callbacks)


def test_the_teacher_control_files_hold_no_control_request_from_the_data_side():
    """Structural guard: no data path can name a revoke, cancel or pause request, or reach the control connection."""
    import pathlib
    import so101_demo.ros.dynamic_mujoco_execution as execution
    import so101_demo.ros.dynamic_runtime as runtime
    for module in (execution, runtime):
        text = pathlib.Path(module.__file__).read_text()
        for needle in ('request("revoke"', "request('revoke'", "connection_for", "drain_hazards",
                       "_abort_collection_source", "collection_source_hazard"):
            assert needle not in text, (module.__name__, needle)


@pytest.mark.parametrize("failure", ["partial_create", "first_destroy"])
def test_observation_ownership_attempts_all_known_handles_on_failure(failure):
    from so101_demo.adapters.act.ros_observation import RosObservationAdapter
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    created, destroyed = [], []
    class Node:
        def create_subscription(self, cls, topic, callback, qos):
            if failure == "partial_create" and topic == "/joint_states":
                raise RuntimeError("ACTUAL_CONSTRUCTION_REFUSED")
            created.append(topic)
            return topic
        def destroy_subscription(self, topic):
            destroyed.append(topic)
            if topic == "/head_camera/color":
                raise RuntimeError("ACTUAL_DESTROY_REFUSED")
    sync = RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1)
    if failure == "partial_create":
        with pytest.raises(RuntimeError, match="ACTUAL_CONSTRUCTION_REFUSED") as caught:
            RosObservationAdapter(Node(), sync)
        assert any("ACTUAL_DESTROY_REFUSED" in note for note in caught.value.__notes__)
    else:
        adapter = RosObservationAdapter(Node(), sync)
        with pytest.raises(RuntimeError, match="ACTUAL_DESTROY_REFUSED"):
            adapter.close()
        adapter.close()
    assert destroyed == created


def test_runtime_binding_decodes_actual_rgb_and_measured_joint_messages(tmp_path):
    import threading
    import time
    from pathlib import Path
    from sensor_msgs.msg import Image, JointState
    from so101_demo.act.joints import ACT_JOINTS
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    from so101_demo.ros.data_source_binding import bind_data_sources
    callbacks, acquired, destroyed = {}, [], []
    class Node:
        def create_subscription(self, cls, topic, callback, qos):
            if topic == "/so101/simulation/scene_state":
                assert qos.depth == 256, "actual collection still uses latest-only source coordinates"
            callbacks[topic] = callback
            return topic
        def destroy_subscription(self, topic):
            destroyed.append(topic)
        def get_clock(self):
            return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=1_010_000_000))
    capture = SimpleNamespace(ingress_lock=threading.RLock(), active=False, started=False,
        on_acquisition=lambda frame, pixels: acquired.append((frame, pixels.copy())),
        audit=SimpleNamespace(append_raw_physics=lambda raw: None,
            inputs={"execution_snapshot": {"physics_chunks": {"max_samples": 50, "max_contacts": 128}}}))
    episode = SimpleNamespace(capture=capture,
        synchronizer=RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1))
    binding = bind_data_sources(Node(), session_id="session", reset_epoch=2,
        model_path=Path(__file__).parents[1] / "assets/mujoco/act/scene.xml", episode_recorder=episode)
    try:
        capture.active = True
        capture.started = True
        image = Image(width=640, height=480, step=1920, encoding="rgb8",
                      data=bytes([37]) * (640 * 480 * 3))
        image.header.stamp.sec = 1
        before = time.monotonic_ns()
        callbacks["/head_camera/color"](image)
        callbacks["/wrist_camera/color"](image)
        joints = JointState(name=list(ACT_JOINTS), position=[.1, .2, .3, .4, .5, .6, .7])
        joints.header.stamp.sec = 1
        callbacks["/joint_states"](joints)
        assert binding.observation_adapter.hazard is None
        observation, source = episode.synchronizer.sample_with_audit("session", "attempt", 1.)
        assert observation["state"][:6] == pytest.approx(joints.position[:6])
        assert len(acquired) == 2 and acquired[0][1].shape == (480, 640, 3)
        assert (acquired[0][1] == 37).all()
        assert all(frame.session_id == "session" and frame.reset_epoch == 2
                   and before <= frame.received_monotonic_ns <= time.monotonic_ns()
                   for frame, pixels in acquired)
        assert source["source_stamps"] == dict.fromkeys(("head", "wrist", "arm", "neck"), 1.)
    finally:
        binding.close()
    assert sorted(destroyed) == sorted(callbacks)


def test_binding_scene_observer_age_is_separate_from_the_act_data_age():
    from pathlib import Path
    from so101_demo.ros.data_source_binding import bind_data_sources

    class Node:
        def create_subscription(self, *args, **kwargs):
            return "owned"

        def destroy_subscription(self, value):
            pass

    path = Path(__file__).parents[1] / "assets/mujoco/act/scene.xml"
    default = bind_data_sources(Node(), session_id="s", reset_epoch=2, model_path=path)
    teacher = bind_data_sources(Node(), session_id="s", reset_epoch=2, model_path=path,
                                         scene_max_age_s=0.5)
    try:
        assert default.observer.max_age == 0.1
        assert teacher.observer.max_age == 0.5
    finally:
        default.close()
        teacher.close()
