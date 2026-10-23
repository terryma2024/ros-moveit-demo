"""Catch false integrity acceptance, unsafe reads and unbounded allocations."""
import hashlib
import json
import os

import pytest

from head_run_audit_support import corpus, make_reader, reader_module, reseal, reference


def test_full_seal_is_independently_verified_without_model_bytes(tmp_path):
    reader = make_reader(tmp_path, [('CLOCK', {'sim_ns': 1})])
    reader.load()
    assert reader.integrity_status == 'PASS'
    assert len(list(reader.events())) == 1
    assert reader.readback()['unchanged'] is True


@pytest.mark.parametrize('missing', ['seal.json', 'completion.json', 'events.jsonl'])
def test_missing_original_is_incomplete_not_false_pass(tmp_path, missing):
    reader = make_reader(tmp_path)
    (reader.run_root / missing).unlink()
    reader.load()
    assert reader.integrity_status == 'INCOMPLETE'


def test_changed_original_under_unchanged_seal_fails(tmp_path):
    reader = make_reader(tmp_path)
    (reader.run_root / 'completion.json').write_text('{}\n')
    reader.load()
    assert reader.integrity_status == 'FAIL'


@pytest.mark.parametrize('payload', ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{'])
def test_sealed_invalid_json_is_failure(tmp_path, payload):
    reader = make_reader(tmp_path)
    (reader.run_root / 'completion.json').write_text(payload)
    reseal(reader.run_root)
    reader.load()
    assert reader.integrity_status == 'FAIL'


@pytest.mark.parametrize('sequence', [True, 0, 2])
def test_boolean_or_discontinuous_sequence_is_rejected(tmp_path, sequence):
    reader = make_reader(tmp_path, [('CLOCK', {})])
    event = json.loads((reader.run_root / 'events.jsonl').read_text())
    event['sequence'] = sequence
    (reader.run_root / 'events.jsonl').write_text(json.dumps(event) + '\n')
    reseal(reader.run_root); reader.load()
    assert reader.integrity_status == 'FAIL'


def test_null_record_schema_and_absent_owner_diagnostics_are_legal(tmp_path):
    reader = make_reader(tmp_path, [('CLOCK', {})]); reader.load()
    assert reader.integrity_status == 'PASS'


def test_input_replacement_after_read_is_detected(tmp_path):
    reader = make_reader(tmp_path); reader.load()
    p = reader.run_root / 'completion.json'
    same = p.read_bytes(); p.unlink(); p.write_bytes(same)
    assert reader.readback()['unchanged'] is False
    assert reader.integrity_status == 'INCOMPLETE'


def test_input_inventory_addition_is_detected(tmp_path):
    reader = make_reader(tmp_path); reader.load()
    (reader.run_root / 'new.txt').write_text('later')
    assert reader.readback()['unchanged'] is False


def test_stream_is_rechecked_and_not_loaded_as_whole_document(tmp_path, monkeypatch):
    reader = make_reader(tmp_path, [('CLOCK', {})] * 20); reader.load()
    assert len(list(reader.events())) == len(list(reader.events())) == 20
    monkeypatch.setattr(type(reader.run_root), 'read_bytes', lambda p: pytest.fail('whole file read'))
    assert len(list(reader.events())) == 20


@pytest.mark.parametrize('target', ['../escape', '/etc/passwd', 'artifacts/../completion.json'])
def test_run_relative_escape_is_never_read(tmp_path, target):
    reader = make_reader(tmp_path)
    p = reader.run_root / 'seal.json'; seal = json.loads(p.read_text())
    seal['files'].append({'path': target, 'size': 1, 'sha256': 'a' * 64})
    p.write_text(json.dumps(seal))
    with pytest.raises(reader_module().AuditToolError): reader.load()


def test_symlink_input_ref_is_not_followed(tmp_path):
    reader = make_reader(tmp_path)
    p = reader.execution_receipt
    real = p.with_name('real.json'); p.rename(real); p.symlink_to(real)
    with pytest.raises(reader_module().AuditToolError): reader.load()


def test_fifo_input_does_not_block(tmp_path):
    reader = make_reader(tmp_path); p = reader.execution_receipt
    p.unlink(); os.mkfifo(p)
    with pytest.raises(reader_module().AuditToolError): reader.load()


def test_external_parent_normalization_keeps_original_path(tmp_path):
    module = reader_module(); root, receipt, sha, _ = corpus(tmp_path)
    folder = tmp_path / 'spare'; folder.mkdir()
    original = folder / '..' / 'inputs' / 'receipt.json'
    reader = module.RunReader(root, original, sha, evidence_root=tmp_path); reader.load()
    assert reader.integrity_status == 'PASS'
    assert any(x['original_path'] == str(original) for x in reader.readback()['files'])


def test_line_limit_is_tool_failure_not_truncated_success(tmp_path, monkeypatch):
    reader = make_reader(tmp_path, [('CLOCK', {'large': 'x' * 500})])
    monkeypatch.setattr(reader_module(), 'MAX_EVENT_BYTES', 100)
    with pytest.raises(reader_module().AuditToolError): reader.load()


def test_symlink_run_root_is_rejected_before_enumeration(tmp_path):
    reader=make_reader(tmp_path)
    link=tmp_path/'linked-run';link.symlink_to(reader.run_root,target_is_directory=True)
    reader.run_root=link
    with pytest.raises(reader_module().AuditToolError):reader.load()


def test_writer_counts_must_match_actual_sealed_records(tmp_path):
    reader=make_reader(tmp_path,[('CLOCK',{})])
    path=reader.run_root/'seal.json';seal=json.loads(path.read_text())
    seal['counters']['event_count']=0;path.write_text(json.dumps(seal));reader.load()
    assert reader.integrity_status=='FAIL'


def test_manifest_generation_boolean_is_not_an_integer(tmp_path):
    reader=make_reader(tmp_path)
    path=reader.run_root/'manifest.json';document=json.loads(path.read_text())
    document['run']['generation']=True;path.write_text(json.dumps(document));reseal(reader.run_root)
    reader.load();assert reader.integrity_status=='FAIL'


def test_event_artifact_size_must_match_seal(tmp_path):
    reader=make_reader(tmp_path,[('CLOCK',{})]);root=reader.run_root
    (root/'artifacts').mkdir();artifact=root/'artifacts/frame.rgb';artifact.write_bytes(b'RGB')
    path=root/'events.jsonl';event=json.loads(path.read_text())
    event['artifact_refs']=[{'path':'artifacts/frame.rgb','sha256':hashlib.sha256(b'RGB').hexdigest(),'size':99}]
    path.write_text(json.dumps(event)+'\n');reseal(root)
    seal=json.loads((root/'seal.json').read_text());seal['counters']['artifact_count']=1
    (root/'seal.json').write_text(json.dumps(seal));reader.load()
    assert reader.integrity_status=='FAIL'


def test_yaml_duplicate_keys_are_not_silently_reinterpreted(tmp_path):
    reader=make_reader(tmp_path)
    yaml=tmp_path/'inputs/controller.yaml';yaml.write_text('joints: [neck_yaw_joint]\njoints: [other]\n')
    path=reader.run_root/'manifest.json';document=json.loads(path.read_text())
    document['refs']['controller_config']=reference(yaml);path.write_text(json.dumps(document));reseal(reader.run_root)
    reader.load();assert reader.integrity_status=='FAIL'


def test_yaml_alias_expansion_is_bounded_before_construction(tmp_path):
    reader=make_reader(tmp_path)
    yaml=tmp_path/'inputs/controller.yaml'
    lines=['a: &a [1, 2]']
    for n in range(1,4):
        previous='a' if n==1 else f'a{n-1}'
        lines.append(f'a{n}: &a{n} ['+', '.join(['*'+previous]*8)+']')
    yaml.write_text('\n'.join(lines)+'\n')
    path=reader.run_root/'manifest.json';document=json.loads(path.read_text())
    document['refs']['controller_config']=reference(yaml);path.write_text(json.dumps(document));reseal(reader.run_root)
    with pytest.raises(reader_module().AuditToolError):reader.load()


@pytest.mark.parametrize('boundary',['document','depth','events'])
def test_resource_limits_fail_closed(tmp_path,monkeypatch,boundary):
    reader=make_reader(tmp_path,[('CLOCK',{}),('CLOCK',{})])
    module=reader_module()
    if boundary=='document':monkeypatch.setattr(module,'MAX_DOCUMENT_BYTES',20)
    elif boundary=='events':monkeypatch.setattr(module,'MAX_EVENTS',1)
    else:monkeypatch.setattr(module,'MAX_DEPTH',1)
    with pytest.raises(module.AuditToolError):reader.load()


def test_unsealed_event_stream_is_hashed_and_read_back(tmp_path):
    reader=make_reader(tmp_path,[('CLOCK',{})])
    artifact=reader.run_root/'artifacts/frame.rgb';artifact.parent.mkdir();artifact.write_bytes(b'RGB')
    (reader.run_root/'seal.json').rename(reader.run_root.parent/'omitted-seal.json')
    reader.load()
    path=reader.run_root/'events.jsonl'
    assert str(path) in reader.files
    assert reader.files[str(artifact)]['sha256']==hashlib.sha256(b'RGB').hexdigest()
    path.write_text(path.read_text()+'\n')
    assert reader.readback()['unchanged'] is False
