"""Functional runs and independent W8 gates are distinct, closed input contracts."""

import hashlib
import importlib
import json

import pytest

from collection_quality_rules import EPISODE_RULE_OF, NAMES, synthetic_rule, write_rule, write_synthetic_rules


def module():
    return importlib.import_module('so101_demo.act.parallel_collection_contracts')


def ref(path,document):
    path.write_text(json.dumps(document))
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def identity():
    image = dict(digest='sha256:'+'a'*64,package_source_sha256='b'*64,install_sha256='c'*64)
    return dict(source_sha256='d'*64,runtime_config_sha256='e'*64,collection_config_sha256='f'*64,
        contact_policy_fingerprint='1'*64,image_source_install=dict(inference=image,shard=image),
        gpu_uuid='GPU-28221cec-9d21-7753-fd5a-da645740df19')


def fixture(tmp_path):
    scene = ref(tmp_path/'qualification-scenes.json',{'scenarios':[
        {'scene_id':f'qualification-{i:02d}','split':'validation'} for i in range(40)]})
    functional = ref(tmp_path/'functional-scenes.json',{'scenarios':[
        {'scene_id':f'functional-{i:02d}','split':'validation'} for i in range(8)]})
    formal = ref(tmp_path/'formal-scenes.json',{'scenarios':[
        {'scene_id':f'formal-{i:02d}','split':'train'} for i in range(12)]})
    # TEST-ONLY synthetic rule files (see collection_quality_rules.py): the pass counts are not approved values
    rules = write_synthetic_rules(tmp_path)
    return dict(schema_version=1,kind='ACT_PARALLEL_COLLECTION_GATE',qualification_run_id='qualification-run',
        worker_count=8,scene_manifest=scene,functional_manifest=functional,formal_split_manifest=formal,
        controlled_identity=identity(),quality_rules=rules)


def test_gate_reads_exact_disjoint_forty_eight_and_formal_manifests(tmp_path):
    document = fixture(tmp_path)
    value = module().validate_qualification_contract(document)
    assert value == document and value is not document
    assert value['worker_count'] == 8
    assert set(value['quality_rules']) == {'recorder_lossless','frame_continuity','qc_valid_rate',
                                         'teacher_physical_success_rate'}


@pytest.mark.parametrize('workers',[1,2])
def test_functional_contract_uses_same_full_eight_scene_list(tmp_path,workers):
    gate = fixture(tmp_path)
    document = dict(schema_version=1,kind='ACT_COLLECTION_FUNCTIONAL_RUN',run_id='functional-run',
        worker_count=workers,scene_manifest=gate['functional_manifest'],controlled_identity=identity())
    assert module().validate_functional_contract(document) == document


@pytest.mark.parametrize('problem',['old_kind','extra','version','workers','identity_extra','image_tag',
                                  'rule_missing','rule_extra','ref_hash','short','duplicate','overlap',
                                  'rule_is_legacy_placeholder','rule_is_valueless','rule_for_another_gate'])
def test_gate_refuses_claims_missing_current_original_inputs(tmp_path,problem):
    document = fixture(tmp_path)
    if problem == 'old_kind': document['kind'] = 'EIGHT_WORKER'
    elif problem == 'extra': document['scenes'] = 40
    elif problem == 'version': document['schema_version'] = True
    elif problem == 'workers': document['worker_count'] = 6
    elif problem == 'identity_extra': document['controlled_identity']['instances'] = 1
    elif problem == 'image_tag': document['controlled_identity']['image_source_install']['shard']['digest'] = 'latest'
    elif problem == 'rule_missing': document['quality_rules'].pop('recorder_lossless')
    elif problem == 'rule_extra': document['quality_rules']['rtf'] = document['quality_rules']['frame_continuity']
    elif problem == 'ref_hash': document['scene_manifest']['sha256'] = '0'*64
    elif problem == 'rule_is_legacy_placeholder':
        path = tmp_path/'legacy-placeholder.json'
        document['quality_rules']['qc_valid_rate'] = ref(path,{'existing_business_rule':'qc_valid_rate'})
    elif problem == 'rule_is_valueless':
        rule = synthetic_rule('qc_valid_rate')
        rule.pop('pass')
        document['quality_rules']['qc_valid_rate'] = write_rule(tmp_path,'qc_valid_rate',rule)
    elif problem == 'rule_for_another_gate':
        document['quality_rules']['qc_valid_rate'] = document['quality_rules']['frame_continuity']
    elif problem in ('short','duplicate','overlap'):
        from pathlib import Path
        path = Path(document['scene_manifest']['path'])
        rows = json.loads(path.read_text())['scenarios']
        if problem == 'short': rows.pop()
        elif problem == 'duplicate': rows[-1] = rows[0]
        else: rows[0]['scene_id'] = 'functional-00'
        document['scene_manifest'] = ref(path,{'scenarios':rows})
    with pytest.raises(ValueError,match='PARALLEL_QUALIFICATION_CONTRACT_INVALID'):
        module().validate_qualification_contract(document)


def test_functional_run_cannot_include_qualification_or_accept_eight_workers(tmp_path):
    gate = fixture(tmp_path)
    with pytest.raises(ValueError,match='FUNCTIONAL_COLLECTION_CONTRACT_INVALID'):
        module().validate_functional_contract(gate)
    document = dict(schema_version=1,kind='ACT_COLLECTION_FUNCTIONAL_RUN',run_id='run',
        worker_count=8,scene_manifest=gate['functional_manifest'],controlled_identity=identity())
    with pytest.raises(ValueError,match='FUNCTIONAL_COLLECTION_CONTRACT_INVALID'):
        module().validate_functional_contract(document)


@pytest.mark.parametrize('kind',['functional','qualification'])
def test_installed_schema_and_reader_accept_current_contract_and_refuse_extra_fields(tmp_path,kind):
    from pathlib import Path
    from jsonschema import Draft202012Validator, ValidationError
    gate = fixture(tmp_path)
    if kind == 'qualification':
        name,document = 'parallel-qualification-contract-schema.json',gate
    else:
        name = 'parallel-functional-contract-schema.json'
        document = dict(schema_version=1,kind='ACT_COLLECTION_FUNCTIONAL_RUN',run_id='run',worker_count=1,
            scene_manifest=gate['functional_manifest'],controlled_identity=identity())
    schema = json.loads((Path(__file__).parents[2]/'config/act'/name).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(document)
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(document|{'status':'QUALIFIED'})


# ---- the closed quality rule file ----------------------------------------------------------------------------------------


def test_every_gate_episode_rule_is_the_code_constant():
    from so101_demo.act import episode_qc, topic_loss
    from so101_demo.parallel_batch import dynamic_manifest
    assert EPISODE_RULE_OF == {'recorder_lossless':topic_loss.RULE_VERSION,'frame_continuity':episode_qc.QC_RULE_VERSION,
        'qc_valid_rate':episode_qc.QC_RULE_VERSION,'teacher_physical_success_rate':dynamic_manifest.RULE_VERSION}
    assert {name:module().quality_episode_rule(name) for name in NAMES} == EPISODE_RULE_OF
    assert module().QUALITY_POPULATIONS == frozenset({'ALL_FROZEN_SCENES'})


@pytest.mark.parametrize('name',NAMES)
def test_synthetic_rule_documents_validate_and_are_copied(name):
    document = synthetic_rule(name)
    value = module().validate_quality_rule(name,document)
    assert value == document and value is not document and value['pass'] is not document['pass']


@pytest.mark.parametrize('change',[
    {'pass':{'kind':'AT_LEAST','numerator':36,'denominator':40}},
    {'pass':{'kind':'AT_LEAST','numerator':1,'denominator':1}},
    {'pass':{'kind':'EVERY'}}],ids=['fraction','whole','every'])
def test_pass_rule_forms_that_are_defined(change):
    assert module().validate_quality_rule('qc_valid_rate',synthetic_rule('qc_valid_rate',**change))['pass'] == change['pass']


@pytest.mark.parametrize('problem',['extra_field','missing_pass','missing_population','version_bool','version_two','kind',
    'name_other','name_unknown','episode_rule_other_gate','episode_rule_unknown','population_unknown','population_dropping',
    'pass_not_object','pass_kind_unknown','pass_kind_lowercase','every_with_count','at_least_without_numerator',
    'at_least_without_denominator','at_least_extra_key','numerator_zero','numerator_negative','numerator_above_denominator',
    'denominator_zero','numerator_bool','numerator_float','numerator_string','denominator_float','threshold_ratio'])
def test_rule_without_a_complete_closed_value_is_refused(problem):
    document = synthetic_rule('qc_valid_rate')
    at_least = {'kind':'AT_LEAST','numerator':1,'denominator':2}
    if problem == 'extra_field': document['unit'] = 'episodes'
    elif problem == 'missing_pass': document.pop('pass')
    elif problem == 'missing_population': document.pop('population')
    elif problem == 'version_bool': document['schema_version'] = True
    elif problem == 'version_two': document['schema_version'] = 2
    elif problem == 'kind': document['kind'] = 'ACT_COLLECTION_QUALITY'
    elif problem == 'name_other': document['name'] = 'frame_continuity'
    elif problem == 'name_unknown': document['name'] = 'rtf'
    elif problem == 'episode_rule_other_gate': document['episode_rule'] = 'topic_loss'
    elif problem == 'episode_rule_unknown': document['episode_rule'] = 'a_rule_the_code_does_not_have'
    elif problem == 'population_unknown': document['population'] = 'ALL'
    elif problem == 'population_dropping': document['population'] = 'ONLY_EPISODES_WITH_EVIDENCE'
    elif problem == 'pass_not_object': document['pass'] = 'EVERY'
    elif problem == 'pass_kind_unknown': document['pass'] = {'kind':'AVERAGE'}
    elif problem == 'pass_kind_lowercase': document['pass'] = {'kind':'every'}
    elif problem == 'every_with_count': document['pass'] = {'kind':'EVERY','numerator':1}
    elif problem == 'at_least_without_numerator': document['pass'] = {'kind':'AT_LEAST','denominator':2}
    elif problem == 'at_least_without_denominator': document['pass'] = {'kind':'AT_LEAST','numerator':1}
    elif problem == 'at_least_extra_key': document['pass'] = dict(at_least,percent=50)
    elif problem == 'numerator_zero': document['pass'] = dict(at_least,numerator=0)
    elif problem == 'numerator_negative': document['pass'] = dict(at_least,numerator=-1)
    elif problem == 'numerator_above_denominator': document['pass'] = dict(at_least,numerator=3)
    elif problem == 'denominator_zero': document['pass'] = dict(at_least,numerator=0,denominator=0)
    elif problem == 'numerator_bool': document['pass'] = dict(at_least,numerator=True)
    elif problem == 'numerator_float': document['pass'] = dict(at_least,numerator=1.0)
    elif problem == 'numerator_string': document['pass'] = dict(at_least,numerator='1')
    elif problem == 'denominator_float': document['pass'] = dict(at_least,denominator=2.0)
    elif problem == 'threshold_ratio': document['pass'] = {'kind':'AT_LEAST','ratio':0.9}
    with pytest.raises(ValueError,match='QUALITY_RULE_INVALID'):
        module().validate_quality_rule('qc_valid_rate',document)


def test_rule_validation_refuses_an_unknown_gate_name_and_a_non_object():
    with pytest.raises(ValueError,match='QUALITY_RULE_INVALID'):
        module().validate_quality_rule('rtf',dict(synthetic_rule('qc_valid_rate'),name='rtf'))
    with pytest.raises(ValueError,match='QUALITY_RULE_INVALID'):
        module().validate_quality_rule('qc_valid_rate',[synthetic_rule('qc_valid_rate')])


def test_installed_rule_schema_accepts_a_rule_and_refuses_extra_fields():
    from pathlib import Path
    from jsonschema import Draft202012Validator, ValidationError
    schema = json.loads((Path(__file__).parents[2]/'config/act/parallel-quality-rule-schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(synthetic_rule('qc_valid_rate'))
    Draft202012Validator(schema).validate(synthetic_rule('recorder_lossless'))
    for bad in (dict(synthetic_rule('qc_valid_rate'),status='QUALIFIED'),
                synthetic_rule('qc_valid_rate',population='ALL'),
                synthetic_rule('qc_valid_rate',**{'pass':{'kind':'AT_LEAST','numerator':0,'denominator':2}}),
                synthetic_rule('qc_valid_rate',**{'pass':{'kind':'EVERY','numerator':1}}),
                synthetic_rule('qc_valid_rate',episode_rule='other')):
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(bad)
