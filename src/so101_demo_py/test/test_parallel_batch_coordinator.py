"""Offline scheduling boundaries using a real durable journal and fake time."""

import importlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from so101_demo.parallel_batch.contracts import BatchRequest, RunMode, load_parallel_runtime_config
from so101_demo.parallel_batch.journal import CoordinatorJournal


class Clock:
    """Monotonic test clock; no sleep is needed for deadline cases."""

    now = 0.0

    def __call__(self):
        """Return the chosen timestamp."""
        return self.now


class Results:
    """Sealed-artifact boundary, deliberately separate from journal persistence."""

    def __init__(self):
        """Keep registered immutable-result fixtures."""
        self.sealed = {}

    def verify(self, lease, location, run_mode):
        """Reject a seal from another attempt."""
        entry = self.sealed.get(str(location))
        if entry is None or entry[0] != lease.attempt_id:
            raise ValueError('unverified result')
        return {'status': entry[1], 'sha256': 'a' * 64}

    def discover(self, lease, workspace):
        """Discover only the reserved workspace's sealed artifact."""
        location = str(workspace / 'sealed')
        return location if location in self.sealed else None


@pytest.fixture
def make(tmp_path):
    """Create isolated coordinators and release every real journal lock."""
    journals = []

    def factory(points=('p1', 'p2'), workers=1, k=3, mode=RunMode.EXECUTE):
        module = importlib.import_module('so101_demo.parallel_batch.coordinator')
        root = tmp_path / str(len(journals))
        journal = CoordinatorJournal.create(root, 'batch-a')
        journals.append(journal)
        request = BatchRequest('batch-a', mode, points, workers, k, root)
        clock, results = Clock(), Results()
        config = load_parallel_runtime_config(
            Path(__file__).resolve().parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
        coordinator = module.BatchCoordinator(
            journal, request, config=config, clock=clock, result_port=results)
        for i in range(workers):
            coordinator.register_worker(f'w{i + 1}', generation=1)
        return coordinator, clock, results, journal, request

    yield factory
    for journal in journals:
        journal.close()


def start(c, worker='w1'):
    """Obtain both durable ACKs before executing a point."""
    lease = c.grant_lease(worker, generation=1)
    c.ack_lease(lease, request_key=f'ack-{lease.attempt_id}')
    c.ack_attempt_started(lease, request_key=f'start-{lease.attempt_id}')
    return lease


def test_available_worker_receives_first_selected_point(make):
    """Available capacity must grant the first frozen selection."""
    c, *_ = make()
    lease = c.grant_lease('w1', generation=1)
    assert lease is not None, 'Available capacity must grant the next selected point'
    assert lease.point_id == 'p1'


def seal(c, results, lease, status):
    """Register evidence under the journal-reserved attempt workspace."""
    location = str(c.snapshot().workers[lease.worker_id].workspace / 'sealed')
    results.sealed[location] = (lease.attempt_id, status)
    return location


def finish(c, results, lease, status):
    """Commit a verified result through the public physical boundary."""
    return c.commit_result(lease, seal(c, results, lease, status),
                           request_key=f'result-{lease.attempt_id}')


@pytest.mark.parametrize('status', ['PASSED', 'FAILED', 'INDETERMINATE'])
def test_terminal_point_never_requeued_and_recovered_worker_steals_next(make, status):
    """A spent point stays terminal while the recovered slot takes fresh work."""
    c, _, results, _, _ = make()
    lease = start(c)
    finish(c, results, lease, status)
    c.record_recovery('w1', generation=1, succeeded=True)
    second = c.grant_lease('w1', generation=1)
    assert second.point_id == 'p2'
    assert c.snapshot().workers['w1'].lease_count == 2
    assert c.snapshot().points['p1'].status == status


def test_concurrent_grants_do_not_double_lease(make):
    """Two simultaneous grants must reserve different points."""
    c, *_ = make(workers=2)
    with ThreadPoolExecutor(2) as pool:
        leases = list(pool.map(lambda w: c.grant_lease(w, generation=1), ['w1', 'w2']))
    assert {lease.point_id for lease in leases} == {'p1', 'p2'}


def test_journal_fsync_precedes_grant_projection_and_ack(make, monkeypatch):
    """Durable grant ACK cannot escape while journal fsync is pending."""
    c, _, _, journal, _ = make()
    entered, release = threading.Event(), threading.Event()
    real_fsync = os.fsync

    def block(fd):
        if Path(f'/proc/self/fd/{fd}').resolve() == journal.segment_path:
            entered.set()
            assert release.wait(5)
        real_fsync(fd)

    monkeypatch.setattr(os, 'fsync', block)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(c.grant_lease, 'w1', generation=1)
        assert entered.wait(5)
        assert not future.done()
        release.set()
        assert future.result().point_id == 'p1'
    assert c.snapshot().workers['w1'].lease_count == 1


@pytest.mark.parametrize('stage', ['LEASED', 'INITIALIZING'])
def test_missing_start_ack_cannot_authorize_next_stage(make, stage):
    """Five seconds without a heartbeat must revoke reset or action authorization."""
    c, clock, *_ = make()
    lease = c.grant_lease('w1', generation=1)
    if stage == 'INITIALIZING':
        c.ack_lease(lease, request_key='grant-ack')
    clock.now = 5
    c.tick()
    with pytest.raises(ValueError):
        if stage == 'LEASED':
            c.ack_lease(lease, request_key='late')
        else:
            c.ack_attempt_started(lease, request_key='late')
    assert not c.snapshot().workers['w1'].action_allowed


@pytest.mark.parametrize('field,value', [('worker_generation', 2), ('coordinator_epoch', 99),
                                         ('lease_generation', 99)])
def test_stale_identity_rejected_without_k_debit(make, field, value):
    """Every fencing dimension rejects stale requests without spending K."""
    c, *_ = make()
    lease = c.grant_lease('w1', generation=1)
    with pytest.raises(ValueError):
        c.ack_lease(replace(lease, **{field: value}), request_key='bad')
    assert c.snapshot().workers['w1'].lease_count == 1


def test_invalid_requires_all_fencing_gates_before_requeue(make):
    """An INVALID point waits for safe recovery while other points proceed."""
    c, _, results, *_ = make(workers=2)
    lease = start(c)
    finish(c, results, lease, 'INVALID')
    with pytest.raises(ValueError):
        c.record_recovery('w1', generation=1, succeeded=True)
    assert c.grant_lease('w2', generation=1).point_id == 'p2'
    c.record_recovery('w1', generation=1, succeeded=True, fenced=True,
                      owned_processes_stopped=True, controllers_stopped=True, readmitted=True)
    assert c.grant_lease('w1', generation=1).point_id == 'p1'


def test_broker_unhealthy_pauses_without_debit(make):
    """Broker loss must pause admission without consuming a slot."""
    c, *_ = make()
    c.mark_broker_health(False)
    assert c.grant_lease('w1', generation=1) is None
    assert c.snapshot().workers['w1'].lease_count == 0
    c.mark_broker_health(True)
    assert c.grant_lease('w1', generation=1).point_id == 'p1'


def test_capacity_exhaustion_waits_for_inflight_and_recoverable_worker(make):
    """Drain every executable point before marking unused selections UNRUN."""
    c, _, results, *_ = make(points=('p1', 'p2', 'p3'), workers=2, k=2)
    lease = start(c)
    c.record_recovery('w2', generation=1, succeeded=False)
    assert c.snapshot().terminal_reason is None
    finish(c, results, lease, 'FAILED')
    assert c.snapshot().terminal_reason is None
    c.record_recovery('w1', generation=1, succeeded=True)
    lease2 = start(c)
    assert lease2.point_id == 'p2'
    finish(c, results, lease2, 'PASSED')
    assert c.snapshot().terminal_reason == 'CAPACITY_EXHAUSTED'
    assert not c.snapshot().points['p3'].terminal
    c.complete_cleanup(owned_processes_stopped=True, controllers_stopped=True)
    assert c.snapshot().points['p3'].terminal
    assert c.snapshot().points['p3'].status == 'UNRUN'


def test_last_pass_does_not_qualify_before_cleanup(make):
    """Physical success cannot qualify a batch with unfinished cleanup."""
    c, _, results, *_ = make(points=('p1',))
    finish(c, results, start(c), 'PASSED')
    assert not c.snapshot().summary.qualification_passed
    c.complete_cleanup(owned_processes_stopped=True, controllers_stopped=True)
    assert c.snapshot().summary.qualification_passed


@pytest.mark.parametrize('mode', [RunMode.DRY_RUN, RunMode.PLAN_ONLY])
@pytest.mark.parametrize('status', ['VALIDATION_PASSED', 'VALIDATION_FAILED',
                                    'VALIDATION_INVALID'])
def test_validation_has_separate_events_status_and_no_physical_qualification(make, mode, status):
    """Validation results cannot become physical qualification evidence."""
    c, _, results, journal, _ = make(points=('p1',), mode=mode)
    lease = c.grant_lease('w1', generation=1)
    c.ack_lease(lease, request_key='ack')
    with pytest.raises(ValueError):
        c.ack_attempt_started(lease, request_key='wrong')
    c.ack_validation_started(lease, request_key='start')
    c.commit_validation(lease, seal(c, results, lease, status), request_key='result')
    c.complete_cleanup(owned_processes_stopped=True, controllers_stopped=True)
    s = c.snapshot()
    assert s.workers['w1'].lease_count == 1
    assert s.points['p1'].status == 'UNRUN'
    assert s.summary.validation_complete
    assert s.summary.validation_passed == (status == 'VALIDATION_PASSED')
    assert not s.summary.qualification_applicable
    assert not s.summary.qualification_passed
    names = [e.type for e in journal.replay().events]
    assert 'VALIDATION_STARTED' in names and 'VALIDATION_COMMITTED' in names
    assert 'ATTEMPT_STARTED' not in names and 'RESULT_COMMITTED' not in names


@pytest.mark.parametrize('stage,duration', [
    ('INITIALIZING', 180), ('EXECUTING', 240), ('FINALIZING', 120)])
def test_heartbeats_cannot_extend_stage_deadline(make, stage, duration):
    """Healthy heartbeat traffic cannot restart a hard phase clock."""
    c, clock, *_ = make()
    lease = c.grant_lease('w1', generation=1)
    c.ack_lease(lease, request_key='ack')
    if stage != 'INITIALIZING':
        c.ack_attempt_started(lease, request_key='start')
    if stage == 'FINALIZING':
        c.begin_finalizing(lease, request_key='final')
    for now in range(1, duration):
        clock.now = now
        renewed = c.heartbeat(lease)
        assert renewed.lease_deadline_monotonic_s == duration
    clock.now = duration
    c.tick()
    assert c.snapshot().workers['w1'].state == 'RECOVERING'
    assert not c.snapshot().workers['w1'].action_allowed


def test_recovery_deadline_not_reset_by_reconnect_or_generation(make):
    """Worker reconnection keeps the original recovery deadline."""
    c, clock, results, *_ = make()
    finish(c, results, start(c), 'FAILED')
    clock.now = 100
    c.register_worker('w1', generation=2)
    assert c.snapshot().workers['w1'].stage_started_monotonic_s == 0
    clock.now = 120
    c.tick()
    assert c.snapshot().workers['w1'].state == 'QUARANTINED'


def test_batch_deadline_bounds_renewal_and_preserves_unstarted_until_cleanup(make):
    """The batch deadline cancels active work and delays UNRUN until cleanup."""
    c, clock, *_ = make()
    clock.now = 5398
    lease = start(c)
    assert c.heartbeat(lease).lease_deadline_monotonic_s == 5400
    clock.now = 5400
    c.tick()
    s = c.snapshot()
    assert s.terminal_reason == 'BATCH_DEADLINE_EXCEEDED'
    assert s.points['p1'].status == 'INDETERMINATE'
    assert not s.points['p2'].terminal
    assert not s.workers['w1'].action_allowed
    assert c.grant_lease('w1', generation=1) is None
    with pytest.raises(ValueError):
        c.heartbeat(lease)
    c.complete_cleanup(owned_processes_stopped=True, controllers_stopped=True)
    assert c.snapshot().points['p2'].status == 'UNRUN'
    assert c.snapshot().summary.execution_complete


def test_sealed_result_wins_expiry_and_replay_ignores_mutable_aggregate(make):
    """A completed seal is committed at expiry and replay ignores forged JSON."""
    c, clock, results, journal, request = make(points=('p1',))
    lease = start(c)
    seal(c, results, lease, 'PASSED')
    clock.now = 6
    c.expire_lease(lease)
    assert c.snapshot().points['p1'].status == 'PASSED'
    assert 'LEASE_EXPIRED' not in [e.type for e in journal.replay().events]
    before = c.snapshot()
    (journal.root / 'aggregate_results.json').write_text('{"forged":true}')
    journal.close()
    with CoordinatorJournal.create(journal.root, request.batch_id) as again:
        cls = type(c)
        restored = cls(again, request, config=c.config, clock=clock, result_port=results)
        assert restored.snapshot() == before
        assert restored.snapshot().workers['w1'].lease_count == 1


def test_duplicate_requests_do_not_debit_or_recommit(make):
    """Lost ACK retries cannot debit K twice or duplicate result history."""
    c, _, results, journal, _ = make(points=('p1',))
    lease = c.grant_lease('w1', generation=1, request_key='grant')
    assert c.grant_lease('w1', generation=1, request_key='grant') == lease
    c.ack_lease(lease, request_key='ack')
    c.ack_attempt_started(lease, request_key='start')
    location = seal(c, results, lease, 'PASSED')
    c.commit_result(lease, location, request_key='result')
    count = len(journal.replay().events)
    c.commit_result(lease, location, request_key='result')
    assert len(journal.replay().events) == count
    assert c.snapshot().workers['w1'].lease_count == 1


def test_aggregate_atomic_write_syncs_file_then_replace_then_parent(make, monkeypatch):
    """The aggregate replacement must follow file and directory durability ordering."""
    c, _, _, journal, _ = make()
    steps = []
    real_sync, real_replace = os.fsync, os.replace

    def sync(fd):
        steps.append(('sync', Path(f'/proc/self/fd/{fd}').resolve()))
        return real_sync(fd)

    def move(source, target):
        steps.append(('replace', Path(target)))
        return real_replace(source, target)

    monkeypatch.setattr(os, 'fsync', sync)
    monkeypatch.setattr(os, 'replace', move)
    c.grant_lease('w1', generation=1)
    assert steps[0] == ('sync', journal.segment_path)
    assert steps[-2:] == [('replace', journal.root / 'aggregate_results.json'),
                          ('sync', journal.root)]
    assert steps[-3][0] == 'sync'
    data = json.loads((journal.root / 'aggregate_results.json').read_text())
    assert data['workers']['w1']['lease_count'] == 1


@pytest.mark.parametrize('operation', ['grant', 'ack', 'start'])
def test_duplicate_authorization_after_heartbeat_loss_is_rejected(make, operation):
    """A repeated request cannot revive authorization after its heartbeat expires."""
    c, clock, *_ = make()
    lease = c.grant_lease('w1', generation=1, request_key='grant')
    if operation != 'grant':
        c.ack_lease(lease, request_key='ack')
    if operation == 'start':
        c.ack_attempt_started(lease, request_key='start')
    clock.now = 5
    with pytest.raises(ValueError):
        if operation == 'grant':
            c.grant_lease('w1', generation=1, request_key='grant')
        elif operation == 'ack':
            c.ack_lease(lease, request_key='ack')
        else:
            c.ack_attempt_started(lease, request_key='start')


def test_old_generation_cannot_repeat_a_committed_result(make):
    """Generation fencing applies even to a previously committed result ACK."""
    c, _, results, *_ = make()
    lease = start(c)
    location = seal(c, results, lease, 'FAILED')
    c.commit_result(lease, location, request_key='result')
    c.register_worker('w1', generation=2)
    with pytest.raises(ValueError):
        c.commit_result(lease, location, request_key='result')


def test_restart_preserves_k_and_fences_old_epoch(make):
    """Replay retains spent K and fences the previous coordinator's tokens."""
    c, clock, results, journal, request = make(k=2)
    lease = start(c)
    finish(c, results, lease, 'FAILED')
    c.record_recovery('w1', generation=1, succeeded=True)
    journal.close()
    with CoordinatorJournal.create(journal.root, request.batch_id) as again:
        c2 = type(c)(again, request, config=c.config, clock=clock, result_port=results)
        c2.register_worker('w1', generation=2)
        next_lease = c2.grant_lease('w1', generation=2)
        assert next_lease.point_id == 'p2'
        assert c2.snapshot().workers['w1'].lease_count == 2
        with pytest.raises(ValueError):
            c2.ack_attempt_started(lease, request_key='old-epoch')


@pytest.mark.parametrize('missing', ['fenced', 'owned_processes_stopped',
                                     'controllers_stopped', 'readmitted'])
def test_each_invalid_readmission_gate_is_required(make, missing):
    """Omitting any recovery proof must leave the INVALID point blocked."""
    c, _, results, *_ = make()
    finish(c, results, start(c), 'INVALID')
    gates = {'fenced': True, 'owned_processes_stopped': True, 'controllers_stopped': True,
             'readmitted': True}
    gates[missing] = False
    with pytest.raises(ValueError):
        c.record_recovery('w1', generation=1, succeeded=True, **gates)
    assert c.snapshot().points['p1'].blocked_by == 'w1'


def test_pending_submission_commits_before_concurrent_expiry(make):
    """Expiry waits for an already submitted seal and observes its journal commit."""
    c, clock, results, journal, _ = make()
    lease = start(c)
    location = seal(c, results, lease, 'PASSED')
    entered, release = threading.Event(), threading.Event()
    verify = results.verify

    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return verify(*args)

    results.verify = delayed
    with ThreadPoolExecutor(2) as pool:
        submission = pool.submit(c.commit_result, lease, location, request_key='result')
        assert entered.wait(5)
        clock.now = 6
        expiry = pool.submit(c.expire_lease, lease)
        assert not expiry.done()
        release.set()
        assert submission.result()['status'] == 'PASSED'
        assert expiry.result() is False
    assert 'LEASE_EXPIRED' not in [e.type for e in journal.replay().events]


def test_unverified_discovery_cannot_prevent_expiry(make):
    """A seal from another attempt cannot suppress INDETERMINATE accounting."""
    c, clock, results, *_ = make()
    lease = start(c)
    location = seal(c, results, lease, 'PASSED')
    results.sealed[location] = ('wrong-attempt', 'PASSED')
    clock.now = 5
    c.tick()
    assert c.snapshot().points['p1'].status == 'INDETERMINATE'


def test_append_failure_never_projects_or_acknowledges_grant(make, monkeypatch):
    """A failed durable append must leave the scheduling projection untouched."""
    c, _, _, journal, _ = make()
    before = c.snapshot()

    def fail(*args):
        raise OSError('durability failure')

    monkeypatch.setattr(journal, 'append', fail)
    with pytest.raises(OSError):
        c.grant_lease('w1', generation=1)
    assert c.snapshot() == before


def test_cleanup_requires_both_stop_confirmations(make):
    """Both process and controller stop evidence are required for qualification."""
    c, _, results, *_ = make(points=('p1',))
    finish(c, results, start(c), 'PASSED')
    for process, controller in ((False, True), (True, False)):
        with pytest.raises(ValueError):
            c.complete_cleanup(owned_processes_stopped=process, controllers_stopped=controller)
        assert not c.snapshot().summary.qualification_passed


def test_unrecoverable_invalid_does_not_leave_batch_stuck_on_idle_capacity(make):
    """Idle capacity cannot wait forever on a point whose recovery has failed."""
    c, _, results, *_ = make(workers=2)
    finish(c, results, start(c), 'INVALID')
    c.record_recovery('w1', generation=1, succeeded=False)
    lease = start(c, 'w2')
    assert lease.point_id == 'p2'
    finish(c, results, lease, 'PASSED')
    c.record_recovery('w2', generation=1, succeeded=True)
    assert c.grant_lease('w2', generation=1) is None
    assert c.snapshot().terminal_reason == 'CAPACITY_EXHAUSTED'


def test_batch_deadline_still_bounds_final_cleanup(make):
    """Completing the last point does not remove the deadline on cleanup."""
    c, clock, results, *_ = make(points=('p1',))
    finish(c, results, start(c), 'PASSED')
    clock.now = 5400
    c.tick()
    assert c.snapshot().terminal_reason == 'BATCH_DEADLINE_EXCEEDED'
    assert not c.snapshot().summary.qualification_passed


def test_same_phase_request_cannot_restart_stage_clock(make):
    """Repeated start ACKs retain phase entry time and deadline."""
    c, clock, *_ = make()
    lease = start(c)
    clock.now = 1
    c.heartbeat(lease)
    c.ack_attempt_started(lease, request_key=f'start-{lease.attempt_id}')
    assert c.snapshot().workers['w1'].stage_started_monotonic_s == 0
    assert c.snapshot().workers['w1'].stage_deadline_monotonic_s == 240
    with pytest.raises(ValueError):
        c.ack_attempt_started(lease, request_key='another-start')


def test_result_directory_scan_never_overrides_journal_commit(make):
    """A changed directory must not overwrite a committed failure."""
    c, clock, results, *_ = make(points=('p1',))
    lease = start(c)
    finish(c, results, lease, 'FAILED')
    seal(c, results, lease, 'PASSED')
    clock.now = 6
    assert c.expire_lease(lease) is False
    assert c.snapshot().points['p1'].status == 'FAILED'


@pytest.mark.parametrize('status,coverage', [('PASSED', True), ('FAILED', True),
                                             ('INDETERMINATE', False)])
def test_execute_coverage_and_completion_have_distinct_meanings(make, status, coverage):
    """INDETERMINATE completes accounting without claiming physical coverage."""
    c, _, results, *_ = make(points=('p1',))
    finish(c, results, start(c), status)
    c.complete_cleanup(owned_processes_stopped=True, controllers_stopped=True)
    summary = c.snapshot().summary
    assert summary.execution_complete
    assert summary.coverage_complete is coverage
    assert summary.qualification_passed is (status == 'PASSED')


def test_batch_deadline_requests_stop_from_idle_workers_too(make):
    """Batch cancellation covers every worker, including slots without a lease."""
    c, clock, *_ = make(workers=2)
    clock.now = 5399
    start(c)
    clock.now = 5400
    c.tick()
    assert all(w.stop_requested for w in c.snapshot().workers.values())
