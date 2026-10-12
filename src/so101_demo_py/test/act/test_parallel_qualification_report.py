"""The container-collection qualification report: written from the originals of a run, never from a claim.

The world (`collection_qualification_world.py`) is a 40-scene, two-wave, eight-instance run on disk. REAL: the run layout, the
launch registry (Teacher plus sixteen shards, bound and settled through the shard stop evidence), the task journals, the sealed
results (with `ActCollectionResultStore`, `EpisodeRecorder`, `EpisodeAuditWriter`, `topic_loss`, including the manifest-free
perception no-pose form), the task result summaries, the wave verifier that wrote `wave-N-verified.json`, the frozen index, the
contract and campaign-config validators. CONTROLLED: the episode bytes, the QC recomputation (the store's published report is read
back), Docker and provenance documents, the shard stop evidence, the frozen-inputs reader (see below) and the TEST-ONLY synthetic
rule files, whose pass counts are not approved values. Nothing here is physical, Teacher, container or qualification evidence.
"""

import hashlib
import json
import sqlite3

import pytest

from collection_qualification_world import (
    GPU, WORKERS, build_world, controlled_frozen_reader, install_controlled_qc, ref, sha, write_json,
)
from collection_quality_rules import synthetic_rule, write_synthetic_rules
from so101_demo.act import collection_qualification_recompute as recompute
from so101_demo.act.parallel_qualification_verifier import build_collection_qualification_report
from so101_demo.runtime.parallel_ipc.frames import canonical_json

NAMES = ('recorder_lossless', 'frame_continuity', 'qc_valid_rate', 'teacher_physical_success_rate')


@pytest.fixture
def patched(monkeypatch):
    install_controlled_qc(monkeypatch)
    monkeypatch.setattr(recompute, 'read_frozen_inputs', controlled_frozen_reader)
    return monkeypatch


@pytest.fixture
def world(tmp_path, patched):
    (tmp_path/'world').mkdir()
    return build_world(tmp_path/'world')


def make(tmp_path, **kwargs):
    (tmp_path/'world').mkdir()
    return build_world(tmp_path/'world', **kwargs)


def build(world):
    path = build_collection_qualification_report(world.run, contract=world.contract_path)
    document = json.loads(path.read_bytes())
    # every reason is a code of the closed vocabulary, optionally with one parameter
    assert {reason.split(':', 1)[0] for reason in document['reasons']} <= recompute.REASON_CODES
    return path, document


def test_qualified_report_from_two_waves_of_twenty(world):
    path, document = build(world)
    assert path == world.run/'host/qualification-report.json'
    assert document['status'] == 'QUALIFIED' and document['reasons'] == []
    assert document['kind'] == 'ACT_PARALLEL_COLLECTION_QUALIFICATION' and document['schema_version'] == 1
    assert document['worker_count'] == 8 and document['qualification_run_id'] == 'gate-run'
    assert document['controlled_identity'] == world.contract['controlled_identity']
    assert document['contract'] == ref(world.contract_path)
    assert document['campaign_index'] == ref(world.run/'campaign-index.json')
    assert document['waves'] == [ref(world.run/f'host/wave-{index}-verified.json') for index in (0, 1)]
    assert path.read_bytes() == canonical_json(document)+b'\n'
    assert list(document['quality']) == sorted(NAMES)
    for name in NAMES:
        block = document['quality'][name]
        assert block['rule'] == world.rule_refs[name] and len(block['evidence']) == 40
        assert [row['scene_id'] for row in block['evidence']] == world.scenes
        assert block['result']['population'] == 'ALL_FROZEN_SCENES' and block['result']['verdict'] == 'PASS'
        for row in block['evidence']:
            assert set(row) == {'scene_id', 'task_id', 'registration', 'source', 'outcome'}
            assert row['registration']['sha256'] == sha(row['registration']['path'])
    # per-gate counts of the labelled default world: two Teacher FAILs with valid data and one Teacher-reference QC FAIL
    passed = {name: document['quality'][name]['result']['passed'] for name in NAMES}
    assert passed == dict(recorder_lossless=40, frame_continuity=40, qc_valid_rate=39, teacher_physical_success_rate=38)
    teacher = {row['scene_id']: row['outcome'] for row in document['quality']['teacher_physical_success_rate']['evidence']}
    assert teacher['load-03'] == teacher['load-11'] == 'FAIL' and teacher['load-00'] == 'PASS'
    assert {row['outcome'] for row in document['quality']['qc_valid_rate']['evidence'] if row['scene_id'] == 'load-07'} == {'FAIL'}
    source = document['quality']['recorder_lossless']['evidence'][0]['source']
    assert source['path'].endswith('/sealed/topic-loss.json') and source['sha256'] == sha(source['path'])
    assert [row['source']['path'].rsplit('/', 1)[1] for row in document['quality']['teacher_physical_success_rate']['evidence']][0] == \
        'dynamic-execute-manifest.json'
    assert [item['path'] for item in document['resource_logs']] == [str(world.run/'host/resources.jsonl')]


def test_report_matches_the_installed_closed_schema(world):
    from pathlib import Path
    from jsonschema import Draft202012Validator, ValidationError
    schema = json.loads((Path(__file__).parents[2]/'config/act/parallel-qualification-schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    _, document = build(world)
    Draft202012Validator(schema).validate(document)
    for bad in (dict(document, extra=1), dict(document, status='PASSED'), dict(document, worker_count=6),
                {key: value for key, value in document.items() if key != 'reasons'},
                dict(document, waves=document['waves']*2), dict(document, kind='ACT_PARALLEL_COLLECTION_GATE')):
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(bad)


def test_report_is_not_overwritten(world):
    path, _ = build(world)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='QUALIFICATION_REPORT_EXISTS'):
        build(world)
    assert path.read_bytes() == before


def test_missing_wave_writes_not_qualified(world):
    (world.run/'host/wave-1-verified.json').unlink()
    path, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and 'WAVE_VERIFIED_MISSING:1' in document['reasons']
    assert document['waves'] == [ref(world.run/'host/wave-0-verified.json')]
    assert document['reasons'] == sorted(set(document['reasons']))


def test_failed_task_record_writes_not_qualified(world):
    scene = world.plans[1]['scene_ids'][0]
    task = next(path for path in (world.run/'host/wave-1/task-journal').iterdir() if path.name.endswith(scene))
    assigned = json.loads((task/'assigned.json').read_bytes())
    (task/'collected.json').unlink()
    failed = {key: assigned[key] for key in ('task_id', 'instance_id', 'worker_id', 'launch_generation', 'wave_id', 'scene_id',
                                             'owner_root', 'host_output')}
    failed.update(schema_version=1, kind='ACT_CONTAINER_TASK_FAILED', reason='controlled execution fault', failed_monotonic_s=1.)
    (task/'failed.json').write_bytes(canonical_json(failed)+b'\n')
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and f'TASK_FAILED:{task.name}' in document['reasons']


def test_unfinished_task_record_writes_not_qualified(world):
    task = next(iter((world.run/'host/wave-0/task-journal').iterdir()))
    (task/'collected.json').unlink()
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and f'TASK_UNFINISHED:{task.name}' in document['reasons']


def test_one_instance_short_writes_not_qualified(tmp_path, patched):
    # the planned reservation of w05 (which has no surplus task) moves to w06: w05 collects fewer than two tasks
    scene = f'load-{20+10:02d}'    # wave 1, w05's first reserved scene
    world = make(tmp_path, reassign={scene: 'w06'})
    assert world.build_errors and 'INSTANCE_SHORT' in str(world.build_errors[0][1])
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED'
    assert 'INSTANCE_SHORT:wave-1/w05' in document['reasons'] and 'WAVE_VERIFIED_MISSING:1' in document['reasons']


def test_surplus_before_reserved_writes_not_qualified(tmp_path, patched):
    world = make(tmp_path, surplus_early=(1,))
    assert world.build_errors
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED'
    assert any(reason.startswith('SURPLUS_BEFORE_RESERVED:wave-1/') for reason in document['reasons'])


@pytest.mark.parametrize('problem', ['missing_shard_row', 'extra_launch'])
def test_extra_or_missing_launch_writes_not_qualified(world, problem):
    if problem == 'missing_shard_row':
        with sqlite3.connect(world.registry_path) as connection:
            connection.execute("DELETE FROM launches WHERE launch_id='wave-1-w05-g2'")
    else:
        from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
        registry = ContainerLaunchRegistry(world.registry_path, create=False)
        registry.register(ContainerLaunch(launch_id='head-g1', role='head', worker_id=None, wave_id=None, launch_generation=1,
            container_name='so101-qualification-head', image_digest='sha256:'+'b'*64, owned_root=str(world.run/'services/head')))
        registry.close()
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and 'LAUNCH_TOPOLOGY_INVALID' in document['reasons']


@pytest.mark.parametrize('problem', ['registry_exit_missing', 'cleanup_not_terminated', 'cleanup_other_stop_reason',
                                     'stop_evidence_removed'])
def test_unterminated_container_writes_not_qualified(world, problem):
    if problem == 'registry_exit_missing':
        with sqlite3.connect(world.registry_path) as connection:
            connection.execute("UPDATE launches SET exit_json=NULL WHERE launch_id='wave-0-w02-g1'")
    elif problem == 'cleanup_not_terminated':
        world.edit_json(world.run/'host/campaign-cleanup.json', lambda value: value.update(terminated=False))
    elif problem == 'cleanup_other_stop_reason':
        world.edit_json(world.run/'host/campaign-cleanup.json', lambda value: value.update(stop_reason='CAMPAIGN_DEADLINE_EXPIRED'))
    else:
        (world.owners['wave-0', 'w01']/'shard-stop.json').write_text('{}')
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and 'CLEANUP_UNCONFIRMED' in document['reasons']


def test_dispatch_fault_writes_not_qualified(world):
    (world.run/'host/dispatch-fault.json').write_bytes(canonical_json(dict(type='ValueError', reason='controlled'))+b'\n')
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and 'DISPATCH_FAULT' in document['reasons']


def test_campaign_result_or_index_that_differs_from_the_recomputation_is_reported(world):
    world.edit_json(world.run/'host/campaign-result.json', lambda value: value.update(scene_count=39))
    world.edit_json(world.run/'collection-index.json', lambda value: value.update(qualification=False))
    _, document = build(world)
    assert {'CAMPAIGN_RESULT_MISMATCH', 'FROZEN_INDEX_MISMATCH'} <= set(document['reasons'])


def test_stored_wave_record_that_differs_from_the_recomputation_is_reported(world):
    world.edit_json(world.run/'host/wave-0-verified.json', lambda value: value['case_results'][0].update(task_id='wave-0-w00-other'))
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and 'WAVE_RECORD_MISMATCH:0' in document['reasons']


def test_campaign_index_that_is_not_the_recomputed_plan_is_reported(world):
    world.edit_json(world.run/'campaign-index.json', lambda value: value['waves'][1]['scene_ids'].reverse())
    _, document = build(world)
    assert 'PLAN_MISMATCH' in document['reasons']


@pytest.mark.parametrize('key', ['runtime_config_sha256', 'collection_config_sha256', 'contact_policy_fingerprint',
                                 'image_source_install', 'gpu_uuid', 'manifest_sha256'])
def test_identity_differs_from_contract_writes_not_qualified(world, key):
    spec = world.run/'shard-wave-1-w03-g2.json'
    if key in ('runtime_config_sha256', 'collection_config_sha256'):
        world.edit_json(spec, lambda value: value['business_identity'].update({key: '9'*64}))
    elif key == 'contact_policy_fingerprint':
        world.edit_json(world.run/'inputs/frozen/roles/contact-proposal.json', lambda value: value.update(policy_fingerprint='9'*64))
    elif key == 'image_source_install':
        world.edit_json(world.run/'host/teacher-provenance.json', lambda value: value['provenance'].update(package_source_sha256='9'*64))
    elif key == 'gpu_uuid':
        world.edit_json(world.run/'host/teacher-ready.json', lambda value: value.update(gpu_uuid=GPU.replace('2', '3')))
    else:
        # `source_sha256` has no original under the run: it is bound only through the contract hash chain
        value = json.loads(world.contract_path.read_bytes())
        value['controlled_identity']['source_sha256'] = '9'*64
        world.contract_path.write_text(json.dumps(value, sort_keys=True))
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and f'IDENTITY_MISMATCH:{key}' in document['reasons']


def test_shard_image_provenance_and_registry_image_are_compared_with_the_contract(world):
    world.edit_json(world.owners['wave-1', 'w06']/'actual-container-provenance.json',
                    lambda value: value['provenance'].update(install_sha256='9'*64))
    _, document = build(world)
    assert 'IDENTITY_MISMATCH:image_source_install' in document['reasons']


def test_scene_binding_of_the_frozen_inputs_is_compared_with_the_contract(world):
    world.edit_json(world.run/'inputs/frozen/controlled-frozen-binding.json',
                    lambda value: value['scene_manifest'].update(sha256='9'*64))
    _, document = build(world)
    assert 'IDENTITY_MISMATCH:scene_manifest' in document['reasons']


def test_scope_that_is_not_the_scenes_own_is_reported(world):
    # a scope file carrying another scene's id; the readback binds the scope bytes, so the summary no longer matches as well
    other = world.scopes[world.scenes[1]].read_bytes()
    world.scopes[world.scenes[0]].write_bytes(other)
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED'
    assert any(reason.startswith(('SCOPE_MISMATCH:', 'WAVE_RECOMPUTE_INVALID:')) for reason in document['reasons'])


def rules_with(tmp_path, **per_name):
    directory = tmp_path/'rules'
    directory.mkdir()
    return write_synthetic_rules(directory, **per_name)


@pytest.mark.parametrize('name,world_args', [
    ('qc_valid_rate', {}),
    ('teacher_physical_success_rate', {}),
    ('recorder_lossless', dict(loss_failed=(5,))),
    ('frame_continuity', dict(no_pose=(39,))),
])
def test_quality_gate_below_rule_writes_not_qualified(tmp_path, patched, name, world_args):
    # default world: QC 39/40, Teacher 38/40; these TEST-ONLY rules are stricter than that (not approved values)
    stricter = dict(qc_valid_rate=synthetic_rule('qc_valid_rate', **{'pass': {'kind': 'EVERY'}}),
                    teacher_physical_success_rate=synthetic_rule('teacher_physical_success_rate',
                        **{'pass': {'kind': 'AT_LEAST', 'numerator': 39, 'denominator': 40}}))
    rules = rules_with(tmp_path, **({name: stricter[name]} if name in stricter else {}))
    world = make(tmp_path, rules=rules, **world_args)
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED'
    assert f'QUALITY_GATE_FAILED:{name}' in document['reasons']
    assert document['quality'][name]['result']['verdict'] == 'FAIL'
    others = {other for other in NAMES if document['quality'][other]['result']['verdict'] == 'FAIL'}
    assert name in others


def test_rule_at_exactly_the_boundary_passes_and_one_below_fails(tmp_path, patched):
    # integer arithmetic: 38 of 40 passes 19/20 exactly and fails 39/40
    def verdict(numerator, denominator):
        directory = tmp_path/f'case-{numerator}-{denominator}'
        directory.mkdir()
        rules = write_synthetic_rules(directory, teacher_physical_success_rate=synthetic_rule(
            'teacher_physical_success_rate', **{'pass': {'kind': 'AT_LEAST', 'numerator': numerator, 'denominator': denominator}}))
        world = make(directory, rules=rules)
        return build(world)[1]['quality']['teacher_physical_success_rate']['result']['verdict']
    assert verdict(19, 20) == 'PASS' and verdict(39, 40) == 'FAIL'


@pytest.mark.parametrize('problem', ['no_pass_value', 'wrong_episode_rule', 'malformed_json'])
def test_rule_without_value_is_undefined_not_pass(tmp_path, patched, problem):
    broken = synthetic_rule('qc_valid_rate')
    if problem == 'no_pass_value':
        broken.pop('pass')
    elif problem == 'wrong_episode_rule':
        broken['episode_rule'] = 'topic_loss'
    directory = tmp_path/'rules'
    directory.mkdir()
    rules = write_synthetic_rules(directory)
    path = directory/'test-only-not-approved-qc_valid_rate.json'
    path.write_text('[1, 2' if problem == 'malformed_json' else json.dumps(broken))
    rules['qc_valid_rate'] = ref(path)
    world = make(tmp_path, rules=rules)
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and 'QUALITY_RULE_UNDEFINED:qc_valid_rate' in document['reasons']
    assert document['quality']['qc_valid_rate']['result']['verdict'] == 'UNDEFINED'
    assert 'QUALITY_GATE_FAILED:qc_valid_rate' not in document['reasons']
    assert all(document['quality'][name]['result']['verdict'] == 'PASS' for name in NAMES if name != 'qc_valid_rate')


def test_no_pose_result_stays_in_every_denominator(tmp_path, patched):
    world = make(tmp_path, no_pose=(39,))
    _, document = build(world)
    last = world.scenes[39]
    for name in NAMES:
        block = document['quality'][name]
        assert len(block['evidence']) == 40 and block['result']['population'] == 'ALL_FROZEN_SCENES'
        row = block['evidence'][-1]
        assert row['scene_id'] == last and row['outcome'] == 'NO_EVIDENCE'
    for name in ('recorder_lossless', 'frame_continuity', 'qc_valid_rate'):
        assert document['quality'][name]['evidence'][-1]['source'] is None
    assert document['quality']['teacher_physical_success_rate']['evidence'][-1]['source']['path'].endswith('/sealed/result.json')
    assert document['quality']['recorder_lossless']['result']['passed'] == 39
    assert document['quality']['qc_valid_rate']['result']['passed'] == 38
    assert document['status'] == 'NOT_QUALIFIED' and 'QUALITY_GATE_FAILED:recorder_lossless' in document['reasons']


def test_unreadable_resource_log_does_not_disqualify(world):
    (world.run/'host/resources.jsonl').unlink()
    (world.run/'host/resources.jsonl').mkdir()
    _, document = build(world)
    assert document['status'] == 'QUALIFIED' and document['resource_logs'] == [] and document['reasons'] == []


def test_forged_result_that_contradicts_its_task_readback_is_not_graded(world):
    # a sealed result edited after collection breaks the registered hash: the wave cannot be recomputed
    sealed = next((world.owners['wave-0', 'w00']/'output/tasks').glob('*/attempts/*/*/sealed'))
    (sealed/'result.json').write_bytes((sealed/'result.json').read_bytes().replace(b'}', b' }', 1))
    _, document = build(world)
    assert document['status'] == 'NOT_QUALIFIED' and 'WAVE_RECOMPUTE_INVALID:0' in document['reasons']
    assert all(document['quality'][name]['result']['verdict'] == 'NOT_EVALUATED' for name in NAMES)


def test_a_run_that_cannot_be_read_raises_and_writes_nothing(world, tmp_path):
    before = world.snapshot()
    with pytest.raises(ValueError, match='QUALIFICATION_RUN_INVALID'):
        build_collection_qualification_report(tmp_path/'missing', contract=world.contract_path)
    with pytest.raises(ValueError, match='QUALIFICATION_CONTRACT_UNREADABLE'):
        build_collection_qualification_report(world.run, contract=tmp_path/'missing-gate.json')
    (world.run/'.campaign-layout.json').write_text('{}')
    with pytest.raises(ValueError, match='QUALIFICATION_RUN_INVALID'):
        build_collection_qualification_report(world.run, contract=world.contract_path)
    assert not world.report_path.exists()
    assert {key: value for key, value in world.snapshot().items() if not key.endswith('.campaign-layout.json')} == \
        {key: value for key, value in before.items() if not key.endswith('.campaign-layout.json')}


def test_contract_other_than_the_campaigns_is_not_this_runs_gate(world, tmp_path):
    other = tmp_path/'other-gate.json'
    other.write_bytes(world.contract_path.read_bytes()+b' ')
    _, document = build_for(world, other)
    assert document['status'] == 'NOT_QUALIFIED' and 'IDENTITY_MISMATCH:manifest_sha256' in document['reasons']


def test_continuity_predicate_is_the_ten_hertz_grid_and_a_single_gap_fails():
    from so101_demo.act.collection_quality_gates import intervals_on_grid
    assert intervals_on_grid([]) and intervals_on_grid([1.0]) and intervals_on_grid([1.0, 1.1, 1.2, 1.3])
    assert intervals_on_grid([1.0, 1.1000004, 1.2000009])
    assert not intervals_on_grid([1.0, 1.1, 1.3, 1.4])
    assert not intervals_on_grid([1.0, 1.1, 1.1])
    with pytest.raises(ValueError, match='EVIDENCE_INVALID'):
        intervals_on_grid([1.0, 'x'])
    with pytest.raises(ValueError, match='EVIDENCE_INVALID'):
        intervals_on_grid([1.0, float('nan')])


def test_rules_are_applied_in_integers_over_the_whole_population():
    from so101_demo.act.collection_quality_gates import apply_rule
    every, at_least = {'pass': {'kind': 'EVERY'}}, {'pass': {'kind': 'AT_LEAST', 'numerator': 9, 'denominator': 10}}
    outcomes = ['PASS']*36+['FAIL']*2+['NO_EVIDENCE']*2
    assert apply_rule(every, outcomes) == (36, 'FAIL') and apply_rule(every, ['PASS']*40) == (40, 'PASS')
    assert apply_rule(at_least, outcomes) == (36, 'PASS')    # 36*10 >= 9*40 exactly
    assert apply_rule(at_least, ['PASS']*35+['FAIL']*5) == (35, 'FAIL')
    assert apply_rule(every, []) == (0, 'FAIL')


def test_frozen_identity_is_read_from_the_fields_a_real_frozen_set_carries(tmp_path):
    contract = dict(controlled_identity=dict(runtime_config_sha256='1'*64, collection_config_sha256='2'*64,
        contact_policy_fingerprint='3'*64), scene_manifest=dict(sha256='4'*64))
    proposal = tmp_path/'contact-proposal.json'
    proposal.write_text(json.dumps(dict(policy_fingerprint='3'*64)))
    frozen = dict(roles=dict(runtime_config=dict(sha256='1'*64), collection_config=dict(sha256='2'*64),
        contact_proposal=dict(path='contact-proposal.json')), scene_manifest=dict(sha256='4'*64))
    manifest = tmp_path/'inputs-manifest.json'
    assert recompute.frozen_identity_problems(frozen, manifest, contract) == []
    drifted = json.loads(json.dumps(frozen))
    drifted['roles']['runtime_config']['sha256'] = '9'*64
    drifted['scene_manifest']['sha256'] = '9'*64
    assert recompute.frozen_identity_problems(drifted, manifest, contract) == ['runtime_config_sha256', 'scene_manifest']
    assert recompute.frozen_identity_problems({'roles': {}}, manifest, contract) == ['frozen_inputs']
    assert recompute.frozen_identity_problems(dict(frozen, scene_manifest=None), manifest, contract) == ['frozen_inputs']


def build_for(world, contract_path):
    path = build_collection_qualification_report(world.run, contract=contract_path)
    return path, json.loads(path.read_bytes())
