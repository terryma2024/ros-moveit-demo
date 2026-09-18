"""Web-less measurement ownership: abort latch, cancellation and containment."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from so101_demo.parallel_batch.contracts import ContractError
from so101_demo.parallel_batch.measurement_control import (
    MeasurementControl, MeasurementOwnerBinding, ProcessIdentity)


@pytest.fixture
def make_control(tmp_path):
    socket_dirs = []

    def create(now_values=None, sender=None, scope_verifier=None, containment=None,
               clock_values=None):
        private = tmp_path / 'private'
        private.mkdir(mode=0o700, exist_ok=True)
        token = private / 'token'
        token.write_text('unit-only-token')
        token.chmod(0o600)
        # The design requires a short control-socket path within the 107-byte AF_UNIX
        # budget; the task evidence scratch is deliberately deep, so the socket lives in
        # a short private directory exactly as the measurement owner will place it.
        socket_dir = Path(tempfile.mkdtemp(prefix='uq-ctl-', dir='/tmp'))
        socket_dirs.append(socket_dir)
        stat = Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()
        identity = ProcessIdentity(os.getpid(), int(stat[19]), os.getuid(), os.getpgrp())
        binding = MeasurementOwnerBinding('a' * 64, 'task-a', 'campaign-a',
            'batch-a', 1, identity, socket_dir / 'control.sock', 'b' * 64,
            'c' * 64, identity, 'd' * 64, private / 'events.jsonl')
        calls = []
        def default_send(owner_binding, reason):
            calls.append((owner_binding.batch_id, reason))
            return {'status': 'STOPPING', 'cleanup_receipt_sha256': None}
        times = list(clock_values or [1.101])
        control = MeasurementControl(
            binding, clock=lambda: times[min(len(calls), len(times) - 1)],
            cancel_sender=sender or default_send,
            scope_verifier=scope_verifier or (lambda scope: True),
            containment=containment or (lambda scope: False))
        return control, calls

    yield create
    for directory in socket_dirs:
        shutil.rmtree(directory, ignore_errors=True)


def test_sampler_gap_latches_abort_without_web(make_control):
    control, calls = make_control()
    control.observe_sample(1, 1.0)
    control.check_health(1.101, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert control.stop_requested()
    assert len(calls) == 1
    with pytest.raises(ContractError):
        control.permit_side_effect()
    control.observe_sample(2, 1.102)
    assert control.stop_requested()
    assert control.event_times()['t_detect'] == 1.101
    assert control.event_times()['t_abort_latch'] == 1.101
    assert control.event_times()['t_send'] == 1.101
    assert control.event_times()['t_durable_stop_ack'] == 1.101
    assert control.event_times()['t_cleanup_receipt'] is None


def test_latch_never_clears_and_never_resends(make_control):
    control, calls = make_control()
    control.observe_sample(1, 1.0)
    control.check_health(1.2, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert control.stop_requested()
    control.check_health(1.3, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert len(calls) == 1
    assert control.latch_reason == 'SAMPLER_GAP'


@pytest.mark.parametrize("kwargs, reason", [
    ({"sampler_alive": False, "endpoint_healthy": True, "breach": None}, 'SAMPLER_EXITED'),
    ({"sampler_alive": True, "endpoint_healthy": False, "breach": None}, 'CONTROL_ENDPOINT_UNHEALTHY'),
    ({"sampler_alive": True, "endpoint_healthy": True, "breach": 'RAM_BREACH'}, 'RAM_BREACH'),
])
def test_health_failures_latch_abort(make_control, kwargs, reason):
    control, calls = make_control()
    control.observe_sample(1, 1.0)
    control.check_health(1.05, **kwargs)
    assert control.stop_requested()
    assert control.latch_reason == reason
    assert len(calls) == 1


def test_sequence_regression_latches_abort(make_control):
    control, calls = make_control()
    control.observe_sample(5, 1.0)
    control.check_health(1.05, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert not control.stop_requested()
    control.observe_sample(4, 1.06)
    assert control.stop_requested()
    assert control.latch_reason == 'SAMPLE_SEQUENCE_REGRESSION'


def test_unreachable_owner_requires_fresh_owned_scope_and_no_receipt(make_control):
    def failing_sender(binding, reason):
        raise ConnectionError('owner socket unreachable')
    control, calls = make_control(sender=failing_sender, scope_verifier=lambda scope: False,
                                  containment=lambda scope: True)
    control.observe_sample(1, 1.0)
    with pytest.raises(ContractError) as error:
        control.check_health(1.2, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert error.value.code == 'FOREIGN_IDENTITY'
    assert control.event_times()['t_cleanup_receipt'] is None
    assert control.operator_recovery_required is True


def test_owned_containment_is_recorded_when_scope_is_fresh(make_control):
    def failing_sender(binding, reason):
        raise ConnectionError('owner socket unreachable')
    control, calls = make_control(sender=failing_sender, scope_verifier=lambda scope: True,
                                  containment=lambda scope: True, clock_values=[2.0])
    control.observe_sample(1, 1.0)
    control.check_health(1.2, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert control.stop_requested()
    assert control.event_times()['t_owned_groups_gone'] == 2.0
    assert control.event_times()['t_cleanup_receipt'] is None


def test_detect_to_send_overrun_invalidates_the_run(make_control):
    def sender(binding, reason):
        return {'status': 'STOPPING', 'cleanup_receipt_sha256': None}
    control, _ = make_control(sender=sender, clock_values=[1.30])
    control.observe_sample(1, 1.0)
    control.check_health(1.2, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert control.stop_requested()
    assert control.event_times()['t_detect'] == 1.2
    assert control.event_times()['t_send'] == 1.30
    assert control.invalid_reason == 'DETECT_TO_SEND_OVERRUN'


def test_permit_side_effect_allows_normal_progress(make_control):
    control, _ = make_control()
    control.observe_sample(1, 1.0)
    control.check_health(1.05, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert control.permit_side_effect() is None
    assert control.stop_requested() is False


def test_binding_validates_socket_budget_and_identity():
    with pytest.raises(ContractError):
        MeasurementOwnerBinding('a' * 64, 'task-a', 'campaign-a', 'batch-a', 1,
            ProcessIdentity(1, 2, 3, 4), Path('/tmp/' + 'x' * 120 + '/control.sock'),
            'b' * 64, 'c' * 64, ProcessIdentity(1, 2, 3, 4), 'd' * 64,
            Path('/tmp/events.jsonl'))
    with pytest.raises(ContractError):
        ProcessIdentity(0, 2, 3, 4)


def test_first_sample_inside_the_grace_window_does_not_latch(make_control):
    """run4 aborted 60 ms after the spawn with exactly one sample: the main thread's
    first health check saw no sample yet and called it a gap. Sampling has to be given
    the same bound for its opening sample that it gets in the steady state."""

    control, calls = make_control()
    control.mark_sampling_start(1.0)
    control.check_health(1.05, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert not control.stop_requested()
    assert calls == []


def test_first_sample_missing_past_the_grace_window_latches(make_control):
    control, calls = make_control()
    control.mark_sampling_start(1.0)
    control.check_health(1.101, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert control.stop_requested()
    assert control.latch_reason == "SAMPLER_GAP"


def test_health_check_before_sampling_starts_still_fails_closed(make_control):
    control, calls = make_control()
    control.check_health(1.05, sampler_alive=True, endpoint_healthy=True, breach=None)
    assert control.stop_requested()


def test_control_event_times_show_what_the_control_saw(make_control):
    """The receipt must carry the control's own view: without t_last_sample and t_breach a
    SAMPLER_GAP latch cannot be told apart from a health check that ran too early."""

    control, calls = make_control()
    control.mark_sampling_start(1.0)
    control.observe_sample(1, 1.02)
    control.check_health(1.5, sampler_alive=True, endpoint_healthy=True, breach=None)
    times = control.event_times()
    assert times["t_last_sample"] == 1.02
    assert times["t_breach"] == 1.5
    assert times["t_abort_latch"] is not None


def test_a_gap_between_two_samples_latches_even_without_a_mid_gap_check(make_control):
    """run39 took a 142.9 ms sample gap and never latched: the health check only ever
    compares now with the *latest* sample, so a gap that opens and closes between two
    checks is invisible. observe_sample sees both timestamps and must rule on them."""

    control, calls = make_control()
    control.mark_sampling_start(1.0)
    control.observe_sample(1, 1.01)
    control.observe_sample(2, 1.1529)
    assert control.stop_requested()
    assert control.latch_reason == "SAMPLER_GAP"
    assert calls and calls[0][1] == "SAMPLER_GAP"


def test_two_consecutive_samples_inside_the_allowance_do_not_latch(make_control):
    control, calls = make_control()
    control.mark_sampling_start(1.0)
    control.observe_sample(1, 1.01)
    control.observe_sample(2, 1.0909)
    assert not control.stop_requested()
    assert calls == []


def test_cold_start_grace_covers_the_workloads_own_startup_once(make_control):
    """run59 and run60 both took a single ~170 ms interval about 3.5 s after the spawn: the
    worker importing torch starves the sampler's own reads. One bounded, one-shot grace
    covers that window; an identical gap outside it still latches."""

    control, calls = make_control()
    control.mark_sampling_start(1.0)
    control.observe_sample(1, 1.02)
    control.mark_workload_start(1.05)
    control.observe_sample(2, 1.22)          # 200 ms inside the cold-start window
    assert not control.stop_requested()
    control.observe_sample(3, 1.42)          # 200 ms later: grace already used
    assert control.stop_requested()
    assert control.latch_reason == "SAMPLER_GAP"
    assert calls and calls[0][1] == "SAMPLER_GAP"


def test_cold_start_grace_does_not_apply_without_a_workload(make_control):
    control, calls = make_control()
    control.mark_sampling_start(1.0)
    control.observe_sample(1, 1.02)
    control.observe_sample(2, 1.22)
    assert control.stop_requested()
    assert calls and calls[0][1] == "SAMPLER_GAP"
