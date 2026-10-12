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


def bound_fixture(tmp_path):
    """Case references over a REAL frozen set that binds a scene manifest (formal, `scene-a`/`scene-b`, non-default).

    Real: `freeze_inputs` (binds and copies the scene file, hash chain) and the manifest it writes. Controlled: the role
    candidates (synthetic approvals) and the hand-written scene rows. The scope files are written by `write_collection_scope`.
    """
    from test_act_child_recorder_binding import _scope_for, frozen_child_inputs
    from test_act_formal_scene_scope import ROWS, scene_file

    rows = ROWS
    manifest_path, manifest, _ = frozen_child_inputs(tmp_path, mode='formal', scene_manifest=scene_file(tmp_path),
                                                     scope_scene=('scene-a', 11))
    inputs = dict(path=str(manifest_path), sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())
    refs = {}
    for row in rows:
        scope = _scope_for(tmp_path, f"scope-{row['scene_id']}.json", row['scene_id'], row['seed'], manifest['inputs_sha256'])
        refs[row['scene_id']] = dict(scope=dict(path=str(scope), sha256=hashlib.sha256(scope.read_bytes()).hexdigest()),
                                     inputs_manifest=dict(inputs))
    return refs, manifest_path


def test_non_default_scenes_of_a_bound_manifest_are_accepted(tmp_path):
    module=importlib.import_module('so101_demo.runtime.container_campaign.case_artifacts')
    refs,_=bound_fixture(tmp_path)
    worker=tmp_path/'worker';worker.mkdir(mode=0o700)
    results=module.CollectionCaseArtifacts(worker_id='w00',launch_generation=1,worker_root=worker,
        case_inputs=refs,clock=lambda:11.)
    assert set(results.writers)=={'scene-a','scene-b'}
    for scene in refs:
        lease=LeaseIdentity('batch',1,'w00',1,scene,'attempt-'+scene,1,10.,100.)
        assert tuple(map(str,results.case_binding(lease)))==(refs[scene]['scope']['path'],
                                                              refs[scene]['inputs_manifest']['path'])


@pytest.mark.parametrize('problem',['unlisted_scene','wrong_seed','default_not_a_row'])
def test_scope_outside_the_bound_manifest_is_refused(tmp_path,problem):
    from test_act_child_recorder_binding import _scope_for
    module=importlib.import_module('so101_demo.runtime.container_campaign.case_artifacts')
    refs,manifest_path=bound_fixture(tmp_path)
    sha=json.loads(manifest_path.read_bytes())['inputs_sha256']
    scene,seed={'unlisted_scene':('scene-z',11),'wrong_seed':('scene-a',99),'default_not_a_row':('default',0)}[problem]
    scope=_scope_for(tmp_path,'scope-outside.json',scene,seed,sha)
    refs={scene:dict(refs['scene-a'],scope=dict(path=str(scope),sha256=hashlib.sha256(scope.read_bytes()).hexdigest()))}
    with pytest.raises(ValueError):
        module.CollectionCaseArtifacts(worker_id='w00',launch_generation=1,worker_root=tmp_path,
            case_inputs=refs,clock=lambda:11.)


def test_replaced_bound_scene_manifest_is_refused_at_every_binding(tmp_path):
    module=importlib.import_module('so101_demo.runtime.container_campaign.case_artifacts')
    refs,manifest_path=bound_fixture(tmp_path)
    worker=tmp_path/'worker';worker.mkdir(mode=0o700)
    results=module.CollectionCaseArtifacts(worker_id='w00',launch_generation=1,worker_root=worker,
        case_inputs=refs,clock=lambda:11.)
    (manifest_path.parent/'scene_manifest'/'scenes.json').write_bytes(json.dumps({'scenarios':[]}).encode())
    with pytest.raises(ValueError):
        results.case_binding(LeaseIdentity('batch',1,'w00',1,'scene-a','attempt-scene-a',1,10.,100.))


def test_root_is_reserved_task_directory_or_worker_root(tmp_path):
    module=importlib.import_module('so101_demo.runtime.container_campaign.case_artifacts')
    refs={'scene-a':fixture(tmp_path)['scene-a']}
    plain=tmp_path/'plain';plain.mkdir()
    assert module.CollectionCaseArtifacts(worker_id='w00',launch_generation=1,worker_root=plain,
        case_inputs=refs).root==plain
    output=tmp_path/'output';output.mkdir()
    task=module.CollectionCaseArtifacts(worker_id='w00',launch_generation=1,worker_root=output,
        case_inputs=refs,task_id='task.1')
    assert task.root==output/'tasks'/'task.1' and task.root.is_dir()


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
