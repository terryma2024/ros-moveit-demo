"""Compose one local ACT collection task inside the shard container.

The closed task input document is validated before anything is created on disk. The builder
starts no simulator, Recorder or Teacher and never connects to the Host. Native stack ownership
stays with the shard; shared inference services stay borrowed.
"""

from dataclasses import asdict,dataclass,replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time

from so101_demo.act.collection_orchestration import CollectionOptions
from so101_demo.act.collection_scope import read_collection_scope
from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs
from so101_demo.act.frozen_runtime_inputs import load_teacher_frozen_inputs,load_recorder_frozen_policy
from so101_demo.act.parallel_collection import ActFixedCollectionWorkload
from so101_demo.act.parallel_collection_contracts import read_document,scene_ids
from so101_demo.cli.mujoco_batch.common import _lease_wire
from so101_demo.cli.mujoco_batch.request import _load_runtime_config
from so101_demo.parallel_batch.act_attempt import ActPerceptionDecision
from so101_demo.parallel_batch.contracts.common import AttemptStatus,RunMode,ExecutionKind,_require_id
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.parallel_batch.contracts.linux_cuda import teacher_execution_bound_s
from so101_demo.parallel_batch.resource_allocation.models import WorkerResources
from so101_demo.parallel_batch.worker_parts.protocol import WorkerProtocol
from so101_demo.runtime.act_ros_runtime import ActRosRuntimePorts
from so101_demo.runtime.parallel_worker_parts.receipts import RuntimeDecision
from so101_demo.runtime.act_teacher_client import ActTeacherClient
from so101_demo.runtime.container_campaign.case_artifacts import CollectionCaseArtifacts
from so101_demo.runtime.container_campaign.collection_runtime import ContainerCollectionRuntime
from so101_demo.runtime.act_instance.identity import (
    ACT_INSTANCE_ROS_DOMAIN_ID, ACT_INSTANCE_ROS_NAMESPACE, INSTANCE_ROOT_ENV, verify_instance_environment)
from so101_demo.runtime.container_campaign.task_contracts import TaskSpec
from so101_demo.runtime.inference.client import InferenceClient
from so101_demo.runtime.inference.config import validate_file_ref,load_campaign_config
from so101_teleop.unified.act_stack import ActStackProcessOwner


KIND='ACT_CONTAINER_COLLECTION_TASK'
_FIELDS={'schema_version','kind','task_id','worker_id','launch_generation','wave_id','scene_id',
    'scene_manifest','scope','inputs_manifest','teacher'}
_ENDPOINT={'role','socket_path','service_generation','max_frame_bytes'}


class CollectionTaskFault(RuntimeError):
    """An execution fault (never a business result); `code` is the first cause."""

    def __init__(self,code,*,sealed_location=None):
        super().__init__(code)
        self.code=code
        self.sealed_location=sealed_location


@dataclass(frozen=True)
class TaskInput:
    task_id: str
    root: Path
    scene_id: str
    row: dict
    refs: dict
    config: object
    campaign: dict
    teacher_policy: dict
    recorder_policy: dict
    teacher: dict
    shard_spec: dict


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value)


_SPEC_TEXT=('workload_kind','campaign_id','worker_id','wave_id','owned_root',
    'simulation_session_id','gpu_uuid')
_SPEC_IDENTITY=('runtime_config_sha256','collection_config_sha256','contact_policy_fingerprint')


def _check_spec(spec):
    """The shard spec keys and types this module reads; anything else is the shard loader's business."""
    try:
        if (type(spec) is not dict or any(type(spec[name]) is not str for name in _SPEC_TEXT)
                or spec['workload_kind']!='act_collection' or re.fullmatch(r'w[0-9]+',spec['worker_id']) is None
                or type(spec['launch_generation']) is not int
                or not _finite(spec['deadline_monotonic_s'])
                or type(spec['business_identity']) is not dict
                or any(type(spec['business_identity'][name]) is not str for name in _SPEC_IDENTITY)
                or any(type(spec[name]) is not dict for name in ('parallel_runtime','campaign_config'))):
            raise ValueError
    except (KeyError,TypeError,ValueError):
        raise ValueError('COLLECTION_SHARD_SPEC_INVALID') from None
    return spec


def load_task_input(task,shard_spec,*,teacher_socket,clock=time.monotonic):
    """Validate the assignment against the shard and the frozen originals; creates nothing."""
    if type(task) is not TaskSpec:
        raise ValueError('COLLECTION_TASK_SPEC_INVALID')
    _check_spec(shard_spec)
    now=clock()
    if (not _finite(shard_spec['deadline_monotonic_s']) or shard_spec['deadline_monotonic_s']<=now
            or task.deadline_monotonic_s<=now or task.deadline_monotonic_s>shard_spec['deadline_monotonic_s']):
        raise ValueError('COLLECTION_TASK_DEADLINE_INVALID')
    root=Path(shard_spec['owned_root'])
    try:
        verify_instance_environment(os.environ,session_id=shard_spec['simulation_session_id'])
        drift=os.environ.get(INSTANCE_ROOT_ENV)!=str(root)
    except ValueError:
        drift=True
    if root.resolve(strict=True)!=root or not root.is_dir() or drift:
        raise ValueError('COLLECTION_TASK_ENVIRONMENT_DRIFT')
    if task.inputs_ref.path!=str(root/'task-inputs'/(task.task_id+'.json')):
        raise ValueError('COLLECTION_TASK_INPUT_LOCATION_INVALID')
    try:
        document=read_document(validate_file_ref(task.inputs_ref.model_dump()))
    except Exception as error:   # unreadable, duplicate keys, not an object: one input fault
        raise ValueError('COLLECTION_TASK_INPUT_INVALID') from error
    if (set(document)!=_FIELDS or type(document['schema_version']) is not int or document['schema_version']!=1
            or document['kind']!=KIND or document['task_id']!=task.task_id):
        raise ValueError('COLLECTION_TASK_INPUT_INVALID')
    _require_id('scene_id',document['scene_id'])
    for name in ('worker_id','launch_generation','wave_id'):
        if type(document[name]) is not type(shard_spec[name]) or document[name]!=shard_spec[name]:
            raise ValueError('COLLECTION_TASK_CONTEXT_MISMATCH')
    config=_load_runtime_config(validate_file_ref(shard_spec['parallel_runtime']))
    campaign=load_campaign_config(validate_file_ref(shard_spec['campaign_config']),roles=('teacher',),
        expected_sha256=shard_spec['campaign_config']['sha256'])
    identity=shard_spec['business_identity']
    if (campaign['gpu_uuid']!=shard_spec['gpu_uuid']
            or campaign['controlled_runtime']['sha256']!=identity['runtime_config_sha256']
            or config.yolo_model_id!=campaign['teacher_service']['model']['model_id']):
        raise ValueError('COLLECTION_TASK_MODEL_OR_RUNTIME_MISMATCH')
    for role in ('teacher',):
        endpoint=document[role]
        if (type(endpoint) is not dict or set(endpoint)!=_ENDPOINT
                or endpoint['role']!=role or endpoint['socket_path']!=str(teacher_socket)
                or type(endpoint['service_generation']) is not str or not endpoint['service_generation']
                or type(endpoint['max_frame_bytes']) is not int
                or endpoint['max_frame_bytes']!=campaign[role+'_service']['max_frame_bytes']):
            raise ValueError('COLLECTION_SERVICE_ENDPOINT_INVALID')
    manifest=validate_file_ref(document['scene_manifest'])
    scene_ids(document['scene_manifest'])
    row={row['scene_id']:row for row in read_document(manifest)['scenarios']}.get(document['scene_id'])
    position=None if row is None else row.get('cup_position_world_m')
    if (type(position) is not list or len(position)!=3 or any(not _finite(value) for value in position)):
        raise ValueError('COLLECTION_TASK_SCENE_INVALID')
    refs={name:document[name] for name in ('scope','inputs_manifest')}
    frozen,_,_=load_teacher_frozen_inputs(validate_file_ref(refs['inputs_manifest']))
    if (frozen['mode']!='formal'
            or frozen['roles']['runtime_config']['sha256']!=identity['runtime_config_sha256']
            or frozen['roles']['collection_config']['sha256']!=identity['collection_config_sha256']):
        raise ValueError('COLLECTION_CASE_RUNTIME_MISMATCH')
    scope=read_collection_scope(validate_file_ref(refs['scope']),expected_mode='formal',
        expected_inputs_sha256=frozen['inputs_sha256'])
    if scope['scene_id']!=document['scene_id']:
        raise ValueError('COLLECTION_CASE_SCOPE_MISMATCH')
    if 'scene_manifest' in frozen:
        # the frozen set binds the scene list: the task must carry that very list, and its scope must be one of its rows
        if document['scene_manifest']['sha256']!=frozen['scene_manifest']['sha256']:
            raise ValueError('COLLECTION_CASE_SCENE_MANIFEST_MISMATCH')
        require_scope_for_inputs(scope,frozen,Path(validate_file_ref(refs['inputs_manifest'])))
    for role in ('contact_proposal','contact_activation'):
        original=read_document(Path(refs['inputs_manifest']['path']).parent/frozen['roles'][role]['path'])
        if original.get('policy_fingerprint')!=identity['contact_policy_fingerprint']:
            raise ValueError('COLLECTION_CASE_CONTACT_POLICY_MISMATCH')
    recorder=load_recorder_frozen_policy(Path(refs['inputs_manifest']['path']))
    for ref in (document['scene_manifest'],*refs.values()):validate_file_ref(ref)
    return TaskInput(task_id=task.task_id,root=root,scene_id=document['scene_id'],row=row,refs=refs,
        config=config,campaign=campaign,teacher_policy=dict(frozen['teacher_execution_policy']['values']),
        recorder_policy=recorder,teacher=document['teacher'],
        shard_spec=shard_spec)


def local_lease(shard_spec,scene_id,*,issued,deadline):
    """The one local lease identity; attempt_id never derives from the task id, which may contain '.'."""
    _check_spec(shard_spec)
    return LeaseIdentity(batch_id=shard_spec['campaign_id']+'-'+shard_spec['wave_id'],coordinator_epoch=1,
        worker_id=shard_spec['worker_id'],worker_generation=shard_spec['launch_generation'],point_id=scene_id,
        attempt_id=scene_id+'-lease-1',lease_generation=1,lease_issued_monotonic_s=issued,
        lease_deadline_monotonic_s=deadline)


def exec_lease(lease,*,deadline):
    """Same identity and issue time, restamped for the executing stage."""
    return replace(lease,lease_deadline_monotonic_s=deadline)


def stage_deadline(config,stage,*,start,task_deadline,shard_deadline):
    """Stage bound from the frozen runtime config, never beyond the task or campaign deadline."""
    if stage not in ('init','exec'):
        raise ValueError('COLLECTION_TASK_STAGE_INVALID')
    bound=config.initializing_hard_timeout_s if stage=='init' else config.executing_hard_timeout_s
    return min(start+bound,task_deadline,shard_deadline)


class LocalTaskState:
    """What the local fences read: the current executing lease, the stop event and the clock."""

    def __init__(self,clock=time.monotonic):
        self.clock=clock
        self.stop=threading.Event()
        self.lease=None


def task_resources(shard_spec,*,task_root):
    """Task data lives under `task_root`; every other path stays under the native owned root."""
    _check_spec(shard_spec)
    root=Path(shard_spec['owned_root'])
    session=shard_spec['simulation_session_id']
    temporary=root/'tmp'
    return WorkerResources(worker_id=shard_spec['worker_id'],slot_index=int(shard_spec['worker_id'][1:]),
        generation=shard_spec['launch_generation'],ros_domain_id=ACT_INSTANCE_ROS_DOMAIN_ID,
        simulation_port=session,bridge_port=session,gz_partition=session,session_id=session,
        controller_namespace=ACT_INSTANCE_ROS_NAMESPACE,render_backend='egl',render_context_id=session,
        render_context_namespace=temporary/'render',virtual_display='not_applicable',
        ros_home=temporary/'ros-home',ros_log_dir=root/'ros-logs',temp_dir=temporary,
        socket_namespace=root/'control',socket_path=root/'control'/'worker-unused.sock',
        worker_root=Path(task_root),environment=dict(os.environ))


def teacher_context_probe(*,state,ports,resources,evidence):
    """Local replacement for the Coordinator projection: the current lease, the stop flag, the deadline and the reset epoch."""
    def probe(lease,execution_kind,start_event_id,start_event_type):
        if (execution_kind is not ExecutionKind.ATTEMPT or start_event_type!='ATTEMPT_STARTED'
                or start_event_id!='attempt-start-'+lease.attempt_id):
            raise ValueError('COLLECTION_TEACHER_START_MISMATCH')
        current=state.lease
        if (current is None or state.stop.is_set() or _lease_wire(lease)!=_lease_wire(current)
                or state.clock()>=current.lease_deadline_monotonic_s):
            raise ValueError('COLLECTION_TEACHER_LEASE_FENCED')
        reset=ports._reset_receipts.get(lease.attempt_id)
        if reset is None:
            raise ValueError('COLLECTION_TEACHER_RESET_CHANGED')
        observed=evidence(resources.session_id)
        if (observed.simulation_session_id!=resources.session_id
                or observed.reset_epoch!=reset.reset_epoch_value):
            raise ValueError('COLLECTION_TEACHER_RESET_CHANGED')
        return _lease_wire(lease)|dict(reset_epoch=reset.reset_epoch,session_id=resources.session_id)
    return probe


def local_authorize(state):
    """Perception-latch authorization: exactly True only for the current lease before its deadline."""
    def authorize(request):
        try:
            lease=state.lease
            if lease is None or state.stop.is_set() or state.clock()>=lease.lease_deadline_monotonic_s:
                return False
            identifier=(request.attempt_id if request.execution_kind is ExecutionKind.ATTEMPT
                        else request.validation_id)
            return (request.batch_id,request.coordinator_epoch,request.worker_id,request.worker_generation,
                    request.point_id,request.lease_generation,identifier)==(lease.batch_id,
                lease.coordinator_epoch,lease.worker_id,lease.worker_generation,lease.point_id,
                lease.lease_generation,lease.attempt_id)
        except Exception:
            return False
    return authorize


def _borrowed_station(_resources):
    raise ValueError('COLLECTION_SECOND_SIMULATOR_FORBIDDEN')


def _current_evidence(session_id):
    from so101_demo.backends.mujoco.teleop_runtime import current_evidence
    return current_evidence(session_id)


def _check_stack(stack,spec,root,output_root):
    try:
        outside=not Path(output_root).resolve().is_relative_to(root/'stack')
    except (OSError,TypeError,ValueError):
        outside=False
    if (not outside or not isinstance(stack,ActStackProcessOwner) or stack.launch.evidence_root!=root/'stack'
            or stack.launch.ros_domain_id!=ACT_INSTANCE_ROS_DOMAIN_ID
            or stack.launch.session_id!=spec['simulation_session_id']):
        raise ValueError('COLLECTION_BORROWED_STACK_MISMATCH')


def result_summary(*,task_input,lease,reset,location,task_root):
    """The run's return value, read back from the sealed `result.json`; every output path is relative to the task directory."""
    sealed=Path(location)
    root=Path(task_root)
    relative=sealed.relative_to(root)   # a location outside the task directory is a fault, not a path to report
    raw=(sealed/'result.json').read_bytes()
    result=json.loads(raw)
    if type(result) is not dict:
        raise ValueError('RESULT_JSON_NOT_AN_OBJECT')
    summary=dict(schema_version=1,kind='ACT_CONTAINER_COLLECTION_TASK_RESULT',scene_id=task_input.scene_id,
        worker_id=lease.worker_id,launch_generation=lease.worker_generation,lease=asdict(lease),
        reset=dict(reset_epoch=reset.reset_epoch,simulation_session_id=reset.simulation_session_id),
        sealed=dict(path=relative.as_posix(),result=dict(path=(relative/'result.json').as_posix(),
                                                       sha256=hashlib.sha256(raw).hexdigest())))
    for name in ('status','teacher_execution_status','teacher_task_result','act_data_status','act_data_reason',
                 'act_data_qc','export_eligible','episode_seal_sha256','qc_report_sha256','inputs_sha256','scope_sha256',
                 'audit_manifest_sha256','collection_mode'):
        if name in result:
            summary[name]=result[name]
    summary['inputs']=dict(scope=dict(task_input.refs['scope']),inputs_manifest=dict(task_input.refs['inputs_manifest']))
    json.dumps(summary,allow_nan=False)
    return summary


def _sealable(decision):
    return (type(decision) is RuntimeDecision
            and decision.status in (AttemptStatus.PASSED,AttemptStatus.FAILED,AttemptStatus.INDETERMINATE)
            and decision.teacher_execution_status is not None and decision.teacher_task_result is not None
            and decision.act_data_status is not None)


def perception_business_decision(decision):
    """The manifest-free sealable form of a perception terminal the model itself produced, else None.

    Only a terminal whose disposition is FAILED with reason PERCEPTION_NO_POSE (the model answered: nothing detected, or a pose
    that was rejected; a MODEL_ERROR is a service error and stays a fault) with every stop fact proven is a
    business result: Teacher execution INDETERMINATE, task result UNCONFIRMED, data INVALID with the perception reason,
    so the recorded attempt status is INDETERMINATE. This is the form the generic Worker commits for a pre-motion input
    refusal (`_pre_motion_decision`); the store accepts it without a Teacher manifest. A service, queue, infrastructure or
    input fault, a cancellation and an unconfirmed stop return None and stay execution faults."""
    if (type(decision) is not ActPerceptionDecision or decision.perception.disposition!='FAILED'
            or decision.perception.reason!='PERCEPTION_NO_POSE'
            or decision.perception.wire_outcome not in ('NOT_DETECTED','DETECTED')
            or not all(decision.stop_facts.values()) or decision.physical_action_proven_absent is not True):
        return None
    reason=decision.perception.reason
    return RuntimeDecision(AttemptStatus.INDETERMINATE,reason,True,teacher_execution_status='INDETERMINATE',
                           teacher_task_result='UNCONFIRMED',act_data_status='INVALID',act_data_reason=reason)


class CollectionTaskExecution:
    """One task over its constructed parts: `run` is the local flow, `request_stop` and `shutdown_owned` end it.

    `run` is called on one thread, `request_stop` and `shutdown_owned` from others. Every fault carries the first cause."""

    def __init__(self,*,task_input,state,artifacts,resources,ports,teacher,runtime,workload,task,stack,clock,
                 teacher_bound_s=None,recovery_timeout_s=None):
        self.task_input,self.state,self.artifacts,self.resources = task_input,state,artifacts,resources
        self.ports,self.teacher,self.runtime,self.workload = ports,teacher,runtime,workload
        self.task,self.stack,self.clock = task,stack,clock
        config=task_input.config
        self.teacher_bound_s=teacher_execution_bound_s(config) if teacher_bound_s is None else teacher_bound_s
        self.recovery_timeout_s=config.worker_recovery_timeout_s if recovery_timeout_s is None else recovery_timeout_s
        self.revoke_wait_s=config.heartbeat_timeout_s
        self.retire_proofs=None
        self.decision=None
        self._cause=None
        self._lock=threading.Lock()
        self._run_started=self._run_raised=False
        self._run_done=threading.Event()
        self._revocation=None
        self._deadline_hit=False
        self._shutdown_lock=threading.Lock()
        self._shutdown_result=None

    # ---- causes, guards and boundaries -------------------------------------------------------------------------------------

    def _note(self,code):
        with self._lock:
            if self._cause is None:
                self._cause=code
            return self._cause

    def _fault(self,code,**options):
        return CollectionTaskFault(self._note(code),**options)

    def _guard(self):
        lease=self.state.lease
        if self.state.stop.is_set():
            raise self._fault('TASK_STOP_REQUESTED')
        if lease is None or self.state.clock()>=lease.lease_deadline_monotonic_s:
            raise self._fault('TASK_LEASE_DEADLINE_EXPIRED')
        return lease

    def boundary(self,call):
        lease=self._guard()
        result=call(lease)
        self._guard()
        return result

    def teacher_boundary(self,call):
        """The Teacher window: its own deadline guard is armed at the open, the runtime closes the window at Teacher exit."""
        lease=self._guard()
        closed=threading.Event()
        deadline=self.state.clock()+self.teacher_bound_s

        def watch():
            while not closed.wait(0.01):
                try:
                    expired=self.state.clock()>=deadline
                except Exception:
                    expired=True
                if expired:
                    self._deadline_hit=True
                    self._note('TEACHER_EXECUTION_DEADLINE')
                    self._start_revocation('TEACHER_EXECUTION_DEADLINE')
                    return

        threading.Thread(target=watch,name='collection-task-teacher-deadline',daemon=True).start()
        bind=getattr(self.runtime,'bind_teacher_exit',None)
        if bind is not None:
            bind(closed.set)
        try:
            result=call(lease)
        finally:
            closed.set()
        if self.state.stop.is_set():
            raise self._fault('TASK_STOP_REQUESTED')
        return result

    def _recorder_stopped(self,lease):
        try:
            return self.runtime.recorder_stop_proven(lease) is True
        except Exception:
            return False

    # ---- revocation ----------------------------------------------------------------------------------------------------------

    def _start_revocation(self,reason=None):
        """At most one cancel-and-confirm path per execution (the local form of the Worker's single-flight revocation)."""
        with self._lock:
            if self._revocation is not None:
                return self._revocation
            lease=self.state.lease
            record=self._revocation=dict(event=threading.Event(),audit_event=threading.Event(),fenced=False,
                                         stopped=False,confirmed=False,lease=lease)
        worker,generation=self.resources.worker_id,self.resources.generation

        def fence():
            try:
                record['fenced']=self.teacher.cancel_generation(worker,generation) is True
            except Exception:
                pass

        if lease is None:   # no lease was ever issued: nothing was started that could be cancelled
            fence()
            record['stopped']=record['confirmed']=True
            record['event'].set()
            record['audit_event'].set()
            return record

        def revoke():
            audit=[]

            def note(phase,**details):
                audit.append((phase,dict(recorded_wall_time_ns=time.time_ns(),recorded_monotonic_ns=time.monotonic_ns(),
                                         **details)))

            broker=threading.Thread(target=fence,name='collection-task-broker-fence',daemon=True)
            try:
                if reason is not None:
                    note('WATCHDOG_REVOKED',reason=reason)
                note('CANCEL_REQUESTED')
                broker.start()
                try:
                    # reset never began: no motion or goal exists for this lease
                    record['stopped']=(True if self.runtime._active_lease is None
                                       else self.runtime.cancel_motion(lease) is True)
                except Exception:
                    pass
                try:
                    record['confirmed']=(True if self.runtime._active_lease is None
                                         else self.runtime.confirm_no_controller_goal(lease) is True)
                except Exception:
                    pass
                note('CONTROLLER_CANCEL_RESULT',motion_stopped=record['stopped'] is True,
                     controllers_confirmed=record['confirmed'] is True)
            finally:
                if broker.ident is not None:
                    broker.join()
                note('CANCEL_RESULT',broker_fenced=record['fenced'] is True,motion_stopped=record['stopped'] is True,
                     controllers_confirmed=record['confirmed'] is True)
                record['event'].set()   # safety completion is visible before any audit I/O
                try:
                    for phase,details in audit:
                        try:
                            self.runtime.record_revocation(lease,phase,**details)
                        except Exception:
                            pass   # a missing audit row fails the evidence gates later; it never delays the stop
                finally:
                    record['audit_event'].set()

        threading.Thread(target=revoke,name='collection-task-revocation',daemon=True).start()
        return record

    def _revoke(self):
        """Stop before motion: `(None, fenced, stopped, confirmed)`, each exactly True or False."""
        record=self._start_revocation()
        record['event'].wait(self.revoke_wait_s)
        record['audit_event'].wait(self.revoke_wait_s)
        return None,record['fenced'] is True,record['stopped'] is True,record['confirmed'] is True

    # ---- the flow ------------------------------------------------------------------------------------------------------------

    def run(self):
        with self._lock:
            if self._run_started:
                raise CollectionTaskFault('TASK_RUN_ALREADY_STARTED')
            self._run_started=True
        try:
            return self._run()
        except BaseException as error:
            self._run_raised=True
            if isinstance(error,CollectionTaskFault):
                raise
            raise self._fault(((str(error) or type(error).__name__))[:300]) from error
        finally:
            self._run_done.set()

    def _run(self):
        runtime,state,spec,task=self.runtime,self.state,self.task_input.shard_spec,self.task
        if state.stop.is_set():
            raise self._fault('TASK_STOP_REQUESTED')
        runtime.start_physical_runtime()
        if runtime.worker_ready_gate() is not True:
            cause=runtime.ready_failure()
            raise self._fault('TASK_RUNTIME_NOT_READY'+('' if cause is None else ': '+cause))
        issued=state.clock()
        scene=self.task_input.scene_id
        deadlines=dict(task_deadline=task.deadline_monotonic_s,shard_deadline=spec['deadline_monotonic_s'])
        init=local_lease(spec,scene,issued=issued,
                         deadline=stage_deadline(self.task_input.config,'init',start=issued,**deadlines))
        state.lease=init
        try:
            reset=self.boundary(lambda lease:runtime.reset_point(lease))
            gate=self.boundary(lambda lease:runtime.point_initial_gate(lease,reset))
            summary=WorkerProtocol._gate_summary(init,reset,gate)
            started=state.clock()
            lease=exec_lease(init,deadline=stage_deadline(self.task_input.config,'exec',start=started,**deadlines))
            state.lease=lease
            decision=self.workload.run_authorized(lease,runtime=runtime,broker=self.teacher,boundary=self.boundary,
                teacher_boundary=self.teacher_boundary,stop_before_motion=lambda current:self._revoke(),
                recorder_stopped=self._recorder_stopped,start_event_id='attempt-start-'+lease.attempt_id,
                start_event_type='ATTEMPT_STARTED',reset_epoch=summary['reset_epoch'])
            self.decision=decision
            pending=None
            if self.workload.cleanup_unconfirmed:
                pending='TASK_CLEANUP_UNCONFIRMED'
            elif state.stop.is_set():
                pending='TASK_STOP_REQUESTED'
            elif self._deadline_hit:
                pending='TEACHER_EXECUTION_DEADLINE'
            if pending is not None:
                self._note(pending)
            classified=classify_task_fault(decision,runtime.collection_facts)
            if classified is not None:
                self._note(classified)
        except BaseException as error:
            self._note((str(error) or type(error).__name__)[:300])
            self._revoke()
            raise
        location=None
        sealed_decision=perception_business_decision(decision) or decision
        if _sealable(sealed_decision) and not state.stop.is_set():
            try:
                location=self.artifacts.seal_attempt(lease,sealed_decision)
            except Exception as error:
                self._note(('RESULT_SEAL_FAILED: '+(str(error) or type(error).__name__))[:300])
                raise self._fault('RESULT_SEAL_FAILED') from error
        if self._cause is not None:
            raise CollectionTaskFault(self._cause,sealed_location=location)
        if state.stop.is_set():
            raise self._fault('TASK_STOP_REQUESTED')
        try:
            summary=result_summary(task_input=self.task_input,lease=lease,reset=reset,location=location,
                                   task_root=self.artifacts.root)
        except Exception as error:
            raise self._fault(('RESULT_READBACK_FAILED: '+(str(error) or type(error).__name__))[:300],
                              sealed_location=location) from error
        if sealed_decision.act_data_status=='VALID' and (summary['act_data_status'],summary['act_data_qc'])!=('VALID','PASS'):
            raise self._fault('RESULT_DATA_REGRADED_AT_SEAL',sealed_location=location)
        return summary

    # ---- stop and cleanup ----------------------------------------------------------------------------------------------------

    def request_stop(self):
        """Non-blocking and idempotent: fence every local gate, then cancel on a thread that is never joined here."""
        self._note('TASK_STOP_REQUESTED')
        self.state.stop.set()
        self.runtime._stop_requested.set()
        try:
            self.teacher.cancel_generation(self.resources.worker_id,self.resources.generation)
        except Exception:
            pass
        self._start_revocation()

    def shutdown_owned(self):
        """Single-flight, cached: True only when every named cleanup fact is exactly True. Never raises."""
        with self._shutdown_lock:
            if self._shutdown_result is None:
                try:
                    self._shutdown_result=self._shutdown() is True
                except BaseException:
                    self._shutdown_result=False
            return self._shutdown_result

    def _shutdown(self):
        runtime,state=self.runtime,self.state
        stopped=state.stop.is_set() or self._run_raised
        record=None
        if stopped:
            record=self._start_revocation()
            if not (record['event'].wait(self.recovery_timeout_s) and record['audit_event'].wait(self.recovery_timeout_s)):
                return False
            try:
                runtime._processes.shutdown()
            except Exception:
                pass   # the final shutdown below reports it
        if self._run_started and not self._run_done.wait(self.recovery_timeout_s):
            return False
        cancelled=None
        if record is not None:
            cancelled=record['stopped'] is True and record['confirmed'] is True
        absent=self.decision is not None and getattr(self.decision,'physical_action_proven_absent',None) is True
        self.retire_proofs=runtime.retire_case(state.lease,cancelled=cancelled,absent=absent)
        return bool(self.retire_proofs) and all(value is True for value in self.retire_proofs.values())


def _data_verdict(facts,reason):
    """True only when the offline processor itself judged the data invalid: a rule or the engine said so, nothing crashed."""
    try:
        processor=facts[0]['processor']
        if facts[1]!=reason or type(processor['returncode']) is not int or processor['returncode']!=3:
            return False
        if processor['report']['verdict']!='INVALID':
            return False
        qc=processor['qc']
        if qc['status']=='NOT_RUN':
            return True
        if qc['status']=='FAIL':
            return type(qc.get('rc')) is int and qc['rc']==1
        return (qc['status']=='ERROR' and type(qc.get('rc')) is int and qc['rc']==2
                and type(qc.get('reason')) is str and qc['reason'].startswith('ValueError: '))
    except (KeyError,TypeError,IndexError):
        return False


def classify_task_fault(decision,facts):
    """None for a business result (the task succeeded, even if the cup was dropped or the data is invalid), else the fault code.

    `facts` is the runtime's `collection_facts` pair. Only a valid datum, or an invalid one the processor itself
    judged (an engine verdict, a QC failure or a QC rule that raised), is business. Every other path -- a crashed or
    timed-out processor or QC process, a recorder that did not start or close, an unverifiable Teacher receipt -- is a
    fault; so is any perception terminal except the model's own no-pose result (`perception_business_decision`)."""
    if isinstance(decision,ActPerceptionDecision):
        return None if perception_business_decision(decision) is not None else 'ACT_PERCEPTION_TERMINAL_UNSEALABLE'
    if (not isinstance(decision,RuntimeDecision) or decision.teacher_execution_status is None
            or decision.teacher_task_result is None or decision.act_data_status is None):
        return 'TASK_DECISION_NOT_A_TEACHER_RESULT'
    reason=decision.act_data_reason if type(decision.act_data_reason) is str else ''
    if reason.startswith(('DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE','TEACHER_CHILD_')):
        return ('TEACHER_RESULT_UNVERIFIED: '+reason)[:200]
    if decision.act_data_status=='VALID':
        return None
    if decision.act_data_status=='INVALID' and reason.startswith('OFFLINE_PROCESSOR_INVALID: rc=3') and _data_verdict(facts,reason):
        return None
    return ('DATA_PIPELINE_FAULT: '+decision.act_data_status+' '+reason)[:200]


def _stack_ready(ports,ready_check):
    """One gate's fresh observation. Only an exact True is ready; an exception or any other answer is not ready, and
    the first cause stays on the ports until a later gate passes, so the fault names why."""
    try:
        answer=ready_check()
        reason=None if answer is True else 'COLLECTION_READY_CHECK_NOT_TRUE'
    except Exception as error:
        reason=(str(error) or type(error).__name__)[:200]
    if reason is None:
        ports.ready_failure_message=None
        return True
    if getattr(ports,'ready_failure_message',None) is None:
        ports.ready_failure_message=reason
    return False


def build_collection_task(task,*,stack,shard_spec,output_root,teacher_socket,ready_check=None,evidence=None,
                          inference_client_factory=InferenceClient,dependencies=None,clock=time.monotonic,
                          runtime_overrides=None,perception_runner=None,teacher_bound_s=None,recovery_timeout_s=None,
                          process_group_factory=None):
    """Validate, then build artifacts, resources, ports, Teacher client, runtime and workload; starts nothing.

    The keywords after `output_root` are test seams with production defaults: the Teacher context evidence reader, the
    inference client factory, port `dependencies`, the clock, runtime port overrides, the process group, the perception chain
    runner and the two bounds that otherwise come from the frozen runtime config.

    `ready_check` is the repeatable native readiness check of the borrowed stack: one call is one fresh no-motion
    observation and returns exactly True when the stack is ready. It is required. The stack's own `ready_probe` is the
    single-use start probe, consumed by the shard start, so it is never a fallback."""
    if not callable(ready_check) or ready_check is getattr(stack,'ready_probe',None):
        raise ValueError('COLLECTION_READY_CHECK_REQUIRED')
    loaded=load_task_input(task,shard_spec,teacher_socket=teacher_socket,clock=clock)
    _check_stack(stack,shard_spec,loaded.root,output_root)
    state=LocalTaskState(clock)
    scene=loaded.scene_id
    # The task directory is reserved before the runtime exists: the process tree writes its manifest there.
    artifacts=CollectionCaseArtifacts(worker_id=shard_spec['worker_id'],launch_generation=shard_spec['launch_generation'],
        worker_root=Path(output_root),case_inputs={scene:loaded.refs},clock=clock,task_id=task.task_id)
    resources=task_resources(shard_spec,task_root=artifacts.root)
    ports=ActRosRuntimePorts(resources,catalog={scene:loaded.row},config=loaded.config,mode=RunMode.EXECUTE,
        broker_generation=resources.generation,dependencies=dict(act_profile=True,
            workspace_provider=artifacts.workspace,authorize=local_authorize(state),
            teacher_execution_policy=loaded.teacher_policy,
            ready_probe=lambda requirements:_stack_ready(ports,ready_check))|dict(dependencies or {}))
    settings=loaded.campaign['teacher_service']
    model=settings['model']
    teacher=ActTeacherClient(client=inference_client_factory(socket_path=loaded.teacher['socket_path'],
            service_generation=loaded.teacher['service_generation'],max_frame_bytes=loaded.teacher['max_frame_bytes']),
        resources=resources,model_id=model['model_id'],weights_sha256=model['weights']['sha256'],
        classes=model['classes'],query_class_id='plastic_cup' if 'plastic_cup' in model['classes'].values() else 'cup',
        launch_generation=resources.generation,request_budget_s=settings['queue_timeout_s']+settings['inference_timeout_s'],
        context_probe=teacher_context_probe(state=state,ports=ports,resources=resources,
            evidence=evidence or _current_evidence),perception_runner=perception_runner or ports.run_perception_chain)
    kwargs=ports.kwargs()|dict(existing_stack=stack,native_owned_root=loaded.root,case_artifacts=artifacts,
        station_config=_borrowed_station,reserve_workspace=artifacts.reserve_workspace,
        episode_scope_path=loaded.refs['scope']['path'],episode_inputs_manifest=loaded.refs['inputs_manifest']['path'],
        collection=CollectionOptions(),recorder_policy=loaded.recorder_policy,
        pose_receive_timeout_s=loaded.teacher_policy['execution_deadline_s'])|dict(runtime_overrides or {})
    if process_group_factory is not None:
        kwargs['process_group']=process_group_factory(resources.worker_root/'owned-runtime-processes.json')
    runtime=ContainerCollectionRuntime(resources,RunMode.EXECUTE,**kwargs)
    return CollectionTaskExecution(task_input=loaded,state=state,artifacts=artifacts,resources=resources,ports=ports,
        teacher=teacher,runtime=runtime,workload=ActFixedCollectionWorkload(scene_ids=(scene,)),task=task,
        stack=stack,clock=clock,teacher_bound_s=teacher_bound_s,recovery_timeout_s=recovery_timeout_s)
