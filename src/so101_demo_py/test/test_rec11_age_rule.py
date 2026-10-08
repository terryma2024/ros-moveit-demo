"""Recorder round 11 (CP-3420): L2 on VeUKeAls wrote row 0 and failed on row 1 with RECORDER_QUEUE_WRITE_FAILED, writer_error
ValueError EPISODE_SOURCE_STALE at recorder.py:184 `_audit`.

Row 1 is the instant 11.9 s. The provider that minted it admits a source whose age is within 100 ms in INTEGER NANOSECONDS
(`round(stamp * 1e9)`), as the capture, the synchronizer and the endpoints do. The recorder's own audit compared FLOAT seconds:
`0 <= t - stamp <= 0.1`. A physics sample stamped 11.799999999999 s is 100,000,000 ns old (accepted by the provider) and
0.100000000001 s old in floats (refused by the recorder). Every sample time of the physics plugin is `step * 0.002` in
floating point, so a step landing exactly 100 ms before the instant fails this way by rounding noise alone. One rule now.
"""
import json

import numpy as np
import pytest

from so101_demo.act.recorder import EpisodeRecorder
from test_act_live_physical_audit import provider
from test_act_recorder import PROVENANCE, audit, observation
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)

AT = 11.9
LIMIT_NS = 100_000_000
# (age in ns, admitted): the boundary and one nanosecond either side, in the order the layers must agree on
CASES = [(0, True), (99_999_999, True), (LIMIT_NS, True), (LIMIT_NS + 1, False), (-1, False)]


def stamp_at_age(at_s, age_ns):
    """The float stamp whose integer-nanosecond age at `at_s` is `age_ns`, with the rounding noise a step*dt product has."""
    return (round(at_s * 1e9) - age_ns) / 1e9 - 5e-13


def recorder(tmp_path, name="episode"):
    return EpisodeRecorder(tmp_path / name, session_id="session-1", attempt_id="attempt-1", reset_epoch=2,
                           provenance=PROVENANCE)


def append_with(tmp_path, stamps, *, physical=True):
    row = audit(AT)
    key = "physical_stamps" if physical else "source_stamps"
    row[key] = dict(row[key], **stamps)
    try:
        recorder(tmp_path, f"episode-{abs(hash(json.dumps(stamps, sort_keys=True)))}").append(
            observation(AT), (0.,) * 6, row)
        return True
    except ValueError as error:
        assert "EPISODE_SOURCE_STALE" in str(error), error
        return False


def test_the_exact_failure_a_physics_sample_exactly_100_ms_old_with_float_noise_is_refused_by_the_old_float_rule(tmp_path):
    stamp = 11.799999999999
    assert AT - stamp > 0.1, "in floats the sample looks older than 100 ms"
    assert round(AT * 1e9) - round(stamp * 1e9) == LIMIT_NS, "in nanoseconds it is exactly at the limit"
    assert append_with(tmp_path, {"cup": stamp, "contacts": stamp}) is True


@pytest.mark.parametrize("age_ns,admitted", CASES)
def test_the_recorder_admits_exactly_what_the_provider_admits(tmp_path, frozen_scene, age_ns, admitted):
    """The SAME synthetic instant, one source at each boundary age, through the provider and through the recorder."""
    source, values, at_s = provider(frozen_scene)
    stamp_ns = round(at_s * 1e9)                       # the fixture's physics, planning and controller stamps
    assert source.ready((stamp_ns + age_ns) / 1e9) is admitted, "provider: every source is age_ns old at that instant"
    stamp = stamp_at_age(AT, age_ns)
    assert append_with(tmp_path, {"cup": stamp}) is admitted, "recorder, physical stamp"
    assert append_with(tmp_path, {"arm": stamp}, physical=False) is admitted, "recorder, joint-state stamp"


@pytest.mark.parametrize("age_ns,admitted", CASES)
def test_the_capture_and_the_synchronizer_admit_the_same_boundary_ages(age_ns, admitted):
    from so101_demo.act.synchronizer import causal_sample, source_age_ok_ns
    assert source_age_ok_ns(round(AT * 1e9), round(AT * 1e9) - age_ns) is admitted
    stamp = stamp_at_age(AT, age_ns)
    try:
        causal_sample([(stamp, "value")], AT, 0.1)
        sync = True
    except ValueError:
        sync = False
    assert sync is admitted
    from test_act_continuous_capture import build, feed, start
    capture, minter = build()
    start(capture, start_s=1.0)
    feed(capture, minter, camera="head", stamp_s=stamp, session="s")
    assert (capture._causal("head", AT) is not None) is admitted


@pytest.mark.parametrize("age_ns,admitted", CASES)
def test_the_audit_binding_check_never_refuses_what_the_provider_admits(age_ns, admitted):
    """QC's causality check keeps its 1 microsecond tolerance: it may be looser than the provider, never tighter."""
    from so101_demo.act import episode_audit
    age_s = (round(AT * 1e9) - round(stamp_at_age(AT, age_ns) * 1e9)) / 1e9
    qc_ok = not (age_s < -episode_audit._TOLERANCE_S or age_s > episode_audit._MAX_SOURCE_AGE_S + episode_audit._TOLERANCE_S)
    assert qc_ok or not admitted


# ---- a failure in one drain stage never stops the others ------------------------------------------------------------------

def stage_sources(*, world_error=None):
    from types import SimpleNamespace
    from so101_demo.ros.episode_recorder_sources import RosRecorderSources
    sources = RosRecorderSources.__new__(RosRecorderSources)
    calls = []
    sources.binding = SimpleNamespace(drain_sources=lambda: calls.append("physics"))

    def drain_world():
        calls.append("world")
        if world_error is not None:
            raise RuntimeError(world_error)

    sources.host = SimpleNamespace(_world_record_cursor=10, _drain_world_sources=drain_world,
                                   _step_data_initial_boundary=lambda: calls.append("initial"))
    sources.episode = SimpleNamespace(capture=SimpleNamespace(started=True))
    sources.world = SimpleNamespace(retained_with_receipts=lambda: (
        SimpleNamespace(evidence=SimpleNamespace(publisher_sequence=40)),))
    sources._service_associations = lambda engine: calls.append("associations")
    return sources, calls


def test_a_world_join_failure_still_services_the_associations_and_moves_the_cursor_on():
    from types import SimpleNamespace
    sources, calls = stage_sources(world_error="DYNAMIC_WORLD_SOURCE_SCENE_MISSING")
    latched = []
    engine = SimpleNamespace(latch=latched.append, telemetry=None)
    with pytest.raises(RuntimeError, match="SCENE_MISSING"):
        sources._drain_stages(engine)
    assert calls == ["physics", "world", "initial", "associations"], "every stage ran"
    assert sources.host._world_record_cursor == 40, "the same record is not raised every pass until it is evicted"


def test_two_failing_stages_both_reach_the_verdict():
    from types import SimpleNamespace
    sources, calls = stage_sources(world_error="WORLD_FAILED")
    sources._service_associations = lambda engine: (_ for _ in ()).throw(RuntimeError("ASSOCIATION_FAILED"))
    latched = []
    engine = SimpleNamespace(latch=latched.append, telemetry=None)
    with pytest.raises(RuntimeError, match="WORLD_FAILED"):
        sources._drain_stages(engine)
    assert latched == ["ASSOCIATION_FAILED"]
