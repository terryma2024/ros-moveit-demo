"""The qualification recomputation over a two-phase run: both phases are re-verified from files and compared with what is stored.

World: the controlled 40-scene world of `collection_qualification_world`, converted to a finished two-phase run by `two_phase_world`
(see its docstring for what is real and what is controlled). The synthetic rule files are TEST-ONLY; their pass counts are not
approved values. Nothing here is physical, Teacher, container or qualification evidence.
"""

import json

import pytest

from collection_qualification_world import build_world, install_controlled_qc, controlled_frozen_reader
from so101_demo.act import collection_qualification_recompute as recompute
from two_phase_world import convert, install_pending_verifier, register_processor


@pytest.fixture
def patched(monkeypatch):
    install_controlled_qc(monkeypatch)
    monkeypatch.setattr(recompute, 'read_frozen_inputs', controlled_frozen_reader)
    install_pending_verifier(monkeypatch)
    return monkeypatch


def two_phase(tmp_path, **conversion):
    (tmp_path/'world').mkdir()
    build = {key: conversion.pop(key) for key in ('no_pose',) if key in conversion}
    world = build_world(tmp_path/'world', **build)
    world.combined = convert(world, **conversion)
    return world


def run(world):
    return recompute.recompute(world.run, world.contract_path, readback_workers=1)


def passed(report):
    return {name: block['result']['passed'] for name, block in report['quality'].items()}


def test_a_complete_two_phase_run_is_qualified_with_the_inline_counts_and_phase_2_sources(tmp_path, patched):
    world = two_phase(tmp_path)
    report = run(world)
    assert report['status'] == 'QUALIFIED' and report['reasons'] == []
    assert passed(report) == dict(recorder_lossless=40, frame_continuity=40, qc_valid_rate=39, teacher_physical_success_rate=38)
    evidence = {name: block['evidence'][0]['source']['path'] for name, block in report['quality'].items()}
    assert '/processing/load-00/' in evidence['recorder_lossless'] and evidence['recorder_lossless'].endswith('/topic-loss.json')
    assert '/processing/load-00/' in evidence['frame_continuity'] and '/processing/load-00/' in evidence['qc_valid_rate']
    assert '/processing/' not in evidence['teacher_physical_success_rate'] and '/sealed/dynamic/' in evidence['teacher_physical_success_rate']
    stored = json.loads((world.run/'host/campaign-result.json').read_bytes())
    assert stored['kind'] == 'act_collection_campaign_result' and stored['counts']['PROCESSED'] == 40


def test_processor_launches_are_part_of_the_topology_and_a_gap_in_their_generations_is_not(tmp_path, patched):
    world = two_phase(tmp_path, processors=3)
    assert 'LAUNCH_TOPOLOGY_INVALID' not in run(world)['reasons']
    register_processor(world.run, 7, 2)      # generation 2 of a slot that never had generation 1
    reasons = run(world)['reasons']
    assert 'LAUNCH_TOPOLOGY_INVALID' in reasons


def test_a_scene_processing_never_delivered_is_no_evidence_in_the_denominator_and_not_qualified(tmp_path, patched):
    world = two_phase(tmp_path, missing=(5,))
    report = run(world)
    assert report['status'] == 'NOT_QUALIFIED' and 'PROCESSING_MISSING:load-05' in report['reasons']
    for name in ('recorder_lossless', 'frame_continuity', 'qc_valid_rate'):
        row = next(item for item in report['quality'][name]['evidence'] if item['scene_id'] == 'load-05')
        assert row['outcome'] == 'NO_EVIDENCE' and row['source'] is None, name
        assert report['quality'][name]['result']['denominator'] == 40
    teacher = next(item for item in report['quality']['teacher_physical_success_rate']['evidence'] if item['scene_id'] == 'load-05')
    assert teacher['outcome'] == 'PASS', 'the Teacher half is phase 1 evidence'
    assert 'QUALITY_GATE_FAILED:recorder_lossless' in report['reasons'], 'a missing scene is never a pass for an EVERY rule'


@pytest.mark.parametrize('conversion,reason', [(dict(faults=(6,)), 'PROCESSING_FAULT:load-06'),
                                               (dict(exhausted=(8,)), 'PROCESSING_FAULT:load-08')])
def test_a_refused_or_exhausted_scene_is_a_named_fault(tmp_path, patched, conversion, reason):
    world = two_phase(tmp_path, **conversion)
    report = run(world)
    assert report['status'] == 'NOT_QUALIFIED' and reason in report['reasons']


def test_a_scene_final_at_phase_1_keeps_its_verdict_and_its_place_in_the_denominator(tmp_path, patched):
    world = two_phase(tmp_path, no_pose=(4,))
    report = run(world)
    stored = {item['scene_id']: item for item in json.loads((world.run/'host/campaign-result.json').read_bytes())['scenes']}
    assert stored['load-04']['state'] == 'FINAL_AT_PHASE1' and stored['load-04']['phase2'] is None
    assert stored['load-04']['verdict']['act_data_reason'] == 'PERCEPTION_NO_POSE'
    row = next(item for item in report['quality']['teacher_physical_success_rate']['evidence'] if item['scene_id'] == 'load-04')
    assert row['outcome'] == 'NO_EVIDENCE'
    assert report['quality']['recorder_lossless']['result']['denominator'] == 40
    assert 'PROCESSING_MISSING:load-04' not in report['reasons'] and 'PROCESSING_FAULT:load-04' not in report['reasons']


def test_a_processed_result_edited_after_the_fact_is_a_fault_and_a_mismatch(tmp_path, patched):
    world = two_phase(tmp_path)
    path = world.run/'processing/load-02/load-02-lease-1-proc-1/processed-result.json'
    document = json.loads(path.read_bytes())
    document['scene_id'] = 'load-03'
    path.write_text(json.dumps(document, sort_keys=True, separators=(',', ':'))+'\n')
    reasons = run(world)['reasons']
    assert 'PROCESSING_FAULT:load-02' in reasons and 'CAMPAIGN_RESULT_MISMATCH' in reasons and 'FROZEN_INDEX_MISMATCH' in reasons


@pytest.mark.parametrize('path,reason', [('host/campaign-result.json', 'CAMPAIGN_RESULT_MISMATCH'),
                                         ('collection-index.json', 'FROZEN_INDEX_MISMATCH'),
                                         ('host/processing-result.json', 'CAMPAIGN_RESULT_MISMATCH')])
def test_every_stored_two_phase_document_is_compared_with_the_recomputation(tmp_path, patched, path, reason):
    world = two_phase(tmp_path)
    target = world.run/path
    raw = target.read_bytes()
    target.write_bytes(raw.replace(b'load-0', b'load-9', 1) if path.endswith('.json') and path != 'host/processing-result.json'
                       else raw+b' ')
    assert reason in run(world)['reasons']


def test_a_missing_campaign_result_is_named(tmp_path, patched):
    world = two_phase(tmp_path)
    (world.run/'host/campaign-result.json').unlink()
    assert 'CAMPAIGN_RESULT_MISSING' in run(world)['reasons']


def test_cleanup_must_confirm_every_processor_too(tmp_path, patched):
    world = two_phase(tmp_path)
    cleanup = json.loads((world.run/'host/campaign-cleanup.json').read_bytes())
    cleanup['processors'][1]['terminated'] = False
    world.edit_json(world.run/'host/campaign-cleanup.json', lambda document: document.update(processors=cleanup['processors']))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons']
    del cleanup['processors']
    world.edit_json(world.run/'host/campaign-cleanup.json', lambda document: document.pop('processors'))
    assert 'CLEANUP_UNCONFIRMED' in run(world)['reasons'], 'a processor launch with no cleanup record is unconfirmed'


def test_a_journal_line_added_after_the_fact_changes_the_hash_the_result_binds(tmp_path, patched):
    world = two_phase(tmp_path)
    path = world.run/'host/processing-journal.jsonl'
    count = len(path.read_text().splitlines())
    path.write_text(path.read_text()+json.dumps(dict(schema_version=1, kind='ACT_PROCESSING_JOURNAL', seq=count+1,
                                                      monotonic_s=1.0, event='noise'))+'\n')
    assert 'CAMPAIGN_RESULT_MISMATCH' in run(world)['reasons']


def test_a_journal_that_cannot_be_read_is_a_named_reason(tmp_path, patched):
    world = two_phase(tmp_path)
    path = world.run/'host/processing-journal.jsonl'
    path.write_text(path.read_text()+'not json\n')
    assert 'PROCESSING_RECORD_INVALID' in run(world)['reasons']


def test_a_functional_two_phase_run_is_still_refused_as_qualification_evidence(tmp_path, patched):
    from collection_qualification_world import ref, write_json

    world = two_phase(tmp_path)
    functional = write_json(world.inputs/'functional-run.json', dict(schema_version=1, kind='ACT_COLLECTION_FUNCTIONAL_RUN',
        run_id='functional-1', worker_count=8, scene_manifest=ref(world.functional),
        controlled_identity=world.contract['controlled_identity']))
    with pytest.raises(ValueError, match='QUALIFICATION_CONTRACT_UNREADABLE'):
        recompute.recompute(world.run, functional, readback_workers=1)


def test_a_phase_1_task_fault_is_re_verified_as_a_named_reason_and_the_wave_is_not_invalid(tmp_path, patched):
    world = two_phase(tmp_path, task_faults=(15,))    # the second reserved scene of w07 in wave 0
    report = run(world)
    scene = world.scenes[15]
    assert report['status'] == 'NOT_QUALIFIED'
    assert f'TASK_FAILED:wave-0-w07-{scene}' in report['reasons']
    refused = [reason for reason in report['reasons'] if reason.split(':')[0] in (
        'WAVE_RECOMPUTE_INVALID', 'WAVE_RECORD_MISMATCH', 'INSTANCE_SHORT', 'PROCESSING_RECORD_INVALID', 'PROCESSING_FAULT',
        'CAMPAIGN_RESULT_MISMATCH', 'FROZEN_INDEX_MISMATCH', 'LAUNCH_TOPOLOGY_INVALID', 'CLEANUP_UNCONFIRMED')]
    assert refused == [], 'the stored documents of the fault shape recompute byte for byte'
    for name in ('recorder_lossless', 'frame_continuity', 'qc_valid_rate', 'teacher_physical_success_rate'):
        assert report['quality'][name]['result']['denominator'] == 40, name
        assert scene not in [item['scene_id'] for item in report['quality'][name]['evidence'] if item['outcome'] == 'PASS']
    stored = json.loads((world.run/'host/campaign-result.json').read_bytes())
    assert next(item for item in stored['scenes'] if item['scene_id'] == scene)['state'] == 'FAULT'
