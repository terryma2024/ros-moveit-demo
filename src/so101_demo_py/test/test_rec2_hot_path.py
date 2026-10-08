"""Recorder round 2 (CP-3403): the evidence of the L2 run named three data-side defects, each pinned here.

* The world record / scene frame join judged "scene missing" from the pump's own pass cadence BEFORE looking at the scene
  frames, so a pass that came late after the frame had arrived failed a join that was satisfied (L2: SCENE_MISSING at
  ready + 12.1 s, followed 23 s later by the world ring losing its prefix because the drain had stopped).
* One reference read deep-copied the whole 2 s window of both controllers (about 110 ms per read at 10 reads per second).
* The controller observer's deques are appended by the receiver and read by the loop, so they need one lock.
"""
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.controller_reference_observer import ControllerReferenceObserver
from so101_demo.ros import episode_recorder_sources as sources_module
from so101_demo.ros import recorder_data_side as data_side_module
from test_b2_controller_reference import ARM, PERIOD_NS, feed
from test_act_episode_recorder_sources import RecordingNode


# ---- the bounded reference read -------------------------------------------------------------------------------

def _port_with_window(frames=1250):
    node = RecordingNode()
    port = sources_module.ControllerReferencePort(node, session_id="s", reset_epoch=1)
    start = node.clock_ns + 1_000_000
    stamps = [start + index * PERIOD_NS for index in range(frames)]
    node.clock_ns = stamps[-1] + 1_000_000
    feed(port.observer, "arm", stamps)
    feed(port.observer, "gripper", stamps, names=("6",))
    return node, port, stamps


def test_a_reference_read_does_not_copy_the_window(monkeypatch):
    node, port, stamps = _port_with_window()

    def refused(*args, **kwargs):
        raise AssertionError("the whole 2 s window was copied for one frame")

    monkeypatch.setattr(port.observer, "recent_by_stamp", refused)
    target = stamps[600]
    record = port.read(target / 1e9)
    assert record["accepted"] is True and record["frames"]["arm"]["sim_stamp_ns"] == target
    assert record["frames"]["gripper"]["sim_stamp_ns"] == target


def test_the_bounded_read_answers_exactly_like_the_window_read():
    from so101_demo.act.collection_reference import build_collection_reference
    node, port, stamps = _port_with_window()
    target = stamps[900] / 1e9
    assert port.read(target) == dict(build_collection_reference(target, port.recent), accepted=True)


@pytest.mark.parametrize("offset_s", [0.0005, -3.0])
def test_the_bounded_read_keeps_the_refusals(offset_s):
    node, port, stamps = _port_with_window(frames=300)
    with pytest.raises(RuntimeError, match="COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE"):
        port.read(stamps[100] / 1e9 + offset_s)      # between two publications / far outside the window


def test_the_bounded_read_refuses_a_stale_history_like_the_window_read():
    node, port, stamps = _port_with_window(frames=300)
    node.clock_ns = stamps[-1] + 2_500_000_000      # older than the 2 s window by stamp
    with pytest.raises(RuntimeError, match="REFERENCE_HISTORY_UNAVAILABLE"):
        port.read(stamps[10] / 1e9)


def test_the_observer_survives_the_receiver_appending_while_the_loop_reads():
    observer = ControllerReferenceObserver(max_frames=2048)
    observer.reset("s", 1, source_floor_ns=1_000_000_000)
    stop, errors = threading.Event(), []
    base = 1_100_000_000

    def receiver():
        stamp = base
        while not stop.is_set():
            feed(observer, "arm", [stamp])
            stamp += PERIOD_NS

    thread = threading.Thread(target=receiver)
    thread.start()
    try:
        end = time.monotonic() + 0.4
        while time.monotonic() < end:
            try:
                observer.matching_by_stamp("arm", now_sim_ns=base + 10_000_000_000, window_ns=20_000_000_000,
                                           target_ns=base + 500 * PERIOD_NS, tolerance_ns=1000)
            except ValueError:
                pass     # a stale or invalid history is an answer; a RuntimeError from a mutated deque is not
            except Exception as error:   # noqa: BLE001
                errors.append(repr(error))
                break
    finally:
        stop.set()
        thread.join()
    assert errors == []


# ---- the world / scene join -----------------------------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    @staticmethod
    def monotonic_ns():
        return time.monotonic_ns()


def _host(monkeypatch, records, scenes):
    clock = _Clock()
    appended = []
    monkeypatch.setattr(data_side_module, "time", clock)
    from so101_demo.act import native_endpoints
    monkeypatch.setattr(native_endpoints, "world_source_record",
                        lambda received, scene, execution_root: {"physics": {"simulation_step": received.evidence.simulation_step},
                                                                 "scene": scene[0]["simulation_step"]})
    episode = SimpleNamespace(capture=SimpleNamespace(audit=SimpleNamespace(append_world_source=appended.append)))
    binding = SimpleNamespace(observer=SimpleNamespace(
        original_frames_with_receipts=lambda min_simulation_step=None: tuple(scenes)))
    world = SimpleNamespace(original_records_after=lambda cursor: tuple(r for r in records
                                                                          if r.evidence.publisher_sequence > cursor))
    host = data_side_module.RecorderDataSide(
        node=None, session_id="s", reset_epoch=1, episode=episode, binding=binding, world_observer=world,
        execution_root="/x", progress=lambda: None, normal_stop_proof=lambda: {}, invalid_latched=lambda: False,
        drain_collection=lambda: None)
    host._world_record_cursor = 0
    return host, clock, appended


def _record(sequence, step):
    return SimpleNamespace(received_monotonic_s=100.0, evidence=SimpleNamespace(
        simulation_session_id="s", reset_epoch=1, publisher_sequence=sequence, simulation_step=step))


def _scene(step, receipt=100.0):
    return ({"simulation_session_id": "s", "reset_epoch": 1, "simulation_step": step}, receipt)


def test_a_scene_frame_that_arrived_during_a_slow_pass_satisfies_the_join(monkeypatch):
    scenes = []
    host, clock, appended = _host(monkeypatch, [_record(1, 10)], scenes)
    assert host._drain_world_sources() == 0          # the frame is not there yet: wait, do not judge
    clock.now += 0.3                                  # one slow pass later ...
    scenes.append(_scene(10))                         # ... the frame is in the ring (the receiver took it meanwhile)
    assert host._drain_world_sources() == 1          # the join is satisfied; the pass cadence is not a reason
    assert [item["physics"]["simulation_step"] for item in appended] == [10]


def test_a_scene_frame_that_never_arrives_is_still_missing_after_100_ms(monkeypatch):
    host, clock, appended = _host(monkeypatch, [_record(1, 10)], [])
    assert host._drain_world_sources() == 0
    clock.now += 0.05
    assert host._drain_world_sources() == 0          # still inside the 100 ms
    clock.now += 0.06
    with pytest.raises(RuntimeError, match="DYNAMIC_WORLD_SOURCE_SCENE_MISSING"):
        host._drain_world_sources()


def test_a_frame_received_more_than_100_ms_after_its_world_record_is_missing_whenever_it_is_read(monkeypatch):
    scenes = [_scene(10, receipt=100.101)]
    host, clock, appended = _host(monkeypatch, [_record(1, 10)], scenes)
    with pytest.raises(RuntimeError, match="DYNAMIC_WORLD_SOURCE_SCENE_MISSING"):
        host._drain_world_sources()
    assert appended == []


def test_a_missing_scene_frame_leaves_its_facts_next_to_the_episode(monkeypatch, tmp_path):
    """CP-3405: SCENE_MISSING recurred after the receipt-based join. The next occurrence must say what the rings held."""
    import json
    scenes = [_scene(5), _scene(6)]
    host, clock, appended = _host(monkeypatch, [_record(7, 10)], scenes)
    host.episode_recorder.capture.audit.root = tmp_path / "episode" / "audit"
    host.episode_recorder.capture.audit.root.mkdir(parents=True)
    host._scene_source_binding.observer.hazard = None
    host._scene_source_binding.adapter = SimpleNamespace(rejected=3)
    assert host._drain_world_sources() == 0
    clock.now += 0.2
    with pytest.raises(RuntimeError, match="DYNAMIC_WORLD_SOURCE_SCENE_MISSING"):
        host._drain_world_sources()
    facts = json.loads((tmp_path / "episode" / "world-scene-failure.json").read_text())
    assert facts["world"]["simulation_step"] == 10 and facts["world"]["publisher_sequence"] == 7
    assert facts["scene_ring"]["count"] == 2 and facts["scene_ring"]["steps_first_last"] == [5, 6]
    assert facts["waited_s"] == pytest.approx(0.2, abs=0.01) and facts["adapter_rejected"] == 3
