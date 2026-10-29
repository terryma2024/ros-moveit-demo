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


# ---- attempts: a stage that failed after admission and provably stopped may run again under attempt-suffixed names ---------------

def failed_attempt(host, stage, attempt, *, terminated=True, **cleanup):
    records.runtime_used_path(host, stage, attempt).write_bytes(b'{}\n')
    records.cleanup_path(host, stage, attempt).write_bytes(records.canonical_json(dict(terminated=terminated, shards=[], **cleanup)) + b'\n')


def test_attempt_names_keep_the_plain_name_for_the_first_attempt(tmp_path):
    assert records.attempt_suffix(1) == '' and records.attempt_suffix(2) == '.a2'
    assert records.attempt_tag('retry-1', 1) == 'retry-1' and records.attempt_tag('retry-1', 3) == 'retry-1-a3'
    assert records.runtime_used_path(tmp_path, 'phase2').name == 'runtime-used-phase2.json'
    assert records.runtime_used_path(tmp_path, 'phase2', 2).name == 'runtime-used-phase2.a2.json'
    assert records.cleanup_path(tmp_path, 'retry-1', 2).name == 'campaign-cleanup-retry-1.a2.json'
    assert records.retry_decision_path(tmp_path, 1).name == 'retry-round-1.json'
    assert records.retry_decision_path(tmp_path, 2, 3).name == 'retry-round-2.a3.json'
    for bad in (0, -1, 99, '2', None):
        with pytest.raises(ValueError, match='STAGE_ATTEMPT_INVALID'):
            records.attempt_suffix(bad)


def test_a_first_attempt_record_is_byte_identical_to_what_was_always_written(tmp_path):
    plain = write(tmp_path, records.PHASE1)
    other = tmp_path / 'other'
    other.mkdir()
    again = records.write_record(other, records.PHASE1, dict(BODY), attempt=1)
    assert again['sha256'] == plain['sha256'] and 'attempt' not in again
    second = records.write_record(other, records.PHASE2, dict(BODY), previous=again, attempt=2)
    assert second['attempt'] == 2 and records.record_attempt(records.read_record(other, records.PHASE2)) == 2
    assert records.record_attempt(plain) == 1


def test_a_stage_that_never_ran_is_attempt_one(tmp_path):
    assert records.next_attempt(tmp_path, 'retry-1') == 1


def test_a_failed_attempt_with_a_cleanup_proving_the_stop_gives_the_next_attempt(tmp_path):
    failed_attempt(tmp_path, 'retry-1', 1)
    assert records.attempts_started(tmp_path, 'retry-1') == [1] and records.attempts_started(tmp_path, 'retry-2') == []
    assert records.next_attempt(tmp_path, 'retry-1') == 2
    failed_attempt(tmp_path, 'retry-1', 2)
    assert records.next_attempt(tmp_path, 'retry-1') == 3


def test_a_cleanup_record_alone_counts_as_an_attempt(tmp_path):
    records.cleanup_path(tmp_path, 'phase2').write_bytes(b'{"terminated":true,"shards":[]}\n')       # failed before runtime-used
    assert records.next_attempt(tmp_path, 'phase2') == 2


@pytest.mark.parametrize('damage', ['no cleanup', 'not terminated', 'not json', 'launched shards', 'launched processors', 'gap'])
def test_an_attempt_that_is_not_a_proven_stop_blocks_the_next_one(tmp_path, damage):
    failed_attempt(tmp_path, 'retry-1', 1)
    plain = records.cleanup_path(tmp_path, 'retry-1')
    if damage == 'no cleanup':
        plain.unlink()
    elif damage == 'not terminated':
        plain.write_bytes(records.canonical_json(dict(terminated=False, shards=[])) + b'\n')
    elif damage == 'not json':
        plain.write_bytes(b'{')
    elif damage == 'launched shards':
        plain.write_bytes(records.canonical_json(dict(terminated=True, shards=[{'launch_id': 'x'}])) + b'\n')
    elif damage == 'launched processors':
        plain.write_bytes(records.canonical_json(dict(terminated=True, shards=[], processors=[{'launch_id': 'p'}])) + b'\n')
    else:
        failed_attempt(tmp_path, 'retry-1', 3)                                  # attempt 2 left nothing
    with pytest.raises(ValueError, match='STAGE_ATTEMPT_PREVIOUS_UNPROVEN'):
        records.next_attempt(tmp_path, 'retry-1')


def test_a_complete_stage_is_never_given_another_attempt(tmp_path):
    first = write(tmp_path, records.PHASE1)
    failed_attempt(tmp_path, 'phase2', 1)
    assert records.next_attempt(tmp_path, 'phase2') == 2
    write(tmp_path, records.PHASE2, previous=first, attempt=2)
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        records.next_attempt(tmp_path, 'phase2')


@pytest.mark.parametrize('stage,leftover', [('phase2', 'processing-journal.jsonl'), ('phase2', 'processing-result.json'),
                                            ('retry-2', 'retry-2-waves.json'), ('retry-2', 'retry-2')])
def test_a_failed_attempt_that_left_stage_outputs_is_not_run_again(tmp_path, stage, leftover):
    failed_attempt(tmp_path, stage, 1)
    path = tmp_path / leftover
    if leftover == 'retry-2':
        path.mkdir()
    else:
        path.write_bytes(b'x')
    with pytest.raises(ValueError, match='STAGE_ATTEMPT_OUTPUTS_LEFT'):
        records.next_attempt(tmp_path, stage)


def test_a_finalize_that_left_the_campaign_result_or_the_index_is_not_run_again(tmp_path):
    host = tmp_path / 'host'
    host.mkdir()
    failed_attempt(host, 'finalize', 1)
    (tmp_path / 'collection-index.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='STAGE_ATTEMPT_OUTPUTS_LEFT'):
        records.next_attempt(host, 'finalize')


def test_the_number_of_attempts_is_bounded(tmp_path):
    for attempt in range(1, records.MAX_ATTEMPTS + 1):
        failed_attempt(tmp_path, 'phase2', attempt)
    with pytest.raises(ValueError, match='STAGE_ATTEMPTS_EXCEEDED'):
        records.next_attempt(tmp_path, 'phase2')
