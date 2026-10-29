"""The qualification recomputation over a run collected stage by stage (phase 1, phase 2, finalize in separate calls).

Such a run has no single `campaign-cleanup.json` that covers every launch: the owner writes one cleanup record per stage, each naming the
hash-chained container receipt of its stage. The recomputation confirms the cleanup from those records, from the stage completion records
and from the receipts (the verifier the stages use), and requires the records to cover every registered launch exactly once. The
all-in-one run keeps the single combined record. World: `two_phase_world.to_staged` (CONTROLLED, see its docstring); nothing here is
container or qualification evidence.
"""

import json
import shutil

import pytest

from collection_qualification_world import build_world, install_controlled_qc, controlled_frozen_reader
from so101_demo.act import collection_qualification_recompute as recompute
from two_phase_world import convert, install_pending_verifier, to_staged


@pytest.fixture
def patched(monkeypatch):
    install_controlled_qc(monkeypatch)
    monkeypatch.setattr(recompute, 'read_frozen_inputs', controlled_frozen_reader)
    install_pending_verifier(monkeypatch)
    return monkeypatch


def staged(tmp_path, attempts=None, receipted_failures=(), **conversion):
    (tmp_path/'world').mkdir(parents=True)
    world = build_world(tmp_path/'world')
    world.combined = convert(world, **conversion)
    to_staged(world.run, attempts=attempts, receipted_failures=receipted_failures)
    return world


def run(world):
    return recompute.recompute(world.run, world.contract_path, readback_workers=1)


def host(world):
    return world.run/'host'


def edit(path, mutate):
    document = json.loads(path.read_bytes())
    mutate(document)
    path.write_bytes(json.dumps(document, sort_keys=True, separators=(',', ':')).encode()+b'\n')


def test_a_staged_run_with_three_cleanup_records_and_its_receipts_is_qualified(tmp_path, patched):
    world = staged(tmp_path)
    report = run(world)
    assert report['reasons'] == [] and report['status'] == 'QUALIFIED'
    assert sorted(path.name for path in host(world).glob('campaign-cleanup*.json')) == [
        'campaign-cleanup-finalize.json', 'campaign-cleanup-phase2.json', 'campaign-cleanup.json']


@pytest.mark.parametrize('name', ['campaign-cleanup.json', 'campaign-cleanup-phase2.json', 'campaign-cleanup-finalize.json'])
def test_a_missing_stage_cleanup_record_is_unconfirmed(tmp_path, patched, name):
    world = staged(tmp_path)
    (host(world)/name).unlink()
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


@pytest.mark.parametrize('stage', ['phase2', 'finalize'])
def test_a_missing_stage_completion_record_is_unconfirmed(tmp_path, patched, stage):
    world = staged(tmp_path)
    (host(world)/f'{stage}-complete.json').unlink()
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_a_launch_that_no_stage_record_covers_is_unconfirmed(tmp_path, patched):
    world = staged(tmp_path)
    edit(host(world)/'campaign-cleanup.json', lambda document: document['shards'].pop())
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_a_processor_missing_from_the_phase_2_record_is_unconfirmed(tmp_path, patched):
    world = staged(tmp_path)
    edit(host(world)/'campaign-cleanup-phase2.json', lambda document: document['processors'].pop())
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_a_launch_named_by_two_stage_records_or_by_none_is_unconfirmed(tmp_path, patched):
    world = staged(tmp_path)
    edit(host(world)/'campaign-cleanup-finalize.json',
         lambda document: document['shards'].append(dict(terminated=True, launch_id='wave-0-w00-g1', errors=[])))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']
    world = staged(tmp_path/'unknown')
    edit(host(world)/'campaign-cleanup-phase2.json',
         lambda document: document['processors'].append(dict(terminated=True, launch_id='processing-p09-g1', errors=[])))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_a_stage_record_that_does_not_say_terminated_is_unconfirmed(tmp_path, patched):
    world = staged(tmp_path)
    edit(host(world)/'campaign-cleanup-phase2.json', lambda document: document['processors'][0].update(terminated=False))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']
    world = staged(tmp_path/'top')
    edit(host(world)/'campaign-cleanup.json', lambda document: document.update(terminated=False))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


@pytest.mark.parametrize('name,mutate', [
    ('campaign-cleanup.json', lambda document: document.update(extra=1)),
    ('campaign-cleanup.json', lambda document: document.update(processors=[])),
    ('campaign-cleanup-phase2.json', lambda document: document.pop('processors')),
    ('campaign-cleanup-finalize.json', lambda document: document.pop('container_receipt')),
    ('campaign-cleanup-finalize.json', lambda document: document.update(container_receipt='containers-receipt-01-phase1.json')),
    ('campaign-cleanup.json', lambda document: document.update(stop_reason='OTHER')),
])
def test_every_stage_record_has_its_exact_key_set_and_names_its_own_receipt(tmp_path, patched, name, mutate):
    world = staged(tmp_path)
    edit(host(world)/name, mutate)
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_a_broken_receipt_is_unconfirmed(tmp_path, patched):
    world = staged(tmp_path)
    receipt = host(world)/'containers-receipt-02-phase2.json'
    edit(receipt, lambda document: document['containers'][0].update(exit_code=9))     # no longer the canonical bytes it was written with
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_a_deleted_receipt_a_broken_chain_or_an_altered_log_is_unconfirmed(tmp_path, patched):
    world = staged(tmp_path)
    (host(world)/'containers-receipt-02-phase2.json').unlink()
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']
    world = staged(tmp_path/'log')
    log = next((host(world)/'container-logs'/'phase1').glob('*.log'))
    log.write_bytes(log.read_bytes()+b'x')
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']
    world = staged(tmp_path/'gone')
    shutil.rmtree(host(world)/'container-logs'/'phase2')
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']
    world = staged(tmp_path/'bound')
    record = host(world)/'phase2-complete.json'
    edit(record, lambda document: document.update(note='altered'))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_the_all_in_one_run_keeps_its_single_combined_record(tmp_path, patched):
    (tmp_path/'world').mkdir()
    world = build_world(tmp_path/'world')
    world.combined = convert(world)
    assert not list(host(world).glob('*-complete.json')) and run(world)['reasons'] == []
    edit(host(world)/'campaign-cleanup.json', lambda document: document.pop('processors'))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_a_stage_completed_by_its_second_attempt_is_qualified_from_the_cleanup_record_of_that_attempt(tmp_path, patched):
    world = staged(tmp_path, attempts=dict(phase2=2))
    assert sorted(path.name for path in host(world).glob('campaign-cleanup*.json')) == [
        'campaign-cleanup-finalize.json', 'campaign-cleanup-phase2.a2.json', 'campaign-cleanup-phase2.json', 'campaign-cleanup.json']
    report = run(world)
    assert report['reasons'] == [] and report['status'] == 'QUALIFIED'


@pytest.mark.parametrize('damage', ['missing', 'not terminated', 'other key set'])
def test_the_cleanup_record_of_the_attempt_that_completed_the_stage_is_the_one_that_counts(tmp_path, patched, damage):
    world = staged(tmp_path, attempts=dict(phase2=2))
    path = host(world)/'campaign-cleanup-phase2.a2.json'
    if damage == 'missing':
        path.unlink()
    elif damage == 'not terminated':
        edit(path, lambda document: document.update(terminated=False))
    else:
        edit(path, lambda document: document.update(extra=1))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']


def test_a_failed_attempt_with_its_own_receipt_is_part_of_the_cleanup_proof(tmp_path, patched):
    world = staged(tmp_path, attempts=dict(finalize=2), receipted_failures=('finalize',))
    assert (host(world)/'containers-receipt-03-finalize-a1.json').is_file()
    report = run(world)
    assert report['reasons'] == [] and report['status'] == 'QUALIFIED'


@pytest.mark.parametrize('damage', ['record missing', 'not terminated', 'names another receipt'])
def test_a_failed_attempt_whose_record_does_not_prove_its_receipt_is_unconfirmed(tmp_path, patched, damage):
    world = staged(tmp_path, attempts=dict(finalize=2), receipted_failures=('finalize',))
    path = host(world)/'campaign-cleanup-finalize.json'
    if damage == 'record missing':
        path.unlink()
    elif damage == 'not terminated':
        edit(path, lambda document: document.update(terminated=False))
    else:
        edit(path, lambda document: document.update(container_receipt='containers-receipt-01-phase1.json'))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']
