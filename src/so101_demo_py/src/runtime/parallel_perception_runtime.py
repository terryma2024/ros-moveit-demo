"""Shared detector service; transport and durable ACK authority are injected.

Input SHA256 covers the exact .npy file bytes (including its header). The Worker
seals the file 0400 before submission. Snapshot metadata is verified against the
authenticated start-event port on every dispatch and completion. This module
does not localize depth, access TF, publish ROS messages, or authorize motion.
"""

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import threading

import numpy as np

from so101_demo.adapters.perception import detector_factory
from so101_demo.adapters.perception.detector_factory import DetectorFactoryOptions
from so101_demo.adapters.perception.errors import (
    DeterministicModelResultError, ModelRuntimeInfrastructureError,
)
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.core.detection import DetectionBatch, DetectionCandidate, DetectionFrame, DetectionQuery
from so101_demo.parallel_batch.broker import BrokerSubmission, ModelResult, PerceptionBroker
from so101_demo.parallel_batch.contracts import (
    ExecutionKind, InferenceRequest, ModelOutcome, NormalizedInferenceResponseIdentity,
    ParallelRuntimeConfig,
)

YOLO_ID = 'plastic-cup-yolo11n-seg-v1'
GROUNDED_ID = 'grounded-sam'
IMAGE_TAG = 'so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1'
YOLO_SHA = ParallelRuntimeConfig.FROZEN_YOLO_WEIGHTS_SHA256
GROUNDED_SHA = ParallelRuntimeConfig.FROZEN_GROUNDED_SAM_MANIFEST_SHA256
PINS = ('torch==2.13.0+cu130', 'torchvision==0.28.0+cu130', 'ultralytics==8.4.115',
        'transformers==4.56.2', 'scipy==1.17.1', 'huggingface-hub==0.34.4',
        'safetensors==0.6.2', 'tokenizers==0.22.0', 'numpy==1.26.4',
        'Pillow==12.3.0', 'PyYAML==6.0.2')


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def frozen_options(yolo_weights, grounded_root):
    return {
        YOLO_ID: DetectorFactoryOptions(
            backend='yolo_seg', requested_device='cuda', allow_cpu_fallback=False,
            yolo_weights_path=yolo_weights, yolo_weights_sha256=YOLO_SHA,
            yolo_model_id=YOLO_ID, yolo_imgsz=640),
        GROUNDED_ID: DetectorFactoryOptions(
            backend='grounded_sam', requested_device='cuda', allow_cpu_fallback=False,
            grounded_model_root=grounded_root, grounded_manifest_sha256=GROUNDED_SHA,
            grounded_thresholds=GroundedSamThresholds.defaults()),
    }


@dataclass(frozen=True)
class Snapshot:
    """Authenticated metadata alongside the canonical Task 1 request identity."""

    shape: tuple
    source_stamp_ns: int
    source_frame_id: str
    start_event_id: str
    start_event_type: str
    start_identity: NormalizedInferenceResponseIdentity
    query_class_id: str = 'plastic_cup'


class StartAuthorizationRejected(ValueError):
    """A verified negative authorization or mismatched execution identity."""


def checked_path(path, *, owner=None, mode=None, directory=False):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('RESOLVED_PATH_REQUIRED')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('SYMLINK_FORBIDDEN')
    info = path.stat()
    predicate = stat.S_ISDIR if directory else stat.S_ISREG
    if not predicate(info.st_mode):
        raise ValueError('PATH_TYPE')
    if owner is not None and (info.st_uid, info.st_gid) != owner:
        raise ValueError('PATH_OWNER')
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise ValueError('PATH_MODE')
    return path


def write_receipt(path, document):
    path = Path(path)
    checked_path(path.parent, owner=(os.getuid(), os.getgid()), mode=0o700, directory=True)
    payload = canonical_json(document)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    checked_path(path, owner=(os.getuid(), os.getgid()), mode=0o600)
    if path.read_bytes() != payload:
        raise OSError('RECEIPT_READBACK')
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def normalize_batch(batch, frame):
    """Validate even mutated adapter objects before lossless wire conversion."""
    try:
        if type(batch) is not DetectionBatch:
            raise ValueError('DETECTION_BATCH_REQUIRED')
        DetectionBatch(**{name: getattr(batch, name) for name in batch.__dataclass_fields__})
        if (batch.image_height, batch.image_width) != frame.rgb8.shape[:2]:
            raise ValueError('BATCH_SHAPE')
        if batch.runtime_device != 'cuda':
            raise ValueError('BATCH_DEVICE')
        candidates = []
        for item in batch.candidates:
            if type(item) is not DetectionCandidate:
                raise ValueError('CANDIDATE_TYPE')
            DetectionCandidate(**{name: getattr(item, name) for name in item.__dataclass_fields__})
            if (item.source_stamp_ns, item.source_frame_id) != (
                    frame.source_stamp_ns, frame.source_frame_id):
                raise ValueError('CANDIDATE_SOURCE')
            flat = item.mask.ravel(order='C')
            changes = np.flatnonzero(flat[1:] != flat[:-1]) + 1
            counts = np.diff(np.concatenate(([0], changes, [flat.size]))).tolist()
            if bool(flat[0]):
                counts.insert(0, 0)
            candidates.append({
                'instance_id': item.instance_id, 'class_id': item.class_id,
                'confidence': float(item.confidence), 'bbox_xyxy': list(item.bbox_xyxy),
                'segmentation_quality': item.segmentation_quality,
                'mask_rle': {'shape': list(item.mask.shape), 'counts': counts},
            })
        document = {
            'model_id': batch.model_id, 'weights_sha256': batch.weights_sha256,
            'runtime_device': batch.runtime_device, 'inference_latency_ms': batch.inference_latency_ms,
            'shape': list(frame.rgb8.shape), 'source_stamp_ns': frame.source_stamp_ns,
            'source_frame_id': frame.source_frame_id, 'candidates': candidates,
        }
        return json.loads(canonical_json(document))
    except (ValueError, TypeError, AttributeError) as error:
        raise DeterministicModelResultError(str(error)) from error


class ParallelPerceptionRuntime:
    """One model pair per service generation, with irreversible unhealthy state."""

    def __init__(self, *, input_root, ready_receipt, options, provenance, authorize,
                 readonly_mount=lambda root: bool(os.statvfs(root).f_flag & os.ST_RDONLY),
                 health_changed=lambda healthy: None):
        self.input_root, self.ready_receipt = Path(input_root), Path(ready_receipt)
        self.options, self.provenance = dict(options), dict(provenance)
        self.authorize, self.readonly_mount = authorize, readonly_mount
        self.health_changed = health_changed
        self.detectors = {}
        self.healthy = False
        self._started = False

    def _unhealthy(self):
        self.healthy = False
        self.health_changed(False)

    def start(self):
        if self._started:
            if not self.healthy:
                raise ModelRuntimeInfrastructureError('RESTART_REQUIRED')
            self.health_changed(True)
            return
        self._started = True
        try:
            checked_path(self.input_root, owner=(os.getuid(), os.getgid()), directory=True)
            if self.readonly_mount(self.input_root) is not True:
                raise ValueError('READONLY_INPUT_MOUNT_REQUIRED')
            for model_id in (YOLO_ID, GROUNDED_ID):
                built = detector_factory.build_detector(self.options[model_id])
                if built.detector.runtime_device != 'cuda':
                    raise ValueError('CUDA_REQUIRED')
                self.detectors[model_id] = built
            receipt = {'ready': True, 'provenance': self.provenance, 'models': {
                key: {'provenance': value.provenance_document,
                      'cold_start_latency_ms': value.cold_start_latency_ms}
                for key, value in self.detectors.items()}}
            write_receipt(self.ready_receipt, receipt)
            self.healthy = True
            self.health_changed(True)
        except Exception as error:
            self._unhealthy()
            raise ModelRuntimeInfrastructureError(f'START_FAILED: {error}') from error

    def _authorized(self, request, snapshot):
        if type(request) is not InferenceRequest or type(snapshot) is not Snapshot:
            raise ValueError('REQUEST_SNAPSHOT_REQUIRED')
        expected = ('ATTEMPT_STARTED' if request.execution_kind is ExecutionKind.ATTEMPT
                    else 'VALIDATION_STARTED')
        if (snapshot.start_event_type != expected or not snapshot.start_event_id
                or snapshot.start_identity != NormalizedInferenceResponseIdentity.from_request(request)):
            raise StartAuthorizationRejected('START_ACK_IDENTITY')
        authorized = self.authorize(request, snapshot)
        if authorized is False:
            raise StartAuthorizationRejected('START_ACK_REJECTED')
        if authorized is not True:
            raise ModelRuntimeInfrastructureError('INVALID_AUTHORITY_RESPONSE')

    def _frame(self, request, snapshot):
        self._authorized(request, snapshot)
        branch, eid = (('attempts', request.attempt_id)
                       if request.execution_kind is ExecutionKind.ATTEMPT
                       else ('validations', request.validation_id))
        expected = f'{request.worker_id}/{branch}/{request.point_id}/{eid}/working/perception/input/rgb.npy'
        if request.input_relative_path != expected:
            raise ValueError('EXECUTION_INPUT_PATH')
        if self.readonly_mount(self.input_root) is not True:
            raise ValueError('READONLY_INPUT_MOUNT_REQUIRED')
        path = checked_path(self.input_root / expected, owner=(os.getuid(), os.getgid()), mode=0o400)
        path.relative_to(self.input_root)
        for parent in path.parents:
            if parent == self.input_root.parent:
                break
            info = parent.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError('INPUT_DIRECTORY_OWNER_MODE')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o400
                    or (before.st_uid, before.st_gid) != (os.getuid(), os.getgid())):
                raise ValueError('INPUT_OPENED_OWNER_MODE')
            data = stream.read()
            after = os.fstat(stream.fileno())
        if (before != after or after != path.stat()
                or hashlib.sha256(data).hexdigest() != request.input_sha256):
            raise ValueError('INPUT_HASH_CHANGED')
        rgb = np.load(io.BytesIO(data), allow_pickle=False)
        if (tuple(rgb.shape) != tuple(snapshot.shape) or rgb.dtype != np.uint8
                or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape) <= 0
                or type(snapshot.source_stamp_ns) is not int or snapshot.source_stamp_ns <= 0
                or snapshot.source_stamp_ns / 1e9 != request.image_timestamp_s):
            raise ValueError('INPUT_SHAPE_STAMP')
        return DetectionFrame(rgb, snapshot.source_stamp_ns, snapshot.source_frame_id)

    def infer(self, request, snapshot):
        try:
            if not self.healthy:
                raise ModelRuntimeInfrastructureError('BROKER_UNHEALTHY')
            frame = self._frame(request, snapshot)
            query = DetectionQuery(snapshot.query_class_id)
            try:
                batch = self.detectors[request.model_id].detector.detect(frame, query)
                candidate = normalize_batch(batch, frame)
                result = (ModelResult(ModelOutcome.QUALIFIED, candidate=candidate)
                          if candidate['candidates'] else ModelResult(ModelOutcome.NORMAL_REJECTION))
            except DeterministicModelResultError as error:
                # Legacy INFERENCE_FAILED wrappers are infrastructure, never a model verdict.
                if 'INFERENCE_FAILED' in str(error):
                    raise ModelRuntimeInfrastructureError(str(error)) from error
                result = ModelResult(ModelOutcome.MODEL_ERROR, reason=str(error))
            self._frame(request, snapshot)
            if not self.healthy:
                raise ModelRuntimeInfrastructureError('BROKER_UNHEALTHY')
            return result
        except Exception as error:
            # PerceptionService publishes this request's exact failure through
            # the Broker before fanning out the irreversible health loss.  An
            # eager callback here would invalidate the same in-flight request
            # as generic BROKER_NOT_READY and erase its initiating reason.
            self.healthy = False
            return ModelResult(ModelOutcome.INFRA_ERROR, reason=str(error))


class PerceptionService:
    """Bind authenticated snapshots to the one canonical bounded Broker.

    Task 11 transport calls submit/run_next/poll_response; an independent timer
    must poll deadlines while run_next blocks on CUDA. The supervisor provides
    generation; an in-process restart never reloads or reuses unhealthy models.
    """

    def __init__(self, runtime, config, *, generation, clock=None):
        self.runtime = runtime
        self._snapshots = {}
        self._requests = {}
        self._lock = threading.RLock()
        kwargs = {} if clock is None else {'clock': clock}
        self.broker = PerceptionBroker(
            config, grounded_model_id=GROUNDED_ID, authorize=self._authorize,
            generation=generation, detectors={model: self._detect for model in (YOLO_ID, GROUNDED_ID)},
            **kwargs)
        runtime.health_changed = self._health_changed

    def _health_changed(self, healthy):
        for model in (YOLO_ID, GROUNDED_ID):
            self.broker.set_model_ready(model, healthy)

    def _authorize(self, request):
        with self._lock:
            snapshot = self._snapshots.get(request.request_id)
        if snapshot is None:
            return False
        try:
            self.runtime._authorized(request, snapshot)
            return True
        except StartAuthorizationRejected:
            return False

    def _detect(self, request):
        with self._lock:
            snapshot = self._snapshots[request.request_id]
        return self.runtime.infer(request, snapshot)

    def start(self):
        self.runtime.start()

    def submit(self, request, snapshot):
        self._sync_health()
        with self._lock:
            previous = self._snapshots.get(request.request_id)
            if previous is not None and previous != snapshot:
                return BrokerSubmission(False, reason='SNAPSHOT_IDENTITY_CHANGED')
            self._snapshots[request.request_id] = snapshot
        submission = self.broker.submit(request)
        with self._lock:
            self._requests.setdefault(request.request_id, request)
        self._response_health(submission.response)
        return submission

    def run_next(self):
        self._sync_health()
        response = self.broker.run_next()
        self._sync_health()
        return self._response_health(self.broker.poll_response(response.request)
                                     if response is not None else None)

    def poll_response(self, request):
        self._sync_health()
        return self._response_health(self.broker.poll_response(request))

    def _sync_health(self):
        # Dispatch scans can finish an expired request without returning it.
        # Poll only the public Broker API; no second deadline/state machine.
        with self._lock:
            requests = tuple(self._requests.values())
        for request in requests:
            self._response_health(self.broker.poll_response(request))

    def _response_health(self, response):
        if not self.broker.healthy or (response is not None and response.outcome in {
                ModelOutcome.INFRA_ERROR, ModelOutcome.QUEUE_TIMEOUT, ModelOutcome.INFERENCE_TIMEOUT}):
            self.runtime._unhealthy()
        return response
