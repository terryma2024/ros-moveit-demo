"""Functional runs and independent W8 gates are distinct, closed input contracts."""

import hashlib
import importlib
import json

import pytest


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
    rules = {name:ref(tmp_path/(name+'.json'),{'existing_business_rule':name}) for name in (
        'recorder_lossless','frame_continuity','qc_valid_rate','teacher_physical_success_rate')}
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
                                  'rule_missing','rule_extra','ref_hash','short','duplicate','overlap'])
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


def test_functional_run_cannot_include_qualification_or_accept_w8(tmp_path):
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
