"""A same-process view of the formal Head owner, with no resource factories."""

import copy
import math
import os
from pathlib import Path
import threading
import uuid

from so101_demo.act.head_evidence_identity import digest
from .head_execution_composition import HeadExecutionComposition


class HeadExecutionOwnerBridge:
    """Delegate the declared initial target and Stop to the already-bound owner."""

    def __init__(self, composition):
        if type(composition) is not HeadExecutionComposition or not composition.complete:
            raise PermissionError('HEAD_BRIDGE_COMPOSITION_INCOMPLETE')
        self.composition = composition
        self.runtime = composition._bound['runtime']['runtime']
        self.inference_owner = composition._bound['inference']
        self.search = composition._bound['search']
        self.port = composition._bound['ros']['port']
        if (self.search.primary is not self.runtime or self.search.owner is not self.inference_owner
                or self.search.port is not self.port or self.runtime.port is not self.port):
            raise PermissionError('HEAD_BRIDGE_OWNER_MISMATCH')
        self._target_lock = threading.Lock()
        self._target_attempted = False

    def _require_live(self):
        if self.composition.closed or self.runtime.retirement_snapshot()['closed']:
            raise PermissionError('HEAD_BRIDGE_CLOSED')

    def descriptor(self):
        """Describe these exact resources without granting qualification or authority."""
        self._require_live()
        inputs = self.composition.inputs
        process_id = os.getpid()
        fields = (Path('/proc')/str(process_id)/'stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            raise PermissionError('HEAD_BRIDGE_OWNER_NOT_LIVE')
        return copy.deepcopy(dict(
            schema_version=1, kind='head_execution_owner',
            operation=inputs.document['operation'], execution_scope=inputs.execution_scope,
            qualification_status='NOT_QUALIFIED', run=inputs.run,
            execution_inputs_sha256=inputs.document_sha256,
            simulation_policy_sha256=digest(self.composition.policy.readback()),
            owner=dict(pid=process_id, started_ticks=int(fields[19])),
            transport='IN_PROCESS_OWNED_RESOURCE',
            node=self.runtime.node.get_fully_qualified_name(),
            native_bound=self.runtime.local_state.controller_bound,
            cuda_device=getattr(self.inference_owner, 'runtime_device', None),
            required_search_domain_rad=self.search.controller.config['required_search_domain_rad'],
            safe_interval_rad=self.search.controller.config['lock_valid_neck_rad'],
            resource_ids=dict(node=id(self.runtime.node), port=id(self.port),
                              runtime=id(self.runtime), inference=id(self.inference_owner),
                              search=id(self.search), writer=id(self.composition.writer))))

    def submit_target(self, target_rad):
        """Use the existing owner thread and its guarded first-MOVE operation once."""
        self._require_live()
        domain = self.search.controller.config.get('required_search_domain_rad')
        if (threading.get_ident() != self.search._entry
                or type(target_rad) not in (int, float) or not math.isfinite(target_rad)
                or type(domain) not in (list, tuple) or len(domain) != 2
                or target_rad != domain[0]):
            raise PermissionError('HEAD_BRIDGE_TARGET_REFUSED')
        with self._target_lock:
            if self._target_attempted:
                raise PermissionError('HEAD_BRIDGE_TARGET_REFUSED')
            self._target_attempted = True
        # The search validates readiness, original deadline, full scene/prefix,
        # typed inventory and native admission; a UI cannot bypass that path.
        goal_uuid = self.search.begin_development_move(target_rad)
        try:
            parsed_uuid = uuid.UUID(goal_uuid)
            valid_uuid = str(parsed_uuid) == goal_uuid and parsed_uuid.version == 4
        except (AttributeError, TypeError, ValueError):
            valid_uuid = False
        if not valid_uuid:
            self.runtime.fault('HEAD_BRIDGE_GOAL_UUID_INVALID')
            raise PermissionError('HEAD_BRIDGE_GOAL_UUID_INVALID')
        return dict(submitted_rad=target_rad, goal_uuid=goal_uuid, status='SUBMITTED')

    @staticmethod
    def _stop_view(receipt):
        result = copy.deepcopy(receipt)
        result['state'] = 'STOPPED' if result['physical_stop_confirmed'] is True else 'STOPPING'
        return result

    def stop(self):
        """Request the existing independent stop workers; accept no caller samples."""
        self._require_live()
        receipt = self.runtime.stop('signal', dict(source='head_execution_owner_bridge'))
        return self._stop_view(receipt)

    def stop_status(self):
        self._require_live()
        return self._stop_view(self.runtime.stop_receipt())
