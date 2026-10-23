"""L2 on W8BmUgyS wrote row 0's two PNGs and then failed with
RECORDER_QUEUE_WRITE_FAILED / writer_error = RecorderInfraError('RECORDER_WRITE_FAILED'): the wrapper hid the cause.

The wrapper is `EpisodeRecorder.append`: `except (OSError, ValueError, TypeError) as error: raise RecorderInfraError(...) from error`
around the PNG writes and `records.jsonl.write(_canonical(row))`. On this run the frames existed and records.jsonl was empty, so the
failing call is `_canonical(row)`: json.dumps(..., allow_nan=False). Everything else in the row is proven finite (chunk samples are
verified, the source alignment planning record and the JTC reference frames are in the audit), except the controller_state record the live
provider embeds: the original /joint_states message (`message_to_ordereddict`), whose velocity and effort arrays are NaN when the
joint_state_broadcaster has no such interface. Reproduced here with the real record builder and the real recorder."""
import json
import math
from types import SimpleNamespace

import pytest

from test_act_live_physical_audit import provider
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)

NAN_JOINT_STATE = dict(names=["1", "2", "3", "4", "5", "6", "neck_yaw_joint"])


def joint_state_message(stamp_ns):
    from sensor_msgs.msg import JointState
    message = JointState()
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(stamp_ns, 10**9)
    message.name = NAN_JOINT_STATE["names"]
    message.position = [0.1] * 7
    message.velocity = [0.0] * 7
    message.effort = [math.nan] * 7              # the broadcaster has no effort interface: NaN
    return message


def sources_with_history():
    from so101_demo.act.offline import sources as module
    sources = module.OfflineRosSources.__new__(module.OfflineRosSources)
    import collections
    import threading
    sources._counts = {"joint_states": 0}
    sources._controller_lock = threading.Lock()
    sources._joint_generation = 0
    sources._controller_history = collections.deque(maxlen=512)
    return sources


def test_a_joint_state_with_nan_effort_is_a_usable_controller_record_that_canonical_json_accepts():
    sources = sources_with_history()
    stamp = 14_118_000_000
    sources._on_joint_state(joint_state_message(stamp))
    record = sources._controller_source_at(stamp / 1e9)
    assert record is not None, "the record builder dropped a message only because an optional array is NaN"
    from so101_demo.act.recorder import _canonical
    _canonical(record)                                       # RED at L2: ValueError, out of range float values


def test_the_original_message_is_kept_faithfully_non_finite_values_are_tagged_not_lost():
    from so101_demo.act.nonfinite import restore_non_finite
    sources = sources_with_history()
    sources._on_joint_state(joint_state_message(14_118_000_000))
    original = sources._controller_source_at(14.118)["original_message"]
    assert original["effort"] == [{"__non_finite_float__": "nan"}] * 7
    assert original["position"] == [0.1] * 7 and original["name"] == NAN_JOINT_STATE["names"]
    restored = restore_non_finite(original)
    assert all(math.isnan(value) for value in restored["effort"]) and restored["velocity"] == [0.0] * 7


@pytest.mark.parametrize("value, tag", [(math.inf, "inf"), (-math.inf, "-inf"), (math.nan, "nan")])
def test_every_non_finite_float_round_trips_through_the_tag(value, tag):
    from so101_demo.act.nonfinite import json_safe, restore_non_finite
    safe = json_safe({"a": [value, 1.0, {"b": value}], "c": (value,)})
    assert safe == {"a": [{"__non_finite_float__": tag}, 1.0, {"b": {"__non_finite_float__": tag}}],
                    "c": [{"__non_finite_float__": tag}]}
    json.dumps(safe, allow_nan=False)
    again = restore_non_finite(safe)
    assert (math.isnan(again["a"][0]) if tag == "nan" else again["a"][0] == value)


def test_the_real_providers_row_with_that_controller_record_is_written_by_the_real_recorder(frozen_scene, tmp_path):
    from so101_demo.act.recorder import EpisodeRecorder
    from test_act_recorder import PROVENANCE, observation
    source, values, at_s = provider(frozen_scene)
    sources = sources_with_history()
    sources._on_joint_state(joint_state_message(round(at_s * 1e9)))
    values["controller"] = sources._controller_source_at(at_s)
    row = source(at_s)
    audit = dict(row, source_stamps={name: at_s for name in ("head", "wrist", "arm", "neck")},
                 reference_time_s=at_s + .1, reference_source="CONTROLLER_REFERENCE", reference_positions=[0.] * 6,
                 session_id="session-1", attempt_id="attempt-1", reset_epoch=2)
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="session-1", attempt_id="attempt-1", reset_epoch=2,
                               provenance=PROVENANCE)
    recorder.append(observation(at_s), (0.,) * 6, audit)
    stored = json.loads((tmp_path / "episode" / "records.jsonl").read_text().splitlines()[0])
    assert stored["audit"]["controller_state"]["original_message"]["effort"][0] == {"__non_finite_float__": "nan"}


# ---- the full exception chain of every writer and seal failure ------------------------------------------------------------

def test_the_exception_chain_names_every_link_and_the_innermost_frame():
    from so101_demo.act.exception_chain import describe_chain

    def innermost():
        raise ValueError("Out of range float values are not JSON compliant: nan")

    try:
        try:
            innermost()
        except ValueError as error:
            raise RuntimeError("RECORDER_WRITE_FAILED") from error
    except RuntimeError as outer:
        chain = describe_chain(outer)
    assert [link["type"] for link in chain["links"]] == ["RuntimeError", "ValueError"]
    assert chain["links"][1]["message"].startswith("Out of range float values")
    assert chain["links"][1]["relation"] == "cause" and chain["innermost_frame"].endswith(" innermost")
    assert "test_recorder_row_write_failure_cause.py" in chain["innermost_frame"]
    assert len(json.dumps(chain)) <= 2000


def test_a_chain_is_bounded_in_depth_message_length_and_survives_cycles():
    from so101_demo.act.exception_chain import describe_chain
    error = ValueError("x" * 5000)
    error.__cause__ = error                                      # a pathological cycle
    chain = describe_chain(error)
    assert len(chain["links"]) == 1 and len(chain["links"][0]["message"]) <= 300
    deep = None
    for index in range(20):
        new = RuntimeError(f"link {index}")
        new.__context__ = deep
        deep = new
    assert len(describe_chain(deep)["links"]) <= 6 and len(json.dumps(describe_chain(deep))) <= 2000


def test_the_queue_keeps_the_writers_whole_chain_not_the_wrapper(tmp_path):
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    from so101_demo.act.recorder import RecorderInfraError

    class Failing:
        root = tmp_path

        def append(self, *job):
            try:
                json.dumps({"x": math.nan}, allow_nan=False)
            except ValueError as error:
                raise RecorderInfraError("RECORDER_WRITE_FAILED") from error

        def close(self):
            pass

    policy = {"sample_rate_hz": 10, "queue_capacity_samples": 16, "queue_high_watermark_samples": 12,
              "queue_recovery_watermark_samples": 8, "queue_high_watermark_hold_s": 0.2, "lossless": True}
    queue = LosslessRecorderQueue(Failing(), policy=policy)
    try:
        queue.append({"sim_time_s": 1.0}, (0.,) * 6, {})
    except Exception:
        pass
    import time
    end = time.monotonic() + 3
    while queue.snapshot()["writer_error"] is None and time.monotonic() < end:
        time.sleep(0.01)
    text = queue.snapshot()["writer_error"]
    assert "RecorderInfraError" in text and "RECORDER_WRITE_FAILED" in text and "ValueError" in text and "nan" in text
    assert len(text) <= 2000
    queue.close()


def test_the_result_carries_the_chain_of_a_queue_failure_and_of_a_seal_failure(tmp_path):
    from test_act_episode_recorder import NOT_EXHAUSTED, build, result_of
    engine, sources, working = build(tmp_path)
    chain = '{"links":[{"type":"RecorderInfraError","message":"' + "w" * 700 + '"},{"type":"ValueError","message":"nan"}]}'
    engine.episode.capture.recorder = type("Q", (), {"snapshot": lambda self: {"writer_error": chain},
        "check": lambda self: None, "close": lambda self: None, "root": engine.episode.capture.recorder.root})()

    def failing(engine_):
        raise RuntimeError("RECORDER_QUEUE_WRITE_FAILED")

    sources.collect = failing
    engine.process(NOT_EXHAUSTED)
    reasons = result_of(working)["reasons"]
    assert reasons[0]["writer_error"] == chain, "up to 2000 characters, not the 300 of an ordinary fact"


def test_a_seal_failure_names_its_exception_chain(tmp_path):
    from test_act_episode_recorder import NOT_EXHAUSTED, build, result_of
    engine, sources, working = build(tmp_path)

    def broken_finish(*args, **kwargs):
        try:
            raise OSError(28, "No space left on device")
        except OSError as error:
            raise ValueError("EPISODE_SEAL_INVALID") from error

    engine.episode.finish = broken_finish
    engine.process(NOT_EXHAUSTED)
    seal = next(item for item in result_of(working)["reasons"] if item["reason"].startswith("RECORDER_SEAL_FAILED"))
    assert "OSError" in seal["exception_chain"] and "No space left" in seal["exception_chain"]
