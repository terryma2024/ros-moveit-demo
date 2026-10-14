"""ACT cases borrow the native shard stack and retire only their own helper processes."""

import copy
import json
import math
from pathlib import Path
import time

from so101_demo.parallel_batch.contracts.common import RunMode
from so101_demo.runtime.act_worker_runtime import ActWorkerRuntime
from so101_teleop.unified.act_stack import ActStackProcessOwner


GOAL_CHECK_PAUSE_S = 0.5


def _pause_between_goal_checks(seconds):
    time.sleep(seconds)


class ContainerCollectionRuntime(ActWorkerRuntime):
    def __init__(self,*args,existing_stack,case_artifacts=None,native_owned_root=None,**kwargs):
        super().__init__(*args,**kwargs)
        # The task data root (resources.worker_root) may differ from the native owned root that holds the stack.
        native=self.resources.worker_root if native_owned_root is None else self._native_root(native_owned_root)
        if (self.run_mode is not RunMode.EXECUTE or not isinstance(existing_stack,ActStackProcessOwner)
                or (native_owned_root is not None and self.resources.worker_root.is_relative_to(native/'stack'))
                or existing_stack.launch.evidence_root!=native/'stack'
                or existing_stack.launch.ros_domain_id!=self.resources.ros_domain_id
                or existing_stack.launch.session_id!=self.resources.session_id):
            raise ValueError('COLLECTION_BORROWED_STACK_MISMATCH')
        self.stack=existing_stack
        self._case_artifacts=case_artifacts
        self._case_cleaned_key=None
        self.collection_facts=None

    @staticmethod
    def _native_root(value):
        try:
            root=Path(value)
            if not root.is_absolute() or root.resolve(strict=True)!=root or not root.is_dir():
                raise ValueError
        except (OSError,TypeError,ValueError):
            raise ValueError('COLLECTION_BORROWED_STACK_MISMATCH') from None
        return root

    def _write_collection_record(self,point_root,facts,reason):
        """Keep what the offline pipeline reported so the task can tell a data verdict from a pipeline fault."""
        self.collection_facts=(copy.deepcopy(facts),reason)
        super()._write_collection_record(point_root,facts,reason)

    def reset_point(self,lease):
        self.collection_facts=None
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
            cause=self.ready_failure()
            raise ValueError('COLLECTION_NATIVE_STACK_NOT_READY'+('' if cause is None else ': '+cause))
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

    def _goal_absent(self,lease,budget_s):
        """The independent controller-goal check, repeated until one attempt proves it or `budget_s` is spent. One attempt is
        the unchanged proof (a fresh participant, statuses terminal or empty, cancel answers). A fresh participant can need
        a second or more to discover the cancel services, so an unsettled attempt is a transient negative and is tried again;
        an attempt that raises counts as unproven. No attempt starts after the budget; `None` is one attempt. The answer is
        True only if some attempt proved it."""
        deadline=None if budget_s is None else self._monotonic()+budget_s
        while True:
            try:
                if self._confirm_no_controller_goal(lease) is True:
                    return True
            except Exception:
                pass
            if deadline is None or self._monotonic()>=deadline:
                return False
            _pause_between_goal_checks(min(GOAL_CHECK_PAUSE_S,max(0.,deadline-self._monotonic())))
            if self._monotonic()>=deadline:
                return False

    def retire_case(self,lease,*,cancelled,absent,goal_budget_s=None):
        """Stop this case's helpers and name what is proven. `cancelled` is None on the clean path; on the stop or
        fault path it is whether the revocation proved motion stopped and controllers confirmed. Only an exact
        True counts; a failed or missing check is False, never inferred. `goal_budget_s` bounds how long the goal
        check may be repeated (None: one attempt)."""
        proofs={}

        def check(name,call):
            try:
                proofs[name]=call() is True
            except Exception:
                proofs[name]=False

        def shut():
            self._processes.shutdown()
            return True

        def disk_empty():
            document=json.loads((self.resources.worker_root/'owned-runtime-processes.json').read_bytes())
            return document['processes']==[]

        started=self._active_lease is not None
        shutdown_failed=not self._ran(shut)
        check('processes_empty',lambda:not shutdown_failed and self._processes.manifest.processes==())
        check('manifest_readback_empty',disk_empty)
        check('recorder_proven',lambda:not self._recorders and (lease is None and not started
                                                                  or self.recorder_stop_proven(lease) is True))
        if not started:
            proofs['controller_proven']=True   # reset never began: no motion or goal can exist for this case
        elif cancelled is None:
            check('controller_proven',lambda:absent is True or self._goal_absent(lease,goal_budget_s) is True)
        else:
            check('controller_proven',lambda:cancelled is True and self._goal_absent(lease,goal_budget_s) is True)
        if lease is not None and self._lease_key(lease) in self._physics_held:
            # before the runtime closes its pause control: native retirement must find the simulation running
            check('physics_resumed',lambda:self.release_physics_hold(lease))
        check('runtime_closed',lambda:self._close_runtime() or True)
        if lease is not None:
            key=self._lease_key(lease)
            self._execute_consumers.pop(key,None)
            self._paused_for_inference.discard(key)
        if cancelled is None:
            check('stack_alive',lambda:self.stack.process is not None and self.stack.process.poll() is None)
            check('ready_gate',lambda:self.worker_ready_gate() is True)
        return proofs

    @staticmethod
    def _ran(call):
        try:
            return call() is True
        except Exception:
            return False
