from fastapi.testclient import TestClient
from so101_teleop.unified.app import create_unified_app,schema_services
from archive_fixture import write_json


def client_for(archive):
    return TestClient(create_unified_app(schema_services(),archive_roots=(archive.root,)))


def test_scan_classifies_and_registers_packages(archive):
    client=client_for(archive)
    config=client.get('/api/archives/config').json()
    assert config['enabled'] is True
    assert '/' not in config['roots'][0]['root_id']
    root_id=config['roots'][0]['root_id']
    response=client.get('/api/archives/packages',params=dict(root_id=root_id))
    assert response.status_code==200
    rows={r['name']:r for r in response.json()['packages']}
    assert set(rows)=={'collection','supporting'}
    assert rows['collection']['kind']=='collection'
    assert rows['collection']['registered'] is True
    assert rows['supporting']['kind']=='supporting'
    assert rows['supporting']['registered'] is False
    assert rows['collection']['bytes']>0
    assert client.get('/api/archives/packages',params=dict(root_id='unknown')).status_code==404


def test_scan_stops_at_seals_and_skips_directory_links(archive):
    nested=archive.package/'nested';nested.mkdir()
    write_json(nested/'SEALED.json',dict(kind='SEALED_EVIDENCE_ROOT'))
    (archive.root/'loop').symlink_to(archive.root,target_is_directory=True)
    (archive.root/'ordinary').mkdir()
    client=client_for(archive);rid=client.get('/api/archives/config').json()['roots'][0]['root_id']
    data=client.get('/api/archives/packages',params=dict(root_id=rid,refresh=True)).json()
    assert sorted(r['name'] for r in data['packages'])==['collection','supporting']


def test_missing_registry_and_invalid_marker_are_safe(archive):
    (archive.root/'SEALED-ROOTS.json').unlink()
    (archive.supporting/'SEALED.json').write_text('{')
    write_json(archive.supporting/'nested/SEALED.json',dict(kind='SEALED_EVIDENCE_ROOT'))
    client=client_for(archive);rid=client.get('/api/archives/config').json()['roots'][0]['root_id']
    data=client.get('/api/archives/packages',params=dict(root_id=rid)).json()
    assert [r['name'] for r in data['packages']]==['collection']
    assert data['warnings']
