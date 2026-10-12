"""Local one-way task composition for the ACT container shard.

Real here: the frozen-input/policy readers, config loaders, `CollectionCaseArtifacts`, the
result-store writer, `ActRosRuntimePorts`, `ActTeacherClient`, `ContainerCollectionRuntime`,
`WorkerOwnedProcessTree` and `ActFixedCollectionWorkload`. Controlled doubles: the borrowed native
stack process (the shard-retirement fixture), the Teacher inference socket client, the Teacher
context evidence reader and the ROS camera/physics. Construction starts no simulator, inference
model, Recorder or Teacher. This is not a physical episode or Head qualification test.
"""

import copy
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import threading
import time

import pytest

from test_act_child_recorder_binding import frozen_child_inputs
from test_act_policy_freeze import rehash
from test_config_identity import campaign_fixture,write_config
from test_shard_retirement import fixture as native_fixture
from so101_demo.act.collection_scope import build_collection_scope,write_collection_scope
from so101_demo.cli.mujoco_batch.request import _load_runtime_config
from so101_demo.runtime.container_campaign.stack_launch import ContainerActStackLaunch
from so101_demo.runtime.container_campaign.task_contracts import InputRef,TaskSpec
from paths import PACKAGE_ROOT


MODULE='so101_demo.runtime.container_campaign.task_builder'


def builder():
    return importlib.import_module(MODULE)


def ref(path):
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def make_env(tmp_path,monkeypatch):
    frozen_path,frozen,snapshot=frozen_child_inputs(tmp_path)
    # Synthetic approvals stay explicitly synthetic; current freeze/readback,
    # policies and execution snapshot are real. No admission/qualification claim.
    frozen['mode']='formal';rehash(frozen_path,frozen)
    frozen=json.loads(frozen_path.read_bytes())
    scope=tmp_path/'formal-scope.json'
    write_collection_scope(build_collection_scope('formal',scene_id='default',seed=0,
        inputs_sha256=frozen['inputs_sha256']),scope)
    native_dir=tmp_path/'native';native_dir.mkdir()
    _,root,process,native,retirement,calls=native_fixture(native_dir,monkeypatch)
    stack=retirement.stack;old=stack.launch
    namespace='/act/campaign/w00'
    stack.launch=ContainerActStackLaunch(ros2_executable=old.ros2_executable,session_id=old.session_id,
        evidence_root=old.evidence_root,ros_domain_id=old.ros_domain_id,environment=old.environment,
        ros_namespace=namespace,readiness_timeout_s=180.)
    runtime_path=PACKAGE_ROOT/'config/mujoco/parallel_batch_act_offline.yaml'
    runtime=_load_runtime_config(runtime_path)
    campaign=campaign_fixture(tmp_path)
    campaign['gpu_uuid']='GPU-28221cec-9d21-7753-fd5a-da645740df19'
    campaign['controlled_runtime']=ref(frozen_path.parent/frozen['roles']['runtime_config']['path'])
    campaign['teacher_service']['model']['model_id']=runtime.yolo_model_id
    campaign_path=write_config(tmp_path,campaign)
    identity=dict(manifest_sha256='a'*64,runtime_config_sha256=campaign['controlled_runtime']['sha256'],
        collection_config_sha256=frozen['roles']['collection_config']['sha256'],
        contact_policy_fingerprint=json.loads((frozen_path.parent/frozen['roles']['contact_proposal']['path']).read_bytes())['policy_fingerprint'])
    scene_path=tmp_path/'scenes.json'
    row=dict(scene_id='default',seed=0,split='qualification',cup_position_world_m=[.2,.1,.02])
    scene_path.write_text(json.dumps(dict(scenarios=[row])))
    (root/'task-inputs').mkdir()
    output=tmp_path/'output';output.mkdir(mode=0o700)
    spec=dict(workload_kind='act_collection',campaign_id='campaign-1',worker_id='w00',launch_generation=1,
        execution_generation=1,simulation_session_id=old.session_id,owned_root=str(root),
        ros_namespace=namespace,ros_domain_id=old.ros_domain_id,business_identity=identity,
        parallel_runtime=ref(runtime_path),campaign_config=ref(campaign_path),
        deadline_monotonic_s=time.monotonic()+3600,wave_id='wave-0',gpu_uuid=campaign['gpu_uuid'])
    document=dict(schema_version=1,kind='ACT_CONTAINER_COLLECTION_TASK',task_id='task-1',worker_id='w00',
        launch_generation=1,wave_id='wave-0',scene_id='default',scene_manifest=ref(scene_path),
        scope=ref(scope),inputs_manifest=ref(frozen_path))
    for role in ('head','teacher'):
        document[role]=dict(role=role,socket_path='/act/ipc/'+role+'/inference.sock',
            service_generation='service-'+role,max_frame_bytes=campaign[role+'_service']['max_frame_bytes'])
    for name,value in dict(SO101_ACT_CONTAINER_NAMESPACE=namespace,ROS_NAMESPACE=namespace,
        ROS_DOMAIN_ID=str(old.ros_domain_id),SO101_ACT_CONTAINER_OWNED_ROOT=str(root),
        SO101_MUJOCO_SESSION_ID=old.session_id,MUJOCO_GL='egl').items():monkeypatch.setenv(name,value)
    stack.process.poll=lambda:None
    return SimpleNamespace(document=document,spec=spec,stack=stack,calls=calls,root=root,output=output,
        tmp=tmp_path,campaign=campaign,runtime=runtime,row=row,scope=scope,frozen_path=frozen_path)


@pytest.fixture(scope='module')
def shared_env(tmp_path_factory):
    """The frozen-input and native-stack setup costs seconds, so it is built once per module. Tests never mutate it:
    a test that changes an input writes a private copy under its own tmp_path (see `private_copy`)."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        yield make_env(tmp_path_factory.mktemp('shared'),monkeypatch)


@pytest.fixture
def env(shared_env,tmp_path):
    output=tmp_path/'output'
    output.mkdir(mode=0o700)
    return SimpleNamespace(**dict(vars(shared_env),output=output,tmp=tmp_path))


def private_copy(env,path):
    """A copy of a frozen input beside the test, for tests that damage it."""
    target=env.tmp/('copy-'+Path(path).name)
    shutil.copyfile(path,target)
    return target


def make_task(env,document=None,*,task_id='task-1',deadline=None,parent=None):
    document=env.document if document is None else document
    directory=Path(parent) if parent is not None else env.root/'task-inputs'
    path=directory/(task_id+'.json')
    path.write_text(json.dumps(document))
    return TaskSpec(task_id=task_id,inputs_ref=InputRef(**ref(path)),
        deadline_monotonic_s=time.monotonic()+1800 if deadline is None else deadline)


def test_task_input_binds_task_instance_and_frozen_scene(env):
    loaded=builder().load_task_input(make_task(env),env.spec)
    assert loaded.scene_id=='default' and loaded.task_id=='task-1' and loaded.root==env.root
    assert loaded.row==env.row and loaded.refs['scope']==env.document['scope']
    assert loaded.refs['inputs_manifest']==env.document['inputs_manifest']
    assert loaded.config.yolo_model_id==env.runtime.yolo_model_id
    assert loaded.campaign['gpu_uuid']==env.spec['gpu_uuid']
    assert loaded.teacher_policy['execution_deadline_s']>0 and loaded.recorder_policy
    assert not (env.output/'tasks').exists() and env.calls==[]


@pytest.mark.parametrize('extra',['output_path','callback','coordinator','lease','token','batch_id','coordinator_epoch'])
def test_task_input_refuses_extra_output_callback_or_lease_fields(env,extra):
    document=copy.deepcopy(env.document);document[extra]='/elsewhere'
    with pytest.raises(ValueError):builder().load_task_input(make_task(env,document),env.spec)


@pytest.mark.parametrize('damage',['task_id','worker','generation','wave','changed_bytes','foreign_parent',
                                   'task_deadline_past','task_deadline_after_shard','kind','scene_unknown'])
def test_task_input_refuses_foreign_instance_or_changed_bytes(env,damage):
    document=copy.deepcopy(env.document);kwargs={}
    if damage=='task_id':document['task_id']='task-2'
    elif damage=='worker':document['worker_id']='w01'
    elif damage=='generation':document['launch_generation']=2
    elif damage=='wave':document['wave_id']='wave-9'
    elif damage=='kind':document['kind']='ACT_CONTAINER_COLLECTION_WORKER'
    elif damage=='scene_unknown':document['scene_id']='other'
    elif damage=='foreign_parent':
        (env.tmp/'foreign').mkdir();kwargs['parent']=env.tmp/'foreign'
    elif damage=='task_deadline_past':kwargs['deadline']=time.monotonic()-1
    elif damage=='task_deadline_after_shard':kwargs['deadline']=env.spec['deadline_monotonic_s']+1
    task=make_task(env,document,**kwargs)
    if damage=='changed_bytes':
        with open(task.inputs_ref.path,'a') as stream:stream.write(' ')
    with pytest.raises(ValueError):builder().load_task_input(task,env.spec)


@pytest.mark.parametrize('damage',['generation_spec','catalog_position','legacy_broker','diagnostic','env_domain',
                                   'env_root','env_session','env_gl','runtime_sha','model','frame_size',
                                   'foreign_head_socket','contact_policy','foreign_namespace'])
def test_bad_input_refuses_before_task_directory_exists(env,monkeypatch,damage):
    document=copy.deepcopy(env.document);spec=copy.deepcopy(env.spec)
    if damage=='generation_spec':spec['launch_generation']=2
    elif damage=='catalog_position':
        scene=private_copy(env,document['scene_manifest']['path'])
        value=json.loads(scene.read_bytes());value['scenarios'][0]['cup_position_world_m']=[0.,0.]
        scene.write_text(json.dumps(value));document['scene_manifest']=ref(scene)
    elif damage=='legacy_broker':document['teacher']['socket_path']='/generic/broker.sock'
    elif damage=='foreign_head_socket':document['head']['socket_path']='/act/ipc/teacher/inference.sock'
    elif damage=='frame_size':document['teacher']['max_frame_bytes']+=1
    elif damage=='diagnostic':
        scope=private_copy(env,document['scope']['path'])
        value=json.loads(scope.read_bytes());value['mode']='preselected_target_diagnostic'
        scope.write_text(json.dumps(value));document['scope']=ref(scope)
    elif damage=='env_domain':monkeypatch.setenv('ROS_DOMAIN_ID','999')
    elif damage=='env_root':monkeypatch.setenv('SO101_ACT_CONTAINER_OWNED_ROOT','/elsewhere')
    elif damage=='env_session':monkeypatch.setenv('SO101_MUJOCO_SESSION_ID','other-session')
    elif damage=='env_gl':monkeypatch.setenv('MUJOCO_GL','glx')
    elif damage=='foreign_namespace':monkeypatch.setenv('SO101_ACT_CONTAINER_NAMESPACE','/act/campaign/w05')
    elif damage=='runtime_sha':spec['business_identity']['runtime_config_sha256']='e'*64
    elif damage=='contact_policy':spec['business_identity']['contact_policy_fingerprint']='f'*64
    elif damage=='model':
        campaign=copy.deepcopy(env.campaign);campaign['teacher_service']['model']['model_id']='other-model'
        spec['campaign_config']=ref(write_config(env.tmp,campaign))
    task=make_task(env,document)
    with pytest.raises(ValueError):
        builder().build_collection_task(task,stack=env.stack,shard_spec=spec,output_root=env.output)
    assert not (env.output/'tasks').exists() and not (env.root/'owned-runtime-processes.json').exists()
    assert env.calls==[]


def test_local_lease_fields_formats_and_dotted_task_id(env):
    document=copy.deepcopy(env.document);document['task_id']='task.1.a'
    task=make_task(env,document,task_id='task.1.a')
    loaded=builder().load_task_input(task,env.spec)
    lease=builder().local_lease(env.spec,loaded.scene_id,issued=10.,deadline=20.)
    assert '.' in task.task_id and '.' not in lease.attempt_id
    assert (lease.batch_id,lease.coordinator_epoch,lease.worker_id,lease.worker_generation,lease.point_id,
            lease.attempt_id,lease.lease_generation,lease.lease_issued_monotonic_s,
            lease.lease_deadline_monotonic_s)==('campaign-1-wave-0',1,'w00',1,'default','default-lease-1',1,10.,20.)
    with pytest.raises(ValueError):builder().local_lease(env.spec,'default',issued=10.,deadline=10.)


def test_exec_lease_keeps_identity_and_issued_and_restamps_deadline(env):
    init=builder().local_lease(env.spec,'default',issued=10.,deadline=20.)
    later=builder().exec_lease(init,deadline=30.)
    assert later.lease_issued_monotonic_s==10. and later.lease_deadline_monotonic_s==30.
    from so101_demo.cli.mujoco_batch.common import _lease_wire
    assert _lease_wire(later)==_lease_wire(init) and init.lease_deadline_monotonic_s==20.
    with pytest.raises(ValueError):builder().exec_lease(init,deadline=10.)


def test_deadlines_come_from_frozen_config_clipped_by_task_and_campaign(env):
    config=env.runtime
    def deadline(stage,*,task=1e9,shard=1e9,start=100.):
        return builder().stage_deadline(config,stage,start=start,task_deadline=task,shard_deadline=shard)
    assert deadline('init')==100.+config.initializing_hard_timeout_s
    assert deadline('exec')==100.+config.executing_hard_timeout_s
    assert deadline('exec',task=150.)==150. and deadline('init',shard=120.)==120.
    assert deadline('exec',task=130.,shard=125.)==125.
    with pytest.raises(ValueError):deadline('finalizing')


class FakeInference:
    """Controlled double for the Teacher inference socket client; no socket is opened."""

    def __init__(self,*,socket_path,service_generation,max_frame_bytes):
        self.socket_path,self.generation,self.max_frame_bytes=Path(socket_path),service_generation,max_frame_bytes
        self.calls=[]

    def new_request_id(self):
        return 'request-1'

    def infer(self,document,payload):
        self.calls.append(document)
        raise AssertionError('the Teacher must not be asked')


class Clock:
    def __init__(self):self.offset=0.
    def __call__(self):return time.monotonic()+self.offset


def build(env,**kwargs):
    """Real builder with controlled doubles: inference client, Teacher context evidence reader."""
    kwargs.setdefault('inference_client_factory',FakeInference)
    kwargs.setdefault('evidence',lambda session:SimpleNamespace(simulation_session_id=session,reset_epoch=2))
    return builder().build_collection_task(make_task(env),stack=env.stack,shard_spec=env.spec,
        output_root=env.output,**kwargs)


def test_builder_constructs_real_runtime_ports_teacher_without_coordinator(env):
    from so101_demo.act.parallel_collection import ActFixedCollectionWorkload
    from so101_demo.runtime.act_ros_runtime import ActRosRuntimePorts
    from so101_demo.runtime.act_teacher_client import ActTeacherClient
    from so101_demo.runtime.container_campaign.case_artifacts import CollectionCaseArtifacts
    from so101_demo.runtime.container_campaign.collection_runtime import ContainerCollectionRuntime
    from so101_demo.runtime.inference.client import InferenceClient
    execution=build(env,inference_client_factory=InferenceClient)
    assert type(execution) is builder().CollectionTaskExecution
    task_root=env.output/'tasks'/'task-1'
    assert type(execution.artifacts) is CollectionCaseArtifacts and execution.artifacts.root==task_root
    assert type(execution.ports) is ActRosRuntimePorts and type(execution.runtime) is ContainerCollectionRuntime
    assert type(execution.teacher) is ActTeacherClient and type(execution.teacher.client) is InferenceClient
    assert execution.teacher.client.socket_path==Path('/act/ipc/teacher/inference.sock')
    assert type(execution.workload) is ActFixedCollectionWorkload and execution.workload.scene_ids=={'default'}
    runtime,resources=execution.runtime,execution.resources
    assert runtime.resources.worker_root==task_root and runtime.stack is env.stack
    assert resources.worker_id=='w00' and resources.generation==1 and resources.session_id==env.spec['simulation_session_id']
    for name in ('render_context_namespace','ros_home','ros_log_dir','temp_dir','socket_namespace','socket_path'):
        assert getattr(resources,name).is_relative_to(env.root) and not getattr(resources,name).is_relative_to(task_root)
    assert runtime.episode_inputs_manifest==env.document['inputs_manifest']['path']
    assert runtime.episode_scope_path==env.document['scope']['path']
    assert env.calls==[] and runtime._physical_started is False and runtime.owned_process_manifest.processes==()
    assert (task_root/'owned-runtime-processes.json').is_file()
    assert not (env.root/'owned-runtime-processes.json').exists()
    assert not hasattr(execution,'coordinator')


def test_module_imports_no_coordinator_protocol_or_worker_modules():
    import ast
    forbidden=('worker_transport','worker_runner','collection_worker','collection_driver','worker_builder')
    tree=ast.parse(Path(builder().__file__).read_text())
    for node in ast.walk(tree):
        names=([alias.name for alias in node.names] if isinstance(node,ast.Import) else
               [node.module or ''] if isinstance(node,ast.ImportFrom) else [])
        for name in names:
            assert not any(part in name.split('.') for part in forbidden),name
            assert name!='so101_demo.parallel_batch.worker' and not name.startswith('so101_demo.parallel_batch.worker.')


@pytest.mark.parametrize('damage',['session','domain','namespace','stack_root','output_inside_stack'])
def test_foreign_stack_or_output_refused_before_task_directory_exists(env,monkeypatch,damage):
    old=env.stack.launch
    output=env.output
    if damage=='output_inside_stack':
        output=env.root/'stack'/'output';output.mkdir(exist_ok=True)
    else:
        fields=dict(ros2_executable=old.ros2_executable,session_id=old.session_id,evidence_root=old.evidence_root,
            ros_domain_id=old.ros_domain_id,environment=old.environment,ros_namespace=old.ros_namespace,
            readiness_timeout_s=old.readiness_timeout_s)
        field=dict(session='session_id',domain='ros_domain_id',namespace='ros_namespace',
            stack_root='evidence_root')[damage]
        fields[field]={'session':'other','domain':old.ros_domain_id+1,'namespace':'/act/campaign/w05',
                       'stack_root':env.tmp}[damage]
        monkeypatch.setattr(env.stack,'launch',type(old)(**fields))
    with pytest.raises(ValueError):
        builder().build_collection_task(make_task(env),stack=env.stack,shard_spec=env.spec,output_root=output)
    assert not (output/'tasks').exists() and not (env.root/'owned-runtime-processes.json').exists()


def test_request_stop_is_idempotent_and_refuses_the_run_before_any_port_is_touched(env):
    execution=build(env)
    assert execution.request_stop() is None and execution.request_stop() is None
    assert execution.state.stop.is_set() and execution.runtime.stop_requested and execution.teacher._is_fenced()
    with pytest.raises(builder().CollectionTaskFault) as raised:execution.run()
    assert raised.value.code=='TASK_STOP_REQUESTED' and env.calls==[]
    assert execution.runtime._physical_started is False


def lease_for(env,**changes):
    from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
    base=builder().local_lease(env.spec,'default',issued=time.monotonic(),deadline=time.monotonic()+600)
    return LeaseIdentity(**(vars_of(base)|changes))


def vars_of(lease):
    from dataclasses import asdict
    return asdict(lease)


def armed(env,clock=None,evidence=None):
    """Builder with an executing lease and a reset receipt installed as the next stage would."""
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    options=dict(clock=clock) if clock is not None else {}
    if evidence is not None:options['evidence']=evidence
    execution=build(env,**options)
    lease=lease_for(env)
    execution.state.lease=lease
    execution.ports._reset_receipts[lease.attempt_id]=ResetBoundaryReceipt(
        'reset-2',execution.resources.session_id,10.5,1.,2)
    return execution,lease


def frame(execution):
    import numpy as np
    from so101_demo.parallel_batch.act_inference import ActInferenceFrame
    return ActInferenceFrame(np.zeros((4,5,3),dtype=np.uint8),11.,11_000_000_000,'camera',
        execution.resources.session_id,'ros_sim',1)


@pytest.mark.parametrize('problem',['stop','deadline','foreign_lease','no_lease','reset_epoch','evidence_session',
                                    'missing_reset','start_event'])
def test_expired_or_changed_local_context_refuses_teacher(env,problem):
    """Real ActTeacherClient and probe; the socket client and the evidence reader are controlled doubles."""
    clock=Clock()
    seen={'epoch':2,'session':None}
    def evidence(session):
        return SimpleNamespace(simulation_session_id=seen['session'] or session,reset_epoch=seen['epoch'])
    execution,lease=armed(env,clock,evidence)
    reached=[]
    execution.teacher.perception_runner=lambda *args:reached.append(args)
    event_id='attempt-start-'+lease.attempt_id
    request=lease
    if problem=='stop':execution.state.stop.set()
    elif problem=='deadline':clock.offset=1e6
    elif problem=='foreign_lease':execution.state.lease=lease_for(env,lease_generation=2)
    elif problem=='no_lease':execution.state.lease=None
    elif problem=='reset_epoch':seen['epoch']=3
    elif problem=='evidence_session':seen['session']='other-session'
    elif problem=='missing_reset':execution.ports._reset_receipts.clear()
    else:event_id='attempt-start-other'
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    code={'reset_epoch':'RESET_CHANGED','evidence_session':'RESET_CHANGED','missing_reset':'RESET_CHANGED',
          'start_event':'START_MISMATCH'}.get(problem,'LEASE_FENCED')
    with pytest.raises(ValueError,match='COLLECTION_TEACHER_'+code):
        execution.teacher.request_model(request,ExecutionKind.ATTEMPT,snapshot=frame(execution),
            start_event_id=event_id,start_event_type='ATTEMPT_STARTED',reset_epoch='reset-2')
    assert reached==[] and execution.teacher.client.calls==[]


def test_probe_returns_exact_expected_mapping(env):
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    execution,lease=armed(env)
    mapping=execution.teacher.context_probe(lease,ExecutionKind.ATTEMPT,'attempt-start-'+lease.attempt_id,'ATTEMPT_STARTED')
    assert mapping==dict(batch_id='campaign-1-wave-0',coordinator_epoch=1,worker_id='w00',worker_generation=1,
        point_id='default',attempt_id='default-lease-1',lease_generation=1,reset_epoch='reset-2',
        session_id=execution.resources.session_id)
    reached=[]
    execution.teacher.perception_runner=lambda *args:reached.append(args) or 'ran'
    assert execution.teacher.request_model(lease,ExecutionKind.ATTEMPT,snapshot=frame(execution),
        start_event_id='attempt-start-'+lease.attempt_id,start_event_type='ATTEMPT_STARTED',
        reset_epoch='reset-2')=='ran' and len(reached)==1


def request_for(lease,kind='attempt',**changes):
    fields=dict(batch_id=lease.batch_id,coordinator_epoch=lease.coordinator_epoch,worker_id=lease.worker_id,
        worker_generation=lease.worker_generation,point_id=lease.point_id,lease_generation=lease.lease_generation)
    fields['attempt_id' if kind=='attempt' else 'validation_id']=lease.attempt_id
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    fields['execution_kind']=ExecutionKind.ATTEMPT if kind=='attempt' else ExecutionKind.VALIDATION
    return SimpleNamespace(**(fields|changes))


def test_authorize_true_only_for_current_lease_before_deadline(env):
    clock=Clock()
    execution,lease=armed(env,clock)
    authorize=execution.ports.dependencies['authorize']
    assert authorize(request_for(lease)) is True and authorize(request_for(lease,'validation')) is True
    for field,value in dict(batch_id='other',coordinator_epoch=2,worker_id='w01',worker_generation=2,
                            point_id='other',lease_generation=2,attempt_id='other').items():
        assert authorize(request_for(lease,**{field:value})) is False,field
    assert authorize(SimpleNamespace()) is False and authorize(None) is False
    execution.state.stop.set()
    assert authorize(request_for(lease)) is False
    execution.state.stop.clear()
    clock.offset=1e6
    assert authorize(request_for(lease)) is False
    clock.offset=0.
    execution.state.lease=None
    assert authorize(request_for(lease)) is False


# ---- review fixes from stage 1 -------------------------------------------------------------------------------------------

@pytest.mark.parametrize('raw',[b'[]',b'null',b'"text"',b'5',b'{',b'',b'\xff\xfe',b'{"a":1,"a":2}'])
def test_task_document_that_is_not_a_json_object_is_a_value_error(env,raw):
    path=env.root/'task-inputs'/'task-raw.json'
    path.write_bytes(raw)
    task=TaskSpec(task_id='task-raw',inputs_ref=InputRef(**ref(path)),deadline_monotonic_s=time.monotonic()+1800)
    with pytest.raises(ValueError):builder().load_task_input(task,env.spec)


@pytest.mark.parametrize('missing',['workload_kind','campaign_id','worker_id','launch_generation','wave_id','owned_root',
    'ros_namespace','ros_domain_id','simulation_session_id','deadline_monotonic_s','business_identity',
    'parallel_runtime','campaign_config','gpu_uuid'])
def test_shard_spec_missing_a_required_key_is_a_value_error(env,missing):
    spec=copy.deepcopy(env.spec);del spec[missing]
    with pytest.raises(ValueError):builder().load_task_input(make_task(env),spec)
    with pytest.raises(ValueError):
        builder().build_collection_task(make_task(env),stack=env.stack,shard_spec=spec,output_root=env.output)
    assert not (env.output/'tasks').exists()


@pytest.mark.parametrize('damage',['not_dict','generation_text','business_text','owned_root_int','identity_key'])
def test_shard_spec_of_the_wrong_shape_is_a_value_error(env,damage):
    spec=copy.deepcopy(env.spec)
    if damage=='not_dict':spec=[]
    elif damage=='generation_text':spec['launch_generation']='1'
    elif damage=='business_text':spec['business_identity']='x'
    elif damage=='owned_root_int':spec['owned_root']=5
    else:del spec['business_identity']['runtime_config_sha256']
    with pytest.raises(ValueError):builder().load_task_input(make_task(env),spec)
    with pytest.raises(ValueError):builder().local_lease(spec,'default',issued=1.,deadline=2.)
    with pytest.raises(ValueError):builder().task_resources(spec,task_root=env.output)


def test_resources_socket_is_a_neutral_never_created_name_under_the_control_directory(env):
    resources=builder().task_resources(env.spec,task_root=env.output)
    assert resources.socket_path.parent==env.root/'control'==resources.socket_namespace
    assert resources.socket_path.name!='coordinator.sock' and resources.socket_path.suffix=='.sock'
    assert 'coordinator.sock' not in Path(builder().__file__).read_text()
    execution=build(env)
    assert not execution.resources.socket_path.exists() and not (env.root/'control').exists()


# ---- the business-vs-fault split (design section 6) ---------------------------------------------------------------------------

def offline_facts(tmp_path,*,processes=None,pilot=None,deadline_s=None,skip=None,**extra):
    """Facts and reason from the real `OfflineCollection.finish()` over its documented fakes (fake bag recorder, scripted
    processor process); shaped as the runtime stores them."""
    from test_offline_recording_switch import LEASE,collection_for,pilot_factory
    tmp_path.mkdir(parents=True,exist_ok=True)
    collection,point,_clock=collection_for(tmp_path,processes=processes,pilot=pilot or pilot_factory(),**extra)
    collection.start_before_teacher()
    outcome=collection.finish(lease=LEASE,skip_processing=skip,deadline_s=deadline_s)
    facts=dict(outcome.facts,act_data_status=outcome.data_status)
    return outcome,(facts,outcome.reason)


def teacher_decision(outcome,*,status='PASSED',execution='COMPLETED',result='PASS',**changes):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus
    from so101_demo.runtime.parallel_worker_parts.receipts import RuntimeDecision
    values=dict(status=AttemptStatus(status),reason='OK',physical_action_proven_absent=False,
        teacher_execution_status=execution,teacher_task_result=result,act_data_status=outcome.data_status,
        act_data_reason=outcome.reason)
    return RuntimeDecision(**(values|changes))


def qc_report(status,**fields):
    return {'verdict':'INVALID','rc':3,'reasons':['OFFLINE_QC_'+status+': x'],'qc':{'status':status,**fields},
            'timing':{'wall_s':1.}}


def test_valid_data_is_a_business_result_whatever_the_teacher_said(tmp_path):
    from test_offline_recording_switch import FakeProcesses
    outcome,facts=offline_facts(tmp_path,processes=FakeProcesses())
    assert outcome.data_status=='VALID'
    for status,execution,result in (('PASSED','COMPLETED','PASS'),('FAILED','COMPLETED','FAIL'),
                                    ('FAILED','DEADLINE','UNCONFIRMED'),('FAILED','STOPPED_SAFETY','UNCONFIRMED'),
                                    ('INDETERMINATE','COMPLETED','UNCONFIRMED')):
        decision=teacher_decision(outcome,status=status,execution=execution,result=result)
        assert builder().classify_task_fault(decision,facts) is None,(execution,result)


def test_qc_invalid_is_business_result(tmp_path):
    from test_offline_recording_switch import FakeProcesses
    cases={'engine_invalid':FakeProcesses(returncode=3,outputs='invalid'),
           'qc_fail':FakeProcesses(returncode=3,outputs='invalid',report=qc_report('FAIL',rc=1,reason='geometry')),
           'qc_rule_raised':FakeProcesses(returncode=3,outputs='invalid',
                                          report=qc_report('ERROR',rc=2,reason='ValueError: rule violated'))}
    for name,processes in cases.items():
        outcome,facts=offline_facts(tmp_path/name,processes=processes)
        assert outcome.reason.startswith('OFFLINE_PROCESSOR_INVALID: rc=3'),name
        assert builder().classify_task_fault(teacher_decision(outcome),facts) is None,name
        assert builder().classify_task_fault(teacher_decision(outcome,status='FAILED',result='FAIL'),facts) is None,name


def test_qc_rule_raise_is_business_invalid(tmp_path):
    from test_offline_recording_switch import FakeProcesses
    outcome,facts=offline_facts(tmp_path,processes=FakeProcesses(returncode=3,outputs='invalid',
        report=qc_report('ERROR',rc=2,reason='ValueError: scene colours differ')))
    assert facts[0]['processor']['qc']=={'status':'ERROR','rc':2,'reason':'ValueError: scene colours differ'}
    assert builder().classify_task_fault(teacher_decision(outcome),facts) is None


@pytest.mark.parametrize('qc',[
    dict(status='ERROR',rc=2,reason='OSError: [Errno 2] no such file'),
    dict(status='ERROR',rc=2,reason='TimeoutExpired'),
    dict(status='ERROR',rc=-9,reason='ValueError: killed'),
    dict(status='ERROR',rc=1,reason='ValueError: x'),
    dict(status='ERROR',rc=None,reason='ValueError: x'),
    dict(status='ERROR',rc=2),
    dict(status='FAIL',rc=2,reason='x'),
    dict(status='PASS',rc=0),
    dict(status='SURPRISE',rc=3)])
def test_qc_process_crash_is_execution_fault(tmp_path,qc):
    from test_offline_recording_switch import FakeProcesses
    outcome,facts=offline_facts(tmp_path,processes=FakeProcesses(returncode=3,outputs='invalid',
        report=qc_report('ERROR')|{'qc':qc}))
    code=builder().classify_task_fault(teacher_decision(outcome),facts)
    assert type(code) is str and code


@pytest.mark.parametrize('how',['rc2','rc4','killed','timeout','no_time_left','start_failed','bad_result'])
def test_offline_timeout_or_processor_crash_is_execution_fault(tmp_path,how):
    from test_offline_recording_switch import FakeProcesses
    processes={'rc2':FakeProcesses(returncode=2,outputs=None),'rc4':FakeProcesses(returncode=4,outputs=None),
               'killed':FakeProcesses(returncode=-9,outputs=None),'timeout':FakeProcesses(exits=False,outputs=None),
               'bad_result':FakeProcesses(returncode=0,outputs=None)}.get(how) or FakeProcesses()
    if how=='start_failed':
        processes.start=lambda spec,**kwargs:1/0
    outcome,facts=offline_facts(tmp_path,processes=processes,deadline_s=120. if how=='no_time_left' else None)
    assert outcome.data_status=='INVALID'
    assert type(builder().classify_task_fault(teacher_decision(outcome),facts)) is str,outcome.reason


@pytest.mark.parametrize('how',['start_raises','not_ready','not_closed'])
def test_recorder_start_or_close_failure_is_execution_fault(tmp_path,how):
    from test_offline_recording_switch import FakeProcesses,pilot_factory
    pilot={'start_raises':pilot_factory(raises='no ros2'),
           'not_ready':pilot_factory(ready=False,failure='RAW_PILOT_READY_TIMEOUT'),
           'not_closed':pilot_factory(facts={'closed':False})}[how]
    outcome,facts=offline_facts(tmp_path,processes=FakeProcesses(),pilot=pilot)
    assert outcome.data_status=='INVALID'
    assert type(builder().classify_task_fault(teacher_decision(outcome),facts)) is str,outcome.reason


@pytest.mark.parametrize('reason',['DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE','DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE: x',
    'TEACHER_CHILD_TIMED_OUT','TEACHER_CHILD_NOT_STOPPED','TERMINAL_CAPTURE_FAILED: no frame'])
def test_unverifiable_teacher_receipt_is_execution_fault(tmp_path,reason):
    from test_offline_recording_switch import FakeProcesses
    outcome,facts=offline_facts(tmp_path,processes=FakeProcesses(),skip=reason)
    assert outcome.reason==reason
    assert type(builder().classify_task_fault(teacher_decision(outcome),facts)) is str


def test_classification_fails_closed_without_matching_facts(tmp_path):
    from test_offline_recording_switch import FakeProcesses
    outcome,facts=offline_facts(tmp_path,processes=FakeProcesses(returncode=3,outputs='invalid'))
    decision=teacher_decision(outcome)
    assert builder().classify_task_fault(decision,facts) is None
    for broken in (None,(None,outcome.reason),({},outcome.reason),({'processor':{}},outcome.reason),
                   ({'processor':{'returncode':2,'report':{'verdict':'INVALID'},'qc':{'status':'NOT_RUN'}}},outcome.reason),
                   ({'processor':{'returncode':3,'report':{'verdict':'VALID'},'qc':{'status':'NOT_RUN'}}},outcome.reason),
                   ({'processor':{'returncode':3,'report':{'verdict':'INVALID'}}},outcome.reason)):
        assert type(builder().classify_task_fault(decision,broken)) is str
    assert type(builder().classify_task_fault(teacher_decision(outcome,act_data_status='DISABLED',act_data_reason=None),
                                              facts)) is str
    assert type(builder().classify_task_fault(teacher_decision(outcome,teacher_execution_status=None),facts)) is str
    assert type(builder().classify_task_fault(object(),facts)) is str


def perception_decision(disposition='FAILED',*,stopped=True,model_error=False):
    from so101_demo.parallel_batch.act_attempt import ActPerceptionDecision,ActPerceptionTerminal
    from so101_demo.parallel_batch.act_inference import ActInferenceRequest
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    request=ActInferenceRequest(request_id='request-1',model_id='teacher-model',image_timestamp_s=11.,
        execution_kind=ExecutionKind.ATTEMPT,batch_id='campaign-1-wave-0',coordinator_epoch=1,worker_id='w00',
        worker_generation=1,point_id='default',lease_generation=1,reset_epoch='reset-2',source_stamp_ns=11_000_000_000,
        source_frame_id='camera',image_shape=(4,5,3),simulation_session_id='session',frame_sequence=1,
        service_generation='service-teacher',deadline_monotonic_ns=2,attempt_id='default-lease-1')
    wire,reason={'FAILED':('NOT_DETECTED','PERCEPTION_NO_POSE'),'INVALID':('INFRA_ERROR','PERCEPTION_INFRA_ERROR'),
                 'CANCELLED':('INFRA_ERROR','PERCEPTION_CANCELLED')}[disposition]
    if model_error:wire,reason='MODEL_ERROR','PERCEPTION_MODEL_ERROR'
    terminal=ActPerceptionTerminal(disposition=disposition,reason=reason,wire_outcome=wire,request=request,
        audit_relative_path='perception/inference/request-1.json',
        failure_type=None if disposition=='CANCELLED' else 'ActInferenceResponse.'+wire,
        failure_message=None if disposition=='CANCELLED' else wire)
    return ActPerceptionDecision.from_terminal(terminal,stop_facts=dict(fenced=True,motion_stopped=stopped,
        controllers_stopped=True,recorder_stopped=True))


@pytest.mark.parametrize('disposition,stopped,model_error,business',[('FAILED',True,False,True),('INVALID',True,False,False),
    ('CANCELLED',True,False,False),('FAILED',False,False,False),('FAILED',True,True,False)])
def test_only_a_stopped_perception_no_pose_is_a_business_result(disposition,stopped,model_error,business):
    classified=builder().classify_task_fault(perception_decision(disposition,stopped=stopped,model_error=model_error),None)
    assert (classified is None) is business
    assert business or classified=='ACT_PERCEPTION_TERMINAL_UNSEALABLE'


@pytest.fixture(scope='module',autouse=True)
def verified_inputs_are_remembered_per_file_signature():
    """The production `qc_session` memo: the real snapshot verifier runs on the first call and again whenever a file
    it read changes; repeats over unchanged files in this process are served from the memo."""
    from so101_demo.act import qc_session
    with qc_session.qc_session():
        yield


# ---- the local flow, stop and cleanup (design sections 1, 7, 8) ------------------------------------------------------------
# Wiring tests. Real: frozen-input/policy readers, CollectionCaseArtifacts and the result store (seal, result.json),
# ActFixedCollectionWorkload, ActTeacherClient, ActRosRuntimePorts' reset wrapper, ContainerCollectionRuntime, OfflineCollection,
# the owned process tree (consumer helper children are short real sys.executable processes) and write_task_result. Controlled
# doubles: ROS ports (reset, gate, cameras, physics, controller cancel/confirm, pose publication, execute result), the perception
# chain, the Teacher inference socket, the evidence reader, the native stack process, the bag recorder (FakePilot) and the offline
# processor process (FakeProcesses). They prove the local wiring only; nothing here is a physical, Teacher or QC qualification.

import itertools
import numpy as np

from test_offline_recording_switch import FakePilot,FakeProcesses
import test_offline_recording_switch as offline_fakes
from so101_demo.act.offline import orchestration
from so101_demo.act.offline.raw_recorder import STATS_SCHEMA
from so101_demo.parallel_batch.act_inference import ActInferenceFrame,ActInferenceRequest,ActLocalizedPose
from so101_demo.parallel_batch.dynamic_manifest import teacher_attempt_status
from so101_demo.runtime.container_campaign.collection_runtime import ContainerCollectionRuntime
from so101_demo.runtime.parallel_ros_ports.observations import AdmittedPose
from so101_demo.runtime.parallel_worker_parts.process_tree import SourceStampedCapture,WorkerOwnedProcessTree
from so101_demo.runtime.parallel_worker_parts.receipts import ExecutionCompletionReceipt,RuntimeDecision
from so101_demo.runtime.task_stack import StackProcessSpec
from act_result_teacher import OUTCOMES,write_manifest
from parallel_worker_runtime_support import _write_numeric

SERIAL=itertools.count(1)
SLEEP=(sys.executable,'-c','import time\ntime.sleep(60)')


class FlowGroup(WorkerOwnedProcessTree):
    """The real owned process tree; only the offline processor role is scripted (the processor CLI is not run)."""

    def __init__(self,processor,events,**options):
        super().__init__(**options)
        self.processor,self.events=processor,events

    def start(self,spec,*,environment=None,pass_fds=()):
        if spec.role=='act-offline-processor':
            self.events.append(('processor_start',))
            return self.processor.start(spec,environment=environment)
        self.events.append(('start',spec.role))
        return super().start(spec,environment=environment,pass_fds=pass_fds)

    def wait_exit(self,identity,timeout_s):
        if identity.role=='act-offline-processor':
            return self.processor.wait_exit(identity,timeout_s)
        return super().wait_exit(identity,timeout_s)

    def terminate(self,identity,grace_s):
        if identity.role=='act-offline-processor':
            return self.processor.terminate(identity,grace_s)
        return super().terminate(identity,grace_s)

    def stop(self,expected):
        if getattr(expected,'role',None)=='act-offline-processor':
            return self.processor.stop(expected)
        return super().stop(expected)


class LoggedPilot(FakePilot):
    events=None

    def finish(self):
        LoggedPilot.events.append(('bag_closed',))
        return super().finish()


class Rig:
    """One task wired to the doubles above. `hooks` maps a stage name to a callable run when that stage is reached."""

    def __init__(self,flow,monkeypatch,*,teacher='FAILED',processor=None,manifest=True,perception='admit',cancel=True,
                 confirm=True,hooks=None,tree=None,build=True,terminal=('FAILED','PERCEPTION_NO_POSE','NOT_DETECTED'),**seams):
        self.flow,self.events,self.hooks=flow,[],dict(hooks or {})
        self.teacher,self.manifest,self.perception_mode,self.terminal=teacher,manifest,perception,terminal
        self.cancel_calls,self.confirm_calls,self.leases,self.groups=[],[],{},[]
        self.release=threading.Event()
        self.cancel=cancel if callable(cancel) else (lambda lease:cancel)
        self.confirm=confirm if callable(confirm) else (lambda lease:confirm)
        self.processor=processor or FakeProcesses(returncode=3,outputs='invalid')
        self.task_id='t%d'%next(SERIAL)
        self.execution=self.runtime=self.task_root=None
        tree=dict(tree or {})
        session=self.session=flow.spec['simulation_session_id']
        LoggedPilot.events=self.events
        monkeypatch.setattr(orchestration,'PilotRecording',lambda **kwargs:LoggedPilot(facts={'schema':STATS_SCHEMA},**kwargs))
        monkeypatch.setattr(orchestration,'_memo_covers',lambda **kwargs:True)
        # the Teacher child command is a short real helper process instead of the dynamic pick-and-place CLI
        monkeypatch.setattr(ContainerCollectionRuntime,'consumer_argv',lambda runtime,reset_epoch,lease=None:SLEEP)
        for key,value in dict(session_id=session,reset_epoch=2,attempt_id='default-lease-1').items():
            monkeypatch.setitem(offline_fakes.IDENTITY,key,value)
        if self.processor.on_start is None:
            self.processor.on_start=lambda processes,argv:self.stage('offline')
        self.task=make_task(flow,dict(flow.document,task_id=self.task_id),task_id=self.task_id)

        def group(path):
            self.task_root=path.parent
            self.groups.append(FlowGroup(self.processor,self.events,manifest_path=path,**tree))
            return self.groups[-1]

        overrides=dict(initial_gate=self.gate,capture_rgb=self.capture,capture_act_frame=self.act_frame,
            consumer_ready=lambda child:True,pause_physics=lambda lease,reset:True,resume_physics=lambda lease,reset:True,
            capture_numeric_evidence=lambda lease,localized,root,boundary:_write_numeric(root,boundary+1.0),
            publish_pose=lambda pose:True,execute_result=self.execute_result,cancel_motion=self.cancelled,
            confirm_no_controller_goal=self.confirmed,close_runtime=lambda:self.events.append(('closed',)))
        self.build_kwargs=dict(stack=flow.stack,shard_spec=flow.spec,output_root=flow.output,evidence=self.evidence,
            inference_client_factory=FakeInference,dependencies=dict(reset_point=self.reset,current_evidence=self.evidence),
            runtime_overrides=overrides,perception_runner=self.perceive,process_group_factory=group,**seams)
        if build:
            self.attach(builder().build_collection_task(self.task,**self.build_kwargs))

    def attach(self,execution):
        self.execution,self.runtime=execution,execution.runtime
        spy=execution.artifacts.seal_attempt
        def sealed(lease,decision):
            self.events.append(('seal',))
            return spy(lease,decision)
        execution.artifacts.seal_attempt=sealed   # a spy over the real store, to order events

    def note_lease(self,name):
        if self.execution is not None:
            self.leases[name]=self.execution.state.lease

    def stage(self,name):
        self.events.append((name,))
        hook=self.hooks.get(name)
        if hook is not None:
            hook(self)

    def evidence(self,session):
        return SimpleNamespace(simulation_session_id=self.session,reset_epoch=2,simulation_time_s=1.0)

    def reset(self,lease,point):
        self.note_lease('reset')
        self.stage('reset')
        return SimpleNamespace(simulation_session_id=self.session,new_epoch=2,joint_positions=None)

    def gate(self,lease,reset):
        self.note_lease('gate')
        self.stage('gate')
        fields={name:getattr(lease,name) for name in ('batch_id','coordinator_epoch','worker_id','worker_generation',
                                                      'point_id','attempt_id','lease_generation')}
        return SimpleNamespace(**fields,reset_epoch=reset.reset_epoch,simulation_session_id=reset.simulation_session_id,
            source_frame_monotonic_s=reset.reset_completed_monotonic_s+.5,canonical_joints=True,no_controller_goal=True,
            no_attachment=True,no_contact=True,no_stale_node=True)

    def capture(self,path,boundary):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'rgb')
        return SourceStampedCapture(path,boundary+1.0,12_000_000_000)

    def act_frame(self,lease,boundary):
        return ActInferenceFrame(np.zeros((4,5,3),dtype=np.uint8),boundary+1.0,12_000_000_000,'camera',self.session,
                                 'ros_sim',1)

    def perceive(self,lease,kind,snapshot,call):
        self.note_lease('inference')
        self.stage('inference')
        request=ActInferenceRequest(request_id='request-1',model_id='teacher-model',
            image_timestamp_s=snapshot.source_stamp_ns/1e9,execution_kind=kind,batch_id=lease.batch_id,
            coordinator_epoch=lease.coordinator_epoch,worker_id=lease.worker_id,worker_generation=lease.worker_generation,
            point_id=lease.point_id,lease_generation=lease.lease_generation,reset_epoch='reset-2',
            source_stamp_ns=snapshot.source_stamp_ns,source_frame_id=snapshot.source_frame_id,image_shape=snapshot.shape,
            simulation_session_id=snapshot.simulation_session_id,frame_sequence=snapshot.sequence,
            service_generation='service-teacher',deadline_monotonic_ns=time.monotonic_ns()+10**10,
            attempt_id=lease.attempt_id)
        if self.perception_mode=='terminal':
            from so101_demo.parallel_batch.act_attempt import ActPerceptionTerminal
            disposition,reason,wire=self.terminal
            return ActPerceptionTerminal(disposition=disposition,reason=reason,wire_outcome=wire,
                request=request,audit_relative_path='perception/inference/request-1.json',
                failure_type=None if disposition=='CANCELLED' else 'ActInferenceResponse.'+wire,
                failure_message=None if disposition=='CANCELLED' else wire)
        localized=ActLocalizedPose(request=request,broker_generation=1,session_id=self.session,depth_timestamp_s=1.,
            depth_sha256='a'*64,tf_timestamp_s=1.,source_frame='camera',target_frame='world',position_xyz=(.1,.2,.3),
            orientation_xyzw=(0.,0.,0.,1.))
        return AdmittedPose('camera',snapshot.source_stamp_ns,time.monotonic(),(.1,.2,.3,0.,0.,0.,1.),'reset-2',localized)

    def execute_result(self,lease,admitted,child):
        self.note_lease('execute')
        self.stage('execute')
        execution,task=OUTCOMES[self.teacher]
        fields=dict(execution_status=execution,task_result=task)
        if self.manifest:
            write_manifest(self.task_root/'attempts'/lease.point_id/lease.attempt_id/'working',fields)
        decision=RuntimeDecision(teacher_attempt_status(execution,task),'OK',False,teacher_execution_status=execution,
                                 teacher_task_result=task,act_data_status='DISABLED')
        return ExecutionCompletionReceipt(decision,time.monotonic()+1.0)

    def cancelled(self,lease):
        self.cancel_calls.append(lease)
        self.release.set()
        return self.cancel(lease)

    def confirmed(self,lease):
        self.confirm_calls.append(lease)
        return self.confirm(lease)

    def run_in_thread(self):
        box={}
        def target():
            try:
                box['result']=self.execution.run()
            except BaseException as error:
                box['error']=error
        thread=threading.Thread(target=target,daemon=True)
        thread.start()
        return thread,box

    def sealed(self):
        return self.task_root/'attempts'/'default'/'default-lease-1'/'sealed'


@pytest.fixture
def flow(env):
    return env


def fault_of(rig):
    with pytest.raises(builder().CollectionTaskFault) as raised:rig.execution.run()
    return raised.value


def test_teacher_failure_seals_and_run_returns_summary(flow,monkeypatch):
    from so101_demo.runtime.container_campaign.task_results import read_task_result,write_task_result
    rig=Rig(flow,monkeypatch,teacher='FAILED')
    summary=rig.execution.run()
    assert summary['kind']=='ACT_CONTAINER_COLLECTION_TASK_RESULT' and summary['scene_id']=='default'
    assert (summary['status'],summary['teacher_execution_status'],summary['teacher_task_result']) == ('FAILED','COMPLETED','FAIL')
    assert summary['act_data_status']=='INVALID' and summary['act_data_reason'].startswith('OFFLINE_PROCESSOR_INVALID: rc=3')
    assert summary['act_data_qc']=='NOT_RUN' and summary['export_eligible'] is False
    assert rig.sealed().is_dir() and (rig.sealed()/'result.json').is_file()
    write_task_result(flow.output,rig.task_id,summary)
    assert read_task_result(flow.output,rig.task_id)['result']==summary


def test_qc_failure_in_flow_is_a_business_result(flow,monkeypatch):
    processor=FakeProcesses(returncode=3,outputs='invalid',report=qc_report('FAIL',rc=1,reason='geometry'))
    summary=Rig(flow,monkeypatch,teacher='PASSED',processor=processor).execution.run()
    assert summary['status']=='PASSED' and summary['act_data_status']=='INVALID' and summary['export_eligible'] is False


def test_success_waits_for_closed_bag_and_seal(flow,monkeypatch):
    rig=Rig(flow,monkeypatch)
    summary=rig.execution.run()
    names=[event[0] for event in rig.events]
    assert names.index('bag_closed')<names.index('processor_start')<names.index('seal')
    assert names[-1]!='closed' and 'closed' not in names, 'runtime teardown belongs to shutdown_owned, not run'
    assert (rig.sealed()/'result.json').is_file() and summary['sealed']['path']=='attempts/default/default-lease-1/sealed'
    assert LoggedPilot.events is rig.events


def test_summary_paths_relative_and_hashes_match_sealed_bytes(flow,monkeypatch):
    rig=Rig(flow,monkeypatch)
    summary=rig.execution.run()
    json.dumps(summary,allow_nan=False)
    result=rig.sealed()/'result.json'
    assert summary['sealed']['result']=={'path':'attempts/default/default-lease-1/sealed/result.json',
                                         'sha256':hashlib.sha256(result.read_bytes()).hexdigest()}
    assert not Path(summary['sealed']['path']).is_absolute() and (rig.task_root/summary['sealed']['path']).is_dir()
    document=json.loads(result.read_bytes())
    for name in ('status','teacher_execution_status','teacher_task_result','act_data_status','act_data_reason','act_data_qc',
                 'export_eligible','episode_seal_sha256'):
        assert summary[name]==document[name],name
    exec_lease=rig.execution.state.lease
    assert summary['lease']==vars_of(exec_lease) and summary['reset']=={'reset_epoch':'reset-2','simulation_session_id':rig.session}
    assert (summary['worker_id'],summary['launch_generation'])==('w00',1)
    assert summary['inputs']=={'scope':flow.document['scope'],'inputs_manifest':flow.document['inputs_manifest']}
    assert 'task_id' not in summary


def test_lease_is_init_stage_until_the_gate_and_exec_stage_after(flow,monkeypatch):
    rig=Rig(flow,monkeypatch)
    rig.execution.run()
    init,exec_=rig.leases['reset'],rig.leases['execute']
    assert rig.leases['gate']==init and rig.leases['inference']==exec_ and init is not exec_
    assert vars_of(init)|dict(lease_deadline_monotonic_s=0)==vars_of(exec_)|dict(lease_deadline_monotonic_s=0)
    config=rig.execution.task_input.config
    assert init.lease_deadline_monotonic_s-init.lease_issued_monotonic_s<=config.initializing_hard_timeout_s+1e-6
    assert exec_.lease_deadline_monotonic_s<=flow.spec['deadline_monotonic_s']
    assert exec_.lease_deadline_monotonic_s<=rig.execution.task.deadline_monotonic_s
    assert exec_.lease_deadline_monotonic_s-exec_.lease_issued_monotonic_s>init.lease_deadline_monotonic_s-init.lease_issued_monotonic_s


def test_fault_still_seals_then_raises_with_first_cause(flow,monkeypatch):
    processor=FakeProcesses(returncode=3,outputs='invalid',report=qc_report('ERROR',rc=2,reason='OSError: disk gone'))
    rig=Rig(flow,monkeypatch,teacher='PASSED',processor=processor)
    error=fault_of(rig)
    assert error.code.startswith('DATA_PIPELINE_FAULT: INVALID OFFLINE_PROCESSOR_INVALID: rc=3')
    assert Path(error.sealed_location)==rig.sealed() and (rig.sealed()/'result.json').is_file()


def test_seal_failure_raises(flow,monkeypatch):
    rig=Rig(flow,monkeypatch,manifest=False)
    error=fault_of(rig)
    assert error.code.startswith('RESULT_SEAL_FAILED') and 'RESULT_TEACHER_MANIFEST_REQUIRED' in error.code
    assert error.sealed_location is None and not rig.sealed().exists()


def test_seal_failure_keeps_an_earlier_fault_as_the_first_cause(flow,monkeypatch):
    processor=FakeProcesses(returncode=4,outputs=None)
    error=fault_of(Rig(flow,monkeypatch,manifest=False,processor=processor))
    assert error.code.startswith('DATA_PIPELINE_FAULT') and error.sealed_location is None


def test_data_regraded_at_seal_is_a_fault(flow,monkeypatch):
    """The processor double claims VALID data; the real store finds no verifiable episode and grades it INVALID."""
    rig=Rig(flow,monkeypatch,teacher='PASSED',processor=FakeProcesses())
    error=fault_of(rig)
    assert error.code=='RESULT_DATA_REGRADED_AT_SEAL' and Path(error.sealed_location)==rig.sealed()
    assert json.loads((rig.sealed()/'result.json').read_bytes())['act_data_status']=='INVALID'


def test_perception_no_pose_seals_manifest_free_business_result(flow,monkeypatch):
    from so101_demo.runtime.container_campaign.task_results import read_task_result,write_task_result
    rig=Rig(flow,monkeypatch,perception='terminal')
    summary=rig.execution.run()
    assert ('execute',) not in rig.events and ('seal',) in rig.events
    assert (summary['status'],summary['teacher_execution_status'],summary['teacher_task_result']) == (
        'INDETERMINATE','INDETERMINATE','UNCONFIRMED')
    assert (summary['act_data_status'],summary['act_data_reason'],summary['act_data_qc']) == (
        'INVALID','PERCEPTION_NO_POSE','NOT_RUN')
    assert summary['export_eligible'] is False and summary['episode_seal_sha256'] is None
    assert summary['qc_report_sha256'] is None and summary['audit_manifest_sha256'] is None
    document=json.loads((rig.sealed()/'result.json').read_bytes())
    assert document['status']=='INDETERMINATE' and document['act_data_status']=='INVALID'
    assert (document['teacher_execution_status'],document['teacher_task_result'])==('INDETERMINATE','UNCONFIRMED')
    assert not (rig.sealed()/'dynamic').exists(), 'the manifest-free form carries no Teacher manifest'
    write_task_result(flow.output,rig.task_id,summary)
    assert read_task_result(flow.output,rig.task_id)['result']==summary
    assert rig.execution.shutdown_owned() is True


@pytest.mark.parametrize('terminal',[('INVALID','PERCEPTION_QUEUE_TIMEOUT','QUEUE_TIMEOUT'),
                                     ('INVALID','PERCEPTION_INFERENCE_TIMEOUT','INFERENCE_TIMEOUT'),
                                     ('INVALID','PERCEPTION_INFRA_ERROR','QUEUE_FULL'),
                                     ('INVALID','PERCEPTION_INFRA_ERROR','INPUT_INVALID'),
                                     ('INVALID','PERCEPTION_INFRA_ERROR','INFRA_ERROR'),
                                     ('CANCELLED','PERCEPTION_CANCELLED','INFRA_ERROR'),
                                     ('FAILED','PERCEPTION_MODEL_ERROR','MODEL_ERROR')])
def test_perception_service_timeout_or_infra_is_execution_fault(flow,monkeypatch,terminal):
    rig=Rig(flow,monkeypatch,perception='terminal',terminal=terminal)
    error=fault_of(rig)
    assert error.code=='ACT_PERCEPTION_TERMINAL_UNSEALABLE' and error.sealed_location is None
    assert not rig.sealed().exists() and ('execute',) not in rig.events and ('seal',) not in rig.events


def test_next_task_runs_after_perception_no_pose(flow,monkeypatch):
    import asyncio
    from functools import partial
    from so101_demo.runtime.container_campaign.task_executor import ContainerTaskExecutor
    from so101_demo.runtime.container_campaign.task_results import read_task_result
    rig=Rig(flow,monkeypatch,perception='terminal',build=False)
    second=make_task(flow,dict(flow.document,task_id='e-second'),task_id='e-second')
    class Retirement:
        calls=0
        async def retire(self,*,fenced):
            Retirement.calls+=1
            return dict(goals_stopped=True,controllers_stopped=True,ros_children_exited=True,ros_graph_empty=True,forced=False)
    async def finished(executor,task_id):
        async def wait():
            while True:
                status=await executor.get_status(task_id)
                if status.task.state in ('SUCCEEDED','FAILED'):
                    return status
                await asyncio.sleep(.02)
        return await asyncio.wait_for(wait(),120)
    async def run():
        executor=ContainerTaskExecutor(instance_id='instance-01',
            builder=partial(builder().build_collection_task,**rig.build_kwargs),retirement=Retirement(),
            output_root=flow.output,stop_timeout_s=10.,retire_timeout_s=10.,owner_timeout_s=120.)
        try:
            assert (await executor.assign_task(rig.task)).state=='ACCEPTED'
            status=await finished(executor,rig.task.task_id)
            assert status.task.state=='SUCCEEDED' and status.state=='READY', status.task.fault_reason
            stored=read_task_result(flow.output,rig.task.task_id)
            assert stored['task_id']==rig.task.task_id and stored['result']['status']=='INDETERMINATE'
            assert stored['result']['act_data_status']=='INVALID' and stored['result']['act_data_reason']=='PERCEPTION_NO_POSE'
            rig.perception_mode='admit'
            assert (await executor.assign_task(second)).state=='ACCEPTED'
            status=await finished(executor,'e-second')
            assert status.task.state=='SUCCEEDED' and status.state=='READY', status.task.fault_reason
            stored=read_task_result(flow.output,'e-second')
            assert stored['result']['teacher_task_result']=='FAIL' and stored['result']['status']=='FAILED'
            assert executor.cleanup_errors==[] and Retirement.calls==0
        finally:
            await executor.terminate('fixture end')
    asyncio.run(run())
    assert len(rig.groups)==2 and rig.groups[0] is not rig.groups[1]


def test_unconfirmed_stop_before_motion_is_execution_fault(flow,monkeypatch):
    rig=Rig(flow,monkeypatch,perception='terminal',cancel=False)
    error=fault_of(rig)
    assert error.code=='TASK_CLEANUP_UNCONFIRMED' and rig.execution.workload.cleanup_unconfirmed is True
    rows=[json.loads(line) for line in (rig.task_root/'revocation-events.jsonl').read_text().splitlines()]
    result=[row for row in rows if row['phase']=='CANCEL_RESULT'][-1]
    assert result['motion_stopped'] is False and result['broker_fenced'] is True and result['controllers_confirmed'] is True
    assert rig.execution.shutdown_owned() is False


@pytest.mark.parametrize('stage',['reset','inference','execute','offline'])
def test_request_stop_interrupts_reset_inference_execution_and_offline(flow,monkeypatch,stage):
    rig=Rig(flow,monkeypatch,hooks={stage:lambda rig:rig.execution.request_stop()})
    error=fault_of(rig)
    assert error.code=='TASK_STOP_REQUESTED' and error.sealed_location is None and not rig.sealed().exists()
    assert rig.runtime.stop_requested and rig.execution.state.stop.is_set() and rig.execution.teacher._is_fenced()
    deadline=time.monotonic()+5
    while not rig.cancel_calls and time.monotonic()<deadline:time.sleep(.01)
    assert rig.cancel_calls, 'the revocation thread cancelled motion'
    assert rig.execution.shutdown_owned() is True
    assert rig.runtime.owned_process_manifest.processes==() and not rig.runtime._recorders


def test_stop_before_run_refuses_the_run(flow,monkeypatch):
    rig=Rig(flow,monkeypatch)
    rig.execution.request_stop()
    assert fault_of(rig).code=='TASK_STOP_REQUESTED'
    assert ('reset',) not in rig.events and rig.execution.shutdown_owned() is True


def test_a_boundary_exception_revokes_and_raises_its_own_message(flow,monkeypatch):
    def explode(rig):
        raise RuntimeError('RESET_PLANNING_SCENE_RESTORE')
    rig=Rig(flow,monkeypatch,hooks={'reset':explode})
    assert fault_of(rig).code=='RESET_PLANNING_SCENE_RESTORE'
    rows=[json.loads(line) for line in (rig.task_root/'revocation-events.jsonl').read_text().splitlines()]
    assert [row['phase'] for row in rows]==['CANCEL_REQUESTED','CONTROLLER_CANCEL_RESULT','CANCEL_RESULT']
    assert rig.execution.shutdown_owned() is True


def test_a_second_run_is_refused(flow,monkeypatch):
    rig=Rig(flow,monkeypatch)
    rig.execution.run()
    assert fault_of(rig).code=='TASK_RUN_ALREADY_STARTED'


def test_teacher_deadline_guard_revokes_and_run_raises(flow,monkeypatch):
    def block(rig):
        assert rig.release.wait(10), 'the deadline guard never revoked'
    rig=Rig(flow,monkeypatch,hooks={'execute':block},teacher_bound_s=.2)
    error=fault_of(rig)
    assert error.code=='TEACHER_EXECUTION_DEADLINE'
    assert rig.cancel_calls and Path(error.sealed_location)==rig.sealed(), 'the Teacher evidence is still sealed'
    assert rig.execution._revocation['audit_event'].wait(10)
    rows=[json.loads(line) for line in (rig.task_root/'revocation-events.jsonl').read_text().splitlines()]
    assert rows[0]['phase']=='WATCHDOG_REVOKED' and rows[0]['reason']=='TEACHER_EXECUTION_DEADLINE'
    assert rig.execution.shutdown_owned() is True


def test_shutdown_true_only_with_empty_manifest_recorder_and_controller_proof(flow,monkeypatch):
    rig=Rig(flow,monkeypatch)
    rig.execution.run()
    assert len(rig.runtime.owned_process_manifest.processes)==1, 'the consumer helper is still owned after run'
    assert rig.execution.shutdown_owned() is True and rig.execution.shutdown_owned() is True
    assert rig.execution.retire_proofs=={'processes_empty':True,'manifest_readback_empty':True,'recorder_proven':True,
        'controller_proven':True,'runtime_closed':True,'stack_alive':True,'ready_gate':True}
    assert [event for event in rig.events if event[0]=='closed']==[('closed',)], 'single flight: closed once'
    assert json.loads((rig.task_root/'owned-runtime-processes.json').read_bytes())['processes']==[]


@pytest.mark.parametrize('problem',['controller','recorder','close_runtime','stack_dead','not_ready'])
def test_shutdown_false_without_a_named_proof(flow,monkeypatch,problem):
    rig=Rig(flow,monkeypatch,confirm=problem!='controller')
    summary=rig.execution.run()
    assert summary['status']=='FAILED'
    if problem=='recorder':rig.runtime._recorders[rig.runtime._lease_key(rig.execution.state.lease)]=object()
    elif problem=='close_runtime':rig.runtime._close_runtime=lambda:1/0
    elif problem=='stack_dead':flow.stack.process.poll=lambda:1
    elif problem=='not_ready':rig.runtime._ready_probe=lambda requirements:False
    try:
        assert rig.execution.shutdown_owned() is False
    finally:
        flow.stack.process.poll=lambda:None


def test_shutdown_false_when_run_does_not_return_or_helper_survives(flow,monkeypatch):
    gate=threading.Event()
    rig=Rig(flow,monkeypatch,hooks={'reset':lambda rig:gate.wait(10)},recovery_timeout_s=.3)
    thread,box=rig.run_in_thread()
    deadline=time.monotonic()+5
    while ('reset',) not in rig.events and time.monotonic()<deadline:time.sleep(.01)
    assert rig.execution.shutdown_owned() is False, 'run() has not returned within the recovery timeout'
    gate.set();thread.join(10)
    assert 'result' in box or 'error' in box
    survivor=Rig(flow,monkeypatch,tree=dict(signal_process=lambda pid,signum:None,interrupt_timeout_s=.2,terminate_timeout_s=.2))
    survivor.execution.run()
    try:
        assert survivor.execution.shutdown_owned() is False
        assert survivor.execution.retire_proofs['processes_empty'] is False
    finally:
        for _identity,child in list(survivor.runtime._processes._children):child.kill();child.wait()


def test_late_helper_after_stop_is_stopped(flow,monkeypatch):
    late={}
    def start_late(rig):
        rig.execution.request_stop()
        late['identity']=rig.runtime._processes.start(StackProcessSpec('late-helper',SLEEP))
    rig=Rig(flow,monkeypatch,hooks={'execute':start_late})
    assert fault_of(rig).code=='TASK_STOP_REQUESTED'
    child=next(child for identity,child in rig.runtime._processes._children if identity==late['identity'])
    assert child.poll() is None, 'the helper outlived the stop request until cleanup'
    assert rig.execution.shutdown_owned() is True
    assert child.poll() is not None and rig.runtime.owned_process_manifest.processes==()


def test_second_task_on_same_stack_gets_fresh_runtime_and_ready_gate(flow,monkeypatch):
    first=Rig(flow,monkeypatch,teacher='FAILED')
    first.execution.run()
    assert first.execution.shutdown_owned() is True
    second=Rig(flow,monkeypatch,teacher='DEADLINE')
    assert second.runtime is not first.runtime and second.execution.teacher is not first.execution.teacher
    assert second.execution.artifacts is not first.execution.artifacts and second.task_root!=first.task_root
    assert second.runtime.worker_ready_gate() is False, 'a fresh runtime has attached nothing yet'
    summary=second.execution.run()
    assert summary['teacher_execution_status']=='DEADLINE' and second.runtime.worker_ready_gate() is True
    assert second.execution.shutdown_owned() is True and second.sealed().is_dir() and first.sealed().is_dir()


def vars_of(lease):
    from dataclasses import asdict
    return asdict(lease)


# ---- branches pinned after review ------------------------------------------------------------------------------------------

def test_runtime_not_ready_is_a_fault_before_any_lease(flow,monkeypatch):
    """The stack attaches (first probe True), then the ready gate is False: nothing was leased, reset or started."""
    answers=iter([True])
    rig=Rig(flow,monkeypatch,build=False)
    rig.build_kwargs['dependencies']['ready_probe']=lambda requirements:next(answers,False)
    rig.attach(builder().build_collection_task(rig.task,**rig.build_kwargs))
    error=fault_of(rig)
    assert error.code=='TASK_RUNTIME_NOT_READY' and error.sealed_location is None
    assert rig.execution.state.lease is None and ('reset',) not in rig.events and rig.runtime._active_lease is None
    assert rig.cancel_calls==[] and rig.confirm_calls==[] and not (rig.task_root/'revocation-events.jsonl').exists()
    # Cleanup is True: the run raised, so the stop path ran; with no lease the revocation is vacuous, no helper process,
    # recorder or controller goal was ever started, and the native stack is the shard's to retire, not this task's.
    assert rig.execution.shutdown_owned() is True
    assert rig.execution.retire_proofs=={'processes_empty':True,'manifest_readback_empty':True,'recorder_proven':True,
                                         'controller_proven':True,'runtime_closed':True}
    assert rig.cancel_calls==[] and rig.confirm_calls==[]


@pytest.mark.parametrize('stage',['init','exec'])
def test_lease_deadline_expiry_is_a_fault(flow,monkeypatch,stage):
    clock=Clock()
    rig=Rig(flow,monkeypatch,build=False,hooks={'reset' if stage=='init' else 'inference':
                                                  lambda rig:setattr(clock,'offset',1e6)})
    rig.build_kwargs['clock']=clock
    rig.attach(builder().build_collection_task(rig.task,**rig.build_kwargs))
    error=fault_of(rig)
    assert error.code=='TASK_LEASE_DEADLINE_EXPIRED' and error.sealed_location is None
    assert rig.cancel_calls, 'the expiry ran the revocation'
    assert not rig.sealed().exists() and ('execute',) not in rig.events
    assert ('inference',) in rig.events if stage=='exec' else ('inference',) not in rig.events
    assert rig.execution.state.lease.lease_deadline_monotonic_s<=flow.spec['deadline_monotonic_s']
    rows=[json.loads(line) for line in (rig.task_root/'revocation-events.jsonl').read_text().splitlines()]
    assert rows[-1]['phase']=='CANCEL_RESULT' and rows[-1]['motion_stopped'] is True


def test_seal_location_outside_task_directory_is_a_fault(flow,monkeypatch):
    rig=Rig(flow,monkeypatch)
    outside=flow.tmp/'elsewhere'/'sealed'
    outside.mkdir(parents=True)
    (outside/'result.json').write_text(json.dumps({'status':'FAILED'}))
    rig.execution.artifacts.seal_attempt=lambda lease,decision:str(outside)   # a store that reports an escaping location
    error=fault_of(rig)
    assert error.code.startswith('RESULT_READBACK_FAILED') and error.sealed_location==str(outside)


def test_fault_before_reset_treats_nothing_as_started(flow,monkeypatch):
    """No active runtime lease means reset never began: the revocation is vacuous and calls no controller port."""
    rig=Rig(flow,monkeypatch)
    rig.execution.state.lease=lease_for(flow)   # a lease exists on the task, but the runtime never saw a reset
    assert rig.runtime._active_lease is None
    rig.execution.request_stop()
    record=rig.execution._revocation
    assert record['event'].wait(5) and record['audit_event'].wait(5)
    assert (record['stopped'],record['confirmed']) == (True,True) and rig.cancel_calls==[] and rig.confirm_calls==[]
    assert rig.execution.shutdown_owned() is True


@pytest.mark.parametrize('port',['cancel_false','cancel_raises','confirm_false','confirm_raises'])
def test_fault_after_reset_began_needs_the_controller_proof(flow,monkeypatch,port):
    """Reset has begun (the runtime holds the lease): an unproven or failing cancel or confirm is never inferred."""
    def explode(lease):
        raise RuntimeError('controller port down')
    options={'cancel_false':dict(cancel=False),'cancel_raises':dict(cancel=explode),
             'confirm_false':dict(confirm=False),'confirm_raises':dict(confirm=explode)}[port]
    def fail(rig):
        raise RuntimeError('RESET_PLANNING_SCENE_RESTORE')
    rig=Rig(flow,monkeypatch,hooks={'reset':fail},**options)
    assert fault_of(rig).code=='RESET_PLANNING_SCENE_RESTORE'
    assert rig.runtime._active_lease is not None and rig.cancel_calls and rig.confirm_calls
    record=rig.execution._revocation
    assert (record['stopped'],record['confirmed']) == {'cancel_false':(False,True),'cancel_raises':(False,True),
        'confirm_false':(True,False),'confirm_raises':(True,False)}[port]
    assert rig.execution.shutdown_owned() is False
    assert rig.execution.retire_proofs['controller_proven'] is False
