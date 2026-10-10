"""CP-3410: the backlog and receiver-lag bounds are frozen policy (episode_recorder_v1), strictly loaded; the lag bound reaches the adapter.

The backlog bound belonged to the retired chunk spool: it stays in the closed document (frozen manifests carry it) and nothing reads it."""
import math
from types import SimpleNamespace

import pytest
import yaml

from so101_demo.act.offline.policy import RecorderConfigRefused, load_recorder_policy
from test_act_episode_recorder_sources import RecordingNode, _binding, _engine, _episode, _options
from paths import PACKAGE_ROOT

POLICY_FILE = PACKAGE_ROOT / "config/act/episode_recorder_v1.yaml"


def document():
    return yaml.safe_load(POLICY_FILE.read_text())


def test_the_frozen_policy_carries_the_two_bounds_with_their_rationale():
    policy = load_recorder_policy(POLICY_FILE)
    assert policy["physics_spool_backlog_frames_max"] == 64 and policy["physics_receiver_lag_max_s"] == 5.0
    text = POLICY_FILE.read_text()
    assert "CP-3410" in text and "NO per-chunk delivery-age rule" in text
    assert "Nominal peak" in text and "4096-step" in text, "the rationale cites the telemetry the numbers came from"


@pytest.mark.parametrize("change", [
    {"physics_spool_backlog_frames_max": 0}, {"physics_spool_backlog_frames_max": 129},
    {"physics_spool_backlog_frames_max": True}, {"physics_spool_backlog_frames_max": 1.5},
    {"physics_receiver_lag_max_s": 0.4}, {"physics_receiver_lag_max_s": 8.5}, {"physics_receiver_lag_max_s": True},
    {"physics_receiver_lag_max_s": math.inf}, {"physics_receiver_lag_max_s": "5"}])
def test_a_bound_outside_its_range_is_refused(change):
    value = document()
    value.update(change)
    with pytest.raises(RecorderConfigRefused):
        load_recorder_policy(yaml.safe_dump(value).encode())


@pytest.mark.parametrize("missing", ["physics_spool_backlog_frames_max", "physics_receiver_lag_max_s"])
def test_a_policy_without_a_bound_is_refused_and_the_old_policy_cannot_be_mistaken_for_the_new(missing):
    value = document()
    del value[missing]
    with pytest.raises(RecorderConfigRefused):
        load_recorder_policy(yaml.safe_dump(value).encode())


def test_the_policy_hash_covers_the_bounds():
    one = load_recorder_policy(POLICY_FILE)
    value = document()
    value["physics_receiver_lag_max_s"] = 4.0
    two = load_recorder_policy(yaml.safe_dump(value).encode())
    assert one["policy_sha256"] != two["policy_sha256"]


def test_the_sources_hand_the_frozen_bounds_to_the_physics_binding():
    from so101_demo.act.offline import sources as module
    seen = {}

    def bind(node, **kwargs):
        seen.update(kwargs)
        return _binding()

    sources = module.OfflineRosSources(
        RecordingNode(), _episode([]), _options(), bind=bind,
        world_observer_factory=lambda node, session: SimpleNamespace(callback_count=1),
        reference_port_factory=lambda node, **kw: SimpleNamespace(read=lambda when: {}, close=lambda: None),
        policy=load_recorder_policy(POLICY_FILE))
    sources.prepare(_engine([]))
    assert seen["physics_lag_max_s"] == 5.0 and "physics_backlog_max" not in seen


def test_the_binding_hands_them_to_the_adapter():
    import inspect
    from so101_demo.ros import data_source_binding
    text = inspect.getsource(data_source_binding.bind_data_sources)
    assert "receiver_lag_max_s=physics_lag_max_s" in text and "spool" not in text


def test_the_sources_wait_for_a_raw_chunk_as_long_as_the_receiver_lag_policy_and_the_default_stays_100_ms():
    from so101_demo.act.offline import sources as module
    from so101_demo.ros.recorder_data_side import RecorderDataSide
    made = module.OfflineRosSources(RecordingNode(), _episode([]), _options(), policy=load_recorder_policy(POLICY_FILE))
    assert made._chunk_wait_s == 5.0 and made.ALIGNMENT_RETRY_S == 5.0
    plain = module.OfflineRosSources(RecordingNode(), _episode([]), _options())
    assert plain._chunk_wait_s == 0.1 and plain.ALIGNMENT_RETRY_S == 1.0
    host = RecorderDataSide.__new__(RecorderDataSide)
    host._scene_source_binding = SimpleNamespace(physics_adapter=SimpleNamespace(received_max_step=lambda: 5,
        history_summary=lambda: {"pending": 0}))
    source = {"physics": {"simulation_step": 9}, "received_monotonic_ns": 1_000_000_000,
              "scene_received_monotonic_ns": 1_000_000_000}
    now = 1_000_000_000 + 300_000_000                 # the raw step is 300 ms behind its world source
    assert host._native_sources_expired("initial", [source], [], [source], now) is True      # the old fixed 100 ms
    host._native_source_wait_ns = 5_000_000_000
    assert host._native_sources_expired("initial", [source], [], [source], now) is False     # the policy wait
    assert host._native_sources_expired("initial", [source], [], [source], 1_000_000_000 + 5_100_000_000) is True
