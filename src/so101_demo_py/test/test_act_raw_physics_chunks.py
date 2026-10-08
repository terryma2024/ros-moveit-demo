"""Original native source clocks and complete ROS physics bytes survive audit readback."""

import copy
from types import SimpleNamespace

import pytest
from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk, ContactSample


def _chunk(sequence=7, first=101, receipt=10_000_000_000):
    samples = []
    for step in range(first, first + 5):
        sample = PhysicsStepEvidence(simulation_session_id="live-source", reset_epoch=2,
            physics_step=step, simulation_time_s=step * .002,
            clock_interval_begin_monotonic_ns=receipt - 12_000_000 + (step-first)*2_000_000,
            clock_interval_end_monotonic_ns=receipt - 11_800_000 + (step-first)*2_000_000,
            model_qpos=[.1, .2], model_qvel=[.3], has_contact=True,
            maximum_normal_force_n=.4, total_normal_force_n=.4, global_max_single_contact_force_n=.4)
        sample.object_pose_world.position.x = .02
        sample.object_pose_world.position.y = -.28
        sample.object_pose_world.position.z = .165
        sample.object_pose_world.orientation.w = 1.
        sample.object_twist_world.angular.z = .01
        contact = ContactSample(body1_id=10, geom1_id=11, body1="plastic_cup", geom1="cup_bottom",
            body2_id=1, geom2_id=1, body2="table", geom2="table_collision",
            signed_distance_m=-.0001, normal_force_n=.4)
        contact.normal_world.z = 1.
        sample.other_object_contacts = [contact]
        samples.append(sample)
    return PhysicsStepEvidenceChunk(chunk_sequence=sequence, simulation_session_id="live-source",
        reset_epoch=2, first_physics_step=first, last_physics_step=first+4,
        first_simulation_time_s=samples[0].simulation_time_s,
        last_simulation_time_s=samples[-1].simulation_time_s, samples=samples)


def _api():
    from so101_demo.act.raw_physics_chunks import raw_chunk_from_ros, verify_raw_chunk
    return raw_chunk_from_ros, verify_raw_chunk


def test_full_conversion_preserves_original_ros_fields_and_owns_copy():
    convert, verify = _api()
    message = _chunk()
    record = convert(message, received_monotonic_ns=10_000_000_000)
    verify(record, session_id="live-source", reset_epoch=2, nq=2, nv=1)
    step = record["chunk"]["samples"][0]
    assert step["clock_interval_begin_monotonic_ns"] == 9_988_000_000
    assert step["object_pose_world"]["orientation"] == {"x": 0., "y": 0., "z": 0., "w": 1.}
    assert step["object_twist_world"]["angular"]["z"] == .01
    assert step["other_object_contacts"][0]["body1_id"] == 10
    assert step["other_object_contacts"][0]["geom1"] == "cup_bottom"
    assert "publisher_sequence" not in step
    message.samples[0].model_qpos[0] = 9.
    assert step["model_qpos"][0] == .1


@pytest.mark.parametrize("damage", ["missing_clock", "zero_clock", "future_clock",
    "reversed_clock", "clock_overlap", "time_gap", "step_gap", "bad_quaternion", "foreign_scope",
    "loss", "retry", "truncated", "hazard", "unknown_field", "wrong_dimension", "bad_contact"])
def test_full_reader_refuses_rehashed_semantic_damage(damage):
    convert, verify = _api()
    record = convert(_chunk(), received_monotonic_ns=10_000_000_000)
    first, second = record["chunk"]["samples"][:2]
    if damage == "missing_clock": del first["clock_interval_begin_monotonic_ns"]
    elif damage == "zero_clock": first["clock_interval_begin_monotonic_ns"] = 0
    elif damage == "future_clock": first["clock_interval_end_monotonic_ns"] = 10_000_000_001
    elif damage == "reversed_clock": first["clock_interval_end_monotonic_ns"] = 1
    elif damage == "clock_overlap": second["clock_interval_begin_monotonic_ns"] = first["clock_interval_end_monotonic_ns"]-1
    elif damage == "time_gap": second["simulation_time_s"] += .001
    elif damage == "step_gap": second["physics_step"] += 1
    elif damage == "bad_quaternion": first["object_pose_world"]["orientation"]["w"] = 0.
    elif damage == "foreign_scope": first["reset_epoch"] += 1
    elif damage == "loss": record["chunk"]["evidence_loss"] = True
    elif damage == "retry": record["chunk"]["failed_publish_attempts"] = 1
    elif damage == "truncated": first["truncated"] = True
    elif damage == "hazard": first["diagnostic_hazard_breached"] = True
    elif damage == "unknown_field": first["revision"] = 123
    elif damage == "wrong_dimension": first["model_qpos"] = [.1]
    else: first["other_object_contacts"][0]["normal_force_n"] = -1.
    with pytest.raises(ValueError):
        verify(record, session_id="live-source", reset_epoch=2, nq=2, nv=1)


_AGE_NS = 100_000_000


@pytest.mark.parametrize("receipt_offset_ns", [_AGE_NS, _AGE_NS + 1, _AGE_NS * 3, 2_000_000_000])
def test_a_late_receipt_is_admitted_whatever_its_age(receipt_offset_ns):
    """CP-3410 (user-authorized contract change): there is no per-chunk delivery-age rule any more. The old pin (exactly
    100 ms accepted, one ns more stale) is gone; lateness is telemetry, bounded by the Recorder's backlog and lag policy."""
    convert, verify = _api()
    record = convert(_chunk(), received_monotonic_ns=10_000_000_000)
    newest = record["chunk"]["samples"][-1]["clock_interval_begin_monotonic_ns"]
    record["received_monotonic_ns"] = newest + receipt_offset_ns
    assert verify(record, session_id="live-source", reset_epoch=2, nq=2, nv=1) is record


@pytest.mark.parametrize("receipt_delta_from_newest_end_ns", [-1, -3_800_000])
def test_receipt_older_than_a_sample_clock_interval_is_refused(receipt_delta_from_newest_end_ns):
    convert, verify = _api()
    record = convert(_chunk(), received_monotonic_ns=10_000_000_000)
    newest = record["chunk"]["samples"][-1]["clock_interval_end_monotonic_ns"]
    record["received_monotonic_ns"] = newest + receipt_delta_from_newest_end_ns
    with pytest.raises(ValueError, match="PHYSICS_RAW_CLOCK_INVALID"):
        verify(record, session_id="live-source", reset_epoch=2, nq=2, nv=1)


def test_reader_checks_continuity_between_original_chunks():
    convert, verify = _api()
    first = convert(_chunk(), received_monotonic_ns=10_000_000_000)
    second = convert(_chunk(sequence=8, first=106, receipt=10_010_000_000),
                     received_monotonic_ns=10_010_000_000)
    verify(second, previous=first)
    second["chunk"]["chunk_sequence"] += 1
    with pytest.raises(ValueError, match="PHYSICS_RAW_CONTINUITY"):
        verify(second, previous=first)


def test_child_binding_callback_is_bounded_no_io_then_drains_original_receipt():
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    callbacks, destroyed, events = [], [], []
    node = SimpleNamespace(create_subscription=lambda cls, topic, cb, qos: callbacks.append((cls, topic, cb)) or "physics-sub",
        destroy_subscription=destroyed.append)
    sink = SimpleNamespace(append_raw_physics=lambda record: events.append(copy.deepcopy(record)))
    now = [10_000_000_000]
    adapter = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=sink, clock_ns=lambda: now[0], pending_capacity=1)
    callbacks[0][2](_chunk())
    assert events == [], "physics ROS callback must not write audit bytes"
    assert adapter.drain() == 1
    assert events[0]["received_monotonic_ns"] == 10_000_000_000
    now[0] += 10_000_000
    callbacks[0][2](_chunk(sequence=8, first=106, receipt=now[0]))
    now[0] += 10_000_000
    callbacks[0][2](_chunk(sequence=9, first=111, receipt=now[0]))
    assert adapter.hazard == "PHYSICS_RAW_PENDING_OVERFLOW"
    with pytest.raises(ValueError, match="PHYSICS_RAW_PENDING_OVERFLOW"):
        adapter.drain()
    with pytest.raises(ValueError, match="PHYSICS_RAW_PENDING_OVERFLOW"):
        adapter.close()
    adapter.close()
    assert destroyed == ["physics-sub"]


def test_failed_retirement_retains_every_already_admitted_original_without_success():
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    retained, destroyed = [], []
    node = SimpleNamespace(create_subscription=lambda *args: "owned", destroy_subscription=destroyed.append)
    adapter = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=retained.append), clock_ns=lambda: 10_000_000_000,
        pending_capacity=1)
    adapter.accept_message(_chunk())
    adapter.accept_message(_chunk(sequence=8, first=106))
    with pytest.raises(ValueError, match="PHYSICS_RAW_PENDING_OVERFLOW"):
        adapter.close()
    assert len(retained) == 1
    assert retained[0]["chunk"]["chunk_sequence"] == 7
    assert adapter.hazard == "PHYSICS_RAW_PENDING_OVERFLOW"
    assert destroyed == ["owned"]
    snapshot = adapter.snapshot()
    assert snapshot["pending_originals"] == []
    assert snapshot["rejected_original"]["received_monotonic_ns"] == 10_000_000_000
    import base64
    from rclpy.serialization import deserialize_message
    assert "cdr_base64" in snapshot["rejected_original"], snapshot["rejected_original"]
    original = deserialize_message(base64.b64decode(snapshot["rejected_original"]["cdr_base64"]),
                                   PhysicsStepEvidenceChunk)
    assert original.chunk_sequence == 8
    assert original.first_physics_step == 106


def test_per_grid_source_lookup_uses_only_durable_originals_and_keeps_full_audit():
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    retained = []
    node = SimpleNamespace(create_subscription=lambda *args: "owned", destroy_subscription=lambda value: None)
    now = [10_000_000_000]
    adapter = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=lambda value: retained.append(copy.deepcopy(value))),
        clock_ns=lambda: now[0], history_capacity=5)
    try:
        adapter.accept_message(_chunk())
        assert adapter.source_at(.208) is None, "callback-only data is not yet durable"
        originals=getattr(adapter,'original_durable_steps',None)
        assert callable(originals), 'FIRST cannot read original durable native history'
        assert originals()==[]
        adapter.drain()
        assert originals()==retained[0]['chunk']['samples']
        independent=originals();independent[0]['model_qpos'][0]=99.
        assert originals()[0]['model_qpos'][0]==.1, 'readonly native history exposed mutable originals'
        result = adapter.source_at(.208)
        assert result["sample"]["physics_step"] == 104
        assert result["received_monotonic_ns"] == now[0]
        assert result["chunk_sequence"] == 7
        assert adapter.source_at(.208, physics_step=105) is None, "no future substitution"
        result["sample"]["model_qpos"][0] = 9.
        assert adapter.source_at(.208)["sample"]["model_qpos"][0] == .1
        now[0] += 10_000_000
        adapter.accept_message(_chunk(sequence=8, first=106, receipt=now[0]))
        adapter.drain()
        assert adapter.source_at(.208) is None, "no fallback after derived lookup expiry"
        assert len(retained) == 2 and sum(len(item["chunk"]["samples"]) for item in retained) == 10
        assert retained[0]["chunk"]["samples"][3]["model_qpos"] == [.1, .2]
        assert adapter.source_at(.5) is None, "stale samples cannot supply a grid"
        for invalid in (True, float("nan"), -.1):
            with pytest.raises(ValueError, match="PHYSICS_GRID_INVALID"):
                adapter.source_at(invalid)
    finally:
        adapter.close()


def test_failed_audit_append_cannot_publish_a_per_grid_source():
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    def refuse(record):
        raise OSError("original append refused")
    node = SimpleNamespace(create_subscription=lambda *args: "owned", destroy_subscription=lambda value: None)
    adapter = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=refuse), clock_ns=lambda: 10_000_000_000)
    adapter.accept_message(_chunk())
    with pytest.raises(ValueError, match="original append refused"):
        adapter.drain()
    with pytest.raises(ValueError, match="original append refused"):
        adapter.source_at(.208)
    assert len(adapter.snapshot()["pending_originals"]) == 1
    with pytest.raises(ValueError, match="original append refused"):
        adapter.close()


def test_native_callback_does_not_wait_for_durable_writer_io():
    import threading
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    entered, release, delivered = threading.Event(), threading.Event(), threading.Event()
    retained, errors = [], []
    def append(record):
        entered.set()
        assert release.wait(5), "test writer release timed out"
        retained.append(copy.deepcopy(record))
    now = [10_000_000_000]
    node = SimpleNamespace(create_subscription=lambda *args: "owned", destroy_subscription=lambda value: None)
    adapter = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=append), clock_ns=lambda: now[0])
    adapter.accept_message(_chunk())
    def drain():
        try:
            adapter.drain()
        except BaseException as error:
            errors.append(error)
    writer = threading.Thread(target=drain)
    writer.start()
    assert entered.wait(2)
    now[0] += 10_000_000
    def callback():
        adapter.accept_message(_chunk(sequence=8, first=106, receipt=now[0]))
        delivered.set()
    producer = threading.Thread(target=callback)
    producer.start()
    try:
        assert delivered.wait(.5), "native callback waited for durable writer I/O"
        assert adapter.source_at(.208) is None
    finally:
        release.set()
        producer.join(2)
        writer.join(2)
        adapter.close()
    assert not producer.is_alive() and not writer.is_alive() and errors == []
    assert [record["chunk"]["chunk_sequence"] for record in retained] == [7, 8]


@pytest.mark.parametrize("operation", ["hazard", "close"])
def test_native_writer_rechecks_callback_fence_after_blocked_append(operation):
    import threading
    import time
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    entered, release = threading.Event(), threading.Event()
    retained, errors = [], []
    def append(record):
        entered.set()
        assert release.wait(5)
        retained.append(copy.deepcopy(record))
    now = [10_000_000_000]
    node = SimpleNamespace(create_subscription=lambda *args: "owned", destroy_subscription=lambda value: None)
    adapter = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=append), clock_ns=lambda: now[0], pending_capacity=2)
    adapter.accept_message(_chunk())
    now[0] += 10_000_000
    adapter.accept_message(_chunk(sequence=8, first=106, receipt=now[0]))
    def run(operation):
        try:
            operation()
        except BaseException as error:
            errors.append(str(error))
    writer = threading.Thread(target=lambda: run(adapter.drain))
    writer.start()
    assert entered.wait(2)
    closer = None
    try:
        if operation == "hazard":
            now[0] += 10_000_000
            adapter.accept_message(_chunk(sequence=9, first=111, receipt=now[0]))
            assert adapter.hazard == "PHYSICS_RAW_PENDING_OVERFLOW"
        else:
            closer = threading.Thread(target=lambda: run(adapter.close))
            closer.start()
            deadline = time.monotonic() + .5
            while not adapter.snapshot().get("admission_closed", False) and time.monotonic() < deadline:
                time.sleep(.001)
            assert adapter.snapshot().get("admission_closed") is True, "close admission fence waited for I/O"
            before = adapter.snapshot()["pending_originals"]
            now[0] += 10_000_000
            adapter.accept_message(_chunk(sequence=9, first=111, receipt=now[0]))
            assert adapter.snapshot()["pending_originals"] == before and adapter.hazard is None
    finally:
        release.set()
        writer.join(2)
        if closer is not None:
            closer.join(2)
    if operation == "hazard":
        assert [item["chunk"]["chunk_sequence"] for item in retained] == [7]
        assert len(adapter.snapshot()["pending_originals"]) == 1
        with pytest.raises(ValueError, match="PHYSICS_RAW_PENDING_OVERFLOW"):
            adapter.close()
        assert errors == ["PHYSICS_RAW_PENDING_OVERFLOW"]
    else:
        assert errors == []
        adapter.close()
    assert [item["chunk"]["chunk_sequence"] for item in retained] == [7, 8]


def test_archival_older_steps_keep_original_age_without_substituting_selected_source():
    convert, verify = _api()
    record = convert(_chunk(), received_monotonic_ns=10_000_000_000)
    # A 100ms batch at RTF .90 can legitimately deliver its earliest historical step
    # after .1 wall seconds. Only the newest source below is a freshness candidate.
    record["chunk"]["samples"][0]["clock_interval_begin_monotonic_ns"] -= 150_000_000
    record["chunk"]["samples"][0]["clock_interval_end_monotonic_ns"] -= 150_000_000
    verify(record)
    assert record["received_monotonic_ns"] - record["chunk"]["samples"][0]["clock_interval_begin_monotonic_ns"] > 100_000_000


@pytest.mark.parametrize("field,value", [("chunk_sequence", 2**64), ("reset_epoch", 2**64),
    ("clock_interval_begin_monotonic_ns", 2**63), ("body1_id", 2**31)])
def test_raw_reader_refuses_values_native_ros_cannot_publish(field, value):
    convert, verify = _api()
    record = convert(_chunk(), received_monotonic_ns=10_000_000_000)
    if field in ("chunk_sequence", "reset_epoch"):
        record["chunk"][field] = value
    elif field == "body1_id":
        record["chunk"]["samples"][0]["other_object_contacts"][0][field] = value
    else:
        record["chunk"]["samples"][0][field] = value
    with pytest.raises(ValueError):
        verify(record)


def test_raw_conversion_refuses_work_exceeding_actual_frozen_producer_limits():
    convert, verify = _api()
    with pytest.raises(ValueError, match="PHYSICS_RAW_PRODUCER_BOUNDS_INVALID"):
        convert(_chunk(), received_monotonic_ns=10_000_000_000, max_samples=4, max_contacts=128)
    with pytest.raises(ValueError, match="PHYSICS_RAW_PRODUCER_BOUNDS_INVALID"):
        convert(_chunk(), received_monotonic_ns=10_000_000_000, max_samples=50, max_contacts=0)


def test_pre_execution_child_failure_durably_retains_rejected_original_and_accepted_chunk(tmp_path):
    import time
    import json
    import base64
    from rclpy.serialization import deserialize_message
    from test_act_child_recorder_binding import frozen_child_inputs, _options
    from so101_demo.act.episode_open import open_recorder_episode
    from so101_demo.ros.data_source_binding import bind_data_sources
    manifest, inputs, snapshot = frozen_child_inputs(tmp_path)
    episode = open_recorder_episode(_options(tmp_path, inputs=manifest))
    node = SimpleNamespace(create_subscription=lambda cls, topic, callback, qos: topic,
                           destroy_subscription=lambda value: None)
    binding = bind_data_sources(node, session_id="session", reset_epoch=2,
        model_path=manifest.parent / inputs["execution_snapshot"]["path"] / snapshot["scene_path"],
        episode_recorder=episode, expected_model=snapshot)
    message = _chunk(receipt=time.monotonic_ns())
    message.simulation_session_id, message.reset_epoch = "session", 2
    for sample in message.samples:
        sample.simulation_session_id, sample.reset_epoch = "session", 2
        sample.model_qpos, sample.model_qvel = [0.] * snapshot["nq"], [0.] * snapshot["nv"]
    adapter = binding.physics_adapter
    adapter.accept_message(message)
    message.chunk_sequence += 2
    adapter.accept_message(message)
    assert adapter.hazard == "PHYSICS_RAW_CONTINUITY_INVALID"
    try:
        with pytest.raises(ValueError, match="PHYSICS_RAW_CONTINUITY_INVALID"):
            binding.close()
        root = episode.capture.recorder.root
        document = json.loads((root.parent / "physics-source-failure.json").read_bytes())
        assert document["identity"] == episode.capture.audit.identity
        assert document["source"]["pending_originals"] == []
        assert document["source"]["hazard"] == "PHYSICS_RAW_CONTINUITY_INVALID"
        original = deserialize_message(base64.b64decode(document["source"]["rejected_original"]["cdr_base64"]),
                                       PhysicsStepEvidenceChunk)
        assert original.chunk_sequence == 9
        events = [json.loads(line) for line in (root / "audit/events.jsonl").read_text().splitlines()]
        assert [event["payload"]["raw_chunk"]["chunk"]["chunk_sequence"] for event in events
                if event["kind"] == "physics_chunk_v1"] == [7]
        assert not (root / "seal.json").exists()
    finally:
        episode.close()


def test_actual_audit_seal_rechecks_raw_scope_clocks_and_chunk_continuity(tmp_path):
    import hashlib
    import json
    from test_act_episode_audit import complete_audit
    from so101_demo.act.episode_audit import verify_audit_manifest
    convert, verify = _api()
    writer, window = complete_audit(tmp_path)
    for sequence, first, receipt in ((7, 101, 10_000_000_000), (8, 106, 10_010_000_000)):
        message = _chunk(sequence, first, receipt)
        message.simulation_session_id = "s"
        message.reset_epoch = 1
        for step in message.samples:
            step.simulation_session_id = "s"
            step.reset_epoch = 1
        writer.append_raw_physics(convert(message, received_monotonic_ns=receipt))
    path = writer.seal(window)
    verify_audit_manifest(path)
    original = {item.relative_to(writer.root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
                for item in writer.root.rglob("*") if item.is_file()}
    import shutil
    copied = tmp_path / "isolated-negative"
    shutil.copytree(writer.root, copied)
    event_path = copied / "audit/events.jsonl"
    events = [json.loads(line) for line in event_path.read_text().splitlines()]
    raw = [event for event in events if event["kind"] == "physics_chunk_v1"]
    raw[1]["payload"]["raw_chunk"]["chunk"]["chunk_sequence"] += 1
    event_path.write_text("".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                                  for event in events))
    manifest_path = copied / "audit/audit-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"]["events.jsonl"] = {"path": "events.jsonl", "sha256": hashlib.sha256(event_path.read_bytes()).hexdigest(),
                                          "size": event_path.stat().st_size}
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="PHYSICS_RAW_CONTINUITY"):
        verify_audit_manifest(manifest_path)
    assert original == {item.relative_to(writer.root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
                        for item in writer.root.rglob("*") if item.is_file()}


class _RealRosFixture:
    """Real rclpy: a publisher node spun on its own executor thread, and an adapter node left unspun."""

    def __init__(self):
        import threading
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        self.rclpy = rclpy
        self.context = rclpy.context.Context()
        # An isolated DDS domain per xdist worker keeps parallel workers' topics apart.
        import os
        worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
        index = int(worker[2:]) if worker.startswith("gw") and worker[2:].isdigit() else 0
        rclpy.init(context=self.context, domain_id=150 + index % 83)
        self.main_node = rclpy.create_node("so101_physics_rx_test_main", context=self.context)
        self.pub_node = rclpy.create_node("so101_physics_rx_test_pub", context=self.context)
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        self.publisher = self.pub_node.create_publisher(PhysicsStepEvidenceChunk,
            "/so101/simulation/physics_step_chunks", QoSProfile(depth=100,
                reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE))
        self.executor = SingleThreadedExecutor(context=self.context)
        self.executor.add_node(self.pub_node)
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def _spin(self):
        while not self._stop.is_set():
            try:
                self.executor.spin_once(timeout_sec=0.01)
            except Exception:
                if self.context.ok():
                    raise
                return  # the test shut the context down on purpose

    def wait_matched(self, timeout_s=5.0):
        import time
        deadline = time.monotonic() + timeout_s
        while self.publisher.get_subscription_count() < 1:
            assert time.monotonic() < deadline, "subscription never matched"
            time.sleep(0.01)
        time.sleep(0.3)  # let both endpoints finish matching so the first chunk is not lost

    def shutdown(self):
        self._stop.set()
        self.thread.join(2)
        self.executor.shutdown()
        self.pub_node.destroy_node()
        self.main_node.destroy_node()
        if self.context.ok():
            self.rclpy.shutdown(context=self.context)


@pytest.fixture
def real_ros():
    fixture = _RealRosFixture()
    try:
        yield fixture
    finally:
        fixture.shutdown()


def _real_adapter(real_ros, **kwargs):
    import time
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    sink = SimpleNamespace(append_raw_physics=lambda record: None)
    return RosEpisodePhysicsAdapter(real_ros.main_node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=sink, clock_ns=time.monotonic_ns, **kwargs)


def _publish_block(real_ros, adapter, seconds=0.3):
    """Publish fresh chunks while the calling thread blocks without spinning anything."""
    import time
    real_ros.wait_matched()
    deadline = time.monotonic() + seconds
    sequence, first = 1, 101
    while time.monotonic() < deadline:
        receipt = time.monotonic_ns()
        real_ros.publisher.publish(_chunk(sequence=sequence, first=first, receipt=receipt))
        sequence, first = sequence + 1, first + 5
        time.sleep(0.02)
    time.sleep(0.05)
    return sequence - 1


def test_dedicated_receiver_receives_while_the_main_thread_blocks_without_spinning(real_ros):
    adapter = _real_adapter(real_ros, dedicated_receiver=True)
    try:
        published = _publish_block(real_ros, adapter)
        diagnostics = adapter.receipt_diagnostics()
        assert adapter.hazard is None
        assert diagnostics["chunk_count"] >= published - 1 and diagnostics["chunk_count"] > 3
        assert diagnostics["late_count"] == 0
    finally:
        adapter.close()


def test_default_receiver_depends_on_the_main_node_being_spun(real_ros):
    adapter = _real_adapter(real_ros)
    try:
        _publish_block(real_ros, adapter)
        assert adapter.receipt_diagnostics()["chunk_count"] == 0
    finally:
        adapter.close()


def test_close_joins_receiver_thread_destroys_rx_node_and_stops_callbacks(real_ros):
    adapter = _real_adapter(real_ros, dedicated_receiver=True)
    _publish_block(real_ros, adapter, seconds=0.1)
    import time
    thread = adapter._receiver_thread
    assert thread.is_alive()
    adapter.close()
    assert not thread.is_alive()
    assert adapter._rx_node is None
    before = adapter.receipt_diagnostics()["chunk_count"]
    real_ros.publisher.publish(_chunk(sequence=900, first=9001, receipt=time.monotonic_ns()))
    time.sleep(0.1)
    assert adapter.receipt_diagnostics()["chunk_count"] == before
    adapter.close()


def test_failed_drain_still_writes_failure_document_with_dedicated_receiver(real_ros, tmp_path):
    import time
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    root = tmp_path / "episode" / "audit"
    root.mkdir(parents=True)
    def broken(record):
        raise OSError("disk gone")
    sink = SimpleNamespace(append_raw_physics=broken, root=root, identity={"session_id": "live-source"})
    adapter = RosEpisodePhysicsAdapter(real_ros.main_node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=sink, clock_ns=time.monotonic_ns, dedicated_receiver=True)
    _publish_block(real_ros, adapter, seconds=0.1)
    with pytest.raises(ValueError, match="disk gone"):
        adapter.close()
    assert (root.parent / "physics-source-failure.json").is_file()
    assert not adapter._receiver_thread.is_alive()


def test_receiver_loop_exception_sets_receiver_failed_hazard(real_ros):
    import time
    adapter = _real_adapter(real_ros, dedicated_receiver=True)
    try:
        def explode(*args, **kwargs):
            raise RuntimeError("executor broke")
        adapter._rx_executor.spin_once = explode
        deadline = time.monotonic() + 2
        while adapter.hazard is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert adapter.hazard == "PHYSICS_RAW_RECEIVER_FAILED"
        assert not adapter._receiver_thread.is_alive()
    finally:
        with pytest.raises(ValueError, match="PHYSICS_RAW_RECEIVER_FAILED"):
            adapter.close()


def test_real_binding_construction_puts_physics_subscription_in_the_spooler_process(real_ros):
    import threading
    from pathlib import Path
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    from so101_demo.ros.data_source_binding import bind_data_sources
    topic = "/so101/simulation/physics_step_chunks"
    capture = SimpleNamespace(ingress_lock=threading.RLock(), active=False, started=False,
        on_acquisition=lambda frame, pixels: None,
        audit=SimpleNamespace(append_raw_physics=lambda raw: None,
            inputs={"execution_snapshot": {"physics_chunks": {"max_samples": 50, "max_contacts": 128}}}))
    episode = SimpleNamespace(capture=capture,
        synchronizer=RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1))
    binding = bind_data_sources(real_ros.main_node, session_id="session", reset_epoch=2,
        model_path=Path(__file__).parents[1] / "assets/mujoco/act/scene.xml", episode_recorder=episode)
    adapter = binding.physics_adapter
    try:
        # A real node's chunk receipt lives in the spooler process: no physics subscription in this process.
        assert adapter._spool is not None and adapter._rx_node is None
        assert topic not in [s.topic_name for s in real_ros.main_node.subscriptions]
        assert adapter._receiver_thread.is_alive() and adapter._spool.child.poll() is None
        spool_directory = adapter._spool.directory
    finally:
        binding.close()
    assert not adapter._receiver_thread.is_alive() and adapter._spool.child.poll() is not None
    assert not spool_directory.exists()
    assert topic not in [s.topic_name for s in real_ros.main_node.subscriptions]
    assert adapter.snapshot()["closed"] is True


def test_context_shutdown_before_close_ends_the_receiver_quietly(real_ros):
    import time
    adapter = _real_adapter(real_ros, dedicated_receiver=True)
    _publish_block(real_ros, adapter, seconds=0.1)
    thread = adapter._receiver_thread
    real_ros.rclpy.shutdown(context=real_ros.context)
    thread.join(2)
    assert not thread.is_alive()
    assert adapter.hazard is None
    assert adapter._receiver_end_reason == "CONTEXT_SHUTDOWN"
    adapter.close()  # destruction after an orderly shutdown completes without failure
    assert adapter.hazard is None and adapter.snapshot()["closed"] is True
    assert adapter._rx_node is None


def test_receiver_exception_with_a_live_context_still_sets_the_hazard_and_no_end_reason(real_ros):
    import time
    adapter = _real_adapter(real_ros, dedicated_receiver=True)
    try:
        def explode(*args, **kwargs):
            raise RuntimeError("executor broke")
        adapter._rx_executor.spin_once = explode
        deadline = time.monotonic() + 2
        while adapter.hazard is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert adapter.hazard == "PHYSICS_RAW_RECEIVER_FAILED"
        assert adapter._receiver_end_reason is None
    finally:
        with pytest.raises(ValueError, match="PHYSICS_RAW_RECEIVER_FAILED"):
            adapter.close()


def _drain_failure_lines(capsys):
    import json
    return [json.loads(line.split(" ", 1)[1]) for line in capsys.readouterr().err.splitlines()
            if line.startswith("PHYSICS_RAW_DRAIN_FAILURE ")]


def test_audit_append_failure_emits_one_drain_failure_line_and_keeps_hazard(capsys):
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    def refuse(record):
        raise OSError("original append refused")
    node = SimpleNamespace(create_subscription=lambda *args: "owned", destroy_subscription=lambda value: None)
    adapter = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=refuse), clock_ns=lambda: 10_000_000_000)
    adapter.accept_message(_chunk())
    capsys.readouterr()
    with pytest.raises(ValueError, match="original append refused") as caught:
        adapter.drain()
    assert isinstance(caught.value.__cause__, OSError)
    assert adapter.hazard == "original append refused"
    lines = _drain_failure_lines(capsys)
    assert len(lines) == 1
    facts = lines[0]
    assert facts["error_type"] == "OSError" and facts["error_message"] == "original append refused"
    assert facts["chunk_sequence"] == 7 and facts["first_physics_step"] == 101
    assert facts["last_physics_step"] == 105 and facts["received_monotonic_ns"] == 10_000_000_000
    assert facts["last_durable_chunk_sequence"] is None and facts["last_durable_physics_step"] is None
    assert facts["pending_count"] == 1 and facts["closing"] is False and facts["closed"] is False
    assert isinstance(facts["hazard_monotonic_ns"], int)


def test_audit_append_success_emits_no_drain_failure_line(capsys):
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    node = SimpleNamespace(create_subscription=lambda *args: "owned", destroy_subscription=lambda value: None)
    adapter = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=lambda record: None), clock_ns=lambda: 10_000_000_000)
    adapter.accept_message(_chunk())
    assert adapter.drain() == 1
    assert _drain_failure_lines(capsys) == []
