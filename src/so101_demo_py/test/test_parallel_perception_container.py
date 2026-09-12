"""Container argument and admission behavior without launching Docker."""

import os
from pathlib import Path
import subprocess
import pytest


@pytest.mark.parametrize('mutation', ['none', 'bytes', 'new_file', 'generated'])
def test_actual_copied_source_is_verified_before_install(tmp_path, mutation):
    import hashlib
    import shutil
    from so101_demo.cli import parallel_perception_broker as cli
    package = tmp_path / 'host'
    (package / 'docker/parallel-perception').mkdir(parents=True)
    (package / 'docker/parallel-perception/Dockerfile').write_text('FROM pinned\n')
    (package / 'source.py').write_text('original\n')
    expected = {'source_sha256': cli.source_hash(package),
                'dockerfile_sha256': hashlib.sha256(b'FROM pinned\n').hexdigest(),
                'lock_sha256': hashlib.sha256(('\n'.join(cli.PINS) + '\n').encode()).hexdigest()}
    copied = tmp_path / 'copied'
    shutil.copytree(package, copied)
    if mutation == 'bytes':
        (copied / 'source.py').write_text('drift during COPY\n')
    if mutation == 'new_file':
        (copied / 'surprise.py').write_text('drift\n')
    if mutation == 'generated':
        for name in ('__pycache__', 'so101_demo.egg-info'):
            (copied / name).mkdir()
            (copied / name / 'generated').write_text('not source')
    if mutation in {'bytes', 'new_file'}:
        with pytest.raises(ValueError, match='SOURCE_PROVENANCE_MISMATCH'):
            cli.verify_source(copied, expected)
    else:
        actual = cli.verify_source(copied, expected)
        assert actual == {**expected, 'verified_source_sha256': expected['source_sha256']}


@pytest.mark.parametrize('mutation', ['none', 'source', 'verified', 'noncanonical'])
def test_image_readback_checks_verified_content_not_only_labels(tmp_path, monkeypatch, mutation):
    import io
    import json
    import tarfile
    from so101_demo.cli import parallel_perception_broker as cli
    expected = dict(dockerfile_sha256='a' * 64, lock_sha256='b' * 64, source_sha256='c' * 64)
    verified = {**expected, 'verified_source_sha256': expected['source_sha256']}
    if mutation == 'source':
        verified['source_sha256'] = 'd' * 64
    if mutation == 'verified':
        verified['verified_source_sha256'] = 'd' * 64
    payload = cli.canonical_json(verified)
    if mutation == 'noncanonical':
        payload = json.dumps(verified, indent=2).encode()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as tar:
        entry = tarfile.TarInfo('parallel-provenance.json')
        entry.size = len(payload)
        tar.addfile(entry, io.BytesIO(payload))
    calls = []
    image_id, container_id = 'sha256:' + 'e' * 64, 'f' * 64

    def check_output(command, **kwargs):
        calls.append(command)
        if command[:3] == ['docker', 'image', 'inspect']:
            return json.dumps([{'Id': image_id, 'Config': {'Labels': {
                'so101.parallel.' + key: value for key, value in expected.items()}}}])
        if command[:2] == ['docker', 'create']:
            assert image_id in command and '--network' in command and 'none' in command
            return container_id + '\n'
        if command[:2] == ['docker', 'cp']:
            assert command[2] == container_id + ':/opt/parallel-provenance.json'
            return archive.getvalue()
        raise AssertionError(command)

    monkeypatch.setattr(cli.subprocess, 'check_output', check_output)
    monkeypatch.setattr(cli.subprocess, 'run', lambda command, **kw: calls.append(command))
    if mutation == 'none':
        assert cli.image_record('tag') == {'image_id': image_id, **verified}
    else:
        with pytest.raises(ValueError, match='IMAGE_VERIFIED_PROVENANCE'):
            cli.image_record('tag')
    assert ['docker', 'rm', container_id] in calls
    assert not any(command[:2] in (['docker', 'start'], ['docker', 'run']) for command in calls)


@pytest.mark.parametrize('name', ['single-plan', 'live-small'])
def test_batch_specific_mounts_identity_and_gpu_groups(tmp_path, name):
    from so101_demo.cli.parallel_perception_broker import container_run_argv
    root = tmp_path / name
    root.mkdir(mode=0o700)
    (root / 'workers').mkdir(mode=0o700)
    yolo, grounded = tmp_path / 'yolo', tmp_path / 'grounded'
    yolo.mkdir(); grounded.mkdir()
    (yolo / 'best.pt').write_bytes(b'model')
    argv = container_run_argv(
        root, image_id='sha256:' + 'b' * 64, yolo_weights=yolo / 'best.pt',
        grounded_root=grounded, gpu_groups=[44, 109], uid=os.getuid(), gid=os.getgid(),
        batch_id='batch-1', broker_generation=1)
    assert f'{root}/ipc:/runtime:rw' in argv
    assert f'{root}/workers:/inputs:ro' in argv
    assert argv[argv.index('--user') + 1] == f'{os.getuid()}:{os.getgid()}'
    assert [argv[i + 1] for i, item in enumerate(argv) if item == '--group-add'] == ['44', '109']
    for flag, value in [('--network', 'none'), ('--ipc', 'private'),
                        ('--security-opt', 'no-new-privileges'), ('--gpus', 'all')]:
        assert argv[argv.index(flag) + 1] == value
    assert '--read-only' in argv
    assert argv[argv.index('--cidfile') + 1] == str(root / 'ipc/container.cid')
    assert 'com.so101.batch-id=batch-1' in argv
    assert 'com.so101.broker-generation=1' in argv
    assert (root / 'ipc').stat().st_mode & 0o777 == 0o700
    assert '/runtime/perception.sock' in argv
    assert '--no-cpu-fallback' in argv


@pytest.mark.parametrize('bad', ['relative', 'symlink', 'ipc_mode', 'root_user', 'no_gpu', 'image'])
def test_unknown_or_unsafe_container_inputs_fail_closed(tmp_path, bad):
    from so101_demo.cli.parallel_perception_broker import container_run_argv
    root = tmp_path / 'batch'
    root.mkdir(mode=0o700)
    (root / 'workers').mkdir(mode=0o700)
    (root / 'ipc').mkdir(mode=0o700)
    weights = tmp_path / 'best.pt'; weights.write_bytes(b'model')
    grounded = tmp_path / 'grounded'; grounded.mkdir()
    args = dict(image_id='sha256:' + 'b' * 64, yolo_weights=weights,
                grounded_root=grounded, gpu_groups=[44], uid=os.getuid(), gid=os.getgid(),
                batch_id='batch-1', broker_generation=1)
    if bad == 'relative': root = Path('batch')
    if bad == 'symlink':
        alias = tmp_path / 'alias'; alias.symlink_to(root); root = alias
    if bad == 'ipc_mode': (root / 'ipc').chmod(0o777)
    if bad == 'root_user': args['uid'] = 0
    if bad == 'no_gpu': args['gpu_groups'] = []
    if bad == 'image': args['image_id'] = 'mutable-tag'
    with pytest.raises(ValueError):
        container_run_argv(root, **args)


def test_wrapper_executes_argument_validation_before_docker():
    script = Path(__file__).parents[3] / 'scripts/parallel-perception-container.sh'
    result = subprocess.run([str(script), 'run'], capture_output=True, text=True)
    assert result.returncode == 2
    assert '--output' in result.stderr


def test_container_refuses_image_drift_before_running(tmp_path, monkeypatch):
    from so101_demo.cli import parallel_perception_broker as cli
    root = Path(__file__).parents[3].resolve()
    calls = []
    monkeypatch.setattr(cli, 'image_record', lambda image: {
        'image_id': 'sha256:' + 'c' * 64, 'dockerfile_sha256': 'a' * 64,
        'lock_sha256': 'a' * 64, 'source_sha256': 'a' * 64})
    monkeypatch.setattr(cli.subprocess, 'run', lambda *a, **kw: calls.append(a))
    with pytest.raises(ValueError, match='DRIFT'):
        cli.container_main(['--repository-root', str(root), 'run', '--batch-root', str(tmp_path),
                            '--image-id', 'sha256:' + 'b' * 64,
                            '--yolo-weights', str(tmp_path / 'best.pt'),
                            '--grounded-root', str(tmp_path), '--output', str(tmp_path / 'run.json')])
    assert calls == []


def test_failed_receipt_readback_keeps_runtime_unhealthy(tmp_path, monkeypatch):
    from so101_demo.runtime.parallel_perception_runtime import write_receipt
    ipc = tmp_path / 'ipc'; ipc.mkdir(mode=0o700)
    monkeypatch.setattr(Path, 'read_bytes', lambda path: b'corrupted')
    with pytest.raises(OSError, match='READBACK'):
        write_receipt(ipc / 'ready.json', {'ready': True})
    assert (ipc / 'ready.json').stat().st_mode & 0o777 == 0o600
