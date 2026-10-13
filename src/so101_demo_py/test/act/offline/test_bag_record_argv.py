"""How the bag recorder subscribes. Experiment 583 (the stock `ros2 bag record --log-level debug`) wrote 42 MB / 500 000 lines of
rcl `Subscription taking serialized message` debug lines per episode into the log of the process that also takes the messages; the
scoped recorder it replaced raised only its own logger. The subscription itself (QoS file, cache, storage, topics) must stay what
the scoped recorder used."""
import sys

import pytest

from so101_demo.act.offline.raw_recorder import DEEP_RELIABLE, TOPICS, RECORDER_LOG_LEVEL, record_argv, qos_overrides_for


def test_the_recorder_argv_runs_the_stock_verb_without_a_global_debug_level():
    argv = record_argv("/b/bag", "/b/bag-qos.yaml", "so101_raw_recorder", TOPICS)
    assert argv[:3] == [sys.executable, "-m", "so101_demo.act.offline.bag_record_entry"]
    assert "--log-level" not in argv, "a process-wide DEBUG level prints two rcl lines per taken message"
    assert RECORDER_LOG_LEVEL == "debug"     # applied by the entry to the recorder's own logger only
    assert argv[argv.index("-s") + 1] == "mcap" and argv[argv.index("-o") + 1] == "/b/bag"
    assert argv[argv.index("--node-name") + 1] == "so101_raw_recorder"
    assert argv[argv.index("--max-cache-size") + 1] == str(256 * 1024 * 1024)
    assert argv[argv.index("--qos-profile-overrides-path") + 1] == "/b/bag-qos.yaml"
    assert "--disable-keyboard-controls" in argv
    assert argv[argv.index("--topics") + 1:] == list(TOPICS), "topics named explicitly, not the deprecated positional list"
    for absent in ("--compression-mode", "--use-sim-time", "--include-unpublished-topics", "--storage-preset-profile"):
        assert absent not in argv


def test_every_deep_topic_is_subscribed_with_the_scoped_recorders_profile():
    """The scoped recorder accepted exactly {history keep_last, reliability reliable, durability volatile, depth > 0} per topic."""
    overrides = qos_overrides_for(TOPICS)
    assert set(overrides) == set(DEEP_RELIABLE) & set(TOPICS)
    for topic, profile in overrides.items():
        assert profile == {"history": "keep_last", "depth": DEEP_RELIABLE[topic], "reliability": "reliable",
                           "durability": "volatile"}
    assert overrides["/clock"]["depth"] == 20000 and overrides["/head_camera/color"]["depth"] == 50


def test_the_entry_keeps_the_global_level_at_info_and_raises_only_the_recorders_logger():
    from so101_demo.act.offline.bag_record_entry import _recorder_class

    seen = {}

    class Base:
        def __init__(self, storage, options, log_level, node_name):
            seen["init"] = (storage, options, log_level, node_name)

    levels = []
    recorder = _recorder_class(Base, lambda name, level: levels.append((name, level)), "DEBUG")("s", "o", "debug", "rec")
    assert isinstance(recorder, Base)
    assert seen["init"] == ("s", "o", "info", "rec"), "the verb's own debug request must not reach the process"
    assert levels == [("rec", "DEBUG")]
