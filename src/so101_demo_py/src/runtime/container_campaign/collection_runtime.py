"""ACT cases borrow the native shard stack and retire only their own helper processes."""

import math
from pathlib import Path

from so101_demo.parallel_batch.contracts.common import RunMode
from so101_demo.runtime.act_worker_runtime import ActWorkerRuntime
from so101_teleop.unified.act_stack import ActStackProcessOwner


class ContainerCollectionRuntime(ActWorkerRuntime):
    def __init__(self,*args,existing_stack,case_artifacts=None,**kwargs):
        super().__init__(*args,**kwargs)
        if (self.run_mode is not RunMode.EXECUTE or not isinstance(existing_stack,ActStackProcessOwner)
                or existing_stack.launch.evidence_root!=self.resources.worker_root/'stack'
                or existing_stack.launch.ros_domain_id!=self.resources.ros_domain_id
                or getattr(existing_stack.launch,'ros_namespace',None)!=self.resources.controller_namespace
                or existing_stack.launch.session_id!=self.resources.session_id):
            raise ValueError('COLLECTION_BORROWED_STACK_MISMATCH')
        self.stack=existing_stack
        self._case_artifacts=case_artifacts
        self._case_cleaned_key=None

    def reset_point(self,lease):
        if self._case_artifacts is not None:
            if (self._recorders or (self._active_lease is not None
                    and self._case_cleaned_key!=self._lease_key(self._active_lease))):
                raise ValueError('COLLECTION_PREVIOUS_CASE_NOT_CLEANED')
            scope,inputs=self._case_artifacts.case_binding(lease)
            self.episode_scope_path=str(scope)
            self.episode_inputs_manifest=str(inputs)
            if self._collection is not None and self._collection.enabled:
                from so101_demo.act.frozen_runtime_inputs import load_recorder_frozen_policy
                self._recorder_policy=load_recorder_frozen_policy(Path(inputs))
            self._case_cleaned_key=None
        return super().reset_point(lease)

    def start_physical_runtime(self):
        self._execution_allowed()
        if self._physical_started:
            raise ValueError('COLLECTION_STACK_ALREADY_ATTACHED')
        if (self.stack.owner is None or self.stack.process is None or self.stack.process.poll() is not None
                or self._ready_probe(('controllers','move_group','joint_states','planning_scene')) is not True):
            raise ValueError('COLLECTION_NATIVE_STACK_NOT_READY')
        # No launch command, generic station, replacement generation or second
        # simulator is started by the Worker. The shard owns this native stack.
        self._physical_started=True

    def prepare_next_case(self,lease,*,deadline_monotonic_s,physical_action_proven_absent):
        if (type(deadline_monotonic_s) not in (int,float) or not math.isfinite(deadline_monotonic_s)
                or type(physical_action_proven_absent) is not bool
                or self._monotonic()>=deadline_monotonic_s or self.stop_requested
                or self._active_lease is None or self._lease_key(self._active_lease)!=self._lease_key(lease)
                or self._recorders):
            return False
        try:
            if not physical_action_proven_absent and self._confirm_no_controller_goal(lease) is not True:
                return False
            self._processes.shutdown()
            if self._processes.manifest.processes or self._monotonic()>=deadline_monotonic_s:
                return False
            self._close_runtime()
            key=self._lease_key(lease)
            self._execute_consumers.pop(key,None)
            self._paused_for_inference.discard(key)
            if self.stack.process is None or self.stack.process.poll() is not None:
                return False
            ready=self.worker_ready_gate() is True and self._monotonic()<deadline_monotonic_s
            if ready:self._case_cleaned_key=key
            return ready
        except Exception:
            return False
