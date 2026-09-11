"""Container argument and admission behavior without launching Docker."""

import os
from pathlib import Path
import subprocess
import pytest


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
        grounded_root=grounded, gpu_groups=[44, 109], uid=os.getuid(), gid=os.getgid())
    assert f'{root}/ipc:/runtime:rw' in argv
    assert f'{root}/workers:/inputs:ro' in argv
    assert argv[argv.index('--user') + 1] == f'{os.getuid()}:{os.getgid()}'
    assert [argv[i + 1] for i, item in enumerate(argv) if item == '--group-add'] == ['44', '109']
    for flag, value in [('--network', 'none'), ('--ipc', 'private'),
                        ('--security-opt', 'no-new-privileges'), ('--gpus', 'all')]:
        assert argv[argv.index(flag) + 1] == value
    assert '--read-only' in argv
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
                grounded_root=grounded, gpu_groups=[44], uid=os.getuid(), gid=os.getgid())
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
