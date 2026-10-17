import json
from test_archive_package import package_request


def file_url(archive, name):
    client, url = package_request(archive)
    episode = url+'/episodes/frm-000'
    response = client.get(episode)
    assert response.status_code == 200
    entry = next(f for f in response.json()['files'] if f['name'].endswith(name))
    assert '/' not in entry['file_id']
    return client, episode+'/files/'+entry['file_id']


def test_json_size_limit_and_unknown_id(archive):
    client, url = file_url(archive, 'seal.json')
    assert client.get(url).json()['content']['committed'] is False
    assert client.get(url.rsplit('/',1)[0]+'/unknown').status_code == 404
    path = archive.outputs['frm-000']/'large.json'
    path.write_text(json.dumps('x'*(2*1024*1024)));archive.seal()
    client,url = file_url(archive, 'large.json')
    assert client.get(url).status_code == 413


def test_jsonl_utf8_offsets_eof_and_invalid_boundaries(archive):
    audit = archive.outputs['frm-000']/'episode/audit/events.jsonl'
    lines = [json.dumps({'text': '中文', 'row': i}, ensure_ascii=False) for i in range(8)]
    audit.write_text('\n'.join(lines),encoding='utf8');archive.seal()
    client, url = file_url(archive, 'events.jsonl')
    offset = 0; received = []
    while True:
        response = client.get(url,params={'offset':offset,'limit':3})
        assert response.status_code == 200
        page = response.json();received.extend(page['lines'])
        if page['eof']: break
        assert page['next_offset'] > offset
        offset = page['next_offset']
    assert received == lines
    assert client.get(url,params={'offset':audit.stat().st_size}).json()['eof']
    for args in ({'offset':1},{'offset':-1},{'offset':audit.stat().st_size+1},{'limit':501}):
        assert client.get(url,params=args).status_code == 422


def test_jsonl_oversized_line_and_bounded_reads(archive, monkeypatch):
    from pathlib import Path
    path = archive.outputs['frm-000']/'episode/audit/events.jsonl'
    path.write_bytes(b'x'*(2*1024*1024+1));archive.seal()
    client, url = file_url(archive, 'events.jsonl')
    original = Path.read_text
    def guarded(p,*args,**kwargs):
        assert p != path
        return original(p,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',guarded)
    assert client.get(url).status_code == 413


def test_qc_path_outside_package_is_refused(archive):
    path = archive.outputs['frm-000']/'processed-result.json'
    doc = json.loads(path.read_text());doc['qc_report_path']='/etc/passwd'
    path.write_text(json.dumps(doc));archive.seal()
    client, url = package_request(archive)
    assert client.get(url+'/episodes/frm-000').status_code == 409
