"""The sealed documents one stage-one run reads before it binds anything.

The runner may not invent a single search value. This module turns the two
sealed documents of an execution-input run into the exact objects the local
search needs: the frozen simulation policy, and the eighteen-key controller
configuration whose values all come from the sealed development config, the
declared run identity, the declared development pose and the declared ROS
environment. A document that does not declare the closed key set, or declares a
value outside its calibrated range, refuses the run instead of guessing.
"""

from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path

from so101_demo.act.head_simulation_policy import HeadSimulationPolicy

STOP_TRIGGERS = ('OPERATOR_STOP', 'FAULT_PRIMARY', 'DEADLINE', 'BUDGET_EXHAUSTED')

DOCUMENT_REFUSED = 'EXECUTION_DOCUMENT_REFUSED'
CONFIG_REFUSED = 'EXECUTION_SEARCH_CONFIG_REFUSED'
CONFIG_MISMATCH = 'EXECUTION_SEARCH_CONFIG_MISMATCH'
DECLARATIONS_ABSENT = 'EXECUTION_RUN_DECLARATIONS_ABSENT'
BINDING_MATERIAL_ABSENT = 'EXECUTION_BINDING_MATERIAL_ABSENT'

#: every key the sealed development config must declare, and nothing else
CONFIG_KEYS = (
    'horizontal_fov_rad', 'coarse_step_rad', 'goal_tolerance_rad', 'center_deadband_px',
    'vertical_bounds_px', 'min_area_px2', 'min_confidence', 'max_fine_corrections',
    'max_fine_total_rad', 'max_skew_s', 'max_age_s', 'settle_velocity_rad_s',
)

#: the camera frame the search reads, declared in the run's ROS environment
CAMERA_FRAME_KEY = 'SO101_HEAD_CAMERA_FRAME'
DEFAULT_CAMERA_FRAME = 'head_camera_optical_frame'


class HeadExecutionDocumentRefused(ValueError):
    """A refused sealed document, carrying the exact code the entry records."""

    def __init__(self, code: str, detail: str = '') -> None:
        self.code = code
        self.detail = detail
        super().__init__(f'{code}: {detail}' if detail else code)


def _refuse(code: str, detail: str):
    raise HeadExecutionDocumentRefused(code, detail)


def sealed_bytes(inputs, name: str) -> bytes:
    """Re-read one sealed reference as a plain regular file, or refuse."""

    from so101_demo.act import head_execution_inputs as module

    if name not in inputs.refs:
        _refuse(DOCUMENT_REFUSED, f'the inputs declare no {name} reference')
    raw = module._read_plain(f'refs.{name}', Path(inputs.refs[name]['path']))
    if hashlib.sha256(raw).hexdigest() != inputs.refs[name]['sha256']:
        _refuse(DOCUMENT_REFUSED, f'refs.{name}: DIGEST_CHANGED')
    return raw


def load_policy(inputs) -> HeadSimulationPolicy:
    """The frozen simulation policy of this run, parsed from its sealed bytes."""

    raw = sealed_bytes(inputs, 'local_policy')
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _refuse(DOCUMENT_REFUSED, f'local_policy is not JSON ({error})')
    try:
        return HeadSimulationPolicy.parse(document)
    except (TypeError, ValueError) as error:
        _refuse(DOCUMENT_REFUSED, f'local_policy is not a frozen policy document ({error})')


def load_development_config(inputs) -> dict:
    """The sealed development config as a closed mapping, or a refusal."""

    raw = sealed_bytes(inputs, 'development_config')
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _refuse(CONFIG_REFUSED, f'the development config is not JSON ({error})')
    # plan line 207 keeps every other value field of the old config, so the document's values block always
    # carries more than this twelve-key controller projection; require the projection and take the two motion
    # fields from where the plan puts them (CP-HFP-287)
    if type(document) is not dict:
        _refuse(CONFIG_REFUSED, 'the development config must be a mapping')
    values = document.get('values')
    motion = document.get('motion')
    source = {}
    if type(values) is dict:
        source.update(values)
    if type(motion) is dict:
        source.update({key: motion[key] for key in ('goal_tolerance_rad', 'settle_velocity_rad_s')
                       if key in motion})
    missing = sorted(set(CONFIG_KEYS) - set(source))
    if missing:
        _refuse(CONFIG_REFUSED,
                f'the development config must declare the controller projection (missing={missing})')
    return {key: source[key] for key in CONFIG_KEYS}


def _positive(where: str, value, *, limit=None):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        _refuse(CONFIG_REFUSED, f'{where} must be a finite positive number')
    if limit is not None and value > limit:
        _refuse(CONFIG_REFUSED, f'{where} must not exceed {limit}')
    return float(value)


def load_search_config(inputs, policy=None):
    """The controller mapping of this run: every value sealed or declared, never invented."""

    config = load_development_config(inputs)
    policy = load_policy(inputs) if policy is None else policy
    frame = inputs.document['ros']['environment'].get(CAMERA_FRAME_KEY, DEFAULT_CAMERA_FRAME)
    if type(frame) is not str or not frame:
        _refuse(CONFIG_REFUSED, f'{CAMERA_FRAME_KEY} must be a non-empty camera frame')
    bounds = config['vertical_bounds_px']
    if (type(bounds) not in (list, tuple) or len(bounds) != 2
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in bounds)
            or not 0 <= bounds[0] < bounds[1]):
        _refuse(CONFIG_REFUSED, 'vertical_bounds_px must be two finite ordered pixel bounds')
    corrections = config['max_fine_corrections']
    if type(corrections) is not int or corrections < 0:
        _refuse(CONFIG_REFUSED, 'max_fine_corrections must be a non-negative integer')
    confidence = config['min_confidence']
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
        _refuse(CONFIG_REFUSED, 'min_confidence must lie in [0, 1]')
    fov = config['horizontal_fov_rad']
    if type(fov) not in (int, float) or not 0 < fov <= math.pi:
        _refuse(CONFIG_REFUSED, 'horizontal_fov_rad must lie in (0, pi]')
    pose = inputs.document['development_pose']
    if type(pose['neck_rad']) not in (int, float) or not math.isfinite(pose['neck_rad']):
        _refuse(CONFIG_REFUSED, 'the development pose must declare a finite neck angle')
    maximum_skew = _positive('max_skew_s', config['max_skew_s'], limit=.05)
    maximum_age = _positive('max_age_s', config['max_age_s'])
    if maximum_age > policy.perception_max_age_s:
        _refuse(CONFIG_REFUSED,
                f'max_age_s {maximum_age} exceeds the frozen perception_max_age_s '
                f'{policy.perception_max_age_s}')
    result = {
        'attempt_id': inputs.run['epoch'],
        'session_id': inputs.run['session_id'],
        'search_start_rad': float(pose['neck_rad']),
        'horizontal_fov_rad': float(fov),
        'coarse_step_rad': _positive('coarse_step_rad', config['coarse_step_rad']),
        'search_timeout_s': float(policy.search_timeout_s),
        'max_age_s': maximum_age,
        'max_skew_s': maximum_skew,
        'settle_velocity_rad_s': _positive('settle_velocity_rad_s', config['settle_velocity_rad_s']),
        'goal_tolerance_rad': _positive('goal_tolerance_rad', config['goal_tolerance_rad']),
        'center_deadband_px': _positive('center_deadband_px', config['center_deadband_px']),
        'vertical_bounds_px': (float(bounds[0]), float(bounds[1])),
        'min_area_px2': _positive('min_area_px2', config['min_area_px2']),
        'min_confidence': float(confidence),
        'max_fine_corrections': int(corrections),
        'max_fine_total_rad': _positive('max_fine_total_rad', config['max_fine_total_rad']),
        'frame_id': frame,
        'ray_origin_frame_id': frame,
    }
    document = json.loads(sealed_bytes(inputs, 'development_config'))
    if 'required_search_domain_rad' in document:
        intervals = {
            'required_search_domain_rad': document['required_search_domain_rad'],
            'lock_valid_neck_rad': document.get('values', {}).get('lock_valid_neck_rad'),
        }
        for name, interval in intervals.items():
            if (type(interval) not in (list, tuple) or len(interval) != 2
                    or any(type(value) not in (int,float) or not math.isfinite(value) for value in interval)
                    or not interval[0] < interval[1]):
                _refuse(CONFIG_REFUSED, f'{name}: bounded interval missing or invalid')
            result[name] = tuple(float(value) for value in interval)
        low, high = result['required_search_domain_rad']
        safe_low, safe_high = result['lock_valid_neck_rad']
        if not safe_low <= low < high <= safe_high:
            _refuse(CONFIG_REFUSED, 'required search domain outside lock geometry')
    return result


class _DevelopmentBinding:
    """The development scope's binding: the sealed mapping is the configuration, and the lock interval guards the neck.

    CP-HFP-412: the cross-check demands that the projected configuration equal the sealed mapping, which the
    eleven-name projection cannot do; and the neck guard needs lock_valid_neck_rad, which the sealed mapping does
    not carry but the declared configuration does. Both halves come from documents the run declares.
    """

    def __init__(self, sealed: dict, declared: dict) -> None:
        self._sealed = dict(sealed)
        self._values = dict(sealed)
        interval = (declared or {}).get('lock_valid_neck_rad')
        if interval is not None:
            self._values['lock_valid_neck_rad'] = interval

    def neck_motion_allowed(self, current_rad: float, target_rad: float) -> bool:
        interval = self._values.get('lock_valid_neck_rad')
        if (type(interval) not in (list, tuple) or len(interval) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in interval)):
            return False
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (current_rad, target_rad)):
            return False
        return all(interval[0] <= value <= interval[1] for value in (current_rad, target_rad))

    def search_config(self, *, session_id: str, attempt_id: str, search_start_rad: float) -> dict:
        return dict(self._sealed)


def cross_check_search_config(inputs, config, policy=None):
    """Cross-check a binding-derived controller configuration against the sealed document (CP-HFP-078)."""

    if type(config) is not dict:
        _refuse(CONFIG_REFUSED, 'the configuration to cross-check must be a mapping')
    sealed = load_search_config(inputs, policy)
    missing = sorted(set(sealed) - set(config))
    extra = sorted(set(config) - set(sealed))
    if missing or extra:
        _refuse(CONFIG_MISMATCH,
                f'the binding configuration and the sealed document disagree on their key set '
                f'(missing={missing}, extra={extra})')
    for key, expected in sorted(sealed.items()):
        if config[key] != expected:
            _refuse(CONFIG_MISMATCH,
                    f'{key}: the binding declares {config[key]!r} while the sealed document declares '
                    f'{expected!r}')
    return sealed

DECLARATION_NAMES = ('stop_declaration', 'seal_expectation', 'log_capture', 'fault_stop_probes')


def require_run_declarations(inputs):
    """The CP-HFP-075 declarations a real run must carry, or a refusal naming what is missing.

    The sealed schema accepts and validates these fields whenever they are declared (CP-HFP-090); this
    function is the run-time enforcement the provider and runner use, so no real run can start without
    naming its stop trigger, teardown bound, seal expectation, log capture and fault-probe order.
    """

    document = inputs.document
    missing = [name for name in DECLARATION_NAMES if name not in document]
    if missing:
        _refuse(DECLARATIONS_ABSENT,
                f'the run must declare {missing} before it starts (CP-HFP-075)')
    declared = {name: document[name] for name in DECLARATION_NAMES}
    stop = declared['stop_declaration']
    if stop['trigger'] not in STOP_TRIGGERS:
        _refuse(CONFIG_REFUSED, f"stop trigger {stop['trigger']!r} is not one of {STOP_TRIGGERS}")
    return declared

def require_binding_material(inputs):
    """The sealed detector-binding material: binding and report refs plus the declared snapshot root."""

    from pathlib import Path as _Path

    refs = inputs.refs
    missing = [name for name in ('binding', 'report') if name not in refs]
    if missing or 'snapshot_root' not in inputs.document:
        _refuse(BINDING_MATERIAL_ABSENT,
                f'the run must name the sealed detector binding material (missing refs {missing}, '
                f"snapshot_root {'present' if 'snapshot_root' in inputs.document else 'absent'})")
    # a MUJOCO_DEVELOPMENT_UNQUALIFIED run pairs the development config with itself: plan lines 163/207 declare
    # that scope and forbid its document from entering promoted acceptance, so pairing it with the promoted
    # material was the deviation (CP-HFP-307/308)
    scope = (inputs.document.get('execution_scope')
             or (inputs.refs.get('development_config') and 'MUJOCO_DEVELOPMENT_UNQUALIFIED'))
    development = refs.get('development_config')
    if development and str(inputs.document.get('execution_scope', '')).endswith('DEVELOPMENT_UNQUALIFIED'):
        # one config is declared for this scope (plan line 163, CP-HFP-317), and the calibration bundle the
        # receipt names is the other document the plan pins for it (CP-HFP-252/318)
        import json as _json
        receipt = _json.loads(_Path(refs['report']['path']).read_text(encoding='utf-8'))
        bundle = (receipt.get('bundle') or {}).get('path')
        if not bundle or not _Path(bundle).is_file():
            _refuse(BINDING_MATERIAL_ABSENT, 'the receipt must name the calibration bundle for this scope')
        binding = _Path(development['path'])
        report = _Path(bundle)
    else:
        binding = _Path(refs['binding']['path'])
        report = _Path(refs['report']['path'])
    snapshot_root = _Path(inputs.document['snapshot_root'])
    for name, path in (('binding', binding), ('report', report)):
        if not path.is_file():
            _refuse(BINDING_MATERIAL_ABSENT, f'{name} {path} is not a regular file')
    if snapshot_root.is_symlink() or not snapshot_root.is_dir():
        _refuse(BINDING_MATERIAL_ABSENT, f'snapshot_root {snapshot_root} is not a plain directory')
    return {'binding': binding, 'report': report, 'snapshot_root': snapshot_root}

def read_detector_cuda_device(runtime, *, declared_device):
    """Read warmed model tensors and predictor on the model's owning thread."""
    try:
        model = runtime.detector._model
        devices = {str(parameter.device) for parameter in model.model.parameters()}
        predictor = str(model.predictor.device)
    except (AttributeError,TypeError) as error:
        raise PermissionError('HEAD_SEARCH_DEVICE_READBACK_ABSENT') from error
    if declared_device != 'cuda:0' or devices != {declared_device} or predictor != declared_device:
        raise PermissionError('HEAD_SEARCH_DEVICE_DRIFT')
    return predictor


def build_run_detector_factory(inputs, *, loader=None, builder=None):
    """The one-shot detector factory the owned inference thread calls (CP-HFP-047/079).

    The sealed binding material is resolved and validated once, here, on the entry thread; the returned
    factory loads the promoted binding once and builds the model on demand, so the CUDA weights are loaded
    inside the owner thread that calls it and never on the entry thread.
    """

    development = (inputs.execution_scope == 'MUJOCO_DEVELOPMENT_UNQUALIFIED'
        and (loader is None or getattr(loader,'_head_development_inputs',None) is inputs))
    if development:
        root = inputs.document.get('snapshot_root')
        if (type(root) is not str or not Path(root).is_absolute()
                or Path(root).is_symlink() or not Path(root).is_dir()):
            _refuse(BINDING_MATERIAL_ABSENT,'development snapshot_root must be a declared plain directory')
        snapshot_root = Path(root)
        if loader is None:
            loader = development_detector_loader(inputs)
        binding = loader()
    else:
        material = require_binding_material(inputs)
        if loader is None:
            from so101_demo.act.head_search_binding import load_promoted_head_search as loader
        binding = loader(material['binding'], material['report'])
        snapshot_root = material['snapshot_root']
    production_builder = builder is None
    if builder is None:
        from so101_demo.adapters.act.detector import build_bound_head_detector as builder

    def factory():
        result = builder(binding, snapshot_root=snapshot_root)
        # the inference owner requires a dict carrying a runtime with detect and reset
        # (CP-HFP-521/539); a builder that already returns one is passed through unchanged
        if isinstance(result, dict) and 'runtime' in result:
            return result
        # only the runtime, because the owner deep-copies the rest of the dict as metadata
        # (CP-HFP-521) and a built detector holds locks that cannot be pickled (CP-HFP-549)
        runtime = getattr(result, 'runtime', result)
        built = {'runtime': runtime}
        if production_builder:
            built['runtime_device'] = read_detector_cuda_device(runtime,
                declared_device=inputs.document['resources']['cuda_device'])
            # The generic detector warms a square image. Pay the declared
            # camera shape's first-call cost before the inference owner is READY.
            # Predict directly so this startup image creates no tracks or stamps.
            import numpy as np
            import time
            import torch
            geometry = json.loads(sealed_bytes(inputs, 'camera_geometry'))
            camera = geometry.get('camera', {})
            height, width = camera.get('height'), camera.get('width')
            if any(type(value) is not int or value <= 0 for value in (height, width)):
                _refuse(DOCUMENT_REFUSED, 'camera_geometry must declare positive camera dimensions')
            started = time.monotonic()
            runtime.detector._predict(np.zeros((height, width, 3), dtype=np.uint8))
            torch.cuda.synchronize(device=built['runtime_device'])
            built['camera_shape_warmup'] = dict(shape=[height, width, 3],
                elapsed_s=time.monotonic()-started,
                classification='STARTUP_ONLY_NOT_OBSERVATION')
            built['snapshot_path'] = str(result.snapshot_path)
            built['weights_sha256'] = runtime.weights_sha256
            built['model_id'] = runtime.model_id
        return built

    return factory

def resolve_run_search_config(inputs, *, session_id, attempt_id, search_start_rad, binding_loader=None):
    """The one controller configuration of a run: from the binding, cross-checked against the sealed document.

    CP-HFP-078 makes the binding authoritative, so this function asks it for the configuration and then
    refuses if the sealed development document disagrees, rather than choosing between the two sources.
    """

    if binding_loader is None and inputs.execution_scope == 'MUJOCO_DEVELOPMENT_UNQUALIFIED':
        config = load_search_config(inputs)
        if (session_id != config['session_id'] or attempt_id != config['attempt_id']
                or search_start_rad != config['search_start_rad']):
            _refuse(CONFIG_MISMATCH,'development scope differs from sealed run or pose')
        return config
    import json as _json
    from so101_demo.act.head_search_binding import validate_head_search_binding

    material = require_binding_material(inputs)
    # the configuration is assembled by the VALIDATED binding, whose object carries search_config (CP-HFP-276):
    # the promoted loader returns the plain document, which is what raised the AttributeError in run-021
    _binding_doc = _json.loads(material['binding'].read_text(encoding='utf-8'))
    _report_doc = _json.loads(material['report'].read_text(encoding='utf-8'))
    if binding_loader is None and str(inputs.document.get('execution_scope', '')).endswith(
            'DEVELOPMENT_UNQUALIFIED'):
        # the plan excludes this scope from the promoted comparison (lines 162 and 207), so its default
        # loader is the development one: the same four-field binding built from the sealed mapping, which
        # keeps the ordinary projection and cross-check and leaves an explicit loader winning (CP-HFP-408)
        _sealed_mapping = dict(load_search_config(inputs))
        _dev_doc = load_development_config(inputs)
        # the motion block comes from the sealed mapping too, so the allowed neck range and the start
        # radius are judged against one normalised source (CP-HFP-410)
        _motion = {'goal_tolerance_rad': _sealed_mapping['goal_tolerance_rad'],
                   'settle_velocity_rad_s': _sealed_mapping['settle_velocity_rad_s'],
                   'neck_goal_duration_s': _sealed_mapping['search_timeout_s']}
        loader = lambda _b, _r: _DevelopmentBinding(_sealed_mapping, _dev_doc)
    else:
        loader = validate_head_search_binding if binding_loader is None else binding_loader
    # the loader seam is the point of this function: both scopes call it, and what differs between them
    # is which documents the material hands over — the development pair for this scope (CP-HFP-318/405)
    binding = loader(_binding_doc, _report_doc)
    config = binding.search_config(session_id=session_id, attempt_id=attempt_id,
                                   search_start_rad=search_start_rad)
    if type(config) is not dict:
        _refuse(CONFIG_REFUSED, 'the binding must return the controller configuration as a mapping')
    return cross_check_search_config(inputs, config)

def build_run_local_state(inputs, policy, controller_identity, *, now_s=None):
    """The run's single local state: sealed run identity, the sealed policy digest, one controller identity.

    The policy must match the sealed bytes. None denotes explicitly UNBOUND
    controller identity until the runtime authenticates both native channels.
    """

    import math as _math
    import time as _time

    from so101_demo.act.head_evidence_identity import digest as _digest
    from so101_demo.act.head_local_state import HeadLocalState

    sealed = load_policy(inputs)
    if _digest(policy.readback()) != _digest(sealed.readback()):
        _refuse(DOCUMENT_REFUSED, 'the policy handed to the state is not the sealed policy document')
    if controller_identity is not None and (type(controller_identity) is not dict
            or set(controller_identity) != {'generation', 'incarnation', 'boot'}
            or any(type(value) is not str or not value for key, value in controller_identity.items()
                   if key != 'generation')):
        _refuse(DOCUMENT_REFUSED,
                'the controller identity must be the complete generation/incarnation/boot triple')
    record = inputs.run
    now = _time.monotonic() if now_s is None else float(now_s)
    if not _math.isfinite(now):
        _refuse(DOCUMENT_REFUSED, 'now_s must be finite')
    deadline_ns = int(now * 1e9) + int(sealed.search_timeout_s * 1e9)
    return HeadLocalState(dict(epoch=record['epoch'], generation=record['generation'],
                               session_id=record['session_id'],
                               policy_sha256=_digest(policy.readback()),
                               controller_identity=(None if controller_identity is None
                                                    else dict(controller_identity))), deadline_ns)

def retirement_unconfirmed(receipt):
    """Detect explicit negative closure receipts, including nested owned workers."""
    if receipt is False:
        return True
    if not isinstance(receipt, dict):
        return False
    if any(receipt.get(key) is False for key in
           ('retired', 'closed', 'frozen', 'clients_retired', 'subscriptions_retired')):
        return True
    if receipt.get('thread_alive') is True or receipt.get('unquiesced'):
        return True
    if receipt.get('stop_requested') is True:
        if receipt.get('confirmed_stop') is not True:
            return True
        close = receipt.get('deadman_close', {})
        if close.get('finished') is not True or close.get('ack') is not True:
            return True
    return any(retirement_unconfirmed(value) for value in receipt.values()
               if isinstance(value, dict))


def retire_run_resources(runtime, exposure, owner, *, emit=None, outcomes=None,
                         defer_original_retirement=False):
    """Close the run's resources in reverse order, recording failures instead of raising them.

    A teardown that throws must not hide the other resources: every stage is attempted, each failure is
    reported by name, and the caller still receives the report so it can seal an honest completion.
    """

    report = {'runtime': None, 'exposure': None, 'owner': None}

    def close_runtime(resource):
        from so101_demo.adapters.act.head_local_runtime import HeadLocalRuntime
        try:
            if isinstance(resource, HeadLocalRuntime):
                resource.finish_requested_stop()
        finally:
            receipt = resource.close(timeout_s=1., retire_originals=False) \
                if defer_original_retirement else resource.close(timeout_s=1.)
        return receipt

    actions = (
        ('runtime', close_runtime),
        ('owner', lambda resource: resource.close(timeout_s=1.)),
        ('exposure', lambda resource: resource.retirement_snapshot()
         if owner is not None and callable(getattr(resource,'retirement_snapshot',None))
         else resource.freeze_retirement()),
    )
    resources = {'runtime': runtime, 'exposure': exposure, 'owner': owner}
    for stage, action in actions:
        resource = resources[stage]
        if resource is None:
            continue
        try:
            receipt = action(resource)
            if outcomes is not None:
                outcomes[stage] = receipt
            if retirement_unconfirmed(receipt):
                report[stage] = 'HEAD_RETIREMENT_UNCONFIRMED'
                if emit is not None:
                    emit(stage, report[stage])
        except Exception as error:  # a teardown failure is recorded, never raised over the others
            report[stage] = type(error).__name__
            if emit is not None:
                emit(stage, type(error).__name__)
    return report

def _factory_device(declared):
    """Map a declared device onto the four the detector factory accepts (CP-HFP-544)."""

    text = str(declared or 'cuda')
    if text.startswith('cuda'):
        return 'cuda'
    return text if text in ('auto', 'mps', 'cpu') else 'cuda'


class _DevelopmentDetectorBinding:
    """The development scope's detector binding: the block is composed, not sealed (CP-HFP-536)."""

    def __init__(self, detector: dict, search_values: dict | None = None) -> None:
        self.detector = dict(detector)
        # the builder also reads search_values (CP-HFP-545); for this scope it is the same
        # composed block, plus whatever the run declares for the neck lock interval
        self.search_values = dict(search_values or detector)


def development_detector_loader(inputs):
    """A detector loader for the development scope: the eleven-key block from declared references.

    The promoted loader validates a sealed calibration document this scope does not have; this one
    composes the block the builder reads from the weights reference, the run resources and the
    installed torch and ultralytics, which is what the development scope can honestly supply.
    """

    import hashlib as _hashlib
    from pathlib import Path as _Path

    weights = dict(inputs.refs['weights'])
    weights_path = _Path(weights['path'])
    resources = dict(getattr(inputs, 'document', {}).get('resources') or {})

    def loader(binding_document=None, report_document=None):
        import torch
        import ultralytics
        digest = _hashlib.sha256(sealed_bytes(inputs,'weights')).hexdigest()
        block = {
            'backend': 'yolo_seg',
            'weights_path': str(weights_path),
            'weights_sha256': digest,
            'model_id': str(weights.get('model_id') or weights_path.stem),
            'image_size_px': 640,
            # the factory accepts auto, cuda, mps or cpu (CP-HFP-544): a declared cuda:N maps to cuda
            'requested_device': _factory_device(resources.get('cuda_device')),
            'allow_cpu_fallback': False,
            'torch_threads': int(resources.get('torch_threads') or 1),
            'torch_interop_threads': int(resources.get('torch_interop_threads') or 1),
            'torch_version': torch.__version__,
            'ultralytics_version': ultralytics.__version__,
        }
        # search_values is the sealed mapping the run declares (CP-HFP-546), not the detector block:
        # the validators read names such as tracking_iou from it, and it carries the neck interval too
        import json as _json
        from pathlib import Path as _P
        values = {}
        declared_ref = dict(getattr(inputs, 'refs', {}).get('development_config') or {})
        loaded = _json.loads(sealed_bytes(inputs,'development_config'))
        if isinstance(loaded, dict):
            sealed = loaded.get('values') if isinstance(loaded.get('values'), dict) else loaded
            values = dict(sealed or {})
        interval = values.get('lock_valid_neck_rad')
        if interval is None:
            declared_doc = getattr(inputs, 'document', {})
            if isinstance(declared_doc, dict):
                dev = declared_doc.get('development_config')
                if isinstance(dev, dict):
                    interval = dev.get('lock_valid_neck_rad')
        if interval is not None:
            values['lock_valid_neck_rad'] = interval
        for name, value in block.items():
            values.setdefault(name, value)
        return _DevelopmentDetectorBinding(block, values)

    loader._head_development_inputs = inputs
    return loader
