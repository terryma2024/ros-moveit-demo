"""Producer ingress controls, without starting a ROS or simulation owner."""

import pytest

from test_act_continuous_capture import (
    build, feed, frames_at, reference, start,
)


class Audit:
    def __init__(self):
        self.references = []
        self.bindings = []

    def append_source(self, kind, record):
        assert kind == "references"
        self.references.append(record)

    def append_acquisition(self, frame):
        pass

    def bind_row(self, *values):
        self.bindings.append(values)


def full_identity():
    return {"session_id": "session", "attempt_id": "attempt", "reset_epoch": 1, "release_epoch": 0,
        "lease": {"batch_id": "batch", "coordinator_epoch": 1, "worker_id": "worker", "worker_generation": 1,
                  "point_id": "point", "attempt_id": "attempt", "lease_generation": 1,
                  "lease_issued_monotonic_s": 1., "lease_deadline_monotonic_s": 121.}}


@pytest.mark.parametrize("delivered", [True, False])
def test_live_physical_join_pins_original_grid_until_durable_source_or_timeout(delivered):
    from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
    from so101_demo.act.acquisition import AcquisitionMinter
    from test_act_continuous_capture import FakeRecorder, FakeSampler, physical_audit
    clock = [0.]
    source_ready = [False]
    calls = []
    class Physical:
        def ready(self, at_s):
            return source_ready[0]
        def __call__(self, at_s):
            assert source_ready[0], "capture consumed physical source before original durable admission"
            calls.append(at_s)
            return physical_audit(at_s)
    capture = ContinuousEpisodeCapture(recorder=FakeRecorder(), sampler=FakeSampler(),
        physical_audit=Physical(), monotonic=lambda: clock[0], asynchronous_sources=True)
    capture.audit = Audit()
    minter = AcquisitionMinter()
    start(capture)
    frames_at(capture, minter, [1.])
    original = tuple(capture._frames[camera][0] for camera in ("head", "wrist"))
    assert capture.drain() == 0 and calls == []
    assert capture._next_grid_s == 1.
    assert tuple(capture._frames[camera][0] for camera in ("head", "wrist")) == original
    clock[0] = .05 if delivered else .100001
    if delivered:
        source_ready[0] = True
        capture.on_reference(reference(1.1))
        frames_at(capture, minter, [1.1, 1.2])
        assert capture.drain() == 1
        assert calls == [1., 1.1, 1.2]
        assert capture.audit.bindings[0][2:4] == (original[0].acquisition_id, original[1].acquisition_id)
    else:
        with pytest.raises(ValueError, match="INPUT_STALE"):
            capture.drain()
        source_ready[0] = True
        with pytest.raises(ValueError, match="INPUT_STALE"):
            capture.drain()
        assert capture.recorder.rows == [] and calls == []


def test_episode_causal_provider_cannot_be_replaced_by_phase_snapshot():
    from so101_demo.act.episode_assembly import PhysicalAuditAdapter, PointEpisode
    from test_act_continuous_capture import physical_audit
    episode = PointEpisode.__new__(PointEpisode)
    episode.capture, _ = build()
    episode._started = False
    episode.identity = full_identity()
    class Provider:
        identity = dict(episode.identity)
        def ready(self, at_s):
            return True
        def __call__(self, at_s):
            return {**physical_audit(at_s), "reset_epoch": 1, "release_epoch": 0,
                    "release_event": False, "release_time_s": None, "phase": "PREPARE",
                    "reference_time_s": None, "reference_source": None, "reference_positions": None}
    provider = Provider()
    episode.bind_physical_provider(provider)
    assert episode.capture.physical_audit.ready(1.) is True
    assert set(episode.capture.physical_audit(1.)) == set(PhysicalAuditAdapter.KEYS)
    with pytest.raises(ValueError, match="EPISODE_CAUSAL_SOURCE_BINDING_INVALID"):
        episode.bind_physical_provider(provider)
    with pytest.raises(ValueError, match="EPISODE_CAUSAL_SOURCE_FIXED"):
        episode.set_physical_audit({"phase": "later"})


@pytest.mark.parametrize("field", ["attempt_id", "lease", "reset_epoch", "boolean_epoch"])
def test_episode_provider_refuses_foreign_full_identity_before_binding(field):
    from so101_demo.act.episode_assembly import PointEpisode
    from types import SimpleNamespace
    episode = PointEpisode.__new__(PointEpisode)
    episode.capture, _ = build()
    episode._started = False
    episode.identity = full_identity()
    identity = full_identity()
    if field == "attempt_id":
        identity["attempt_id"] = identity["lease"]["attempt_id"] = "other"
    elif field == "lease":
        identity["lease"]["worker_generation"] = 2
    else:
        identity["reset_epoch"] = True if field == "boolean_epoch" else 2
    provider = SimpleNamespace(identity=identity, ready=lambda at: True)
    class CallableProvider:
        identity = provider.identity
        ready = staticmethod(provider.ready)
        def __call__(self, at):
            return {}
    with pytest.raises(ValueError, match="EPISODE_CAUSAL_SOURCE_IDENTITY_INVALID"):
        episode.bind_physical_provider(CallableProvider())
    assert not getattr(episode, "_physical_provider_bound", False)


def test_reference_callback_never_writes_and_drain_preserves_raw_order():
    capture, minter = build()
    capture.audit = Audit()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.2))
    assert capture.audit.references == [], "producer callback performed audit IO"
    assert capture.drain() == 1
    assert [row["reference_time_s"] for row in capture.audit.references] == [1.1, 1.2]


def test_acquisition_capacity_fails_before_silent_eviction():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0 + index * .1 for index in range(8)])
    with pytest.raises(ValueError, match="CAPTURE_ACQUISITION_OVERFLOW"):
        feed(capture, minter, camera="head", stamp_s=1.8)
    assert capture._frames["head"][0].stamp_s == 1.0
    with pytest.raises(ValueError, match="CAPTURE_ACQUISITION_OVERFLOW"):
        capture.drain()


def test_reference_binding_uses_actual_raw_stream_ordinal():
    capture, minter = build()
    capture.audit = Audit()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.0))
    capture.on_reference(reference(1.0, accepted=False))
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    assert capture.audit.bindings[0][-1] == 3


def test_live_camera_join_waits_for_original_delayed_pair():
    from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
    from test_act_continuous_capture import FakeRecorder, FakeSampler, physical_audit
    from so101_demo.act.acquisition import AcquisitionMinter
    ticks = {"now": 0.0}
    capture = ContinuousEpisodeCapture(recorder=FakeRecorder(), sampler=FakeSampler(),
        physical_audit=physical_audit, monotonic=lambda: ticks["now"],
        asynchronous_sources=True)
    minter = AcquisitionMinter()
    start(capture)
    feed(capture, minter, camera="head", stamp_s=1.0)
    assert capture.drain() == 0
    ticks["now"] = .05
    feed(capture, minter, camera="wrist", stamp_s=1.0)
    assert capture.drain() == 0
    capture.on_reference(reference(1.1))
    frames_at(capture, minter, [1.1, 1.2])
    assert capture.drain() == 1
    assert capture.recorder.rows[0]["observation"]["sim_time_s"] == 1.0


def test_live_missing_pair_expires_without_replacement_or_skip():
    from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
    from test_act_continuous_capture import FakeRecorder, FakeSampler, physical_audit
    from so101_demo.act.acquisition import AcquisitionMinter
    ticks = {"now": 0.0}
    capture = ContinuousEpisodeCapture(recorder=FakeRecorder(), sampler=FakeSampler(),
        physical_audit=physical_audit, monotonic=lambda: ticks["now"],
        asynchronous_sources=True)
    minter = AcquisitionMinter()
    start(capture)
    feed(capture, minter, camera="head", stamp_s=1.0)
    assert capture.drain() == 0
    ticks["now"] = .100001
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.drain()
    assert capture.recorder.rows == []


def test_delivery_timeout_starts_only_when_actual_sim_grid_is_eligible():
    from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
    from test_act_continuous_capture import FakeRecorder, FakeSampler, physical_audit
    from so101_demo.act.acquisition import AcquisitionMinter
    ticks = {"now": 0.}
    capture = ContinuousEpisodeCapture(recorder=FakeRecorder(), sampler=FakeSampler(),
        physical_audit=physical_audit, monotonic=lambda: ticks["now"], asynchronous_sources=True)
    minter = AcquisitionMinter()
    start(capture)
    frames_at(capture, minter, [1.0])
    assert capture.drain() == 0
    ticks["now"] = .12  # actual simulator has not reached the next instant yet
    assert capture.drain() == 0
    feed(capture, minter, camera="head", stamp_s=1.1)
    assert capture.drain() == 0
    ticks["now"] = .19
    feed(capture, minter, camera="wrist", stamp_s=1.1)
    assert capture.drain() == 0


def test_original_camera_pair_waits_for_measured_numeric_delivery(tmp_path):
    from so101_demo.act.episode_assembly import LiveSampler
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
    from so101_demo.act.acquisition import AcquisitionMinter
    from test_act_continuous_capture import FakeRecorder, ZERO, physical_audit
    ticks = {"now": 0.}
    sync = RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1, monotonic=lambda: ticks["now"])
    sync.reset("s")
    capture = ContinuousEpisodeCapture(recorder=FakeRecorder(), sampler=LiveSampler(sync),
        physical_audit=physical_audit, monotonic=lambda: ticks["now"], asynchronous_sources=True)
    minter = AcquisitionMinter()
    start(capture)
    for camera in ("head", "wrist"):
        value = minter.mint(camera, session_id="s", reset_epoch=1, stamp_s=1.,
                            received_monotonic_ns=1, pixels=ZERO)
        capture.on_acquisition(value, ZERO)
        sync.push(camera, "s", 1., ZERO)
    assert capture.drain() == 0
    assert sync._last_sample is None
    ticks["now"] = .05
    sync.push("arm", "s", 1., [0.] * 6)
    sync.push("neck", "s", 1., 0.)
    capture.on_reference(reference(1.1))
    capture.on_source_clock(1.100002)
    assert capture.drain() == 1
    assert capture.recorder.rows[0]["observation"]["sim_time_s"] == 1.


@pytest.mark.parametrize("operation", ["acquisition", "binding"])
def test_audit_refusal_latches_and_never_retries_a_partial_row(operation):
    class Refusing(Audit):
        def append_acquisition(self, frame):
            if operation == "acquisition":
                raise OSError("ACTUAL_ACQUISITION_IO_ERROR")

        def bind_row(self, *values):
            raise OSError("ACTUAL_BINDING_IO_ERROR")

    capture, minter = build()
    capture.audit = Refusing()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    reason = "ACTUAL_" + operation.upper() + "_IO_ERROR"
    with pytest.raises(ValueError, match=reason):
        capture.drain()
    count = len(capture.recorder.rows)
    assert count == (0 if operation == "acquisition" else 1)
    for call in (capture.drain, lambda: capture.finish(1.3)):
        with pytest.raises(ValueError, match=reason):
            call()
    assert len(capture.recorder.rows) == count


@pytest.mark.parametrize("fault", ["rgb", "joints", "duplicate", "reset"])
def test_active_ros_producer_fault_is_terminal_despite_later_good_input(fault):
    from sensor_msgs.msg import Image, JointState
    from so101_demo.act.joints import ACT_JOINTS
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    from so101_demo.adapters.act.ros_observation import RosObservationAdapter

    class Node:
        def create_subscription(self, *args):
            return args[1]

    capture, _ = build()
    sync = RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1, monotonic=lambda: 5.)
    adapter = RosObservationAdapter(Node(), sync, capture=capture, reset_epoch=1)
    adapter.reset("s", source_floor_s=.5, reset_epoch=1)
    start(capture)
    image = Image(width=640, height=480, step=1920, encoding="rgb8",
                  data=bytes(640 * 480 * 3))
    image.header.stamp.sec = 1
    if fault == "rgb":
        image.data = b"truncated"
        adapter._image("head", image)
        reason = "INPUT_RGB_INVALID"
    elif fault == "joints":
        joints = JointState(name=list(ACT_JOINTS), position=[0.])
        joints.header.stamp.sec = 1
        adapter._joints(joints)
        reason = "JOINT_MAPPING_INVALID"
    elif fault == "reset":
        image.header.stamp.sec = 0
        adapter._image("head", image)
        reason = "INPUT_RESET_STALE"
    else:
        adapter._image("head", image)
        adapter._image("head", image)
        reason = "ACQUISITION_STAMP_REGRESSED"
    assert adapter.hazard == reason
    accepted = len(sync.buffers["head"])
    image.data = bytes(640 * 480 * 3)
    image.header.stamp.sec = 2
    adapter._image("head", image)
    assert len(sync.buffers["head"]) == accepted
    with pytest.raises(ValueError, match=reason):
        capture.drain()


@pytest.mark.parametrize("change", [None, "stale", "foreign_pair", "pixels", "duplicate_admission"])
def test_actual_rgb_before_capture_retains_original_seed_without_early_capture_or_remint(change):
    import numpy as np
    from dataclasses import replace
    from types import SimpleNamespace
    from sensor_msgs.msg import Image
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    from so101_demo.adapters.act.ros_observation import RosObservationAdapter
    ticks = [5.]
    capture, _ = build()
    sync = RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1, monotonic=lambda: ticks[0])
    adapter = RosObservationAdapter(SimpleNamespace(create_subscription=lambda *args: object()),
        sync, capture=capture, reset_epoch=1, sim_time=lambda: 1.02)
    adapter.reset("s", source_floor_s=.5, reset_epoch=1)
    image = Image(width=640, height=480, step=1920, encoding="rgb8", data=bytes([37]) * (640 * 480 * 3))
    image.header.stamp.sec = 1
    adapter._image("head", image)
    adapter._image("wrist", image)
    assert len(sync.buffers["head"]) == len(sync.buffers["wrist"]) == 1, "inactive capture swallowed original RGB"
    assert adapter.rejected == [] and capture._frames["head"] == capture._frames["wrist"]
    pair = adapter.capture_seed_pair(min_stamp_s=1.)
    assert all(frame is adapter.last_acquisitions[camera] for camera, (frame, pixels) in pair.items())
    assert all(np.all(pixels == 37) for frame, pixels in pair.values())
    start(capture)
    if change == "stale":
        ticks[0] += .101
    elif change == "foreign_pair":
        frame, pixels = pair["head"]
        from so101_demo.act.acquisition import canonical_acquisition_id
        pair["head"] = (replace(frame, session_id="foreign",
            acquisition_id=canonical_acquisition_id("foreign", 1, "head", frame.sequence)), pixels)
    elif change == "pixels":
        pair["head"][1][0, 0, 0] = 99
    if change in ("stale", "foreign_pair", "pixels"):
        with pytest.raises(ValueError):
            adapter.admit_capture_seed(pair)
        assert not capture._frames["head"] and not capture._frames["wrist"]
        return
    adapter.admit_capture_seed(pair)
    assert tuple(capture._frames["head"]) == (pair["head"][0],)
    assert tuple(capture._frames["wrist"]) == (pair["wrist"][0],)
    assert all(camera_frame.sequence == 1 for camera_frame in adapter.last_acquisitions.values())
    if change == "duplicate_admission":
        with pytest.raises(ValueError):
            adapter.admit_capture_seed(pair)
        assert len(capture._frames["head"]) == len(capture._frames["wrist"]) == 1


def prestart_adapter(*, sim_now=1.1, wall_now=5.1):
    from types import SimpleNamespace
    from sensor_msgs.msg import Image
    from so101_demo.act.synchronizer import RgbObservationSynchronizer
    from so101_demo.adapters.act.ros_observation import RosObservationAdapter
    capture, _ = build()
    ticks = [5.]
    sync = RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1, monotonic=lambda: ticks[0])
    adapter = RosObservationAdapter(SimpleNamespace(create_subscription=lambda *args: object()),
        sync, capture=capture, reset_epoch=1, sim_time=lambda: sim_now)
    adapter.reset("s", source_floor_s=.5, reset_epoch=1)
    image = Image(width=640, height=480, step=1920, encoding="rgb8", data=bytes(640 * 480 * 3))
    image.header.stamp.sec = 1
    for camera in ("head", "wrist"):
        adapter._image(camera, image)
    ticks[0] = wall_now
    return adapter, capture, image


@pytest.mark.parametrize("terminal", ["stop", "finish"])
def test_terminal_capture_ingress_cannot_restart_seed_or_reset(terminal):
    adapter, capture, image = prestart_adapter(sim_now=2., wall_now=5.)
    start(capture)
    if terminal == "stop":
        capture.on_event({"kind": "stop", "sim_time_s": 1.2})
    else:
        capture.finish(1.2)
    original = dict(adapter.last_acquisitions)
    buffers = {key: tuple(buffer) for key, buffer in adapter.synchronizer.buffers.items()}
    image.header.stamp.nanosec = 100_000_000
    adapter._image("head", image)
    assert adapter.last_acquisitions == original, "terminal ingress minted a new pre-start identity"
    assert all(len(buffer) == len(buffers[key]) for key, buffer in adapter.synchronizer.buffers.items())
    with pytest.raises(ValueError, match="INPUT_COLLECTION_SEED_FIXED"):
        adapter.capture_seed_pair(min_stamp_s=1.)
    with pytest.raises(ValueError, match="INPUT_COLLECTION_RESET_FORBIDDEN"):
        adapter.reset("s", source_floor_s=1.2, reset_epoch=1)


@pytest.mark.parametrize("extra_ns", [0, 1])
def test_seed_age_uses_inclusive_original_nanosecond_boundary(extra_ns):
    adapter, capture, _ = prestart_adapter(sim_now=1.1 + extra_ns / 1e9)
    if extra_ns:
        with pytest.raises(ValueError, match="INPUT_COLLECTION_SEED_EXPIRED"):
            adapter.capture_seed_pair(min_stamp_s=1.)
    else:
        pair = adapter.capture_seed_pair(min_stamp_s=1.)
        assert pair["head"][0].stamp_s == 1.


def test_capture_activation_excludes_concurrent_callback_until_original_seeds_admitted():
    import threading
    adapter, capture, image = prestart_adapter(sim_now=1.02, wall_now=5.)
    originals = dict(adapter.last_acquisitions)
    activated = threading.Event()
    callback_waiting = threading.Event()
    callback_finished = threading.Event()
    order = []
    original_admit = capture.on_acquisition
    def admit(frame, pixels):
        order.append((frame.camera, frame.sequence))
        original_admit(frame, pixels)
    capture.on_acquisition = admit
    def callback():
        assert activated.wait(2.)
        callback_waiting.set()
        adapter._image("head", image)
        callback_finished.set()
    worker = threading.Thread(target=callback)
    worker.start()
    def activate(grid_s):
        capture.start("s", "attempt", 1, grid_s)
        image.header.stamp.nanosec = 10_000_000
        activated.set()
        assert callback_waiting.wait(2.)
        assert not callback_finished.wait(.02), "callback entered the activation fence"
    try:
        pair = adapter.activate_capture(min_stamp_s=1., activate=activate)
    finally:
        activated.set()
        worker.join(2.)
    assert not worker.is_alive() and callback_finished.is_set()
    assert order == [("head", 1), ("wrist", 1), ("head", 2)]
    assert all(pair[key][0] is originals[key] for key in originals)
    assert capture._next_grid_s == 1. and capture._frames["head"][0] is originals["head"]


@pytest.mark.parametrize("at_s,eligible", [(1.1, True), (1.100000001, False), (.999999999, False)])
def test_capture_camera_selection_uses_same_original_nanosecond_age_and_causality(at_s, eligible):
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.])
    assert (capture._causal("head", at_s) is not None) == eligible


@pytest.mark.parametrize("origin_ns", [1_000_000_001, 1_000_000_501])
def test_capture_retains_original_nanosecond_grid_and_t_plus_point_one_labels(origin_ns):
    capture, minter = build()
    origin_s = origin_ns / 1e9
    start(capture, start_s=origin_s)
    stamps = [(origin_ns + offset * 100_000_000) / 1e9 for offset in range(3)]
    frames_at(capture, minter, stamps)
    capture.on_reference({**reference(stamps[1]), "requested_sim_time_s": stamps[1]})
    capture.on_reference({**reference(stamps[2]), "requested_sim_time_s": stamps[2]})
    capture.on_source_clock(stamps[2] + .000002)
    assert capture.drain() == 2
    assert [round(row["observation"]["sim_time_s"] * 1e9) for row in capture.recorder.rows] == [
        origin_ns, origin_ns + 100_000_000]
    assert [round(row["audit"]["reference_time_s"] * 1e9) for row in capture.recorder.rows] == [
        origin_ns + 100_000_000, origin_ns + 200_000_000]


def test_active_ingress_refuses_one_nanosecond_future_original_camera_stamp():
    adapter, capture, image = prestart_adapter(sim_now=1., wall_now=5.)
    start(capture)
    original = dict(adapter.last_acquisitions)
    image.header.stamp.nanosec = 1
    adapter._image("head", image)
    assert adapter.hazard == "INPUT_TIMESTAMP_FUTURE"
    assert adapter.last_acquisitions == original
    with pytest.raises(ValueError, match="INPUT_TIMESTAMP_FUTURE"):
        capture.check_health()


@pytest.mark.parametrize("before_start", [False, True])
def test_same_thread_callback_during_owner_activation_fails_without_admitting_newer_frame(before_start):
    adapter, capture, image = prestart_adapter(sim_now=1.02, wall_now=5.)
    originals = dict(adapter.last_acquisitions)
    def activate(grid_s):
        if not before_start:
            capture.start("s", "attempt", 1, grid_s)
        image.header.stamp.nanosec = 10_000_000
        adapter._image("head", image)
        if before_start:
            capture.start("s", "attempt", 1, grid_s)
    with pytest.raises(ValueError, match="INPUT_COLLECTION_ACTIVATION_REENTRANT"):
        adapter.activate_capture(min_stamp_s=1., activate=activate)
    assert adapter.last_acquisitions == originals
    assert not capture._frames["head"] and not capture._frames["wrist"]
    with pytest.raises(ValueError, match="INPUT_COLLECTION_ACTIVATION_REENTRANT"):
        capture.check_health()
