"""Run-locator and readback-proof publication helpers for ACT results.

Split out of `result_store` only to keep that module under the line limit; `result_store` re-exports every name here. The shared
helpers are imported lazily because `result_store` imports this module at its end.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import uuid

from so101_demo.parallel_batch.contracts.common import RunMode
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity


def resolve_native_run(run_root):
    """Locate retained originals from one actual dispatch and its journaled lease workspace."""
    from .result_store import _read_regular,_safe,_workspace
    from .diagnostic_episode_inputs import verify_frozen_inputs
    from .collection_scope import read_collection_scope,build_collection_scope
    from so101_demo.parallel_batch.journal import CoordinatorJournal,JournalCorruption
    try:
        root=_safe(Path(run_root));metadata={}
        for line in _read_regular(root/'run.log').decode().splitlines():
            key,separator,value=line.partition('=')
            if separator and key in ('batch_id','mode','lifecycle','inputs'):
                if key in metadata:raise ValueError('ambiguous run locator')
                metadata[key]=value
        if set(metadata)!={'batch_id','mode','lifecycle','inputs'} or metadata['lifecycle']!='FULL_RESTART':
            raise ValueError('run metadata absent')
        inputs_manifest=_safe(Path(metadata['inputs'])/'inputs-manifest.json')
        frozen=verify_frozen_inputs(inputs_manifest)
        if (_read_regular(root/'inputs-manifest.json')!=_read_regular(inputs_manifest)
                or frozen['mode']!=metadata['mode']):
            raise ValueError('original inputs mismatch')
        scope=root/'episode-scope.json'
        anchor=frozen['roles']['anchor_scene']['identity']
        if read_collection_scope(scope)!=build_collection_scope(frozen['mode'],scene_id=anchor['scene_id'],
                seed=anchor['seed'],inputs_sha256=frozen['inputs_sha256']):
            raise ValueError('original scope mismatch')
        coordinator_root=root/'run/coordinator'
        replay=CoordinatorJournal.read_only_replay(coordinator_root,metadata['batch_id'])
        grants=[event for event in replay.events if event.type=='LEASE_GRANTED']
        starts=[event for event in replay.events if event.type=='BATCH_STARTED']
        if len(grants)!=1 or len(starts)!=1:
            raise ValueError('one run lease required')
        request=starts[0].payload['delta']['request']
        current=LeaseIdentity(**grants[0].payload['response'])
        workspace=_workspace(root/'run/workers'/current.worker_id,current)
        observed=grants[0].payload['delta']['workers'][current.worker_id]['workspace']
        if (request['batch_id']!=metadata['batch_id'] or request['run_mode']!=RunMode.EXECUTE.value
                or request['worker_count']!=1 or request['selected_point_ids']!=[current.point_id]
                or _safe(Path(request['evidence_root']))!=root/'run'
                or _safe(Path(observed))!=workspace):
            raise ValueError('journaled run locator mismatch')
        location=workspace/'sealed'
        if not location.is_dir():raise ValueError('sealed result missing')
        return dict(episode=location/'episode',location=location,scope=scope,
            inputs_manifest=inputs_manifest,coordinator_root=coordinator_root)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,JournalCorruption) as error:
        raise ValueError('RESULT_RUN_CONTEXT_INVALID') from error


def write_commit_proof(proof, output):
    """Publish a new durable readback artifact; it grants no execution or commit authority."""
    if (type(proof) is not dict or proof.get('kind')!='ACT_COORDINATOR_COMMIT_PROOF'
            or proof.get('schema_version')!=1 or proof.get('status')!='PASS'):
        raise ValueError('COMMIT_PROOF_INVALID')
    return _publish_readback_proof(proof,output)


def write_export_rejection_proof(proof,output):
    """Publish the two actual common export refusals without granting training eligibility."""
    if (type(proof) is not dict or proof.get('kind')!='ACT_DIAGNOSTIC_EXPORT_REJECTION'
            or proof.get('schema_version')!=1 or proof.get('status')!='PASS'
            or proof.get('dataset_produced') is not False
            or proof.get('perception_or_policy_models_loaded') is not False
            or proof.get('checks')!={'resolver':'DIAGNOSTIC_EPISODE_NOT_TRAINABLE',
                                    'direct_export':'DIAGNOSTIC_EPISODE_NOT_TRAINABLE'}):
        raise ValueError('EXPORT_REJECTION_PROOF_INVALID')
    return _publish_readback_proof(proof,output)


def write_readback_receipt(receipt,output):
    """Publish the combined receipt of one independent readback; it grants no execution, commit or export authority."""
    if (type(receipt) is not dict or receipt.get('kind')!='ACT_READBACK_RECEIPT' or receipt.get('schema_version')!=1
            or receipt.get('status') not in ('PASS','FAIL')):
        raise ValueError('READBACK_RECEIPT_INVALID')
    return _publish_readback_proof(receipt,output)


def _publish_readback_proof(proof,output):
    from .result_store import _canonical,_fsync_dir,_safe
    target=_safe(Path(output))
    if target.exists():raise ValueError('COMMIT_PROOF_ALREADY_WRITTEN')
    payload=_canonical(proof)
    staged=target.parent/('.'+target.name+'.'+uuid.uuid4().hex+'.pending')
    try:
        fd=os.open(staged,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        _fsync_dir(target.parent)
        os.link(staged,target,follow_symlinks=False)
        _fsync_dir(target.parent)
    except OSError as error:
        raise ValueError('COMMIT_PROOF_UNWRITABLE') from error
    return hashlib.sha256(payload).hexdigest()
