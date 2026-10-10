"""Directed tests for the local owned search: shared state commit and channel.

The local search must keep its authoritative target/lock in the one shared
HeadLocalState so that a fault and the commit can never interleave, must refuse
a completed row from a foreign motion epoch, and must consume completed
observations through the local channel instead of the monitor exposure rows.
"""

from copy import deepcopy
from types import SimpleNamespace
import threading

import pytest

from so101_demo.act.head_evidence_identity import digest
from so101_demo.adapters.act.head_owned_search import OwnedHeadSearch
from test_act_head_local_observer import local_state, simulation_policy
from test_act_head_local_runtime import armed_runtime, runtime_setup
from test_act_head_owned_search import exposure
from test_act_search import BOX, config


class Owner:
    """Local inference owner exposing only the stopped-observation channel."""

    def __init__(self, rows):
        self.rows = rows
        self.infer_calls = 0
        self.requests = []

    def infer(self):
        self.infer_calls += 1

    def next_completed_observation(self, after_sequence):
        return next((deepcopy(row) for row in self.rows
                     if row['observation_sequence'] > after_sequence), None)

    def request_observation(self, request):
        self.requests.append(deepcopy(request))
        return deepcopy(request)


class Neck:
    def __init__(self, port, state, sent, clock):
        self.port, self.state, self.sent, self.clock = port, state, sent, clock

    def command_neck(self, target, **scope):
        gid = 'goal-%d' % (len(self.sent) + 1)
        # The shared state must already show the committed move at send time.
        self.sent.append(dict(goal_uuid=gid, target=target, scope=scope,
                              committed=self.state.search_state))
        self.port._goals[gid] = dict(accepted=None, result=None)
        return gid


def local_driver(*, faulted=False, controller_policy=None):
    policy = controller_policy or simulation_policy()
    state = local_state(policy)
    if faulted:
        state.latch_fault('HEAD_LOCAL_TEST_FAULTED')
    clock, faults, deadlines, events = [1.0], [], [], []
    port = SimpleNamespace(_lock=threading.Lock(), _goals={}, _head_samples=[])
    from test_act_head_feedback_freshness import policy as feedback_policy
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
            deadlines.append(value)

    rows, sent = [], []
    owner = Owner(rows)
    search = OwnedHeadSearch(config=config(), primary=Primary(), port=port, owner=owner,
                             settlement=lambda *a, **k: None, stop_velocity_rad_s=.01,
                             monotonic=lambda: clock[0],
                             emit=lambda event, **fields: events.append(dict(event=event, **fields)),
                             local_state=state, policy=policy)
    search.bind_transport(Neck(port, state, sent, clock))
    return SimpleNamespace(search=search, state=state, clock=clock, rows=rows, port=port,
                           events=events, sent=sent, deadlines=deadlines, faults=faults,
                           owner=owner, policy=policy)


def off_center_row(sequence=1, *, motion_epoch=0):
    row = exposure(sequence, detections=[dict(BOX, xyxy=[340., 200., 380., 280.])])
    row['motion_epoch'] = motion_epoch
    row['observation_sequence'] = sequence
    # A local completed observation always carries its own outcome.
    row['observation_outcome'] = 'VALID'
    return row


def test_local_search_commits_the_initial_target_into_the_shared_state():
    c = local_driver()
    state = c.state.search_state
    assert state['target_rad'] == pytest.approx(config()['search_start_rad'])
    assert state['motion_epoch'] == 0 and state['lock_count'] == 0
    assert state['reason'] == 'init'
    assert c.search._target == pytest.approx(state['target_rad'])


def test_initial_development_move_precedes_any_stopped_observation_request():
    c = local_driver()
    domain = (-.17559216195018026,.08047101126546086)
    c.search.controller.config['required_search_domain_rad'] = domain
    c.search.begin_development_move(domain[0])
    assert len(c.sent) == 1 and c.sent[0]['target'] == domain[0]
    assert c.sent[0]['committed']['motion_epoch'] == 1
    assert c.search._active['goal_uuid'] == c.sent[0]['goal_uuid']
    assert c.search.pending_observation_request is None and c.search.observations == []
    with pytest.raises(PermissionError): c.search.begin_development_move(domain[0])


@pytest.mark.parametrize('accepted', [None, True])
def test_stopped_request_waits_for_exact_move_terminal_and_three_advancing_samples(accepted):
    from so101_demo.act.head_feedback import bound_goal_settlement

    c = local_driver()
    requests = []
    c.owner.request_observation = lambda request: requests.append(deepcopy(request)) or deepcopy(request)
    c.search.settlement = bound_goal_settlement
    domain = (-.17559216195018026, .08047101126546086)
    c.search.controller.config['required_search_domain_rad'] = domain
    gid = c.search.begin_development_move(domain[0])
    c.port._goals[gid]['accepted'] = accepted
    assert c.search.tick() is None
    assert requests == []
    assert c.search.pending_observation_request is None
    assert not any(row['event'] == 'SEARCH_OBSERVATION_REQUESTED' for row in c.events)

    c.port._goals[gid].update(accepted=True,
        result=SimpleNamespace(status=4, result=SimpleNamespace(error_code=0)))
    assert c.search.tick() is None
    assert requests == []
    for index in range(1, 4):
        c.clock[0] += .01
        c.port._head_samples.append(dict(sequence=index, valid=True,
            source_ns=round(c.clock[0] * 1e9), wall_s=c.clock[0],
            positions=[domain[0]], velocities=[0.]))
        assert c.search.tick() is None
        if index < 3:
            assert requests == []
    assert len(requests) == 1
    assert requests[0]['settled_source_floor_ns'] == c.port._head_samples[-1]['source_ns']
    assert c.search._active is None


def test_direct_stopped_request_refuses_while_exact_move_is_pending():
    c = local_driver()
    requests = []
    c.owner.request_observation = lambda request: requests.append(deepcopy(request)) or deepcopy(request)
    domain = (-.17559216195018026, .08047101126546086)
    c.search.controller.config['required_search_domain_rad'] = domain
    c.search.begin_development_move(domain[0])
    with pytest.raises(PermissionError, match='HEAD_SEARCH_OBSERVATION_BEFORE_SETTLEMENT'):
        c.search._submit_observation_request()
    assert requests == []


@pytest.mark.parametrize('damage',['target','fault'])
def test_initial_development_move_refuses_wrong_endpoint_or_faulted_state(damage):
    c = local_driver()
    domain = (-.17559216195018026,.08047101126546086)
    c.search.controller.config['required_search_domain_rad'] = domain
    if damage == 'fault': c.state.latch_fault('TEST_INITIAL_FAULT')
    with pytest.raises(PermissionError):
        c.search.begin_development_move(domain[0] if damage == 'fault' else domain[1])
    assert c.sent == []


def test_local_search_commits_the_move_before_the_transport_sees_it():
    c = local_driver()
    assert c.search.tick() is None
    c.rows.append(off_center_row(1))
    c.clock[0] = c.rows[-1]['image_received_wall_s'] + .01
    assert c.search.tick() is None
    assert len(c.sent) == 1
    sent = c.sent[0]
    assert sent['committed']['motion_epoch'] == 1
    assert sent['committed']['reason'] == 'dispatch'
    assert sent['committed']['target_rad'] == pytest.approx(sent['target'])
    assert sent['committed']['source_ns'] == c.rows[-1]['source_ns']
    assert c.search.search_state['motion_epoch'] == 1
    assert c.state.inventory == {}


def test_local_search_refuses_a_move_when_the_shared_state_is_faulted():
    c = local_driver()
    c.state.latch_fault('HEAD_LOCAL_TEST_FAULTED')
    c.rows.append(off_center_row(1))
    c.clock[0] = c.rows[-1]['image_received_wall_s'] + .01
    before = c.state.search_state
    with pytest.raises(PermissionError):
        c.search.tick()
    assert c.sent == []
    assert c.state.search_state == before
    assert c.state.snapshot['fault']['reason'] == 'HEAD_LOCAL_TEST_FAULTED'
    assert c.faults


def test_local_search_refuses_a_completed_row_from_a_foreign_motion_epoch():
    c = local_driver()
    assert c.search.tick() is None
    c.rows.append(off_center_row(1, motion_epoch=0))
    c.clock[0] = c.rows[-1]['image_received_wall_s'] + .01
    assert c.search.tick() is None
    before = c.state.search_state
    # The committed move advanced the epoch to 1, so a row claiming epoch 0 is foreign.
    c.rows.append(off_center_row(2, motion_epoch=0))
    c.clock[0] = c.rows[-1]['image_received_wall_s'] + .01
    with pytest.raises(PermissionError):
        c.search.tick()
    assert c.state.search_state == before
    assert len(c.sent) == 1


def test_local_search_consumes_only_the_local_observation_channel():
    c = local_driver()
    assert c.search.tick() is None
    assert not hasattr(c.owner, 'next_completed_exposure')
    c.rows.append(off_center_row(1))
    c.clock[0] = c.rows[-1]['image_received_wall_s'] + .01
    assert c.search.tick() is None
    assert len(c.sent) == 1 and c.owner.infer_calls >= 1


def test_local_search_commits_a_lock_only_for_a_locked_target():
    c = local_driver()
    for sequence in (1, 2, 3):
        assert c.search.tick() is None
        row = exposure(sequence)
        row['observation_sequence'] = sequence
        row['motion_epoch'] = 0
        row['observation_outcome'] = 'VALID'
        c.rows.append(row)
        c.clock[0] = row['image_received_wall_s'] + .01
        result = c.search.tick()
    assert result['status'] == 'TARGET_LOCKED'
    state = c.state.search_state
    assert state['lock_count'] == 3 and state['reason'] == 'lock'
    assert state['motion_epoch'] == 0 and state['target_rad'] == pytest.approx(
        config()['search_start_rad'])
    assert c.sent == []


def test_local_search_accepts_the_real_local_runtime_as_primary(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    clock, events, sent = [row.runtime.monotonic()], [], []
    port = SimpleNamespace(_lock=threading.Lock(), _goals={}, _head_samples=[])
    port.feedback_policy = row.port.feedback_policy
    port.feedback_snapshot = row.port.feedback_snapshot
    owner = Owner([])
    search = OwnedHeadSearch(config=config(), primary=runtime, port=port, owner=owner,
                             settlement=lambda *a, **k: None, stop_velocity_rad_s=.01,
                             monotonic=row.runtime.monotonic,
                             emit=lambda event, **fields: events.append(event),
                             local_state=row.state, policy=row.policy)
    assert search.search_state['target_rad'] == pytest.approx(config()['search_start_rad'])
    assert runtime.ready is True and runtime.failed is False
    runtime.fault('HEAD_LOCAL_TEST_SEARCH_BOUND')
    with pytest.raises(PermissionError):
        search.tick()
    runtime.close(timeout_s=1.)
