"""The stage completion records: the chain a stage-by-stage run continues along, and every refusal of a stage that may not start."""

import json

import pytest

from so101_demo.runtime.container_campaign import stage_records as records

LOGIC = dict(path='/c/campaign.json', sha256='a' * 64)
BODY = dict(campaign_id='c1', campaign_config=LOGIC, scene_count=2)


def write(host, stage, previous=None, **extra):
    return records.write_record(host, stage, {**BODY, **extra}, previous=previous)


def test_the_stage_order_and_the_previous_stage():
    assert records.previous_stage(records.PHASE1) is None
    assert records.previous_stage(records.PHASE2) == records.PHASE1
    assert records.previous_stage('retry-1') == records.PHASE2
    assert records.previous_stage('retry-3') == 'retry-2'


def test_a_stage_continues_from_the_record_the_earlier_stage_left(tmp_path):
    first = write(tmp_path, records.PHASE1)
    assert first['previous'] is None and len(first['sha256']) == 64
    assert records.require_previous(tmp_path, records.PHASE2, logic=LOGIC)['sha256'] == first['sha256']
    second = write(tmp_path, records.PHASE2, previous=first)
    assert second['previous'] == dict(stage='phase1', sha256=first['sha256'])
    assert records.require_previous(tmp_path, 'retry-1', logic=LOGIC)['sha256'] == second['sha256']
    assert records.last_completed(tmp_path)['stage'] == 'phase2'


def test_a_missing_previous_record_refuses(tmp_path):
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):
        records.require_previous(tmp_path, records.PHASE2, logic=LOGIC)
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):
        records.require_previous(tmp_path, records.PHASE1, logic=LOGIC)          # nothing precedes phase 1
    write(tmp_path, records.PHASE1)
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):
        records.require_previous(tmp_path, 'retry-2', logic=LOGIC)                # retry 1 never ran


def test_a_stage_that_is_already_complete_refuses(tmp_path):
    first = write(tmp_path, records.PHASE1)
    write(tmp_path, records.PHASE2, previous=first)
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        records.require_previous(tmp_path, records.PHASE2, logic=LOGIC)
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        write(tmp_path, records.PHASE2, previous=first)


def test_a_changed_logic_document_refuses(tmp_path):
    write(tmp_path, records.PHASE1)
    with pytest.raises(ValueError, match='STAGE_LOGIC_DOCUMENT_CHANGED'):
        records.require_previous(tmp_path, records.PHASE2, logic=dict(LOGIC, sha256='b' * 64))


@pytest.mark.parametrize('damage', ['not json', 'other kind', 'wrong stage', 'not canonical'])
def test_a_record_that_is_not_the_one_written_is_invalid(tmp_path, damage):
    write(tmp_path, records.PHASE1)
    path = records.record_path(tmp_path, records.PHASE1)
    document = json.loads(path.read_bytes())
    if damage == 'not json':
        path.write_bytes(b'{')
    elif damage == 'other kind':
        path.write_bytes(json.dumps(dict(document, kind='x'), sort_keys=True, separators=(',', ':')).encode() + b'\n')
    elif damage == 'wrong stage':
        path.write_bytes(json.dumps(dict(document, stage='phase2'), sort_keys=True, separators=(',', ':')).encode() + b'\n')
    else:
        path.write_bytes(json.dumps(document, indent=4).encode() + b'\n')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_INVALID'):
        records.require_previous(tmp_path, records.PHASE2, logic=LOGIC)


def test_a_record_changed_after_its_successor_named_it_breaks_the_chain(tmp_path):
    first = write(tmp_path, records.PHASE1)
    write(tmp_path, records.PHASE2, previous=first)
    path = records.record_path(tmp_path, records.PHASE1)
    document = json.loads(path.read_bytes())
    document['scene_count'] = 3                                                    # a valid record, but not the one phase 2 named
    path.write_bytes(records.canonical_json(document) + b'\n')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_INVALID'):
        records.require_previous(tmp_path, 'retry-1', logic=LOGIC)
