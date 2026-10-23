"""The independent verifier of a container-collection qualification report: it recomputes the run, it does not read the claim.

World, REAL and CONTROLLED parts are those of test_parallel_qualification_report.py (see its docstring and
`collection_qualification_world.py`). The verifier itself is real; the only test double inside it is the same controlled
frozen-inputs reader and the store-published QC report, because a real formal frozen set needs a formal episode audit that no
fixture can produce. The synthetic rule files are TEST-ONLY and their pass counts are not approved values.
"""

import copy
import json
import os

import pytest

from collection_qualification_world import build_world, install_controlled_qc, ref
from so101_demo.act import collection_qualification_recompute as recompute
from so101_demo.act.parallel_qualification_verifier import (
    build_collection_qualification_report, verify_collection_qualification,
)
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from test_parallel_qualification_report import controlled_frozen_reader

REFUSED = 'COLLECTION_QUALIFICATION_'


@pytest.fixture
def world(tmp_path, monkeypatch):
    install_controlled_qc(monkeypatch)
    monkeypatch.setattr(recompute, 'read_frozen_inputs', controlled_frozen_reader)
    (tmp_path/'world').mkdir()
    return build_world(tmp_path/'world')


def qualified(world):
    return build_collection_qualification_report(world.run, contract=world.contract_path)


def verify(world, **kwargs):
    kwargs.setdefault('registered_root', world.root)
    kwargs.setdefault('expected_identity', copy.deepcopy(world.contract['controlled_identity']))
    return verify_collection_qualification(world.report_path, **kwargs)


def test_verifier_returns_proof_for_a_qualified_run(world):
    qualified(world)
    proof = verify(world)
    assert proof == dict(kind='ACT_COLLECTION_QUALIFICATION_READBACK', schema_version=1, status='PASS',
        report_sha256=ref(world.report_path)['sha256'], qualification_run_id='gate-run', run_root=str(world.run),
        controlled_identity=world.contract['controlled_identity'], contract_sha256=ref(world.contract_path)['sha256'],
        scene_manifest_sha256=ref(world.scene_file)['sha256'], functional_manifest_sha256=ref(world.functional)['sha256'],
        formal_split_manifest_sha256=ref(world.formal)['sha256'], task_count=40)
    # no external identity: only that comparison is skipped
    assert verify(world, expected_identity=None) == proof


def test_self_declared_qualification_is_not_evidence(world):
    (world.run/'host/wave-1-verified.json').unlink()
    qualified(world)
    document = json.loads(world.report_path.read_bytes())
    assert document['status'] == 'NOT_QUALIFIED'
    forged = dict(document, status='QUALIFIED', reasons=[])
    world.report_path.write_bytes(canonical_json(forged)+b'\n')
    with pytest.raises(ValueError, match=REFUSED+'RECOMPUTE_MISMATCH'):
        verify(world)


def test_a_qualified_report_whose_run_has_a_missing_original_is_refused(world):
    qualified(world)
    (world.run/'host/wave-0-verified.json').unlink()
    with pytest.raises(ValueError, match=REFUSED+'RECOMPUTE_MISMATCH'):
        verify(world)


def never_read(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('the run was read before the report passed the closed check')
    monkeypatch.setattr(recompute, 'recompute', fail)
    monkeypatch.setattr(recompute, 'campaign_contract_path', fail)


def test_passed_legacy_receipt_is_refused_before_anything_else_is_read(world, monkeypatch):
    world.report_path.write_text(json.dumps(dict(status='PASSED', worker_count=8, qualification_run_id='gate-run')))
    never_read(monkeypatch)
    with pytest.raises(ValueError, match=REFUSED+'REPORT_INVALID'):
        verify(world)


def test_pick_place_live_fourteen_case_document_is_refused(world, monkeypatch):
    # the shape the pick-place live qualification wrote: QUALIFIED, eight workers and a live campaign block
    digest = '1'*64
    world.report_path.write_text(json.dumps(dict(status='QUALIFIED', worker_count=8, live_campaign=dict(
        case_root=str(world.run), campaign_result_sha256=digest, preparation_receipt_sha256=digest, journal_sha256=[digest]*14))))
    never_read(monkeypatch)
    with pytest.raises(ValueError, match=REFUSED+'REPORT_INVALID'):
        verify(world)


@pytest.mark.parametrize('edit', ['extra_field', 'missing_field', 'wrong_kind', 'status_word', 'worker_count', 'not_json', 'array'])
def test_report_outside_the_closed_form_is_refused(world, monkeypatch, edit):
    qualified(world)
    document = json.loads(world.report_path.read_bytes())
    if edit == 'extra_field':
        document['live_campaign'] = {}
    elif edit == 'missing_field':
        document.pop('resource_logs')
    elif edit == 'wrong_kind':
        document['kind'] = 'ACT_PARALLEL_COLLECTION_GATE'
    elif edit == 'status_word':
        document['status'] = 'PASSED'
    elif edit == 'worker_count':
        document['worker_count'] = 6
    payload = {'not_json': b'{"status": ', 'array': b'[]'}.get(edit) or canonical_json(document)+b'\n'
    world.report_path.write_bytes(payload)
    never_read(monkeypatch)
    with pytest.raises(ValueError, match=REFUSED+'REPORT_INVALID'):
        verify(world)


def test_tampered_report_number_is_refused(world):
    qualified(world)
    document = json.loads(world.report_path.read_bytes())
    document['quality']['qc_valid_rate']['result']['passed'] = 40
    world.report_path.write_bytes(canonical_json(document)+b'\n')
    with pytest.raises(ValueError, match=REFUSED+'RECOMPUTE_MISMATCH'):
        verify(world)
    world.report_path.write_bytes(world.report_path.read_bytes()+b' ')
    with pytest.raises(ValueError, match=REFUSED+'RECOMPUTE_MISMATCH'):
        verify(world)


def sealed(world, wave=0, worker='w00'):
    return next((world.owners[f'wave-{wave}', worker]/'output/tasks').glob('*/attempts/*/*/sealed'))


def flip(path):
    path.write_bytes(path.read_bytes().replace(b'}', b' }', 1))


def tamper(world, what):
    if what == 'task_result':
        flip(next((world.owners['wave-0', 'w00']/'output/tasks').glob('*/task-result.json')))
    elif what == 'sealed_result':
        flip(sealed(world)/'result.json')
    elif what == 'sealed_qc_report':
        flip(sealed(world)/'qc-report.json')
    elif what == 'topic_loss_document':
        flip(sealed(world)/'topic-loss.json')
    elif what == 'teacher_manifest':
        path = sealed(world)/'dynamic/dynamic-execute-manifest.json'
        path.write_bytes(path.read_bytes().replace(b'"PASS"', b'"FAIL"'))
    elif what == 'collected_record':
        flip(next((world.run/'host/wave-0/task-journal').glob('*/collected.json')))
    elif what == 'wave_record':
        flip(world.run/'host/wave-1-verified.json')
    elif what == 'frozen_index':
        flip(world.run/'collection-index.json')
    elif what == 'campaign_result':
        flip(world.run/'host/campaign-result.json')
    elif what == 'contract':
        flip(world.contract_path)
    elif what == 'rule_file':
        flip(next(world.inputs.glob('test-only-not-approved-qc_valid_rate.json')))
    elif what == 'scene_list':
        flip(world.scene_file)
    elif what == 'campaign_config':
        flip(world.campaign_path)
    elif what == 'shard_spec':
        world.edit_json(world.run/'shard-wave-0-w00-g1.json', lambda value: value.update(worker_id='w07'))
    elif what == 'registry_launch':
        import sqlite3
        with sqlite3.connect(world.registry_path) as connection:
            connection.execute("UPDATE launches SET exit_json=NULL WHERE launch_id='wave-1-w07-g2'")
    elif what == 'teacher_ready':
        world.edit_json(world.run/'host/teacher-ready.json', lambda value: value.update(ready=False))
    elif what == 'campaign_cleanup':
        world.edit_json(world.run/'host/campaign-cleanup.json', lambda value: value.update(terminated=False))
    elif what == 'frozen_inputs':
        world.edit_json(world.run/'inputs/frozen/controlled-frozen-binding.json',
                        lambda value: value['roles']['runtime_config'].update(sha256='9'*64))
    elif what == 'scope':
        flip(world.scopes[world.scenes[5]])
    elif what == 'journal_failed':
        task = next(iter((world.run/'host/wave-0/task-journal').iterdir()))
        (task/'failed.json').write_text('{}')


@pytest.mark.parametrize('what', ['task_result', 'sealed_result', 'sealed_qc_report', 'topic_loss_document', 'teacher_manifest',
    'collected_record', 'wave_record', 'frozen_index', 'campaign_result', 'contract', 'rule_file', 'scene_list', 'campaign_config',
    'shard_spec', 'registry_launch', 'teacher_ready', 'campaign_cleanup', 'frozen_inputs', 'scope', 'journal_failed'])
def test_tampered_original_is_refused(world, what):
    qualified(world)
    assert verify(world)['status'] == 'PASS'
    tamper(world, what)
    with pytest.raises(ValueError, match=REFUSED):
        verify(world)


def test_wave_spliced_from_another_run_is_refused(world, tmp_path, monkeypatch):
    qualified(world)
    other_base = tmp_path/'other'
    other_base.mkdir()
    other = build_world(other_base, tag='run-2')
    (world.run/'host/wave-1-verified.json').write_bytes((other.run/'host/wave-1-verified.json').read_bytes())
    with pytest.raises(ValueError, match=REFUSED+'RECOMPUTE_MISMATCH'):
        verify(world)


def test_report_of_another_run_is_not_this_runs_proof(world, tmp_path):
    qualified(world)
    other_base = tmp_path/'other'
    other_base.mkdir()
    other = build_world(other_base, tag='run-2')
    qualified(other)
    # the other run's report copied over this run's: its contract, paths and hashes are not what this run's originals recompute to
    world.report_path.write_bytes(other.report_path.read_bytes())
    with pytest.raises(ValueError, match=REFUSED+'RECOMPUTE_MISMATCH'):
        verify(world)


def test_report_path_escape_or_symlink_is_refused(world, tmp_path):
    qualified(world)
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify_collection_qualification(world.run/'host/../host/qualification-report.json', registered_root=world.root,
                                        expected_identity=None)
    alias = world.root/'alias'
    alias.symlink_to(world.run, target_is_directory=True)
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify_collection_qualification(alias/'host/qualification-report.json', registered_root=world.root,
                                        expected_identity=None)
    link = world.run/'host/report-link.json'
    link.symlink_to(world.report_path)
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify_collection_qualification(link, registered_root=world.root, expected_identity=None)
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify_collection_qualification(world.report_path.relative_to(world.root.parent), registered_root=world.root,
                                        expected_identity=None)
    root_alias = tmp_path/'root-alias'
    root_alias.symlink_to(world.root, target_is_directory=True)
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify_collection_qualification(world.report_path, registered_root=root_alias, expected_identity=None)


def test_report_outside_registered_root_is_refused(world, tmp_path):
    qualified(world)
    elsewhere = tmp_path/'elsewhere'
    elsewhere.mkdir()
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify(world, registered_root=elsewhere)
    # a report nested one level deeper than a run of the root is not a run of the root
    nested = world.root/'group'
    nested.mkdir()
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify(world, registered_root=nested)
    other_layout = json.loads((world.run/'.campaign-layout.json').read_bytes())
    other_layout['root'] = str(elsewhere)
    (world.run/'.campaign-layout.json').write_bytes(json.dumps(other_layout).encode())
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify(world)


def test_renamed_run_directory_is_refused(world):
    qualified(world)
    renamed = world.root/'run-renamed'
    os.rename(world.run, renamed)
    with pytest.raises(ValueError, match=REFUSED+'PATH_INVALID'):
        verify_collection_qualification(renamed/'host/qualification-report.json', registered_root=world.root,
                                        expected_identity=None)


def test_not_qualified_report_is_refused(world):
    (world.run/'host/dispatch-fault.json').write_bytes(canonical_json(dict(type='ValueError', reason='controlled'))+b'\n')
    qualified(world)
    assert json.loads(world.report_path.read_bytes())['status'] == 'NOT_QUALIFIED'
    with pytest.raises(ValueError, match=REFUSED+'NOT_QUALIFIED'):
        verify(world)


@pytest.mark.parametrize('key', ['source_sha256', 'runtime_config_sha256', 'collection_config_sha256',
                                 'contact_policy_fingerprint', 'image_source_install', 'gpu_uuid'])
def test_identity_mismatch_is_refused(world, key):
    qualified(world)
    expected = copy.deepcopy(world.contract['controlled_identity'])
    if key == 'image_source_install':
        expected[key]['shard']['install_sha256'] = '9'*64
    elif key == 'gpu_uuid':
        expected[key] = 'GPU-00000000-0000-0000-0000-000000000000'
    else:
        expected[key] = '9'*64
    with pytest.raises(ValueError, match=REFUSED+'IDENTITY_MISMATCH'):
        verify(world, expected_identity=expected)


def test_verifier_writes_nothing(world):
    qualified(world)
    before = world.snapshot()
    stat_before = {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in world.run.rglob('*') if path.is_file()}
    verify(world)
    with pytest.raises(ValueError, match=REFUSED):
        verify(world, expected_identity=dict(world.contract['controlled_identity'], gpu_uuid='GPU-00000000-0000-0000-0000-000000000000'))
    assert world.snapshot() == before
    assert {path: (path.stat().st_mtime_ns, path.stat().st_size) for path in world.run.rglob('*') if path.is_file()} == stat_before
