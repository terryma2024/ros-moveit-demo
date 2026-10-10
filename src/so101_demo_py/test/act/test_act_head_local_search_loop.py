"""Directed tests for the local stopped-demand search loop.

The loop must build the frozen schema-1 observation request from the committed
state, never submit a second job while one is outstanding, charge a discarded
completion to the one original retry budget without moving the target or the
lock, and terminate as a failure when that budget is exhausted.
"""

from copy import deepcopy
from types import SimpleNamespace
import threading

import pytest

import itertools

from so101_demo.act.head_evidence_identity import digest
from so101_demo.act.head_local_state import HeadLocalState
from so101_demo.adapters.act.head_owned_search import OwnedHeadSearch
from test_act_head_feedback_freshness import policy as feedback_policy
from test_act_head_local_observer import simulation_policy
from test_act_head_owned_search import exposure
from test_act_search import BOX, config


class LocalOwner:
    """Local inference owner with the stopped-observation request channel."""

    def __init__(self):
        self.requests = []
        self.rows = []
        self.infer_calls = 0

    def infer(self):
        self.infer_calls += 1

    def request_observation(self, request):
        self.requests.append(deepcopy(request))
        return deepcopy(request)

    def next_completed_observation(self, after_sequence):
        return next((deepcopy(row) for row in self.rows
                     if row['observation_sequence'] > after_sequence), None)


class Neck:
    def __init__(self, port, sent):
        self.port, self.sent = port, sent

    def command_neck(self, target, **scope):
        gid = 'goal-%d' % (len(self.sent) + 1)
        self.sent.append(dict(goal_uuid=gid, target=target, scope=scope))
        self.port._goals[gid] = dict(accepted=None, result=None)
        return gid


_SEQUENCE = itertools.count(1)


def loop_state(policy, *, now, timeout_s=30., clock=None):
    """A coherent local state whose search deadline matches the driver wall clock."""
    sequence = next(_SEQUENCE)
    scope = dict(epoch='loop-epoch-%d' % sequence, generation=7,
                 session_id='loop-session-%d' % sequence,
                 policy_sha256=digest(policy.readback()),
                 controller_identity=dict(generation=7, incarnation='inc-1', boot='boot-1'))
    deadline = round((now + timeout_s) * 1e9)
    if clock is None:
        return HeadLocalState(scope, deadline)
    return HeadLocalState(scope, deadline, clock_ns=lambda: round(clock[0] * 1e9))


def loop_driver(policy=None):
    policy = simulation_policy() if policy is None else policy
    clock, faults, events = [1.0], [], []
    state = loop_state(policy, now=clock[0], clock=clock)
    port = SimpleNamespace(_lock=threading.Lock(), _goals={}, _head_samples=[])
    port.feedback_policy = feedback_policy()
    port.feedback_snapshot = lambda: dict(
        sequence=1, valid=True, positions=[0.], velocities=[0.], wall_s=clock[0],
        source_ns=round(clock[0] * 1e9),
        decision=dict(sim_ns=round(clock[0] * 1e9), sim_s=clock[0], wall_before_s=clock[0],
                      wall_after_s=clock[0]))

    class Primary:
        def dispatch_guard(self):
            return True

        def fault(self, *args):
            faults.append(args)

        def dispatch_observation_deadline(self, value):
            pass

    owner, sent = LocalOwner(), []
    search = OwnedHeadSearch(config=config(), primary=Primary(), port=port, owner=owner,
                             settlement=lambda *a, **k: None, stop_velocity_rad_s=.01,
                             monotonic=lambda: clock[0],
                             emit=lambda event, **fields: events.append(dict(event=event, **fields)),
                             local_state=state, policy=policy)
    search.bind_transport(Neck(port, sent))
    return SimpleNamespace(search=search, state=state, owner=owner, policy=policy, clock=clock,
                           events=events, sent=sent, faults=faults)


def prepared_record(driver, message, goal_uuid, cdr):
    """A real prepared record whose claim window lives in the driver's clock domain."""
    import hashlib
    import json
    import uuid
    from rosidl_runtime_py.convert import message_to_ordereddict
    claim = round((driver.clock[0] - .001) * 1e9)
    scope = driver.state.scope
    return dict(goal_uuid=str(uuid.UUID(bytes=bytes(goal_uuid.uuid))),
        typed_goal=json.loads(json.dumps(message_to_ordereddict(message))),
        payload_sha256=hashlib.sha256(cdr).hexdigest(), generation=scope['generation'],
        controller_identity=dict(scope['controller_identity']), attempt_epoch=scope['epoch'],
        session_id=scope['session_id'], role='neck', operation_sequence=1,
        claim_monotonic_ns=claim, deadline_ns=claim + 400_000_000)


def valid_row(sequence=1, *, motion_epoch=0, q=0., detections=None):
    row = exposure(sequence, q=q, detections=detections)
    row['observation_sequence'] = sequence
    row['motion_epoch'] = motion_epoch
    row['observation_outcome'] = 'VALID'
    return row


def discarded_row(sequence, outcome, *, motion_epoch=0):
    row = exposure(sequence)
    row['observation_sequence'] = sequence
    row['sequence'] = None
    row['motion_epoch'] = motion_epoch
    row['observation_outcome'] = outcome
    row['detections'] = []
    return row


@pytest.mark.parametrize('outcome', ['EXPIRED', 'SHORT_DROP'])
def test_discard_then_valid_uses_distinct_request_and_admitted_counters(outcome):
    c = loop_driver()
    c.search.tick()
    c.owner.rows.append(discarded_row(1, outcome))
    c.clock[0] = 1.01
    assert c.search.tick() is None
    row = valid_row(1)
    row['observation_sequence'] = 2
    c.owner.rows.append(row)
    c.clock[0] = 1.02
    assert c.search.tick() is None
    assert c.search.controller.lock_count == 1
    assert c.search.observations[0]['sequence'] == 1
    assert c.search.tick() is None
    assert c.owner.requests[-1]['observation_sequence'] == 3
    assert c.search.controller.lock_count == 1
    assert c.faults == [] and c.sent == []


def test_valid_completion_expired_at_consumer_reobserves_without_state_commit():
    c = loop_driver()
    c.search.tick()
    c.owner.rows.append(valid_row(1, detections=[off_center()]))
    before = c.state.search_state
    c.clock[0] = 1.15
    assert c.search.tick() is None
    assert c.state.search_state == before
    assert c.search.controller.lock_count == 0 and c.search.controller.track is None
    assert c.search.observations == [] and c.sent == [] and c.faults == []
    assert c.search.observation_budget['reobservations_total'] == 1
    assert c.owner.requests[-1]['observation_sequence'] == 2


def off_center(**kwargs):
    return dict(BOX, xyxy=[340., 200., 380., 280.])


def test_valid_completion_expiring_during_core_does_not_commit_candidate(monkeypatch):
    c = loop_driver()
    c.search.tick()
    before = c.state.search_state
    original_tick = type(c.search.controller).tick

    def delayed_tick(controller, *args, **kwargs):
        result = original_tick(controller, *args, **kwargs)
        c.clock[0] = 1.15
        return result

    monkeypatch.setattr(type(c.search.controller), 'tick', delayed_tick)
    c.owner.rows.append(valid_row(1, detections=[off_center()]))
    assert c.search.tick() is None
    assert c.state.search_state == before
    assert c.search.controller.lock_count == 0 and c.search.controller.track is None
    assert c.search.observations == [] and c.sent == [] and c.faults == []
    assert c.search.observation_budget['reobservations_total'] == 1
    assert c.owner.requests[-1]['observation_sequence'] == 2


def test_local_search_submits_one_frozen_observation_request():
    c = loop_driver()
    scope = c.state.scope
    assert c.search.tick() is None
    assert len(c.owner.requests) == 1
    request = c.owner.requests[0]
    assert (request['epoch'], request['generation'], request['session_id']) == (
        scope['epoch'], scope['generation'], scope['session_id'])
    assert request['policy_sha256'] == scope['policy_sha256']
    assert request['simulation_policy_sha256'] == digest(c.policy.readback())
    assert request['schema_version'] == 1
    assert request['motion_epoch'] == 0
    assert request['observation_sequence'] == 1
    assert request['search_deadline_ns'] == c.state.search_deadline_ns
    assert request['settled_source_floor_ns'] >= 1
    assert request['settled_wall_s'] <= request['requested_wall_s'] <= c.clock[0]
    assert c.search.pending_observation_request['observation_sequence'] == 1
    assert c.search.observation_budget['reobservations_total'] == 0


def test_local_search_never_submits_a_second_job_while_one_is_outstanding():
    c = loop_driver()
    assert c.search.tick() is None
    assert c.search.tick() is None
    assert c.search.tick() is None
    assert len(c.owner.requests) == 1


def test_local_search_discards_an_expired_row_and_reobserves_without_moving():
    c = loop_driver()
    c.search.tick()
    before = c.state.search_state
    c.owner.rows.append(discarded_row(1, 'EXPIRED'))
    c.clock[0] = 1.5
    assert c.search.tick() is None
    assert c.state.search_state == before
    assert len(c.owner.requests) == 2
    assert c.owner.requests[1]['observation_sequence'] == 2
    assert c.search.observation_budget['reobservations_total'] == 1
    assert c.search.observation_budget['per_stop'] == {0: 1}
    assert c.sent == [] and c.faults == []


# MISS stays a valid budget reason but this loop cannot produce it: the owner
# refuses a replacement while a job is outstanding, and a stalled job is
# closed by the runtime inference deadline instead.
@pytest.mark.parametrize('outcome', ['EXPIRED', 'SHORT_DROP'])
def test_local_search_exhausts_the_reobservation_budget_as_a_failure(outcome):
    c = loop_driver()
    for sequence in range(1, 5):
        c.search.tick()
        c.owner.rows.append(discarded_row(sequence, outcome))
        c.clock[0] = 1.0 + sequence * .1
        result = c.search.tick()
    assert result is not None
    assert result['status'] == 'SEARCH_OBSERVATION_BUDGET_EXHAUSTED' and result['found'] is False
    assert c.search.observation_budget['reobservations_total'] == 3
    assert c.search.observation_budget['per_stop'] == {0: 3}
    state = c.state.search_state
    assert state['lock_count'] == 0 and state['motion_epoch'] == 0
    assert c.sent == []
    assert c.faults and c.faults[-1][0] == 'HEAD_SEARCH_SEARCH_OBSERVATION_BUDGET_EXHAUSTED'


def test_local_search_request_follows_the_committed_move_epoch():
    from test_act_head_prepared_sdk import prepared
    from so101_demo.act.head_feedback import bound_goal_settlement
    c = loop_driver()
    c.search.tick()
    c.owner.rows.append(valid_row(1, motion_epoch=0, detections=[off_center()]))
    c.clock[0] = c.owner.rows[-1]['image_received_wall_s'] + .01
    assert c.search.tick() is None
    assert len(c.sent) == 1
    assert c.state.search_state['motion_epoch'] == 1
    # A real dispatched move registers one prepared goal, which is what the
    # exposure and the owner compare the request's motion epoch against.
    message, goal_uuid, cdr = prepared()
    c.state.register_prepared(prepared_record(c, message, goal_uuid, cdr), cdr)
    assert len(c.state.inventory) == 1
    assert c.search.tick() is None
    assert len(c.owner.requests) == 1
    gid = c.sent[0]['goal_uuid']
    c.search.port._goals[gid].update(accepted=True,
        result=SimpleNamespace(status=4, result=SimpleNamespace(error_code=0)))
    c.search.settlement = bound_goal_settlement
    assert c.search.tick() is None
    for index in range(1, 4):
        c.clock[0] += .01
        c.search.port._head_samples.append(dict(sequence=index, valid=True,
            source_ns=round(c.clock[0] * 1e9), wall_s=c.clock[0],
            positions=[c.search._target], velocities=[0.]))
        assert c.search.tick() is None
        if index < 3:
            assert len(c.owner.requests) == 1
    request = c.owner.requests[-1]
    assert len(c.owner.requests) == 2
    assert request['motion_epoch'] == 1 and request['observation_sequence'] == 2
    assert request['search_deadline_ns'] == c.state.search_deadline_ns
