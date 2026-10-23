"""The two human decisions of 2026-10-14 on the W8 pass rules, as named populations and integer pass counts.

D1: `teacher_physical_success_rate` passes at 38 of 40 or more and `qc_valid_rate` at 34 of 40 or more, both over all forty
frozen scenes (a no-pose attempt, an INVALID result and a failed gate stay in the denominator as not passed).
D2: `recorder_lossless` and `frame_continuity` are judged over the episodes whose data is VALID with QC PASS
(`QC_VALID_EPISODES`), and every such episode must satisfy them; the other scenes are listed with a closed reason.

The world is `collection_qualification_world.py`; the rule files are the decided ones from `collection_quality_rules.py`.
"""

import json

import pytest

from collection_qualification_world import build_world, controlled_frozen_reader, install_controlled_qc
from collection_quality_rules import DECIDED, decided_rule, write_decided_rules
from so101_demo.act import collection_qualification_recompute as recompute
from so101_demo.act import collection_quality_gates as gates
from so101_demo.act.parallel_collection_contracts import validate_quality_rule
from so101_demo.act.parallel_qualification_verifier import (
    build_collection_qualification_report, verify_collection_qualification,
)

NAMES = tuple(DECIDED)


@pytest.fixture
def patched(monkeypatch):
    install_controlled_qc(monkeypatch)
    monkeypatch.setattr(recompute, 'read_frozen_inputs', controlled_frozen_reader)
    return monkeypatch


def run(tmp_path, **world_args):
    (tmp_path/'rules').mkdir()
    (tmp_path/'world').mkdir()
    world = build_world(tmp_path/'world', rules=write_decided_rules(tmp_path/'rules'), **world_args)
    path = build_collection_qualification_report(world.run, contract=world.contract_path)
    return world, json.loads(path.read_bytes())


# ---- the rule files --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('name', NAMES)
def test_decided_rule_documents_validate(name):
    assert validate_quality_rule(name, decided_rule(name))['population'] == DECIDED[name][0]


def test_decided_values_are_exactly_the_human_decision():
    assert DECIDED['teacher_physical_success_rate'][1] == dict(kind='AT_LEAST', numerator=38, denominator=40)
    assert DECIDED['qc_valid_rate'][1] == dict(kind='AT_LEAST', numerator=34, denominator=40)
    assert DECIDED['recorder_lossless'] == DECIDED['frame_continuity'] == ('QC_VALID_EPISODES', dict(kind='EVERY'))


@pytest.mark.parametrize('name', ['qc_valid_rate', 'teacher_physical_success_rate'])
def test_a_rate_cannot_be_narrowed_to_the_valid_episodes(name):
    with pytest.raises(ValueError, match='QUALITY_RULE_INVALID'):
        validate_quality_rule(name, decided_rule(name, population='QC_VALID_EPISODES'))


@pytest.mark.parametrize('name', ['recorder_lossless', 'frame_continuity'])
def test_the_valid_episode_population_demands_every_episode(name):
    for loosened in (dict(kind='AT_LEAST', numerator=39, denominator=40), dict(kind='AT_LEAST', numerator=1, denominator=1)):
        with pytest.raises(ValueError, match='QUALITY_RULE_INVALID'):
            validate_quality_rule(name, decided_rule(name, **{'pass': loosened}))
    assert validate_quality_rule(name, decided_rule(name, population='ALL_FROZEN_SCENES'))['population'] == 'ALL_FROZEN_SCENES'


# ---- the report -------------------------------------------------------------------------------------------------------------

def test_decided_rules_qualify_the_default_world_and_state_each_population(tmp_path, patched):
    # default world: scene 7 QC FAIL, scenes 3 and 11 Teacher FAIL with valid data
    world, document = run(tmp_path)
    assert document['reasons'] == [] and document['status'] == 'QUALIFIED'
    quality = document['quality']
    for name in ('qc_valid_rate', 'teacher_physical_success_rate'):
        result = quality[name]['result']
        assert result['population'] == 'ALL_FROZEN_SCENES' and result['denominator'] == 40 and result['excluded'] == []
        assert len(quality[name]['evidence']) == 40
    assert quality['qc_valid_rate']['result']['passed'] == 39 and quality['qc_valid_rate']['result']['verdict'] == 'PASS'
    assert quality['teacher_physical_success_rate']['result']['passed'] == 38
    for name in ('recorder_lossless', 'frame_continuity'):
        result = quality[name]['result']
        assert result['population'] == 'QC_VALID_EPISODES' and result['denominator'] == 39 and result['passed'] == 39
        assert result['excluded'] == [dict(scene_id=world.scenes[7], reason='QC_NOT_PASS')]
        assert world.scenes[7] not in [row['scene_id'] for row in quality[name]['evidence']]
        assert len(quality[name]['evidence']) == 39 and result['verdict'] == 'PASS'


def test_a_no_pose_attempt_is_excluded_from_the_episode_gates_but_stays_in_both_denominators(tmp_path, patched):
    world, document = run(tmp_path, no_pose=(39,), teacher_failed=(3,))
    assert document['status'] == 'QUALIFIED'
    quality = document['quality']
    for name in ('recorder_lossless', 'frame_continuity'):
        excluded = {item['scene_id']: item['reason'] for item in quality[name]['result']['excluded']}
        assert excluded == {world.scenes[7]: 'QC_NOT_PASS', world.scenes[39]: 'NO_QC_EVIDENCE'}
        assert quality[name]['result']['denominator'] == 38
    for name in ('qc_valid_rate', 'teacher_physical_success_rate'):
        last = quality[name]['evidence'][-1]
        assert quality[name]['result']['denominator'] == 40 and last['scene_id'] == world.scenes[39]
        assert last['outcome'] == 'NO_EVIDENCE'
    assert quality['qc_valid_rate']['result']['passed'] == 38 and quality['teacher_physical_success_rate']['result']['passed'] == 38


def test_a_topic_loss_episode_is_invalid_data_counted_against_the_qc_rate_only(tmp_path, patched):
    world, document = run(tmp_path, loss_failed=(5,))
    quality = document['quality']
    assert document['status'] == 'QUALIFIED'
    assert quality['qc_valid_rate']['result']['passed'] == 38
    for name in ('recorder_lossless', 'frame_continuity'):
        assert {item['scene_id'] for item in quality[name]['result']['excluded']} == {world.scenes[5], world.scenes[7]}
        assert quality[name]['result']['verdict'] == 'PASS'


@pytest.mark.parametrize('failed,verdict', [((3, 11), 'PASS'), ((3, 11, 12), 'FAIL')])
def test_the_teacher_count_is_exactly_38_of_40(tmp_path, patched, failed, verdict):
    _, document = run(tmp_path, teacher_failed=failed, qc_failed=())
    result = document['quality']['teacher_physical_success_rate']['result']
    assert (result['passed'], result['verdict']) == (40-len(failed), verdict)
    assert ('QUALITY_GATE_FAILED:teacher_physical_success_rate' in document['reasons']) == (verdict == 'FAIL')
    assert document['status'] == ('QUALIFIED' if verdict == 'PASS' else 'NOT_QUALIFIED')


@pytest.mark.parametrize('failed,verdict', [(tuple(range(6)), 'PASS'), (tuple(range(7)), 'FAIL')])
def test_the_qc_count_is_exactly_34_of_40_and_fewer_valid_episodes_fail_the_rate(tmp_path, patched, failed, verdict):
    _, document = run(tmp_path, qc_failed=failed, teacher_failed=())
    result = document['quality']['qc_valid_rate']['result']
    assert (result['passed'], result['verdict']) == (40-len(failed), verdict)
    assert ('QUALITY_GATE_FAILED:qc_valid_rate' in document['reasons']) == (verdict == 'FAIL')
    # the excluded invalid episodes are never a second failure of the episode gates
    assert 'QUALITY_GATE_FAILED:recorder_lossless' not in document['reasons']
    assert 'QUALITY_GATE_FAILED:frame_continuity' not in document['reasons']


def test_one_gap_in_one_valid_episode_fails_the_continuity_gate(tmp_path, patched):
    real = gates._GATES['frame_continuity']

    def continuity(sealed, result, report):
        outcome, source = real(sealed, result, report)
        if sealed.parts[-3].endswith('load-20'):
            return 'FAIL', source
        return outcome, source
    patched.setitem(gates._GATES, 'frame_continuity', continuity)
    _, document = run(tmp_path)
    assert document['status'] == 'NOT_QUALIFIED' and 'QUALITY_GATE_FAILED:frame_continuity' in document['reasons']
    result = document['quality']['frame_continuity']['result']
    assert (result['passed'], result['denominator'], result['verdict']) == (38, 39, 'FAIL')


def test_every_scene_is_either_in_the_population_or_listed_as_excluded(tmp_path, patched):
    world, document = run(tmp_path, no_pose=(39, 38), teacher_failed=())
    for name in NAMES:
        block = document['quality'][name]
        listed = [row['scene_id'] for row in block['evidence']] + [item['scene_id'] for item in block['result']['excluded']]
        assert sorted(listed) == sorted(world.scenes)
        assert block['result']['denominator'] == len(block['evidence'])


def test_the_verifier_accepts_a_report_made_under_the_decided_rules(tmp_path, patched):
    world, _ = run(tmp_path)
    proof = verify_collection_qualification(world.report_path, registered_root=world.root,
                                            expected_identity=world.contract['controlled_identity'])
    assert proof['status'] == 'PASS' and proof['task_count'] == 40


def test_the_qualification_schema_accepts_the_population_report(tmp_path, patched):
    from pathlib import Path
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).parents[2]/'config/act/parallel-qualification-schema.json').read_text())
    _, document = run(tmp_path, no_pose=(39,), teacher_failed=(3,))
    Draft202012Validator(schema).validate(document)
    rule_schema = json.loads((Path(__file__).parents[2]/'config/act/parallel-quality-rule-schema.json').read_text())
    for name in NAMES:
        Draft202012Validator(rule_schema).validate(decided_rule(name))
