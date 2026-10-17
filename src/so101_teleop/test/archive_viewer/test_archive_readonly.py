"""Retained synthetic non-root read-only proof for all archive HTTP operations."""
import builtins
import hashlib
import os
from pathlib import Path
from test_archive_package import package_request


def tree_snapshot(root):
    result={}
    for p in [root,*sorted(root.rglob('*'))]:
        st=p.lstat()
        result[str(p.relative_to(root))]=(st.st_mode,st.st_size,st.st_mtime_ns,
            os.readlink(p) if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
    return result


def test_every_endpoint_is_readonly_as_nonroot(archive,monkeypatch):
    assert os.geteuid()!=0, 'read-only proof must run without root privileges'
    client,url=package_request(archive)
    assert client.get(url+'/episodes/frm-000').status_code==200
    for p in [*archive.root.rglob('*'),archive.root]:
        p.chmod(p.stat().st_mode & ~0o222)
    before=tree_snapshot(archive.root)
    original_open=builtins.open;original_path_open=Path.open;original_os_open=os.open
    def protected(p):
        return isinstance(p,(str,bytes,os.PathLike)) and Path(os.fsdecode(p)).absolute().is_relative_to(archive.root)
    def guarded_open(p,mode='r',*args,**kwargs):
        assert not protected(p) or not any(c in str(mode) for c in 'wax+')
        return original_open(p,mode,*args,**kwargs)
    def guarded_path_open(p,mode='r',*args,**kwargs):
        assert not protected(p) or not any(c in str(mode) for c in 'wax+')
        return original_path_open(p,mode,*args,**kwargs)
    def guarded_os_open(p,flags,*args,**kwargs):
        assert not protected(p) or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)==0
        return original_os_open(p,flags,*args,**kwargs)
    monkeypatch.setattr(builtins,'open',guarded_open);monkeypatch.setattr(Path,'open',guarded_path_open);monkeypatch.setattr(os,'open',guarded_os_open)
    for name in ('rename','unlink','mkdir','chmod','rmdir','replace'):
        original=getattr(Path,name)
        def guarded(p,*args,_original=original,**kwargs):
            assert not protected(p)
            return _original(p,*args,**kwargs)
        monkeypatch.setattr(Path,name,guarded)
    rid=client.get('/api/archives/config').json()['roots'][0]['root_id']
    assert client.get('/api/archives/packages',params=dict(root_id=rid,refresh=True)).status_code==200
    assert client.get(url).status_code==200
    assert client.get(url+'/episodes',params=dict(outcome='FAULT')).status_code==200
    for scene,count in [('frm-000',5),('frm-001',7),('frm-002',0)]:
        ep=url+'/episodes/'+scene
        detail=client.get(ep).json()
        assert client.get(ep+'/series').status_code==200
        for row in ({0,count-1} if count else set()):
            for camera in ('head','wrist'): assert client.get(ep+f'/frames/{row}/{camera}').status_code==200
        for entry in detail['files']:
            endpoint=ep+'/files/'+entry['file_id']
            if entry['name'].endswith('.json'): assert client.get(endpoint).status_code==200
            if entry['name'].endswith('.jsonl'):
                page=client.get(endpoint,params=dict(limit=1)).json()
                assert client.get(endpoint,params=dict(offset=page['next_offset'],limit=1)).status_code==200
        for suffix in ('/frames/-1/head','/frames/0/eye','/files/unknown'):
            assert client.get(ep+suffix).status_code in (404,422)
    assert client.post(url+'/verify').status_code==200
    client.delete(url+'/verify');client.app.state.archives.verifier.join()
    assert client.post(url+'/verify').status_code==200
    client.app.state.archives.verifier.join()
    assert client.get(url+'/verify').json()['state']=='complete'
    assert client.get(url+'/episodes/unknown').status_code==404
    assert tree_snapshot(archive.root)==before
