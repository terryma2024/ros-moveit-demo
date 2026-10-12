"""Real per-case workspace/store routing; no physical or fresh-QC claim."""

import hashlib
import importlib
import json

import pytest

from so101_demo.act.collection_scope import build_collection_scope,write_collection_scope
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt


def fixture(tmp_path):
    refs={}
    for index,scene in enumerate(('scene-a','scene-b')):
        inputs=tmp_path/(scene+'-inputs.json')
        inputs.write_text(json.dumps(dict(inputs_sha256=str(index+1)*64,mode='formal')))
        scope=tmp_path/(scene+'-scope.json')
        write_collection_scope(build_collection_scope('formal',scene_id=scene,seed=index,
            inputs_sha256=str(index+1)*64),scope)
        refs[scene]={name:dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                     for name,path in (('scope',scope),('inputs_manifest',inputs))}
    return refs


def test_two_cases_reserve_distinct_original_store_bindings_and_recovery_receipts(tmp_path):
    module=importlib.import_module('so101_demo.runtime.container_campaign.case_artifacts')
    refs=fixture(tmp_path)
    worker=tmp_path/'worker';worker.mkdir(mode=0o700)
    results=module.CollectionCaseArtifacts(worker_id='w00',launch_generation=1,worker_root=worker,
        case_inputs=refs,clock=lambda:11.)
    leases=[]
    for scene in refs:
        lease=LeaseIdentity('batch',1,'w00',1,scene,'attempt-'+scene,1,10.,100.)
        leases.append(lease)
        reset=ResetBoundaryReceipt('reset-2','session',10.5,1.,2)
        assert results.reserve_workspace(lease,reset) is True
        reader=results.writers[scene]
        store=reader._act_stores[reader._key(lease)]
        assert str(store.scope)==refs[scene]['scope']['path']
        assert str(store.inputs_manifest)==refs[scene]['inputs_manifest']['path']
        assert results.workspace(lease).path.is_relative_to(worker/'attempts'/scene)
        receipt=results.write_recovery_receipt(lease,succeeded=True,generation=1)
        assert results.verify_recovery_receipt(receipt,lease,succeeded=True,generation=1) is True
    assert results.writers['scene-a'] is not results.writers['scene-b']
    assert results.workspace(leases[0]).path!=results.workspace(leases[1]).path
    scope_path=refs['scene-b']['scope']['path']
    with open(scope_path,'a') as stream:stream.write(' ')
    with pytest.raises(ValueError):results.workspace(leases[1])
    assert results.workspace(leases[0]).path.is_dir()


@pytest.mark.parametrize('problem',['diagnostic','wrong_scene','wrong_inputs','null_inputs','extra_ref'])
def test_case_binding_refuses_diagnostic_or_mismatched_originals(tmp_path,problem):
    module=importlib.import_module('so101_demo.runtime.container_campaign.case_artifacts')
    refs=fixture(tmp_path)
    scope_path=refs['scene-a']['scope']['path']
    scope=json.loads(open(scope_path).read())
    if problem=='diagnostic':scope['mode']='preselected_target_diagnostic'
    elif problem=='wrong_scene':scope['scene_id']='scene-b'
    elif problem=='wrong_inputs':scope['inputs_sha256']='f'*64
    elif problem=='null_inputs':
        inputs=refs['scene-a']['inputs_manifest']
        with open(inputs['path'],'w') as stream:json.dump(dict(mode='formal',inputs_sha256=None),stream)
        inputs['sha256']=hashlib.sha256(open(inputs['path'],'rb').read()).hexdigest()
    else:refs['scene-a']['unknown']=refs['scene-a']['scope']
    if problem!='extra_ref':
        with open(scope_path,'w') as stream:json.dump(scope,stream)
        refs['scene-a']['scope']['sha256']=hashlib.sha256(open(scope_path,'rb').read()).hexdigest()
    with pytest.raises(ValueError):
        module.CollectionCaseArtifacts(worker_id='w00',launch_generation=1,worker_root=tmp_path,
            case_inputs=refs,clock=lambda:11.)
