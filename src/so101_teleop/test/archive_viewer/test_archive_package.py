import json
from archive_fixture import write_json
from test_archive_scan import client_for


def package_request(archive):
    client=client_for(archive)
    root=client.get('/api/archives/config').json()['roots'][0]['root_id']
    rows=client.get('/api/archives/packages',params=dict(root_id=root)).json()['packages']
    pid=next(r['package_id'] for r in rows if r['name']=='collection')
    return client,'/api/archives/packages/'+pid


def test_package_statistics_distinguish_collection_commit_and_seal(archive):
    client,url=package_request(archive)
    response=client.get(url)
    assert response.status_code==200
    data=response.json();s=data['statistics']
    assert s['planned']==4 and s['committed']==2
    assert s['committed_by_split']==dict(train=1,validation=1,offline_test=0)
    assert s['non_committed_by_outcome']==dict(FAULT=1,MISSING=1,INVALID=0)
    assert s['retry_rounds_run']==1 and s['recovered']==1
    assert s['recovered_by_round']=={'1':1}
    assert s['duration_rows']==dict(total=12,median=6)
    assert s['duration_seconds']==dict(total=1.2,median=0.6)
    assert s['episode_bytes']['total']>0
    assert data['identity']['source_commit']['value']=='source-commit'
    rows=client.get(url+'/episodes').json()['episodes']
    assert [r['scene_id'] for r in rows]==['frm-000','frm-001','frm-002','frm-003']
    assert rows[1]['recording_attempt_count']==2
    assert rows[1]['final_recording_round']==1
    assert rows[0]['collection_committed'] is True
    assert rows[2]['record_count'] is None


def test_episode_list_filters_searches_sorts_and_pages(archive):
    client,url=package_request(archive)
    assert client.get(url+'/episodes',params=dict(split='train',outcome='FAULT')).json()['total']==1
    assert client.get(url+'/episodes',params=dict(q='001')).json()['episodes'][0]['scene_id']=='frm-001'
    data=client.get(url+'/episodes',params=dict(sort='-record_count',offset=1,limit=1)).json()
    assert data['total']==4 and data['episodes'][0]['scene_id']=='frm-000'
    for sort in ['scene_id','split','collection_committed','outcome','reason','recording_attempt_count','final_recording_round','record_count','duration_s','bytes','teacher_result','qc_status']:
        assert client.get(url+'/episodes',params=dict(sort=sort)).status_code==200
    assert client.get(url+'/episodes',params=dict(sort='../../bad')).status_code==422
    assert client.get(url+'/episodes',params=dict(limit=201)).status_code==422


def test_schema_two_without_frozen_metadata_keeps_fault_rows(archive):
    (archive.package/'inputs/frozen/inputs-manifest.json').unlink()
    archive.index['schema_version']=2
    write_json(archive.package/'collection-index.json',archive.index);archive.seal()
    client,url=package_request(archive)
    assert client.get(url).status_code==200
    rows=client.get(url+'/episodes').json()['episodes']
    assert len(rows)==4 and rows[2]['outcome']=='FAULT'
    assert all(r['split'] is None for r in rows)


def test_corrupt_manifest_and_required_document_are_not_silently_accepted(archive):
    manifest=archive.package.with_name('collection.seal-manifest.jsonl')
    manifest.write_text(manifest.read_text()+'{}\n')
    client,url=package_request(archive)
    assert client.get(url).status_code==422
    archive.seal();(archive.package/'collection-index.json').write_text('{');archive.seal()
    client,url=package_request(archive)
    response=client.get(url)
    assert response.status_code==422
    assert 'collection-index.json' in response.json()['message']


def test_external_processing_output_is_refused(archive):
    archive.index['committed_episodes'][0]['collection_evidence']['processing_output']=str(archive.root/'outside')
    write_json(archive.package/'collection-index.json',archive.index);archive.seal()
    client,url=package_request(archive)
    assert client.get(url).status_code==409


def test_invalid_final_scene_is_counted_and_processing_retries_are_not_recordings(archive):
    archive.index['committed_episodes']=archive.index['committed_episodes'][:1]
    row=archive.campaign['scenes'][1]
    row['attempts']=[dict(outcome='INVALID',reason='QC_BAD',proc_attempt=2)]
    row['recording_round']=0;row['recording_attempts']=[dict(recording_round=0,attempts=row['attempts'])]
    archive.outputs['frm-001'].joinpath('processed-result.json').unlink()
    archive.campaign['retry']['decisions']=[]
    write_json(archive.package/'collection-index.json',archive.index)
    write_json(archive.package/'host/campaign-result.json',archive.campaign);archive.seal()
    client,url=package_request(archive);s=client.get(url).json()['statistics']
    assert s['non_committed_by_outcome']['INVALID']==1
    row=client.get(url+'/episodes',params=dict(q='001')).json()['episodes'][0]
    assert row['recording_attempt_count']==1 and row['outcome']=='INVALID'


def test_malformed_scene_object_returns_document_error(archive):
    archive.campaign['scenes']=[None]
    write_json(archive.package/'host/campaign-result.json',archive.campaign);archive.seal()
    client,url=package_request(archive)
    response=client.get(url)
    assert response.status_code==422
    assert response.json()['code']=='ARCHIVE_DOCUMENT_INVALID'


def test_package_cache_evicts_but_retained_snapshot_stays_readable(archive):
    from so101_teleop.archive_viewer.config import ArchiveConfig
    from so101_teleop.archive_viewer.scan import ArchiveStore
    extra=archive.root/'third';extra.mkdir();archive.seal(extra)
    store=ArchiveStore(ArchiveConfig((archive.root,)))
    root=store.config_view().roots[0].root_id
    packages=store.packages(root).packages
    ids={r.name:r.package_id for r in packages}
    first=store.package(ids['collection'])
    store.package(ids['supporting']);store.package(ids['third'])
    assert store.package(ids['collection']) is not first
    assert first.view().statistics.committed==2
    store.packages(root,True)
    assert store.package(ids['collection']) is not first


def test_bound_scene_sha_and_duplicate_rows_are_validated(archive):
    import hashlib
    frozen_path=archive.package/'inputs/frozen/inputs-manifest.json'
    frozen=json.loads(frozen_path.read_text())
    scene_path=archive.package/'inputs/frozen/scene_manifest/scenes.json'
    frozen['scene_manifest']['sha256']='0'*64
    write_json(frozen_path,frozen);archive.seal()
    client,url=package_request(archive)
    assert client.get(url).status_code==422
    frozen['scene_manifest']['sha256']=hashlib.sha256(scene_path.read_bytes()).hexdigest()
    write_json(frozen_path,frozen)
    archive.campaign['scenes'].append(archive.campaign['scenes'][0])
    write_json(archive.package/'host/campaign-result.json',archive.campaign);archive.seal()
    client,url=package_request(archive)
    assert client.get(url).status_code==422


def test_schema_two_fallback_uses_campaign_index_scene_ids(archive):
    (archive.package/'inputs/frozen/inputs-manifest.json').unlink()
    (archive.package/'host/campaign-result.json').unlink()
    archive.index['schema_version']=2
    write_json(archive.package/'collection-index.json',archive.index)
    write_json(archive.package/'campaign-index.json',dict(waves=[dict(scene_ids=['frm-000','frm-001','frm-002','frm-003'])]))
    archive.seal()
    client,url=package_request(archive)
    rows=client.get(url+'/episodes').json()['episodes']
    assert len(rows)==4
    assert rows[2]['outcome']=='MISSING'


def test_corrupt_nested_attempts_return_document_error(archive):
    archive.campaign['scenes'][0]['recording_attempts']=[None]
    write_json(archive.package/'host/campaign-result.json',archive.campaign);archive.seal()
    client,url=package_request(archive)
    assert client.get(url).status_code==422


def test_metadata_projection_does_not_open_records_frames_or_audit(archive,monkeypatch):
    from pathlib import Path
    original=Path.open
    def guarded(path,*args,**kwargs):
        assert path.name!='records.jsonl' and path.suffix!='.png' and 'audit' not in path.parts
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded)
    client,url=package_request(archive)
    assert client.get(url).status_code==200
