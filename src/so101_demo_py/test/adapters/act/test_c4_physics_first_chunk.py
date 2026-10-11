"""Superseded by the removal of the per-chunk delivery-age rule: a chunk delivered while the Recorder's subscription is still matching can be arbitrarily late
(sequence 25 reached the callback 313 ms after its newest sample began and PHYSICS_RAW_CLOCK_INVALID closed the whole
episode;  a later run: sequence 58, 283 ms late, 26 chunks in). Under the old rule the first stale chunk was discarded and a later
one was a hazard. The user-authorized contract change removes the per-chunk delivery rule: a late chunk, first or not, is
admitted, audited and recorded as lateness; scope and continuity are still enforced."""
import copy
from types import SimpleNamespace

from test_act_raw_physics_chunks import _chunk

STALE_NS = 313_000_000


def adapter_at(now):
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    retained = []
    node = SimpleNamespace(create_subscription=lambda *args: 'owned', destroy_subscription=lambda value: None)
    adapter = RosEpisodePhysicsAdapter(node, session_id='live-source', reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=lambda value: retained.append(copy.deepcopy(value))),
        clock_ns=lambda: now[0])
    return adapter, retained


def test_a_late_first_chunk_is_admitted_audited_and_recorded():
    now = [10_000_000_000 + STALE_NS]
    adapter, retained = adapter_at(now)
    adapter.accept_message(_chunk(sequence=25, first=101, receipt=10_000_000_000))
    assert adapter.hazard is None
    assert adapter.receipt_diagnostics()["late_count"] == 1
    adapter.drain()
    assert [item["chunk"]["chunk_sequence"] for item in retained] == [25]
    now[0] += 10_000_000
    adapter.accept_message(_chunk(sequence=26, first=106, receipt=now[0]))
    adapter.drain()
    assert adapter.hazard is None and adapter.retained_step_range() == (101, 110)
    assert [item["chunk"]["chunk_sequence"] for item in retained] == [25, 26]


def test_a_late_chunk_after_the_first_is_admitted_too():
    now = [10_000_000_000]
    adapter, retained = adapter_at(now)
    adapter.accept_message(_chunk(sequence=25, first=101, receipt=10_000_000_000))
    now[0] += 10_000_000 + STALE_NS
    adapter.accept_message(_chunk(sequence=26, first=106, receipt=now[0]))
    adapter.drain()
    assert adapter.hazard is None and len(retained) == 2


def test_a_late_first_chunk_of_another_session_is_still_refused_for_its_scope():
    now = [10_000_000_000 + STALE_NS]
    adapter, _ = adapter_at(now)
    message = _chunk(sequence=25, first=101, receipt=10_000_000_000)
    message.simulation_session_id = 'other'
    adapter.accept_message(message)
    assert adapter.hazard == "PHYSICS_RAW_SCOPE_INVALID"
