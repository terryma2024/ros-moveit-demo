"""Report publication must not turn semantic failure into success or alter input."""
import importlib
import json
import hashlib
import os

import pytest

from head_run_audit_support import make_reader
from test_act_head_run_audit import audit


def module():
    try:return importlib.import_module('so101_demo.act.head_run_audit_report')
    except ModuleNotFoundError as error:pytest.fail(f'Report feature absent: {error}')


def test_atomic_completion_names_exact_report_bytes(tmp_path, monkeypatch):
    reader=make_reader(tmp_path,[('FAULT',{'reason':'intended'})],monkeypatch)
    result=audit(reader);output=tmp_path/'reviews/audit'
    module().publish_report(reader,result,output)
    marker=json.loads((output/'audit-completion.json').read_text())
    assert marker['status']=='COMPLETE'
    assert {x['path'] for x in marker['files']}=={'review.json','review.md','metrics.json','input-readback.json'}
    for ref in marker['files']:
        raw=(output/ref['path']).read_bytes()
        assert len(raw)==ref['size'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
    assert json.loads((output/'review.json').read_text())['report']['status']=='COMPLETE'
    assert 'execution_checks' in (output/'review.md').read_text()


def test_semantic_failure_is_prominent_in_json_markdown_and_summary(tmp_path, monkeypatch):
    reader=make_reader(tmp_path,[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':'same'})]*2,monkeypatch)
    result=audit(reader);module().publish_report(reader,result,tmp_path/'reviews/audit')
    report=json.loads((tmp_path/'reviews/audit/review.json').read_text())
    assert report['integrity']['status']=='PASS' and report['execution_checks']['status']=='FAIL'
    assert 'execution_checks=FAIL' in module().summary(report)
    assert 'execution_checks=FAIL' in (tmp_path/'reviews/audit/review.md').read_text()


@pytest.mark.parametrize('where',['run','input','existing'])
def test_output_collision_leaves_all_input_bytes_unchanged(tmp_path, monkeypatch, where):
    reader=make_reader(tmp_path,[('FAULT',{})],monkeypatch);result=audit(reader)
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    output={'run':reader.run_root/'audit','input':tmp_path/'inputs/audit','existing':tmp_path/'reviews'}[where]
    if where=='existing':output.mkdir()
    with pytest.raises(Exception):module().publish_report(reader,result,output)
    assert all(__import__('pathlib').Path(p).read_bytes()==raw for p,raw in before.items())
    assert not (output/'audit-completion.json').exists()


def test_directory_symlink_cannot_redirect_output(tmp_path, monkeypatch):
    reader=make_reader(tmp_path);result=audit(reader)
    (tmp_path/'redirect').symlink_to(reader.run_root,target_is_directory=True)
    with pytest.raises(Exception):module().publish_report(reader,result,tmp_path/'redirect/audit')
    assert not (reader.run_root/'audit').exists()


def test_fsync_failure_never_leaves_valid_completion(tmp_path, monkeypatch):
    reader=make_reader(tmp_path);result=audit(reader)
    def fail(descriptor):raise OSError('injected fsync error')
    monkeypatch.setattr(os,'fsync',fail)
    with pytest.raises(Exception):module().publish_report(reader,result,tmp_path/'reviews/audit')
    assert not (tmp_path/'reviews/audit/audit-completion.json').exists()


def test_changed_input_cannot_support_semantic_pass(tmp_path, monkeypatch):
    reader=make_reader(tmp_path,[('FAULT',{'reason':'intended'})],monkeypatch);result=audit(reader)
    path=reader.run_root/'events.jsonl';path.write_text(path.read_text()+'\n')
    module().publish_report(reader,result,tmp_path/'reviews/audit')
    report=json.loads((tmp_path/'reviews/audit/review.json').read_text())
    assert report['integrity']['status']=='INCOMPLETE'
    assert report['execution_checks']['status']=='UNKNOWN'
    assert report['search']['outcome']=='UNKNOWN'


def test_tainted_config_only_invalidates_dependent_rules(tmp_path,monkeypatch):
    from test_act_head_run_audit import observation_records
    reader=make_reader(tmp_path,observation_records(),monkeypatch)
    config=tmp_path/'inputs/config.json';config.write_text(config.read_text()+' ')
    result=audit(reader)
    module().publish_report(reader,result,tmp_path/'reviews/audit')
    assert result['integrity']['status']=='FAIL'
    assert result['coverage']['rules']['HFA-008']['verdict']=='UNKNOWN'
    assert result['coverage']['rules']['HFA-002']['verdict']=='HOLDS'


def test_last_marker_directory_fsync_failure_retains_unconfirmed_bytes(tmp_path,monkeypatch):
    from pathlib import Path
    reader=make_reader(tmp_path);result=audit(reader);output=tmp_path/'reviews/audit'
    real_fsync=os.fsync
    def fail_last(descriptor):
        if (output/'audit-completion.json').exists():
            raise OSError('last directory fsync failed')
        return real_fsync(descriptor)
    monkeypatch.setattr(os,'fsync',fail_last)
    with pytest.raises(OSError):module().publish_report(reader,result,output)
    assert not (output/'audit-completion.json').exists()
    assert (output/'audit-completion.unconfirmed.json').is_file()
    assert result['report']['status']=='NOT_COMPLETED'


def test_tainted_threshold_cannot_invent_semantic_violation(tmp_path,monkeypatch):
    from test_act_head_run_audit import observation_records
    records=observation_records(center=321)
    reader=make_reader(tmp_path,records,monkeypatch)
    config=tmp_path/'inputs/config.json';document=json.loads(config.read_text())
    document['values']['center_deadband_px']=.1;config.write_text(json.dumps(document))
    result=audit(reader);module().publish_report(reader,result,tmp_path/'reviews/audit')
    assert result['integrity']['status']=='FAIL'
    assert result['coverage']['rules']['HFA-008']['verdict']=='UNKNOWN'
    assert result['execution_checks']['status']=='UNKNOWN'


def test_tainted_completion_cannot_invent_declared_outcome_violation(tmp_path,monkeypatch):
    reader=make_reader(tmp_path,[('FAULT',{'reason':'intended'})],monkeypatch)
    path=reader.run_root/'completion.json';document=json.loads(path.read_text())
    document['execution']='SUCCEEDED';path.write_text(json.dumps(document))
    result=audit(reader);module().publish_report(reader,result,tmp_path/'reviews/audit')
    assert result['integrity']['status']=='FAIL'
    assert result['coverage']['rules']['HFA-011']['verdict']=='UNKNOWN'


def test_auditor_freeze_is_protected_from_output(tmp_path,monkeypatch):
    report_module=module();freeze=tmp_path/'auditor-freeze'
    installed_module=freeze/'install/package/lib/python/so101_demo/act/head_run_audit_report.py'
    installed_module.parent.mkdir(parents=True);installed_module.write_text('# installed audit module\n')
    monkeypatch.setattr(report_module,'__file__',str(installed_module))
    reader=make_reader(tmp_path);result=audit(reader)
    output=freeze/'reviews/run/audit'
    with pytest.raises(Exception):report_module.publish_report(reader,result,output)
    assert not output.exists()
