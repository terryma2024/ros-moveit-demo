"""Independent file-v1 fixture; never uses the production writer or auditor."""
import hashlib
import json
from pathlib import Path

RUN = {'run_id': 'sample', 'epoch': 'epoch', 'session_id': 'session', 'generation': 7}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    return reference(path)


def reference(path):
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def reseal(root):
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name != 'seal.json':
            ref = reference(path)
            files.append({'path': str(path.relative_to(root)), 'size': ref['bytes'],
                          'sha256': ref['sha256']})
    count = len((root / 'events.jsonl').read_text().splitlines())
    return write_json(root / 'seal.json', {'file_protocol_version': 1, 'files': files,
        'event_count': count, 'artifact_count': sum(x['path'].startswith('artifacts/') for x in files),
        'counters': {'event_count': count, 'artifact_count': 0, 'drop_count': 0, 'fault_count': 0}})


def corpus(tmp_path, records=()):
    root = tmp_path / 'runs' / 'sample'; root.mkdir(parents=True)
    refs_root = tmp_path / 'inputs'
    refs = {
        'development_config': write_json(refs_root / 'config.json', {'camera': {'frame_id': 'camera',
            'width': 640, 'height': 480}, 'values': {'center_deadband_px': 3.0,
            'stop_velocity_rad_s': .04, 'lock_valid_neck_rad': [-6.28, 6.28],
            'min_confidence': .25, 'min_area_px2': 64.0, 'min_bbox_aspect': .5},
            'motion': {'goal_tolerance_rad': .05, 'settle_velocity_rad_s': .05}}),
        'local_policy': write_json(refs_root / 'policy.json', {'search_timeout_s': 30.0,
            'stop_confirmation_timeout_s': 1.0, 'native_close_timeout_s': .05,
            'fault_reaction_limit_s': .25, 'perception_max_age_s': .15,
            'perception_job_timeout_s': 1.0, 'max_reobservations_per_stop': 3,
            'max_reobservations_total': 12}),
    }
    source = write_json(refs_root / 'source.json', {'files': []})
    freeze = write_json(refs_root / 'freeze.json', {'schema_version': 1})
    refs['weights'] = {'path': str(refs_root / 'unread-model.pt'), 'sha256': 'b' * 64}
    policy_sha = 'c' * 64
    manifest = {'file_protocol_version': 1, 'schema_version': 1, 'run': RUN,
        'source_manifest': source, 'freeze_receipt': freeze, 'refs': refs,
        'simulation_policy_sha256': policy_sha, 'evidence_root': str(tmp_path)}
    write_json(root / 'manifest.json', manifest)
    events = []
    for n, (kind, record) in enumerate(records, 1):
        events.append({'schema_version': 1, 'record_schema_version': None, 'run': RUN,
            'source_sha256': source['sha256'], 'config_sha256': refs['development_config']['sha256'],
            'model_sha256': 'b' * 64, 'owner': {}, 'sequence': n, 'kind': kind,
            'record': record, 'source_stamp_ns': None, 'observed_mono_ns': n * 1000000,
            'occurrence_mono_ns': n * 1000000, 'artifact_refs': []})
    (root / 'events.jsonl').write_text(''.join(json.dumps(e, sort_keys=True) + '\n' for e in events))
    write_json(root / 'completion.json', {'business_return_code': 1, 'execution': 'FAILED',
        'complete_composition': True, 'failure': 'intended fixture fault'})
    reseal(root)
    launcher = write_json(refs_root / 'launcher.json', {'actual_os_return_code': 1,
        'owner': {'pid': 1234, 'started_ticks': 10}, 'ros_domain_id': '200', 'partition': 'session'})
    receipt = write_json(refs_root / 'receipt.json', {'run_id': 'sample', 'refs': {'launcher': launcher}})
    return root, Path(receipt['path']), receipt['sha256'], manifest


def reader_module():
    import importlib
    import pytest
    try:
        return importlib.import_module('so101_demo.act.head_run_reader')
    except ModuleNotFoundError as error:
        pytest.fail(f'Offline reader feature is absent: {error}')


def make_reader(tmp_path, records=(), monkeypatch=None):
    module = reader_module()
    root, receipt, sha, manifest = corpus(tmp_path, records)
    if monkeypatch is not None:
        monkeypatch.setitem(module.PROFILES, (manifest['source_manifest']['sha256'],
            manifest['freeze_receipt']['sha256']), 'postflight-domain-key')
    return module.RunReader(root, receipt, sha, evidence_root=tmp_path)
