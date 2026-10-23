"""What the Host checks about an instance the same way whichever launcher started it.

The container owner and the native owner own different things (a Docker container, a Host process group) but read the same
documents the one instance program writes: its spec, its runtime-ready record and its instance-exit record.
"""

from dataclasses import asdict
import hashlib
from pathlib import Path

from so101_demo.act.parallel_collection_contracts import read_document


def load_instance_spec(path, *, admitted_context, launch, service_token):
    """Load the instance spec and prove it names exactly this admitted campaign, launch and token."""
    from so101_demo.runtime.act_instance.spec import load_spec

    spec, _runtime = load_spec(path)
    expected = dict(campaign_id=admitted_context.campaign_id, worker_id=launch.worker_id,
        execution_generation=admitted_context.execution_generation, service_epoch=admitted_context.service_epoch,
        launch_generation=launch.launch_generation, owned_root=str(Path(launch.owned_root)),
        simulation_session_id=launch.session_id, gpu_uuid=admitted_context.physical_gpu_uuid,
        service_token=service_token)
    if (any(spec.get(name) != value or type(spec.get(name)) is not type(value) for name, value in expected.items())
            or type(spec.get('runtime_id')) is not str or not spec['runtime_id']):
        raise ValueError('SHARD_SPEC_CONTEXT_MISMATCH')
    if spec['workload_kind'] == 'act_collection':
        identity = {name: getattr(admitted_context, name) for name in (
            'manifest_sha256', 'runtime_config_sha256', 'collection_config_sha256', 'contact_policy_fingerprint')}
        if (spec['business_identity'] != identity
                or spec['campaign_config'] != dict(path=admitted_context.campaign_config_path,
                    sha256=admitted_context.campaign_config_sha256)
                or spec['deadline_monotonic_s'] != admitted_context.deadline_monotonic_s
                or spec['wave_id'] != launch.wave_id):
            raise ValueError('SHARD_SPEC_CONTEXT_MISMATCH')
    if spec['workload_kind'] == 'act_rollout':
        # A rollout is self-admitted (no unified service): the context's hash fields carry the run's own identity.
        identity = spec['rollout_identity']
        if (identity['scenes_sha256'] != admitted_context.manifest_sha256
                or identity['run_identity_sha256'] != admitted_context.collection_config_sha256
                or identity['policy_sha256'] != admitted_context.contact_policy_fingerprint
                or spec['deadline_monotonic_s'] != admitted_context.deadline_monotonic_s
                or spec['wave_id'] != launch.wave_id):
            raise ValueError('SHARD_SPEC_CONTEXT_MISMATCH')
    return spec


def check_runtime_ready(root, *, generation, process):
    """The instance's runtime-ready record names this generation and this process and its stack readiness bytes."""
    ready = read_document(root/'runtime-ready.json')
    expected = dict(schema_version=2, kind='ACT_SHARD_RUNTIME_READY', generation=generation,
        process_owner=asdict(process))
    if (set(ready) != set(expected)|{'readiness_sha256'}
            or any(ready[name] != value or type(ready[name]) is not type(value) for name, value in expected.items())
            or hashlib.sha256((root/'stack-readiness.json').read_bytes()).hexdigest() != ready['readiness_sha256']):
        raise ValueError('SHARD_RUNTIME_READINESS_INVALID')
    return ready


def read_instance_exit(root):
    """The instance's own exit record, or None when it is absent or not a closed, valid record."""
    try:
        record = read_document(root/'instance-exit.json')
        if (type(record) is not dict or set(record) != {'schema_version', 'kind', 'state', 'fault_reason', 'task',
                'cleanup_confirmed', 'cleanup_errors'} or type(record['schema_version']) is not int
                or record['schema_version'] != 1 or record['kind'] != 'ACT_SHARD_INSTANCE_EXIT'
                or record['fault_reason'] is not None and (type(record['fault_reason']) is not str
                    or not 0 < len(record['fault_reason']) <= 300)
                or type(record['cleanup_confirmed']) is not bool or type(record['cleanup_errors']) is not list
                or record['task'] is not None and type(record['task']) is not dict):
            return None
        return record
    except (OSError, ValueError, TypeError, KeyError):
        return None
