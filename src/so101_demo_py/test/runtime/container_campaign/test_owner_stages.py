"""A run collected stage by stage equals the all-in-one run, and every stage that may not start is refused (controlled world)."""

import asyncio
import json
from dataclasses import replace

import pytest

from so101_demo.runtime.container_campaign import container_receipts, stage_records
from test_owner_retry import drive, retry_world


def drive_phase1(phase):
    """Phase 1 as its own process ends: the owner is closed; the registry stays open for the later stages of the test."""
    async def run():
        try:
            return await phase.owner.run(phase.world.manifest)
        finally:
            await phase.owner.close()
    return asyncio.run(run())


def staged_world(tmp_path, monkeypatch, **kwargs):
    """A world whose phase 1 ran with `stop_after_phase1`; the same owner then runs the later stages."""
    phase = retry_world(tmp_path, monkeypatch, rounds=0, **kwargs)
    phase.owner.stop_after_phase1 = True
    drive_phase1(phase)
    return phase


def new_process(phase, stage=None, attempt=1):
    """What a separate process starts with: an owner that is not closing and a coordinator that is not stopped.

    `attempt` is what the CLI derives from the host directory (`stage_records.next_attempt`) and hands to the service owner."""
    phase.owner._closing, phase.owner.dispatch_stopped, phase.owner.stop_reason = False, False, None
    phase.owner._close_task = None
    phase.owner._run_done, phase.owner._run_task, phase.owner._started = asyncio.Event(), None, False       # `run()` is phase 1's
    phase.owner.shards, phase.scheduler.owners = [], []                     # a new process has launched no shard and no processor yet
    phase.owner.coordinator.stop_reason = None
    services = phase.owner.services
    services._close_task = None
    if hasattr(services, '_closing') and stage is not None:
        services._closing, services._start_task, services._endpoints, services._launch_ids = False, None, {}, []
        services.stage, services.attempt = stage, attempt
        services._tail = '-' + stage + ('' if attempt == 1 else '-a%d' % attempt)
        services._startup_done = asyncio.Event()


async def ended(phase, run, close):
    """A stage as its own process ends it: the stage, then `close()`, which proves the stage's containers, removes them and receipts.

    `close=False` is a stage the CLI refuses before admission: that process would never exist, so nothing closes."""
    try:
        return await run
    finally:
        if close:
            phase.closed = getattr(phase, 'closed', []) + [await phase.owner.close()]


def stage(phase, name, close=True, attempt=1):
    new_process(phase, name, attempt)
    return asyncio.run(ended(phase, getattr(phase.owner, 'stage_' + name)(phase.world.manifest), close))


def retry(phase, number, close=True, attempt=1):
    new_process(phase, 'retry-%d' % number, attempt)
    return asyncio.run(ended(phase, phase.owner.stage_retry(phase.world.manifest, number), close))


def normalised(phase, name):
    """The document with this world's root name removed and the digests of files that contain that root left out."""
    raw = (phase.owner.root / name).read_text().replace(str(phase.owner.root), 'ROOT')

    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if key not in ('sha256', 'estimate')}
        return [strip(item) for item in value] if isinstance(value, list) else value
    return strip(json.loads(raw))


def test_phase1_phase2_finalize_equal_the_all_in_one_run(tmp_path, monkeypatch):
    (tmp_path / 'whole').mkdir()
    (tmp_path / 'staged').mkdir()
    whole = retry_world(tmp_path / 'whole', monkeypatch, rounds=0)
    result = drive(whole)
    staged = staged_world(tmp_path / 'staged', monkeypatch)
    assert not (staged.owner.root / 'collection-index.json').exists()
    stage(staged, 'phase2')
    assert not (staged.owner.root / 'collection-index.json').exists()
    final = stage(staged, 'finalize')
    assert final['processing'] == result['processing'] == 'COMPLETE'
    for name in ('collection-index.json', 'host/campaign-result.json', 'host/processing-result.json'):
        assert normalised(staged, name) == normalised(whole, name), name
    assert [call['round'] for call in staged.scheduler.calls] == [call['round'] for call in whole.scheduler.calls] == [0]
    assert [r['scene_id'] for r in staged.scheduler.calls[0]['rows']] == [r['scene_id'] for r in whole.scheduler.calls[0]['rows']]
    last = stage_records.read_record(staged.owner.root / 'host', stage_records.FINALIZE)
    assert last['previous']['stage'] == 'phase2'


def test_the_records_form_a_chain_and_name_the_runtime_values_of_each_stage(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    phase.owner.runtime_document = {'processor_count': 3}
    phase.owner.config = {n: v for n, v in phase.owner.config.items() if n != 'processor_count'}
    stage(phase, 'phase2')
    stage(phase, 'finalize')
    host = phase.owner.root / 'host'
    first, second, third = (stage_records.read_record(host, name) for name in ('phase1', 'phase2', 'finalize'))
    assert first['previous'] is None
    assert second['previous'] == dict(stage='phase1', sha256=first['sha256'])
    assert third['previous'] == dict(stage='phase2', sha256=second['sha256'])
    assert json.loads((host / 'runtime-used-phase2.json').read_text())['values']['processor_count'] == 3


def test_a_stage_run_twice_is_refused_and_does_nothing_the_second_time(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        stage(phase, 'phase2', close=False)
    stage(phase, 'finalize')
    before = (phase.owner.root / 'collection-index.json').read_bytes()
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        stage(phase, 'finalize', close=False)
    assert len(phase.scheduler.calls) == 1 and (phase.owner.root / 'collection-index.json').read_bytes() == before


def test_phase2_and_finalize_need_the_stage_before_them(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch, rounds=0)                       # no phase 1 record at all
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):
        stage(phase, 'phase2')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):
        stage(phase, 'finalize')
    phase.world.registry.close()
    (tmp_path / 'b').mkdir()
    one = staged_world(tmp_path / 'b', monkeypatch)
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):      # phase 1 only: nothing was processed
        stage(one, 'finalize')
    assert one.scheduler.calls == []


def test_a_changed_logic_document_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    phase.owner.context = replace(phase.owner.context, campaign_config_sha256='f' * 64)
    with pytest.raises(ValueError, match='STAGE_LOGIC_DOCUMENT_CHANGED'):
        stage(phase, 'phase2')
    assert phase.scheduler.calls == []


@pytest.mark.parametrize('field', ['source_sha256', 'runtime_config_sha256', 'collection_config_sha256',
                                   'contact_policy_fingerprint'])
def test_inputs_other_than_those_of_phase_1_are_refused(tmp_path, monkeypatch, field):
    phase = staged_world(tmp_path, monkeypatch)
    phase.owner.context = replace(phase.owner.context, **{field: 'e' * 64})
    with pytest.raises(ValueError, match='STAGE_INPUTS_CHANGED'):
        stage(phase, 'phase2')


def test_other_images_than_those_of_phase_1_are_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    image = dict(phase.owner.config['shard_image'], digest='sha256:' + '9' * 64)
    phase.owner.config = {**phase.owner.config, 'shard_image': image}
    with pytest.raises(ValueError, match='STAGE_IMAGES_CHANGED'):
        stage(phase, 'phase2')


def test_a_phase1_result_changed_after_its_record_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    path = phase.owner.root / 'host/phase1-result.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_INVALID'):
        stage(phase, 'phase2')


def test_a_record_changed_after_its_successor_named_it_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    path = stage_records.record_path(phase.owner.root / 'host', 'phase1')
    document = json.loads(path.read_bytes())
    document['scene_count'] += 1
    path.write_bytes(stage_records.canonical_json(document) + b'\n')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_INVALID'):
        stage(phase, 'finalize')
    assert not (phase.owner.root / 'collection-index.json').exists()


def test_a_run_without_a_processing_scheduler_cannot_process(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    phase.owner.processing = None
    with pytest.raises(ValueError, match='STAGE_PROCESSING_UNAVAILABLE'):
        stage(phase, 'phase2')
    with pytest.raises(ValueError, match='STAGE_PROCESSING_UNAVAILABLE'):
        stage(phase, 'finalize')


def retry_staged(tmp_path, monkeypatch, **kwargs):
    kwargs.setdefault('rounds', 2)
    phase = retry_world(tmp_path, monkeypatch, **kwargs)
    phase.owner.stop_after_phase1 = True
    drive_phase1(phase)
    return phase


def test_a_run_with_retry_rounds_collected_stage_by_stage_equals_the_all_in_one_run(tmp_path, monkeypatch):
    (tmp_path / 'whole').mkdir()
    (tmp_path / 'staged').mkdir()
    whole = retry_world(tmp_path / 'whole', monkeypatch, rounds=2)
    result = drive(whole)
    staged = retry_staged(tmp_path / 'staged', monkeypatch)
    stage(staged, 'phase2')
    first = retry(staged, 1)
    assert first['status'] == 'RUN', first
    assert retry(staged, 2)['status'] == 'SKIPPED'
    final = stage(staged, 'finalize')
    assert final['processing'] == result['processing'] == 'COMPLETE'
    for name in ('collection-index.json', 'host/campaign-result.json', 'host/retry-round-1.json', 'host/retry-round-2.json'):
        assert normalised(staged, name) == normalised(whole, name), name
    assert [call['round'] for call in staged.scheduler.calls] == [call['round'] for call in whole.scheduler.calls]
    chain = [stage_records.read_record(staged.owner.root / 'host', name)['previous']['stage']
             for name in ('phase2', 'retry-1', 'retry-2', 'finalize')]
    assert chain == ['phase1', 'phase2', 'retry-1', 'retry-2']


def test_a_retry_round_beyond_the_maximum_is_refused(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch, rounds=1)
    stage(phase, 'phase2')
    with pytest.raises(ValueError, match='STAGE_RETRY_ROUNDS_EXCEEDED'):
        retry(phase, 2)
    with pytest.raises(ValueError, match='STAGE_RETRY_ROUNDS_EXCEEDED'):
        retry(phase, 0)


def test_a_retry_round_needs_the_round_before_it(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):
        retry(phase, 2)


def test_a_round_after_a_skipped_round_is_out_of_order(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch, outcomes=('VALID',))           # nothing to retry: round 1 is skipped
    stage(phase, 'phase2')
    assert retry(phase, 1)['status'] == 'SKIPPED'
    with pytest.raises(ValueError, match='STAGE_RETRY_ROUND_OUT_OF_ORDER'):
        retry(phase, 2)


def test_a_retry_round_of_a_qualification_run_is_refused(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    phase.owner.qualification = True
    with pytest.raises(ValueError, match='STAGE_RETRY_ON_QUALIFICATION_RUN'):
        retry(phase, 1)
    assert len(phase.scheduler.calls) == 1


def test_a_retry_round_run_twice_is_refused(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    retry(phase, 1)
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        retry(phase, 1, close=False)


def test_a_teacher_failed_scene_without_a_recording_receipt_does_not_break_the_staged_retry_decision(tmp_path, monkeypatch):
    """EXP-7036: `stage_retry` raised STAGE_FAILED `'>' not supported between instances of 'NoneType' and 'int'` because the disk estimate took
    `recording_bytes` (None for a Teacher-failed scene) into `max`."""
    from test_owner_retry import teacher_failed_scene
    phase = retry_staged(tmp_path, monkeypatch, rounds=1, verify=teacher_failed_scene([]))
    stage(phase, 'phase2')
    decision = retry(phase, 1)
    assert decision['status'] == 'RUN', decision
    recorded = json.loads((phase.owner.root / 'host/retry-round-1.json').read_text())
    assert recorded['candidates'] == ['scene-00'] and recorded['reason'] is None


# ---- EXP-7036 (b): the health monitor starts only after the Teacher is up -------------------------------------------------------

def test_a_staged_retry_round_whose_service_start_is_slow_runs_instead_of_aborting(tmp_path, monkeypatch):
    """EXP-7036: the monitor was created before `services.start()`; its first `check_health()` raised SERVICE_OWNER_NOT_AVAILABLE, fenced
    dispatch, and the round ended ABORTED / CAMPAIGN_RETRY_DISPATCH_FENCED. The unit worlds started instantly and never saw it."""
    phase = retry_staged(tmp_path, monkeypatch, rounds=1)
    stage(phase, 'phase2')
    services = phase.owner.services
    real_start = services._start

    async def slow_start():
        await asyncio.sleep(.3)                       # longer than the first monitor pass
        return await real_start()
    services._start = slow_start
    decision = retry(phase, 1)
    host = phase.owner.root / 'host'
    assert decision['status'] == 'RUN', decision
    assert not (host / 'dispatch-fault.json').exists()
    assert phase.world.waves == [0, 1]


def test_a_health_fault_after_the_services_are_up_still_fences_the_round(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch, rounds=1)
    stage(phase, 'phase2')
    services = phase.owner.services

    async def failing():
        if services._start_task is None or not services._start_task.done():
            raise ValueError('SERVICE_OWNER_NOT_AVAILABLE')
        raise ValueError('SERVICE_CONTAINER_NOT_RUNNING')
    services.check_health = failing
    decision = retry(phase, 1)
    host = phase.owner.root / 'host'
    assert decision['status'] == 'ABORTED' and 'SERVICE_CONTAINER_NOT_RUNNING' in decision['reason'], decision
    fault = json.loads((host / 'dispatch-fault.json').read_text())
    assert fault['reason'] == 'SERVICE_CONTAINER_NOT_RUNNING'
    assert phase.closed[-1]['stop_reason'] == 'CAMPAIGN_RESOURCE_OR_SERVICE_FAULT'


# ---- EXP-7036 (c): close() never masks the stage's error; a stage that failed after admission runs again as a new attempt -----------

def fail_once(owner, name, error='BOOM_AFTER_ADMISSION'):
    """Make `owner.<name>` raise on its first call and be the real method afterwards."""
    real = getattr(owner, name)
    calls = []

    async def wrapper(*args, **kwargs):
        if not calls:
            calls.append(1)
            raise ValueError(error)
        return await real(*args, **kwargs)
    setattr(owner, name, wrapper)


def test_close_does_not_mask_the_stage_error_when_its_cleanup_record_cannot_be_written(tmp_path, monkeypatch):
    """EXP-7036: a leftover `campaign-cleanup-<stage>.json` made `close()` raise FileExistsError out of the CLI's `finally`, which hid the
    stage's own exception (and, in the CLI, left the lease held)."""
    phase = staged_world(tmp_path, monkeypatch)
    leftover = phase.owner.root / 'host/campaign-cleanup-phase2.json'
    leftover.write_bytes(b'{"leftover":true}\n')
    phase.owner.processing = None
    with pytest.raises(ValueError, match='STAGE_PROCESSING_UNAVAILABLE'):
        stage(phase, 'phase2')
    cleanup = phase.closed[-1]
    assert cleanup['terminated'] is True and 'FileExistsError' in cleanup['cleanup_record_error']
    assert leftover.read_bytes() == b'{"leftover":true}\n'


def test_a_stage_that_failed_after_admission_runs_again_as_attempt_two(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    host = phase.owner.root / 'host'
    fail_once(phase.owner, 'start_phase_two')
    with pytest.raises(ValueError, match='BOOM_AFTER_ADMISSION'):
        stage(phase, 'phase2')
    first = {name: (host / name).read_bytes() for name in ('runtime-used-phase2.json', 'campaign-cleanup-phase2.json')}
    assert json.loads(first['campaign-cleanup-phase2.json'])['terminated'] is True
    assert not stage_records.record_path(host, 'phase2').exists()
    assert stage_records.next_attempt(host, 'phase2') == 2
    result = stage(phase, 'phase2', attempt=2)
    assert result['stage'] == 'phase2'
    for name, raw in first.items():                                          # the first attempt's artefacts are kept as they were
        assert (host / name).read_bytes() == raw
    assert json.loads((host / 'runtime-used-phase2.a2.json').read_text())['stage'] == 'phase2'
    assert json.loads((host / 'campaign-cleanup-phase2.a2.json').read_text())['terminated'] is True
    record = stage_records.read_record(host, 'phase2')
    assert record['attempt'] == 2 and stage_records.record_attempt(record) == 2
    final = stage(phase, 'finalize')                                         # the chain goes on from the completed attempt
    assert final['processing'] == 'COMPLETE'
    assert [item['stage'] for item in container_receipts.read_receipts(host)] == ['phase1', 'phase2', 'finalize']


def test_a_run_without_attempt_suffixes_reads_as_attempt_one(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    stage(phase, 'finalize')
    host = phase.owner.root / 'host'
    for name in ('phase1', 'phase2', 'finalize'):
        record = stage_records.read_record(host, name)
        assert 'attempt' not in record and stage_records.record_attempt(record) == 1
    for name in ('runtime-used-phase2.json', 'campaign-cleanup-phase2.json', 'campaign-cleanup-finalize.json'):
        assert (host / name).is_file()
    assert sorted(path.name for path in host.glob('*.a[0-9].json')) == []


@pytest.mark.parametrize('aborted', [False, True])
def test_a_completed_retry_round_is_never_run_again_whether_it_ran_or_aborted(tmp_path, monkeypatch, aborted):
    phase = retry_staged(tmp_path, monkeypatch, rounds=1)
    stage(phase, 'phase2')
    if aborted:
        async def refuse(**kwargs):
            raise ValueError('RETRY_INFRASTRUCTURE_FAILURE')
        phase.owner.coordinator.run_wave = refuse
    assert retry(phase, 1)['status'] == ('ABORTED' if aborted else 'RUN')
    host = phase.owner.root / 'host'
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        stage_records.next_attempt(host, 'retry-1')
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        retry(phase, 1, close=False, attempt=2)
    assert not (host / 'runtime-used-retry-1.a2.json').exists()


def test_a_retry_round_that_failed_before_launching_anything_runs_again_and_the_finalize_reads_the_attempt_that_completed(tmp_path, monkeypatch):
    """The EXP-7036 shape: attempt 1 died in the decision part (there a TypeError) after admission. Attempt 2 writes every once-only
    artefact under its own name and the finalize reads the decision of the attempt that completed the round."""
    phase = retry_staged(tmp_path, monkeypatch, rounds=1)
    stage(phase, 'phase2')
    host = phase.owner.root / 'host'
    real_rounds, calls = phase.owner.verifier.verify_rounds, []

    def rounds_once_broken(rounds, ids):
        if not calls:
            calls.append(1)
            raise TypeError("'>' not supported between instances of 'NoneType' and 'int'")
        return real_rounds(rounds, ids)
    phase.owner.verifier.verify_rounds = rounds_once_broken
    with pytest.raises(TypeError, match="not supported between"):
        retry(phase, 1)
    assert not (host / 'retry-round-1.json').exists() and phase.world.waves == [0]
    assert json.loads((host / 'campaign-cleanup-retry-1.json').read_text())['terminated'] is True
    assert stage_records.next_attempt(host, 'retry-1') == 2
    assert retry(phase, 1, attempt=2)['status'] == 'RUN'
    assert json.loads((host / 'retry-round-1.a2.json').read_text())['status'] == 'RUN' and not (host / 'retry-round-1.json').exists()
    assert json.loads((host / 'runtime-used-retry-1.a2.json').read_text())['stage'] == 'retry-1'
    assert json.loads((host / 'campaign-cleanup-retry-1.a2.json').read_text())['terminated'] is True
    assert stage_records.record_attempt(stage_records.read_record(host, 'retry-1')) == 2
    final = stage(phase, 'finalize')
    assert final['retry']['recovered'] == 1 and final['retry']['decisions'][0]['status'] == 'RUN'
    assert phase.world.waves == [0, 1]
    assert [item['stage'] for item in container_receipts.read_receipts(host)] == ['phase1', 'phase2', 'retry-1', 'finalize']


def test_an_attempt_without_a_cleanup_record_proving_the_stop_blocks_a_new_attempt(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch, rounds=1)
    stage(phase, 'phase2')
    host = phase.owner.root / 'host'
    stage_records.runtime_used_path(host, 'retry-1').write_bytes(b'{}\n')                  # attempt 1 started and never closed
    with pytest.raises(ValueError, match='STAGE_ATTEMPT_PREVIOUS_UNPROVEN'):
        stage_records.next_attempt(host, 'retry-1')
    stage_records.cleanup_path(host, 'retry-1').write_bytes(b'{"terminated":false}\n')
    with pytest.raises(ValueError, match='STAGE_ATTEMPT_PREVIOUS_UNPROVEN'):
        stage_records.next_attempt(host, 'retry-1')
    with pytest.raises(ValueError, match='STAGE_ATTEMPT_PREVIOUS_UNPROVEN'):
        retry(phase, 1, close=False, attempt=2)
    assert phase.world.waves == [0]


def test_a_retry_round_that_recorded_waves_and_then_failed_is_not_run_again(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch, rounds=1)
    stage(phase, 'phase2')
    host = phase.owner.root / 'host'
    real_write, calls = stage_records.write_record, []

    def write_once_broken(*args, **kwargs):
        if args[1] == 'retry-1' and not calls:
            calls.append(1)
            raise OSError('DISK_FULL')
        return real_write(*args, **kwargs)
    monkeypatch.setattr(stage_records, 'write_record', write_once_broken)
    with pytest.raises(OSError, match='DISK_FULL'):
        retry(phase, 1)
    assert phase.world.waves == [0, 1] and not stage_records.record_path(host, 'retry-1').exists()
    with pytest.raises(ValueError, match='STAGE_ATTEMPT_'):
        stage_records.next_attempt(host, 'retry-1')


def test_a_failed_attempt_that_launched_the_teacher_is_receipted_so_the_next_attempt_is_admitted(tmp_path, monkeypatch):
    """A Teacher a failed attempt started and proved stopped is removed and receipted under `<stage>-aN`; without the receipt the next
    admission would refuse the run for an uncovered launch."""
    phase = retry_staged(tmp_path, monkeypatch, rounds=1)
    stage(phase, 'phase2')
    host = phase.owner.root / 'host'
    new_process(phase, 'retry-1')
    phase.owner._stage = 'retry-1'

    async def attempt_one():
        try:
            await phase.owner.services.start()                  # the Teacher is up, then the stage dies outside any round handling
            raise ValueError('BOOM_AFTER_TEACHER')
        finally:
            phase.cleanup = await phase.owner.close()
    with pytest.raises(ValueError, match='BOOM_AFTER_TEACHER'):
        asyncio.run(attempt_one())
    assert phase.cleanup['terminated'] is True
    assert [item['stage'] for item in container_receipts.read_receipts(host)] == ['phase1', 'phase2', 'retry-1-a1']
    assert container_receipts.verify_receipts(host, stage_records.read_record(host, 'phase2'), phase.world.registry.records())
