"""Owned file and lossless original metadata; no ROS or motion authority."""
import hashlib
import json
import threading
import pytest

try:
    from so101_demo.adapters.act.head_original_journal import HeadOriginalJournal
except ModuleNotFoundError:
    class HeadOriginalJournal:
        def __init__(self,path,*,fault_callback):self.path=path
        def __call__(self,*args):pass
        def close(self,timeout_s):return {}


def test_owned_original_journal_preserves_all_sources_and_original_receipts(tmp_path):
    path=tmp_path/'originals.jsonl';faults=[]
    writer=HeadOriginalJournal(path,fault_callback=faults.append)
    record=dict(source_ns=1_000_000_000,wall_s=10.,valid=True,k=[415.,0.,1.])
    for kind in ('JOINT','IMAGE','INFO','CLOCK'):writer(kind,record)
    record['k'][0]=-1.;receipt=writer.close(timeout_s=1.)
    assert not faults and receipt['count']==4 and receipt['thread_exited'] is True
    assert receipt['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    assert [row['kind'] for row in rows]==['JOINT','IMAGE','INFO','CLOCK']
    assert all(row['record']['wall_s']==10. and row['record']['k'][0]==415. for row in rows)
    with pytest.raises(PermissionError):writer('CLOCK',record)


def test_journal_never_overwrites_an_existing_run(tmp_path):
    path=tmp_path/'originals.jsonl';path.write_text('retained\n')
    with pytest.raises(FileExistsError):HeadOriginalJournal(path,fault_callback=lambda *a:None)
    assert path.read_text()=='retained\n'


def test_encoder_failure_faults_and_cannot_produce_a_sealed_receipt(tmp_path):
    path=tmp_path/'originals.jsonl';faults=[];latched=threading.Event()
    def fault(reason):faults.append(reason);latched.set()
    writer=HeadOriginalJournal(path,fault_callback=fault)
    writer('JOINT',dict(source_ns=1,wall_s=10.,raw_positions=[float('nan')],valid=False))
    assert latched.wait(timeout=1.)
    with pytest.raises(RuntimeError):writer.close(timeout_s=1.)
    assert faults==['HEAD_ORIGINAL_JOURNAL_FAILED']
