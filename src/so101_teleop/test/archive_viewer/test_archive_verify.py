import threading
import pytest
from fastapi import HTTPException
from test_archive_package import package_request


def manager_for(archive):
    client, url = package_request(archive)
    assert client.get(url).status_code == 200
    return client, url, getattr(client.app.state.archives, 'verifier', None)


def test_verify_clean_mismatch_missing_and_manifest_identity(archive):
    client,url,manager = manager_for(archive)
    response = client.post(url+'/verify')
    assert response.status_code == 200
    manager.join()
    data = client.get(url+'/verify').json()
    assert data['state'] == 'complete' and data['checked'] == data['total'] > 0
    assert data['mismatch_count'] == data['missing_count'] == 0
    path = archive.outputs['frm-000']/'episode/frames/000000-head.png'
    path.write_bytes(b'changed')
    path.with_name('000000-wrist.png').unlink()
    assert client.post(url+'/verify').status_code == 200
    manager.join();data = client.get(url+'/verify').json()
    assert data['mismatch_count'] == data['missing_count'] == 1
    archive.package.with_name('collection.seal-manifest.jsonl').write_text('{}\n')
    assert client.post(url+'/verify').status_code == 200
    manager.join()
    assert client.get(url+'/verify').json()['state'] == 'failed'


def test_single_worker_cancel_shutdown_and_snapshot_retention(archive, monkeypatch):
    client,url,manager = manager_for(archive)
    assert manager is not None
    entered = threading.Event();release = threading.Event()
    original = manager._hash_file
    def blocked(path,cancel):
        entered.set();assert release.wait(5)
        return original(path,cancel)
    monkeypatch.setattr(manager,'_hash_file',blocked)
    client.post(url+'/verify');assert entered.wait(5)
    assert client.post(url+'/verify').status_code == 409
    assert client.delete(url+'/verify').json()['state'] == 'cancelling'
    assert client.post(url+'/verify').status_code == 409
    # Refresh/eviction and concurrent frame reading must not invalidate held snapshot.
    client.get('/api/archives/packages',params=dict(root_id=client.get('/api/archives/config').json()['roots'][0]['root_id'],refresh=True))
    assert client.get(url+'/episodes/frm-000/frames/0/head').status_code == 200
    assert client.get('/api/archives/packages/other/verify').json()['state'] == 'idle'
    release.set();manager.join()
    assert client.get(url+'/verify').json()['state'] == 'cancelled'
    assert client.post(url+'/verify').status_code == 200
    manager.close()
    assert not manager._thread.is_alive()


def test_issues_bounded_and_symlink_never_reads_target(archive,monkeypatch):
    for i in range(105):
        (archive.package/f'bad-{i}.json').write_text('{}')
    archive.seal()
    client,url,manager = manager_for(archive)
    assert manager is not None
    for i in range(105): (archive.package/f'bad-{i}.json').write_text('bad')
    path=archive.outputs['frm-000']/'episode/frames/000000-head.png'
    path.unlink();path.symlink_to(archive.root/'SEALED-ROOTS.json')
    from pathlib import Path
    original=Path.open
    def guarded(p,*args,**kwargs):
        assert p != archive.root/'SEALED-ROOTS.json'
        return original(p,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded)
    client.post(url+'/verify');manager.join();data=client.get(url+'/verify').json()
    assert data['state']=='complete' and data['truncated'] and len(data['issues'])==100
    assert data['mismatch_count']==106


def test_app_shutdown_reaps_own_thread(archive):
    client,url,manager=manager_for(archive)
    assert manager is not None
    with client:
        client.post(url+'/verify')
    assert not manager._thread.is_alive()


def test_large_file_hash_cancels_between_bounded_chunks(archive,monkeypatch):
    client,url,manager=manager_for(archive)
    assert manager is not None
    path=archive.package/'large.bin';path.write_bytes(b'x'*(3*1024*1024))
    reads=[];original=__import__('os').fdopen
    class Stream:
        def __init__(self,stream): self.stream=stream
        def __enter__(self): return self
        def __exit__(self,*args): self.stream.close()
        def fileno(self): return self.stream.fileno()
        def read(self,size):
            reads.append(size)
            result=self.stream.read(size);cancel.set()
            return result
    cancel=threading.Event()
    monkeypatch.setattr('os.fdopen',lambda fd,*args,**kwargs:Stream(original(fd,*args,**kwargs)))
    assert manager._hash_file(path,cancel) is None
    assert reads==[1024*1024]


def test_verify_exceptions_are_terminal_not_stuck_running(archive,monkeypatch):
    client,url,manager=manager_for(archive)
    assert manager is not None
    def broken(*args): raise RuntimeError('injected failure')
    monkeypatch.setattr(manager,'_hash_file',broken)
    client.post(url+'/verify');manager.join()
    assert client.get(url+'/verify').json()['state']=='failed'


def test_parent_link_replacement_before_hash_is_refused(archive,monkeypatch):
    client,url,manager=manager_for(archive)
    assert manager is not None
    parent=archive.outputs['frm-000']/'episode/frames'
    outside=archive.root/'external-frames';outside.mkdir()
    for p in parent.iterdir(): (outside/p.name).write_bytes(p.read_bytes())
    original=manager._hash_file;changed=[]
    def replacing(path,cancel):
        if path.parent==parent and not changed:
            parent.rename(parent.with_name('saved-frames'));parent.symlink_to(outside,target_is_directory=True);changed.append(True)
        return original(path,cancel)
    monkeypatch.setattr(manager,'_hash_file',replacing)
    client.post(url+'/verify');manager.join()
    data=client.get(url+'/verify').json()
    assert data['mismatch_count']>=10
