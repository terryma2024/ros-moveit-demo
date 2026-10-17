import json
import pytest
from archive_fixture import PNG
from test_archive_package import package_request


def test_detail_signals_cameras_and_fault(archive):
    client, url = package_request(archive)
    episode = url + '/episodes/frm-000'
    response = client.get(episode)
    assert response.status_code == 200
    detail = response.json()
    assert detail['scene']['seed'] == 200
    assert detail['collection_committed'] is True and detail['seal']['committed'] is False
    assert detail['processed_result']['export_eligible'] and detail['qc_summary']['status'] == 'PASS'
    assert detail['frame_count'] == 5 and detail['files']
    assert len(client.get(url+'/episodes/frm-001').json()['attempts']) == 4
    series = client.get(episode+'/series').json()
    assert len(series['points'][0]['action']) == 6 and len(series['points'][0]['state']) == 8
    assert series['row_times_s'][4] == pytest.approx(36.6)
    assert 'audit' not in json.dumps(series)
    for camera in ('head', 'wrist'):
        frame = client.get(episode+'/frames/4/'+camera)
        assert frame.status_code == 200 and frame.content == PNG
        assert frame.headers['content-type'] == 'image/png'
    fault = client.get(url+'/episodes/frm-002').json()
    assert fault['frame_count'] == 0 and fault['attempts'][0]['reason'] == 'not recorded'
    assert client.get(url+'/episodes/unknown').status_code == 404


def test_long_series_retains_endpoints_and_empty_records(archive):
    path = archive.outputs['frm-000']/'episode/records.jsonl'
    row = json.loads(path.read_text().splitlines()[0])
    with path.open('w') as stream:
        for i in range(5001):
            row['observation']['sim_time_s'] = i/10
            stream.write(json.dumps(row)+'\n')
    archive.seal()
    client, url = package_request(archive)
    data = client.get(url+'/episodes/frm-000/series').json()
    assert len(data['points']) <= 2000 and len(data['row_times_s']) == 5001
    assert [data['points'][i]['row'] for i in (0, -1)] == [0, 5000]
    path.write_text('');archive.seal()
    client, url = package_request(archive)
    assert client.get(url+'/episodes/frm-000/series').json()['points'] == []


@pytest.mark.parametrize('suffix,code', [('frames/-1/head',422),('frames/5/head',404),('frames/0/eye',422)])
def test_bad_frame_parameters(archive, suffix, code):
    client, url = package_request(archive)
    assert client.get(url+'/episodes/frm-000/'+suffix).status_code == code


def test_frame_revalidates_path_and_manifest_each_request(archive):
    client, url = package_request(archive)
    episode = url+'/episodes/frm-000'
    assert client.get(episode+'/frames/0/head').status_code == 200
    frame = archive.outputs['frm-000']/'episode/frames/000000-head.png'
    frame.unlink();frame.symlink_to(archive.root/'SEALED-ROOTS.json')
    assert client.get(episode+'/frames/0/head').status_code == 409
    assert client.get(episode+'/frames/1/head').status_code == 200
    (frame.parent/'000001-head.png').unlink()
    assert client.get(episode+'/frames/1/head').status_code == 404


@pytest.mark.parametrize('value', ['../seal.json', '/etc/passwd', 'frames/unlisted.png'])
def test_frame_names_cannot_escape_or_bypass_manifest(archive, value):
    records = archive.outputs['frm-000']/'episode/records.jsonl'
    row = json.loads(records.read_text().splitlines()[0]);row['observation']['head_png'] = value
    records.write_text(json.dumps(row)+'\n');archive.seal()
    client, url = package_request(archive)
    assert client.get(url+'/episodes/frm-000/frames/0/head').status_code == 409


def test_records_cache_bounded_and_retained_episode_survives_eviction(archive):
    client, url = package_request(archive)
    store = client.app.state.archives
    package = store.package(url.rsplit('/',1)[-1])
    first = package.episode('frm-000')
    first.series();package.episode('frm-001').series();package.episode('frm-002').series()
    assert len(package._records) <= 2
    assert first.frame(4,'head').is_file()


def test_state_dimensions_are_preserved_and_records_reads_are_bounded(archive, monkeypatch):
    from pathlib import Path
    path = archive.outputs['frm-000']/'episode/records.jsonl'
    row = json.loads(path.read_text().splitlines()[0]);row['observation']['state'] = [1,2,3]
    path.write_text(json.dumps(row)+'\n');archive.seal()
    original = Path.open
    class Bounded:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self,*args): self.stream.close()
        def read(self, size=-1):
            assert size >= 0
            return self.stream.read(size)
        def readline(self, size=-1):
            assert size >= 0
            return self.stream.readline(size)
    def guarded(p,*args,**kwargs):
        stream = original(p,*args,**kwargs)
        return Bounded(stream) if p == path else stream
    monkeypatch.setattr(Path,'open',guarded)
    client, url = package_request(archive)
    assert client.get(url+'/episodes/frm-000/series').json()['points'][0]['state'] == [1,2,3]


def test_frame_directory_cannot_redirect_to_another_episode(archive):
    frames = archive.outputs['frm-000']/'episode/frames'
    old = frames.with_name('old-frames');frames.rename(old)
    frames.symlink_to(archive.outputs['frm-001']/'episode/frames',target_is_directory=True)
    client, url = package_request(archive)
    assert client.get(url+'/episodes/frm-000/frames/0/head').status_code == 409
