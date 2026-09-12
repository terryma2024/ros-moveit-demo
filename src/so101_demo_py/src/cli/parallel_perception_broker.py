"""Frozen CUDA container launcher and transport-injected model service entry."""

import argparse
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import time

from so101_demo.adapters.perception.errors import (
    DeterministicModelResultError, ModelRuntimeInfrastructureError,
)

from so101_demo.runtime.parallel_perception_runtime import (
    GROUNDED_SHA, IMAGE_TAG, PINS, YOLO_ID, YOLO_SHA,
    ParallelPerceptionRuntime, canonical_json, checked_path, frozen_options,
    normalize_batch, write_receipt,
)


def broker_argv():
    return ['--endpoint', '/runtime/perception.sock', '--input-root', '/inputs',
            '--ready-receipt', '/runtime/ready.json',
            '--runtime-spec', '/runtime/broker-spec.json',
            '--yolo-weights', '/models/yolo/best.pt',
            '--yolo-weights-sha256', YOLO_SHA, '--yolo-model-id', YOLO_ID, '--yolo-imgsz', '640',
            '--grounded-root', '/models/grounded', '--grounded-manifest-sha256', GROUNDED_SHA,
            '--device', 'cuda', '--no-cpu-fallback', '--grounding-box-threshold', '0.35',
            '--grounding-text-threshold', '0.25', '--grounding-duplicate-iou', '0.85',
            '--grounding-max-candidates', '16', '--sam-mask-quality-threshold', '0.75',
            '--sam-min-mask-pixels', '64', '--sam-max-mask-area-ratio', '0.5']


def container_run_argv(batch_root, *, image_id, yolo_weights, grounded_root,
                       gpu_groups, uid, gid, batch_id, broker_generation,
                       runtime_root=None,
                       input_root=None, path_checker=checked_path):
    if type(uid) is not int or uid <= 0 or uid != os.getuid() or gid != os.getgid():
        raise ValueError('HOST_NONROOT_IDENTITY_REQUIRED')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('IMMUTABLE_IMAGE_ID_REQUIRED')
    if not isinstance(batch_id, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', batch_id) is None:
        raise ValueError('BATCH_ID_REQUIRED')
    if type(broker_generation) is not int or broker_generation <= 0:
        raise ValueError('BROKER_GENERATION_REQUIRED')
    if not gpu_groups or any(type(group) is not int or group < 0 for group in gpu_groups):
        raise ValueError('GPU_GROUPS_REQUIRED')
    root = path_checker(batch_root, owner=(uid, gid), directory=True)
    inputs = path_checker(
        root / 'workers' if input_root is None else Path(input_root),
        owner=(uid, gid), directory=True,
    )
    ipc = root / 'ipc' if runtime_root is None else Path(runtime_root)
    if runtime_root is None and not ipc.exists() and not ipc.is_symlink():
        ipc.mkdir(mode=0o700)
    path_checker(ipc, owner=(uid, gid), mode=0o700, directory=True)
    if ipc.parent != root / 'ipc' and ipc != root / 'ipc':
        raise ValueError('RUNTIME_ROOT_OUTSIDE_BATCH_IPC')
    for name in ('ready.json', 'perception.sock', 'container.cid'):
        if (ipc / name).exists() or (ipc / name).is_symlink():
            raise ValueError('EXISTING_RUNTIME_ENDPOINT')
    yolo_weights = path_checker(yolo_weights)
    grounded_root = path_checker(grounded_root, directory=True)
    argv = ['docker', 'run', '--rm', '--init', '--cidfile', str(ipc / 'container.cid'),
            '--label', f'com.so101.batch-id={batch_id}',
            '--label', f'com.so101.broker-generation={broker_generation}',
            '--gpus', 'all', '--network', 'none', '--ipc', 'private',
            '--read-only', '--security-opt', 'no-new-privileges', '--user', f'{uid}:{gid}',
            '--tmpfs', f'/tmp:rw,nosuid,nodev,mode=0700,uid={uid},gid={gid}']
    for group in sorted(set(gpu_groups)):
        argv.extend(['--group-add', str(group)])
    for mount in (f'{ipc}:/runtime:rw', f'{inputs}:/inputs:ro',
                  f'{yolo_weights}:/models/yolo/best.pt:ro', f'{grounded_root}:/models/grounded:ro'):
        argv.extend(['--volume', mount])
    argv.extend(['--env', f'PARALLEL_IMAGE_ID={image_id}', image_id, *broker_argv()])
    return argv


def gpu_groups():
    nodes = sorted(Path('/dev').glob('nvidia*'))
    devices = []
    for path in nodes:
        if path.is_symlink():
            raise ValueError('GPU_SYMLINK')
        children = sorted(path.iterdir()) if path.is_dir() else [path]
        for child in children:
            info = child.lstat()
            if not stat.S_ISCHR(info.st_mode):
                raise ValueError('GPU_DEVICE_TYPE')
            devices.append(info.st_gid)
    if not devices:
        raise ValueError('GPU_DEVICE_REQUIRED')
    return sorted(set(devices))


def source_hash(package):
    """Hash sorted relative POSIX path + NUL + bytes, excluding Python artifacts.

    This exact function runs on the host and copied image tree before install.
    Installation uses a separate temporary copy, leaving this tree unchanged.
    """
    digest = hashlib.sha256()
    for path in sorted(package.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and not any(
                part.endswith('.egg-info') for part in path.parts) and path.suffix != '.pyc':
            digest.update(path.relative_to(package).as_posix().encode() + b'\0')
            digest.update(path.read_bytes())
    return digest.hexdigest()


def verify_source(package, expected):
    actual = {'source_sha256': source_hash(package),
              'dockerfile_sha256': hashlib.sha256(
                  (package / 'docker/parallel-perception/Dockerfile').read_bytes()).hexdigest(),
              'lock_sha256': hashlib.sha256(('\n'.join(PINS) + '\n').encode()).hexdigest()}
    if any(expected.get(name) != value for name, value in actual.items()):
        raise ValueError('SOURCE_PROVENANCE_MISMATCH')
    return {**actual, 'verified_source_sha256': actual['source_sha256']}


def image_record(image):
    record = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], text=True))[0]
    image_id = record['Id']
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('IMAGE_ID')
    labels = record['Config']['Labels']
    expected = {name: labels['so101.parallel.' + name]
                for name in ('dockerfile_sha256', 'lock_sha256', 'source_sha256')}
    # Read a build-verified file from the immutable image, never execute it.
    container_id = subprocess.check_output(
        ['docker', 'create', '--read-only', '--network', 'none', '--entrypoint', '/bin/true',
         image_id], text=True).strip()
    if not re.fullmatch(r'[0-9a-f]{64}', container_id):
        raise ValueError('IMAGE_READBACK_CONTAINER_ID')
    try:
        archive = subprocess.check_output(
            ['docker', 'cp', container_id + ':/opt/parallel-provenance.json', '-'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            entries = tar.getmembers()
            if (len(entries) != 1 or entries[0].name != 'parallel-provenance.json'
                    or not entries[0].isfile() or entries[0].size > 4096):
                raise ValueError('IMAGE_VERIFIED_PROVENANCE_ARCHIVE')
            payload = tar.extractfile(entries[0]).read()
        verified = json.loads(payload)
        if (canonical_json(verified) != payload or verified != {
                **expected, 'verified_source_sha256': expected['source_sha256']}):
            raise ValueError('IMAGE_VERIFIED_PROVENANCE_MISMATCH')
        return {'image_id': image_id, **verified}
    finally:
        subprocess.run(['docker', 'rm', container_id], check=True, capture_output=True)


def container_main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository-root', type=Path, required=True)
    parser.add_argument('operation', choices=['build', 'run', 'smoke'])
    parser.add_argument('--image', default=IMAGE_TAG, choices=[IMAGE_TAG])
    parser.add_argument('--batch-root', type=Path)
    parser.add_argument('--image-id')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--yolo-weights', type=Path)
    parser.add_argument('--grounded-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    repo = checked_path(args.repository_root, directory=True)
    package = repo / 'src/so101_demo_py'
    dockerfile = package / 'docker/parallel-perception/Dockerfile'
    hashes = {'dockerfile_sha256': hashlib.sha256(dockerfile.read_bytes()).hexdigest(),
              'lock_sha256': hashlib.sha256(('\n'.join(PINS) + '\n').encode()).hexdigest(),
              'source_sha256': source_hash(package)}
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('OUTPUT_ALREADY_EXISTS')
    checked_path(args.output.parent, owner=(os.getuid(), os.getgid()), directory=True)
    if args.operation == 'build':
        command = ['docker', 'build', '--platform', 'linux/amd64', '--provenance=false',
                   '--file', str(dockerfile), '--tag', args.image]
        for name, value in hashes.items():
            command.extend(['--build-arg', f'{name.upper()}={value}'])
        subprocess.run([*command, str(repo)], check=True)
        record = image_record(args.image)
        if any(record[name] != value for name, value in hashes.items()):
            raise ValueError('BUILD_PROVENANCE_MISMATCH')
        _exclusive_json(args.output, record)
        return 0
    if not args.batch_root or not args.image_id or not args.yolo_weights or not args.grounded_root:
        parser.error('run/smoke require resolved --batch-root, --image-id and both model paths')
    record = image_record(args.image)
    if record['image_id'] != args.image_id or any(record[name] != value for name, value in hashes.items()):
        raise ValueError('IMAGE_OR_SOURCE_DRIFT')
    groups = gpu_groups()
    command = container_run_argv(args.batch_root, image_id=args.image_id,
                                 yolo_weights=args.yolo_weights, grounded_root=args.grounded_root,
                                 gpu_groups=groups, uid=os.getuid(), gid=os.getgid(),
                                 batch_id=args.batch_root.name, broker_generation=1)
    if args.operation == 'smoke':
        source = checked_path(args.input)
        destination = args.batch_root / 'workers/smoke.png'
        with destination.open('xb') as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        destination.chmod(0o400)
        command.extend(['--smoke-input', '/inputs/smoke.png'])
    admission = {'provenance': record, 'gpu_groups': groups, 'uid': os.getuid(),
                 'gid': os.getgid(), 'argv': command, 'batch_root': str(args.batch_root)}
    _exclusive_json(args.output, admission)
    subprocess.run(command, check=True)
    if image_record(args.image) != record:
        raise ValueError('IMAGE_DRIFT_AFTER_RUN')
    return 0


def _exclusive_json(path, document):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical_json(document))
        stream.flush()
        os.fsync(stream.fileno())


def smoke_models(runtime, frame, *, clock=time.monotonic):
    """Measure each complete model call; broken clocks cannot yield a receipt.

    An infrastructure failure poisons the runtime. Remaining models get an
    explicit unexecuted INFRA record, so an earlier result cannot hide the loss.
    Both measured service latency and the adapter's inference latency are kept.
    """
    from so101_demo.core.detection import DetectionQuery
    last_time = None

    def now():
        nonlocal last_time
        try:
            value = clock()
            if (type(value) not in (int, float) or not math.isfinite(value) or value < 0
                    or (last_time is not None and value < last_time)):
                raise ValueError('nonfinite, negative or regressing clock')
            last_time = float(value)
            return last_time
        except Exception as error:
            runtime._unhealthy()
            raise ModelRuntimeInfrastructureError(f'SMOKE_CLOCK_FAILED: {error}') from error

    results = {}
    for model_id, built in runtime.detectors.items():
        started = now()
        record = {'model_provenance': built.provenance_document, 'executed': False}
        try:
            if not runtime.healthy:
                raise ModelRuntimeInfrastructureError('BROKER_UNHEALTHY')
            record['executed'] = True
            candidate = normalize_batch(built.detector.detect(frame, DetectionQuery('plastic_cup')), frame)
            record.update(outcome='QUALIFIED' if candidate['candidates'] else 'NORMAL_REJECTION',
                          result=candidate)
        except DeterministicModelResultError as error:
            if 'INFERENCE_FAILED' in str(error):
                runtime._unhealthy()
                record.update(outcome='INFRA_ERROR', reason=str(error))
            else:
                record.update(outcome='MODEL_ERROR', reason=str(error))
        except Exception as error:
            runtime._unhealthy()
            record.update(outcome='INFRA_ERROR', reason=str(error))
        completed = now()
        latency = (completed - started) * 1000.
        if not math.isfinite(latency) or latency < 0:
            runtime._unhealthy()
            raise ModelRuntimeInfrastructureError('SMOKE_CLOCK_LATENCY_INVALID')
        record.update(started_monotonic_s=started, completed_monotonic_s=completed,
                      latency_ms=latency)
        results[model_id] = record
    return json.loads(canonical_json(results))


def main(argv=None, *, transport=None, authorize=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'container':
        return container_main(argv[1:])
    parser = argparse.ArgumentParser()
    # Exact frozen argument values prevent accidental fallback or threshold drift.
    frozen = broker_argv()
    index = 0
    while index < len(frozen):
        flag = frozen[index]
        if flag == '--no-cpu-fallback':
            parser.add_argument(flag, action='store_true', required=True)
            index += 1
        else:
            parser.add_argument(flag, required=True, choices=[frozen[index + 1]])
            index += 2
    parser.add_argument('--smoke-input', type=Path)
    args = parser.parse_args(argv)
    if args.smoke_input is None and transport is None:
        from so101_demo.runtime.parallel_ipc import build_broker_transport

        transport = build_broker_transport(Path(args.runtime_spec))
    if args.smoke_input is None and authorize is None:
        authorize = getattr(transport, 'authorize', None)
    if args.smoke_input is None and not callable(authorize):
        raise ValueError('AUTHENTICATED_TRANSPORT_REQUIRED')
    versions = {}
    for pin in PINS:
        name, expected = pin.split('==')
        versions[name] = importlib.metadata.version(name)
        if versions[name] != expected:
            raise ValueError('RUNTIME_VERSION_DRIFT: ' + name)
    provenance = json.loads(Path('/opt/parallel-provenance.json').read_bytes())
    if verify_source(Path('/opt/so101_demo_py'), provenance) != provenance:
        raise ValueError('RUNTIME_SOURCE_PROVENANCE_MISMATCH')
    provenance['image_id'] = os.environ['PARALLEL_IMAGE_ID']
    provenance['versions'] = versions
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', provenance['image_id']):
        raise ValueError('IMAGE_ID_REQUIRED')
    ready_path = Path(args.ready_receipt)
    model_ready_path = ready_path.with_name(".model-ready.json")
    runtime = ParallelPerceptionRuntime(
        input_root=Path(args.input_root), ready_receipt=model_ready_path,
        options=frozen_options(Path(args.yolo_weights), Path(args.grounded_root)),
        provenance=provenance, authorize=authorize or (lambda request, snapshot: False))
    runtime.start()
    if args.smoke_input is None and model_ready_path.is_file():
        spec = getattr(transport, 'runtime_identity', None)
        required = {
            "schema_version", "kind", "batch_id", "coordinator_epoch",
            "broker_generation", "run_mode", "image_id", "yolo_weights_sha256",
            "grounded_manifest_sha256", "config_path", "authority_endpoint",
            "authority_token_path", "request_deadline_s", "max_frame_bytes",
        }
        if type(spec) is not dict or set(spec) != required:
            raise ValueError("BROKER_RUNTIME_SPEC_SCHEMA")
        model_receipt = json.loads(model_ready_path.read_text(encoding="utf-8"))
        if model_receipt.get("ready") is not True or set(runtime.detectors) != {
            YOLO_ID, "grounded-sam"
        }:
            raise ValueError("BROKER_MODEL_READY_SCHEMA")
        strict_ready = {
            "schema_version": 1,
            "kind": "so101_parallel_broker_ready",
            "batch_id": spec["batch_id"],
            "run_mode": spec["run_mode"],
            "coordinator_epoch": spec["coordinator_epoch"],
            "broker_generation": spec["broker_generation"],
            "image_id": spec["image_id"],
            "yolo_weights_sha256": spec["yolo_weights_sha256"],
            "grounded_manifest_sha256": spec["grounded_manifest_sha256"],
            "models": {
                YOLO_ID: {
                    "ready": True,
                    "weights_sha256": spec["yolo_weights_sha256"],
                },
                "grounded-sam": {
                    "ready": True,
                    "manifest_sha256": spec["grounded_manifest_sha256"],
                },
            },
        }
        transport.bind_ready_identity(strict_ready)
        write_receipt(ready_path, strict_ready)
    if args.smoke_input:
        from PIL import Image
        import numpy as np
        from so101_demo.core.detection import DetectionFrame
        source = checked_path(args.smoke_input, owner=(os.getuid(), os.getgid()), mode=0o400)
        source.relative_to(Path(args.input_root))
        frame = DetectionFrame(np.asarray(Image.open(source).convert('RGB')), 1, 'offline_smoke')
        results = smoke_models(runtime, frame)
        write_receipt(Path('/runtime/smoke.json'), {'provenance': provenance, 'results': results})
        return int(any(item['outcome'] not in {'QUALIFIED', 'NORMAL_REJECTION'}
                       for item in results.values()))
    # The only real framing/auth protocol is implemented by Task 11.
    try:
        return transport.serve(runtime, endpoint=Path(args.endpoint))
    except Exception:
        runtime._unhealthy()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
