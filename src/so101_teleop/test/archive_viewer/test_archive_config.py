"""Disabled routing must not expose data or fall through to the SPA."""
from fastapi.testclient import TestClient
from so101_teleop.unified.app import create_unified_app, schema_services


def test_no_root_disables_every_archive_operation():
    client=TestClient(create_unified_app(schema_services()))
    for method,path in [('GET','config'),('GET','packages'),('GET','packages/unknown'),('POST','packages/unknown/verify'),('DELETE','packages/unknown/verify'),('GET','unknown')]:
        response=client.request(method,'/api/archives/'+path)
        assert response.status_code==404
        assert response.json().get('code')=='ARCHIVES_DISABLED'


def test_invalid_roots_and_bind_are_refused(tmp_path):
    import pytest
    for root in [tmp_path/'missing',__import__('pathlib').Path('relative')]:
        with pytest.raises(ValueError):create_unified_app(schema_services(),archive_roots=(root,))
    with pytest.raises(ValueError,match='BIND_ADDRESS_UNSAFE'):
        create_unified_app(schema_services(),bind_address='0.0.0.0')


def test_cli_accepts_repeatable_roots():
    from so101_teleop.unified.main import build_parser
    args=build_parser().parse_args(['--archive-root','/first','--archive-root','/second'])
    assert [str(p) for p in args.archive_root]==['/first','/second']


def test_archive_reader_imports_no_robot_runtime():
    import os,subprocess,sys
    script="import sys; import so101_teleop.archive_viewer.api; assert 'rclpy' not in sys.modules; assert 'docker' not in sys.modules"
    result=subprocess.run([sys.executable,'-c',script],env=dict(os.environ),capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_unknown_archive_api_never_falls_back_to_spa(archive,tmp_path):
    bundle=tmp_path/'bundle';(bundle/'assets').mkdir(parents=True);(bundle/'index.html').write_text('<html>spa</html>')
    client=TestClient(create_unified_app(schema_services(),archive_roots=(archive.root,),static_dir=bundle))
    response=client.get('/api/archives/unknown')
    assert response.status_code==404
    assert 'application/json' in response.headers['content-type']
    assert client.get('/archives').text=='<html>spa</html>'
