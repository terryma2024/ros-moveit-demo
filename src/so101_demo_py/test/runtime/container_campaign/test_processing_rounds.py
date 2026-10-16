"""Independent per-round readback and final-attempt selection from synthetic sealed evidence."""

import json

import pytest

from processed_fixture import Processed, echo_reader
from so101_demo.runtime.container_campaign import processing_verifier
from so101_demo.runtime.container_campaign.processing_scheduler import ProcessingJournal
from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index
from so101_demo.runtime.container_campaign.service_owner import _write


def recorded_round(tmp_path, recording_round, states):
    root = tmp_path / 'run'
    host = root / 'host' if recording_round == 0 else root / 'host' / f'retry-{recording_round}'
    journal = ProcessingJournal(host / 'processing-journal.jsonl')
    rows, summary = [], []
    for scene, (number, outcome) in states.items():
        fixture = Processed(tmp_path, scene, number=number, valid=outcome == 'VALID', wave_index=recording_round)
        rows.append(fixture.row())
        if outcome == 'MISSING':
            journal.append('scene_missing', scene_id=scene, reason='PROCESSING_DEADLINE')
            summary.append(dict(scene_id=scene, status='MISSING', reason='PROCESSING_DEADLINE', attempts=0))
            continue
        journal.append('dispatch', scene_id=scene, task_id=f'{scene}-proc-{number}', proc_attempt=number,
                       processor_id='p00', launch_generation=recording_round + 1, output_dir=str(fixture.output))
        journal.append('result', scene_id=scene, task_id=f'{scene}-proc-{number}', proc_attempt=number,
                       outcome='REFUSED' if outcome == 'FAULT' else outcome, processor_rc=0)
        if outcome == 'FAULT':
            journal.append('scene_fault', scene_id=scene, fault='PROCESSING_REFUSED', reason='REFUSED')
            summary.append(dict(scene_id=scene, status='FAULT', fault='PROCESSING_REFUSED', reason='REFUSED', attempts=1))
        else:
            summary.append(dict(scene_id=scene, status='FINAL', outcome=outcome, attempts=1,
                                output_dir=str(fixture.output)))
    _write(host / 'processing-result.json', dict(scenes=summary, processors_stopped=True))
    wave = dict(wave_index=recording_round, scene_count=len(rows), case_results=rows)
    return dict(recording_round=recording_round, scene_ids=list(states), waves=[wave])


def verify(tmp_path, rounds, ids=('a', 'b')):
    return processing_verifier.verify_rounds(tmp_path / 'run', rounds, list(ids), readback_workers=1,
                                             processed_reader=echo_reader)


def test_a_retry_recovers_only_its_candidate_and_the_index_exports_only_the_final_attempt(tmp_path):
    first = recorded_round(tmp_path, 0, dict(a=(1, 'INVALID'), b=(1, 'VALID')))
    second = recorded_round(tmp_path, 1, dict(a=(2, 'VALID')))
    combined = verify(tmp_path, [first, second])
    recovered, untouched = combined['scenes']
    assert recovered['verdict']['export_eligible'] is True and recovered['wave_index'] == 1
    assert [item['attempts'][0]['proc_attempt'] for item in recovered['recording_attempts']] == [1, 2]
    assert len(untouched['recording_attempts']) == 1 and combined['counts']['PROCESSED'] == 2
    index = build_frozen_index(campaign_id='c', qualification=False, scene_count=2, combined=combined)
    assert index['schema_version'] == 3 and len(index['collected_tasks']) == 3
    attempts = [item for item in index['collected_tasks'] if item['scene_id'] == 'a']
    assert [(item['recording_round'], item['wave_index'], item['final']) for item in attempts] == [(0, 0, False), (1, 1, True)]
    assert len(index['committed_episodes']) == 2
    assert index['committed_episodes'][0]['collection_evidence']['processing_output'].endswith('a-lease-1-proc-2')
    result = processing_verifier.build_campaign_result('c', 2, combined)
    assert result['rounds'] == combined['rounds'] and len(result['rounds']) == 2


@pytest.mark.parametrize('outcome', ['FAULT', 'MISSING'])
def test_an_unsuccessful_retry_is_listed_and_cannot_supersede_a_final_verdict(tmp_path, outcome):
    first = recorded_round(tmp_path, 0, dict(a=(1, 'INVALID'), b=(1, 'VALID')))
    second = recorded_round(tmp_path, 1, dict(a=(2, outcome)))
    combined = verify(tmp_path, [first, second])
    item = combined['scenes'][0]
    assert item['state'] == 'PROCESSED' and item['verdict']['act_data_status'] == 'INVALID'
    assert item['recording_round'] == 0 and item['recording_attempts'][-1]['state'] == outcome
    assert combined['counts'] == dict(PROCESSED=2, FINAL_AT_PHASE1=0, FAULT=0, MISSING=0)
    assert combined['missing_evidence'] == []


@pytest.mark.parametrize('number', [1, 3])
def test_processing_numbers_cannot_repeat_or_skip_between_recording_rounds(tmp_path, number):
    first = recorded_round(tmp_path, 0, dict(a=(1, 'INVALID')))
    second = recorded_round(tmp_path, 1, dict(a=(2, 'VALID')))
    path = tmp_path / 'run/host/retry-1/processing-journal.jsonl'
    events = [json.loads(line) for line in path.read_text().splitlines()]
    for event in events:
        if 'proc_attempt' in event:
            event.update(proc_attempt=number, task_id=f'a-proc-{number}')
    path.write_text(''.join(json.dumps(event) + '\n' for event in events))
    with pytest.raises(ValueError, match='PROCESSING_ROUND_ATTEMPTS_INVALID'):
        verify(tmp_path, [first, second], ('a',))


def test_a_valid_scene_is_not_admitted_as_a_retry_candidate(tmp_path):
    first = recorded_round(tmp_path, 0, dict(a=(1, 'VALID')))
    second = recorded_round(tmp_path, 1, dict(a=(2, 'VALID')))
    with pytest.raises(ValueError, match='PROCESSING_ROUND_CANDIDATES_INVALID'):
        verify(tmp_path, [first, second], ('a',))


def test_round_zero_can_be_read_from_an_explicit_host_directory_without_changing_bytes(tmp_path):
    first = recorded_round(tmp_path, 0, dict(a=(1, 'VALID')))
    root = tmp_path / 'run'
    ordinary = processing_verifier.verify_processing(root, first['waves'], ['a'], readback_workers=1,
                                                     processed_reader=echo_reader)
    explicit = processing_verifier.verify_processing(root, first['waves'], ['a'], host_dir=root / 'host',
                                                     readback_workers=1, processed_reader=echo_reader)
    assert json.dumps(ordinary, sort_keys=True) == json.dumps(explicit, sort_keys=True)
    assert 'rounds' not in ordinary and 'recording_attempts' not in ordinary['scenes'][0]


@pytest.mark.parametrize('change', ['round_gap', 'duplicate_scene', 'duplicate_wave', 'unknown_scene'])
def test_round_metadata_cannot_reuse_waves_or_change_the_frozen_scene_list(tmp_path, change):
    first = recorded_round(tmp_path, 0, dict(a=(1, 'INVALID')))
    second = recorded_round(tmp_path, 1, dict(a=(2, 'VALID')))
    if change == 'round_gap':
        second['recording_round'] = 2
    elif change == 'duplicate_scene':
        second['scene_ids'].append('a')
    elif change == 'duplicate_wave':
        second['waves'][0]['wave_index'] = 0
    else:
        second['scene_ids'] = ['foreign']
    with pytest.raises(ValueError, match='PROCESSING_ROUND'):
        verify(tmp_path, [first, second], ('a',))
