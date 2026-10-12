"""Route each collection lease to its own immutable original artifact bindings."""

import copy
from pathlib import Path
import time

from so101_demo.act.collection_scope import read_collection_scope
from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.cli.mujoco_batch.worker_process import _ArtifactResults
from so101_demo.parallel_batch.contracts.common import RunMode,_require_id,_require_sha256,_require_positive_int
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.runtime.inference.config import validate_file_ref


class CollectionCaseArtifacts:
    def __init__(self,*,worker_id,launch_generation,worker_root,case_inputs,clock=time.monotonic,
                 task_id=None):
        _require_id('worker_id',worker_id)
        _require_positive_int('launch_generation',launch_generation)
        root=Path(worker_root)
        if (root.resolve(strict=True)!=root or not root.is_dir()
                or type(case_inputs) is not dict or not case_inputs or not callable(clock)):
            raise ValueError('COLLECTION_CASE_ARTIFACTS_INVALID')
        self.worker_id=worker_id
        self.launch_generation=launch_generation
        self.references=copy.deepcopy(case_inputs)
        self.writers={}
        for scene,refs in self.references.items():
            _require_id('scene_id',scene)
            if type(refs) is not dict or set(refs)!={'scope','inputs_manifest'}:
                raise ValueError('COLLECTION_CASE_INPUTS_INVALID')
            scope,inputs=self._binding(scene)
        if task_id is not None:
            if len(self.references) != 1:
                raise ValueError('ONE_TASK_ONE_CASE_REQUIRED')
            from .task_results import reserve_task_output
            root = reserve_task_output(root, task_id)
        for scene in self.references:
            scope,inputs=self._binding(scene)
            self.writers[scene]=_ArtifactResults({worker_id:root},RunMode.EXECUTE,
                collection_scope=scope,collection_inputs_manifest=inputs,clock=clock)

    def _binding(self,scene):
        refs=self.references[scene]
        paths={name:validate_file_ref(ref) for name,ref in refs.items()}
        inputs=read_document(paths['inputs_manifest'])
        _require_sha256('inputs_sha256',inputs.get('inputs_sha256'))
        scope=read_collection_scope(paths['scope'],expected_mode='formal',
            expected_inputs_sha256=inputs['inputs_sha256'])
        if scope['scene_id']!=scene or inputs.get('mode')!='formal':
            raise ValueError('COLLECTION_CASE_SCOPE_MISMATCH')
        for ref in refs.values():validate_file_ref(ref)
        return paths['scope'],paths['inputs_manifest']

    def case_binding(self,lease):
        if (type(lease) is not LeaseIdentity or lease.worker_id!=self.worker_id
                or lease.worker_generation!=self.launch_generation or lease.point_id not in self.writers):
            raise ValueError('COLLECTION_CASE_LEASE_MISMATCH')
        return self._binding(lease.point_id)

    def _writer(self,lease):
        self.case_binding(lease)
        return self.writers[lease.point_id]

    def reserve_workspace(self,lease,reset_receipt):
        return self._writer(lease).reserve_workspace(lease,reset_receipt)

    def workspace(self,lease):
        return self._writer(lease).workspace(lease)

    def seal_attempt(self,lease,decision):
        return self._writer(lease).seal_attempt(lease,decision)

    def write_recovery_receipt(self,lease,**kwargs):
        return self._writer(lease).write_recovery_receipt(lease,**kwargs)

    def verify_recovery_receipt(self,location,lease,**kwargs):
        return self._writer(lease).verify_recovery_receipt(location,lease,**kwargs)
