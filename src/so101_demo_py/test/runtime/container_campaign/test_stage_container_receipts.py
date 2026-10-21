"""Each stage of a run collected stage by stage proves its own containers gone, removes them and leaves a receipt; the later stages and
the finalize verify termination from the receipts and need no live container (controlled world of `test_owner_stages`)."""

import json
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign import container_receipts, stage_records
from test_owner_retry import drive, retry_world
from test_owner_stages import drive_phase1, retry, retry_staged, stage, staged_world


def receipt_names(phase):
    return [path.name for _, _, path in container_receipts.receipt_files(phase.owner.root / 'host')]


def rewrite(path, change):
    """A receipt edited in place but still in canonical form (what a careful tamperer leaves)."""
    document = json.loads(path.read_bytes())
    change(document)
    path.write_bytes(stage_records.canonical_json(document) + b'\n')


def receipt(phase, name):
    return phase.owner.root / 'host' / name


def test_a_run_collected_stage_by_stage_finalizes_with_its_containers_removed_between_stages(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    assert phase.world.containers == {}                                  # phase 1 removed the Teacher it had proven exited
    assert receipt_names(phase) == ['containers-receipt-01-phase1.json']
    stage(phase, 'phase2')
    assert phase.world.containers == {}
    final = stage(phase, 'finalize')
    assert final['processing'] == 'COMPLETE' and phase.world.containers == {}
    assert receipt_names(phase) == ['containers-receipt-01-phase1.json', 'containers-receipt-02-phase2.json',
                                    'containers-receipt-03-finalize.json']
    assert all(item['terminated'] is True for item in phase.closed)
    host = phase.owner.root / 'host'
    receipts = container_receipts.read_receipts(host)
    assert [item['previous_receipt'] for item in receipts] == [
        None, dict(seq=1, sha256=receipts[0]['sha256']), dict(seq=2, sha256=receipts[1]['sha256'])]
    for item in receipts:
        assert item['stage_record_sha256'] == stage_records.read_record(host, item['stage'])['sha256']
    teacher, = receipts[0]['containers']
    assert (teacher['status'], teacher['exit_code'], teacher['removed'], teacher['absent_after_removal']) == (
        'exited', 0, True, True)
    assert teacher['finished_at'] and len(teacher['container_id']) == 64 and teacher['launch_id'] == 'teacher-g1'
    cleanup = json.loads((host / 'campaign-cleanup-phase2.json').read_text())
    assert cleanup['container_receipt'] == 'containers-receipt-02-phase2.json'


def test_retry_rounds_start_their_own_teacher_with_the_earlier_containers_removed(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    assert retry(phase, 1)['status'] == 'RUN'
    assert phase.world.containers == {}
    final = stage(phase, 'finalize')
    assert final['processing'] == 'COMPLETE'
    launched = [entry['launch_id'] for item in container_receipts.read_receipts(phase.owner.root / 'host')
                for entry in item['containers']]
    assert launched == ['teacher-g1', 'teacher-g1-retry-1']


def test_the_all_in_one_run_is_unchanged_it_removes_nothing_and_writes_no_receipt(tmp_path, monkeypatch):
    whole = retry_world(tmp_path, monkeypatch, rounds=0)
    drive(whole)
    assert container_receipts.receipt_files(whole.owner.root / 'host') == []
    assert len(whole.world.containers) == 1
    assert all(not item['State']['Running'] for item in whole.world.containers.values())
    assert [call for call in whole.world.calls if call[:2] in (['docker', 'rm'], ['docker', 'ps'])] == []
    cleanup = json.loads((whole.owner.root / 'host/campaign-cleanup.json').read_text())
    assert cleanup['terminated'] is True and 'container_receipt' not in cleanup and 'container_receipt_error' not in cleanup


def test_the_finalize_refuses_a_stage_without_a_receipt(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    receipt(phase, 'containers-receipt-02-phase2.json').unlink()
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_MISSING'):
        stage(phase, 'finalize', close=False)
    assert not (phase.owner.root / 'collection-index.json').exists()


def test_phase_two_refuses_when_phase_one_has_no_receipt(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    receipt(phase, 'containers-receipt-01-phase1.json').unlink()
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_MISSING'):
        stage(phase, 'phase2', close=False)
    assert phase.scheduler.calls == []


def test_the_finalize_refuses_a_tampered_receipt_by_the_sha_chain(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    rewrite(receipt(phase, 'containers-receipt-01-phase1.json'), lambda d: d['containers'][0].update(finished_at='2020-01-01T00:00:00Z'))
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_INVALID'):
        stage(phase, 'finalize', close=False)


@pytest.mark.parametrize('damage', ['not json', 'not canonical', 'other stage'])
def test_the_finalize_refuses_a_receipt_that_is_not_the_one_written(tmp_path, monkeypatch, damage):
    phase = staged_world(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    path = receipt(phase, 'containers-receipt-02-phase2.json')
    if damage == 'not json':
        path.write_bytes(b'{')
    elif damage == 'not canonical':
        path.write_bytes(path.read_bytes().replace(b'{', b'{ ', 1))
    else:
        rewrite(path, lambda d: d.update(stage='finalize'))
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_INVALID'):
        stage(phase, 'finalize', close=False)


def test_a_receipt_bound_to_another_stage_record_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    rewrite(receipt(phase, 'containers-receipt-01-phase1.json'), lambda d: d.update(stage_record_sha256='0' * 64))
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_INVALID'):
        stage(phase, 'phase2', close=False)


def test_a_receipt_that_does_not_cover_a_container_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    rewrite(receipt(phase, 'containers-receipt-01-phase1.json'), lambda d: d.update(containers=[]))
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_COVERAGE'):
        stage(phase, 'phase2', close=False)
    assert phase.scheduler.calls == []


def test_the_finalize_refuses_a_receipt_set_that_does_not_cover_a_container(tmp_path, monkeypatch):
    phase = retry_staged(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    retry(phase, 1)
    # the retry round's Teacher is dropped from the last receipt, which nothing chains after
    rewrite(receipt(phase, 'containers-receipt-03-retry-1.json'), lambda d: d.update(containers=[]))
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_COVERAGE'):
        stage(phase, 'finalize', close=False)


def test_a_receipt_that_disagrees_with_the_registry_settlement_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    rewrite(receipt(phase, 'containers-receipt-01-phase1.json'), lambda d: d['containers'][0].update(exit_code=137))
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_COVERAGE'):
        stage(phase, 'phase2', close=False)


@pytest.mark.parametrize('field,value', [('removed', False), ('absent_after_removal', False), ('status', 'running'),
                                         ('finished_at', '')])
def test_a_receipt_entry_that_does_not_show_exited_removed_and_absent_is_refused(tmp_path, monkeypatch, field, value):
    phase = staged_world(tmp_path, monkeypatch)
    rewrite(receipt(phase, 'containers-receipt-01-phase1.json'), lambda d: d['containers'][0].update({field: value}))
    with pytest.raises(ValueError, match='STAGE_CONTAINER_RECEIPT_NOT_TERMINATED'):
        stage(phase, 'phase2', close=False)


def staged_phase1_world(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch, rounds=0)
    phase.owner.stop_after_phase1 = True
    return phase


def test_a_container_that_cannot_be_removed_fails_the_stage_and_writes_no_receipt(tmp_path, monkeypatch):
    phase = staged_phase1_world(tmp_path, monkeypatch)
    runner = phase.owner.services.docker_runner
    phase.owner.services.docker_runner = lambda argv: (
        SimpleNamespace(returncode=1, stdout='', stderr='removal refused') if argv[:2] == ['docker', 'rm'] else runner(argv))
    drive_phase1(phase)
    cleanup = json.loads((phase.owner.root / 'host/campaign-cleanup.json').read_text())
    assert cleanup['terminated'] is False and 'STAGE_CONTAINER_REMOVE_FAILED' in cleanup['container_receipt_error']
    assert receipt_names(phase) == [] and len(phase.world.containers) == 1


def test_a_container_that_is_still_present_after_removal_fails_the_stage(tmp_path, monkeypatch):
    phase = staged_phase1_world(tmp_path, monkeypatch)
    runner = phase.owner.services.docker_runner

    def stubborn(argv):
        if argv[:2] == ['docker', 'rm']:
            return SimpleNamespace(returncode=0, stdout=argv[2] + '\n', stderr='')           # says removed, removes nothing
        return runner(argv)
    phase.owner.services.docker_runner = stubborn
    drive_phase1(phase)
    cleanup = json.loads((phase.owner.root / 'host/campaign-cleanup.json').read_text())
    assert cleanup['terminated'] is False and 'STAGE_CONTAINER_STILL_PRESENT' in cleanup['container_receipt_error']
    assert receipt_names(phase) == []


def test_a_container_not_proven_exited_is_not_removed_and_the_stage_fails(tmp_path, monkeypatch):
    phase = staged_phase1_world(tmp_path, monkeypatch)
    original = phase.owner.services.inspect_container

    def running(record):
        document = original(record['owner']['container_id'])
        return dict(document, State=dict(document['State'], Running=True, Status='running'))
    phase.owner._live_document = running
    drive_phase1(phase)
    cleanup = json.loads((phase.owner.root / 'host/campaign-cleanup.json').read_text())
    assert cleanup['terminated'] is False and 'LAUNCH_STOP_UNCONFIRMED' in cleanup['container_receipt_error']
    assert receipt_names(phase) == [] and len(phase.world.containers) == 1
    assert [call for call in phase.world.calls if call[:2] == ['docker', 'rm']] == []


def test_a_stage_that_did_not_complete_removes_nothing_and_writes_no_receipt(tmp_path, monkeypatch):
    phase = staged_phase1_world(tmp_path, monkeypatch)

    async def fail(*args, **kwargs):
        raise ValueError('phase 1 failed')
    phase.owner._finish_phase1 = fail
    with pytest.raises(ValueError, match='phase 1 failed'):
        drive_phase1(phase)
    assert receipt_names(phase) == [] and len(phase.world.containers) == 1
    assert json.loads((phase.owner.root / 'host/campaign-cleanup.json').read_text())['terminated'] is True
