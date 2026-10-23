"""CLI tool rc is integrity/publication status, not a qualification decision."""
import importlib
import json
import sys

import pytest

from head_run_audit_support import corpus, reader_module


def cli():
    try:return importlib.import_module('so101_demo.cli.head_search_audit')
    except ModuleNotFoundError as error:pytest.fail(f'Audit CLI feature absent: {error}')


@pytest.mark.parametrize('change,expected',[('none',0),('missing-seal',2),('missing-file',2),('corrupt',1)])
def test_installed_contract_rc_matrix(tmp_path,monkeypatch,change,expected,capsys):
    root,receipt,sha,_=corpus(tmp_path,[('FAULT',{'reason':'intended'})])
    if change=='missing-seal':(root/'seal.json').unlink()
    if change=='missing-file':(root/'completion.json').unlink()
    if change=='corrupt':(root/'completion.json').write_text('{}')
    monkeypatch.setattr(reader_module(),'DEFAULT_EVIDENCE_ROOT',tmp_path)
    output=tmp_path/'reviews/audit'
    rc=cli().main(['--run-root',str(root),'--execution-receipt',str(receipt),
        '--execution-receipt-sha256',sha,'--output-root',str(output)])
    assert rc==expected
    assert json.loads((output/'audit-completion.json').read_text())['status']=='COMPLETE'


def test_invalid_arguments_are_rc3_without_report(capsys):
    assert cli().main([])==3


def test_help_is_zero_without_auditing(capsys):
    assert cli().main(['--help'])==0


def test_rc0_does_not_conceal_execution_failure(tmp_path,monkeypatch,capsys):
    root,receipt,sha,manifest=corpus(tmp_path,[('HEAD_ACTION_SDK_RETURNED',{'goal_uuid':'a'})]*2)
    reader=reader_module();monkeypatch.setattr(reader,'DEFAULT_EVIDENCE_ROOT',tmp_path)
    monkeypatch.setitem(reader.PROFILES,(manifest['source_manifest']['sha256'],
        manifest['freeze_receipt']['sha256']),'postflight-domain-key')
    rc=cli().main(['--run-root',str(root),'--execution-receipt',str(receipt),
        '--execution-receipt-sha256',sha,'--output-root',str(tmp_path/'reviews/audit')])
    assert rc==0
    assert 'execution_checks=FAIL' in capsys.readouterr().out


def test_in_process_full_cli_never_calls_runtime_or_online_resources(tmp_path,monkeypatch):
    root,receipt,sha,_=corpus(tmp_path,[('FAULT',{})])
    monkeypatch.setattr(reader_module(),'DEFAULT_EVIDENCE_ROOT',tmp_path)
    import builtins, socket, subprocess
    real_import=builtins.__import__
    def guarded(name,*args,**kwargs):
        if name.split('.')[0] in {'rclpy','torch','ultralytics','mujoco'} or 'head_execution_provider' in name:
            pytest.fail('audit imported runtime: '+name)
        return real_import(name,*args,**kwargs)
    def prohibited(*args,**kwargs):pytest.fail('audit accessed online resource')
    monkeypatch.setattr(builtins,'__import__',guarded)
    monkeypatch.setattr(socket,'socket',prohibited);monkeypatch.setattr(subprocess,'Popen',prohibited)
    assert cli().main(['--run-root',str(root),'--execution-receipt',str(receipt),
        '--execution-receipt-sha256',sha,'--output-root',str(tmp_path/'reviews/audit')])==0


def test_runtime_import_firewall_in_fresh_interpreter(tmp_path):
    import os,subprocess
    script='''import builtins,sys
real=builtins.__import__
def guard(name,*a,**kw):
 if name.split('.')[0] in {'rclpy','torch','ultralytics','mujoco','subprocess','socket'}: raise RuntimeError('runtime import: '+name)
 return real(name,*a,**kw)
builtins.__import__=guard
from so101_demo.cli.head_search_audit import main
assert main(['--help'])==0
assert not any(n.split('.')[0] in {'rclpy','torch','ultralytics','mujoco'} for n in sys.modules)
'''
    result=subprocess.run([sys.executable,'-c',script],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),
        capture_output=True,text=True)
    assert result.returncode==0,result.stderr
