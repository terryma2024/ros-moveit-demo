"""Drive the owned search on one bound composition (post-CP-HFP-116 contract).

The provider hands over the stack, the activated Head neck owner and the detector constructor entry, so
this module owns the frozen order: bind ros, construct the local runtime on the neck owner, bind the owner,
build the detector through the inference-owner factory once that owner is ready, then bind inference,
runtime and search, drive a bounded tick loop and always retire.
"""

from __future__ import annotations

import time

from so101_demo.act.head_execution_documents import build_run_detector_factory
from so101_demo.act.head_execution_documents import build_run_local_state
from so101_demo.act.head_execution_documents import require_run_declarations
from so101_demo.act.head_execution_documents import resolve_run_search_config
from so101_demo.act.head_execution_documents import retire_run_resources
from so101_demo.adapters.act.head_execution_composition import HeadExecutionComposition
from so101_demo.adapters.act.head_inference_owner import HeadInferenceOwner
from so101_demo.adapters.act.head_live_exposure import HeadLiveExposures
from so101_demo.adapters.act.head_local_observer import HeadLocalObserver
from so101_demo.adapters.act.head_local_runtime import HeadLocalRuntime
from so101_demo.adapters.act.head_owned_search import OwnedHeadSearch

RUNNER_REFUSED = 'EXECUTION_RUNNER_REFUSED'
SOURCE_ABSENT = 'EXECUTION_RUNNER_SOURCE_ABSENT'
NECK_ABSENT = 'EXECUTION_RUNNER_NECK_ABSENT'
OWNER_ABSENT = 'EXECUTION_RUNNER_OWNER_ABSENT'
SETTLEMENT_ABSENT = 'EXECUTION_RUNNER_SETTLEMENT_ABSENT'
ENTRY_ABSENT = 'EXECUTION_RUNNER_HANDOVER_INCOMPLETE'
DEVICE_REFUSED = 'EXECUTION_RUNNER_DEVICE_REFUSED'


class HeadExecutionRunnerRefused(RuntimeError):
    """A refused runner step, carrying the exact code the entry records."""

    def __init__(self, code: str, detail: str = '') -> None:
        self.code = code
        self.detail = detail
        super().__init__(f'{code}: {detail}' if detail else code)


def _refuse(code: str, detail: str):
    raise HeadExecutionRunnerRefused(code, detail)


def _require_entry(handle, name):
    entry = handle.get(name)
    if not isinstance(entry, dict) or not callable(entry.get('callable')):
        _refuse(ENTRY_ABSENT, f'the provider must hand over {name} as a callable with keywords')
    return entry['callable'], dict(entry.get('keywords') or {})


def _require_resource(handle, name, attribute, code, detail):
    resource = handle.get(name)
    if resource is None or not callable(getattr(resource, attribute, None)):
        _refuse(code, detail)
    return resource


def _bind_originals(composition, capture, port, observer, runtime):
    """Deliver originals to the local observer and, when enabled, the writer."""
    from so101_demo.adapters.act.head_original_router import HeadOriginalRouter

    record = None
    capture.emit = None
    capture.detection_image_recorder = None
    if composition.event_log_enabled:
        def record(kind, original):
            composition.emit(kind, original, source_stamp_ns=original.get('source_ns'))

        def image_payload(kind, *, record, payload):
            ref = composition.add_artifact(payload, media_type='application/octet-stream', suffix='rgb')
            stamp = composition.monotonic_ns()
            composition.writer.append('IMAGE_PAYLOAD', record,
                source_stamp_ns=record['source_ns'], observed_mono_ns=stamp,
                occurrence_mono_ns=round(record['wall_s'] * 1e9), artifact_refs=(ref,))

        if composition.inputs.save_all_rgb_frames:
            capture.emit = image_payload
        else:
            capture.detection_image_recorder = image_payload
    router = HeadOriginalRouter(port, record, progress=runtime.executor_progress)
    router.bind_primary(observer)
    capture.bind_original_sink(router)
    port.bind_head_original_sink(router)

    capture.begin_live_capture()
    return router


def run_owned_search(composition, handle, *, max_ticks=None, clock=time.monotonic,
                     binding_loader=None, detector_loader=None, detector_builder=None,
                     owner_factory=None, exposure_binder=None):
    """Bind the run's resources in the frozen order and drive the owned search; 0 on lock, else 1."""

    if type(composition) is not HeadExecutionComposition:
        _refuse(RUNNER_REFUSED, 'the runner needs the open composition')
    if not isinstance(handle, dict) or handle.get('stack') is None:
        _refuse(RUNNER_REFUSED, 'the runner needs the provider handle with its stack')
    stack = handle['stack']
    capture = _require_resource(handle, 'capture', 'bind_live_sink', SOURCE_ABSENT,
                                'the entry must supply the camera capture')
    neck = _require_resource(handle, 'neck', 'command_neck', NECK_ABSENT,
                             'the entry must supply the neck transport')
    settlement = handle.get('settlement')
    if not callable(settlement):
        _refuse(SETTLEMENT_ABSENT, 'the entry must supply the settlement check')
    neck_owner = handle.get('neck_owner')
    if neck_owner is None:
        _refuse(OWNER_ABSENT, 'the provider must hand over the activated Head neck owner')
    _require_entry(handle, 'detector_entry')

    inputs = composition.inputs
    policy = composition.policy
    declarations = require_run_declarations(inputs)
    config = resolve_run_search_config(inputs, session_id=inputs.run['session_id'],
                                       attempt_id=inputs.run['epoch'],
                                       search_start_rad=inputs.document['development_pose']['neck_rad'],
                                       binding_loader=binding_loader)
    # Only the neck owner's readback-checked activation may bind controller identity.
    # Assembly snapshots cannot supply this authority.
    state = build_run_local_state(inputs, policy, None, now_s=clock())

    observer = HeadLocalObserver(stack.node, stack.port, state, policy=policy,
                                 camera_frame=config['frame_id'], bind_port_sink=False)
    runtime = HeadLocalRuntime(node=stack.node, port=stack.port, local_state=state, owner=neck_owner,
                               observer=observer, policy=policy,
                               sink=(lambda kind, record, stamp: composition.emit(
                                   kind, record, source_stamp_ns=stamp,
                                   occurrence_mono_ns=record.get('callback_wall_ns')))
                               if composition.event_log_enabled else None)
    router = _bind_originals(composition, capture, stack.port, observer, runtime)
    composition.begin_resource_lifetime('search_runtime')
    original_owner = handle.get('local_ros')
    if original_owner is not None:
        original_owner.retain_originals_until_close(runtime)
    owner = exposure = None
    try:
        scene = handle.get('scene')
        if scene is not None:
            scene.bind_fault(runtime.fault)
        composition.bind_owner(owner=neck_owner)

        built = {}

        def factory():
            built['detector'] = build_run_detector_factory(inputs, loader=detector_loader,
                                                           builder=detector_builder)()
            if 'camera_shape_warmup' in built['detector']:
                if composition.event_log_enabled:
                    runtime.record('HEAD_CAMERA_SHAPE_WARMUP', built['detector']['camera_shape_warmup'])
            return built['detector']

        make_owner = owner_factory or HeadInferenceOwner
        owner = make_owner(factory=factory, fault_callback=runtime.fault, simulation_policy=policy)
        # the inference owner is READY only after its loader finishes (CP-HFP-521); waiting here keeps the
        # call on the owner's own thread and lets a model that cannot load refuse by name inside its bound
        if callable(getattr(owner, 'configuration', None)):
            try:
                owner.configuration(timeout_s=90.0)
            except Exception:
                # the owner records why it failed internally (CP-HFP-527); surface it here or the run
                # reports only that it was not ready and the cause stays invisible in the sealed record
                import sys
                # the operation error carries the metadata of the exception that stopped the loader
                # (CP-HFP-525), so it is preferred over the future's wrapper string
                recorded = getattr(owner, '_operation_error', None)
                if not recorded:
                    recorded = getattr(owner, '_error', None) or 'no reason recorded'
                print('INFERENCE_OWNER_ERROR %s' % (recorded,), file=sys.stderr, flush=True)
                raise
        bind_exposure = exposure_binder or _bind_exposure
        exposure = owner.bind_live(
            lambda detector: bind_exposure(detector, port=stack.port, primary=runtime, policy=policy,
                                           buffer=handle.get('buffer'),
                                           image_recorder=capture.detection_image_recorder),
            timeout_s=1.)
        # the owner's bind answers with its metadata while the exposure it built lives on the owner
        # (CP-HFP-547/549); the capture needs the exposure, so take it from there when needed
        if not callable(getattr(exposure, 'observe', None)):
            exposure = getattr(owner, '_live', exposure)
        detector = built.get('detector') or getattr(owner, 'detector', None)
        declared_device = inputs.document['resources']['cuda_device']
        observed = getattr(owner, 'runtime_device', None)
        if observed != declared_device:
            _refuse(DEVICE_REFUSED, f'the owner reports {observed!r} but the run declares '
                                    f'{declared_device!r}')
        composition.bind_detector(detector, runtime_device=observed)
        composition.bind_inference(owner)
        composition.bind_runtime(observer=observer, runtime=runtime)
        search = OwnedHeadSearch(config=config, primary=runtime, port=stack.port, owner=owner,
                                 settlement=settlement,
                                 stop_velocity_rad_s=config['settle_velocity_rad_s'],
                                 emit=(lambda kind, **record: runtime.record(kind, record))
                                 if composition.event_log_enabled else None,
                                 monotonic=clock, local_state=state, policy=policy)
        search.bind_transport(neck)
        composition.bind_search(search)
        from so101_demo.adapters.act.head_execution_owner_bridge import HeadExecutionOwnerBridge
        owner_bridge = HeadExecutionOwnerBridge(composition)
        handle['execution_owner'] = owner_bridge
        if composition.event_log_enabled:
            composition.emit('EXECUTION_LOOP_BOUND',
                             {'run': inputs.run, 'scope': inputs.execution_scope,
                              'declarations': sorted(declarations)})
        _await_originals(observer, composition, clock=clock)
        guard = _build_trajectory_guard(composition, handle, runtime)
        def admit_initial_move():
            _bind_prepared_transport(composition,handle,runtime,guard)
            if composition.event_log_enabled:
                composition.emit('EXECUTION_OWNER_DESCRIPTOR', owner_bridge.descriptor())
            receipt = owner_bridge.submit_target(config['required_search_domain_rad'][0])
            if handle.get('camera_relay') is not None:
                handle['camera_relay'].cut_after_sdk_return(receipt)
        return _drive(composition, search, runtime, owner, capture, exposure,
                      max_ticks if max_ticks is not None else _loop_bound(policy),
                      after_arm=admit_initial_move)
    finally:
        outcomes = {} if composition.event_log_enabled else None
        report = retire_run_resources(runtime, exposure, owner, outcomes=outcomes,
                             defer_original_retirement=original_owner is not None,
                             emit=(lambda stage, error: composition.emit(
                                 'EXECUTION_LOOP_RETIRE_FAILED', {'stage': stage, 'error': error}))
                             if composition.event_log_enabled else None)
        if composition.event_log_enabled:
            composition.emit('EXECUTION_LOOP_RETIREMENT', {'failures': report, 'outcomes': outcomes})
        composition.finish_resource_lifetime('search_runtime', confirmed=not any(report.values()))
        if any(report.values()):
            _refuse(RUNNER_REFUSED, f'owned retirement unconfirmed: {report}')



def _bind_exposure(detector, *, port, primary, policy, buffer, image_recorder=None):
    """The owner hands back the detector it built; the exposure is bound to it exactly once."""

    reset = getattr(detector, 'reset', None)
    if callable(reset):
        reset()
    return HeadLiveExposures(port=port, buffer=buffer, detector=detector, primary=primary, monitor=None,
                             camera_skew_s=min(.05, policy.perception_max_age_s),
                             image_recorder=image_recorder,
                             emit=(lambda kind, **record: primary.record(kind, record))
                             if primary._sink is not None else None)


def _loop_bound(policy) -> int:
    """A hard tick bound from the sealed search cap and the sealed watchdog period."""

    period = policy.watchdog_period_s
    if type(period) not in (int, float) or period <= 0:
        _refuse(RUNNER_REFUSED, 'the frozen policy declares no usable watchdog period')
    return max(1, min(1_000_000, int(policy.search_timeout_s / period) + 1))


def _await_originals(observer, composition, *, clock=time.monotonic, timeout_s=10.):
    """Bound startup input admission and preserve the first failed boundary."""
    deadline = clock() + timeout_s
    first_error = last_error = None
    while True:
        now = clock()
        try:
            current = observer.current_inputs(now)
        except PermissionError as error:
            last_error = str(error)
            if first_error is None:
                first_error = last_error
            if observer.failed or observer.closed or now >= deadline:
                if composition.event_log_enabled:
                    composition.emit('EXECUTION_STARTUP_INPUT_REFUSED',
                        {'first_error': first_error, 'last_error': last_error,
                         'deadline_wall_s': deadline, 'observed_wall_s': now})
                _refuse(SOURCE_ABSENT, f'{first_error}; latest: {last_error}')
            time.sleep(min(.01, max(0., deadline - now)))
        else:
            if composition.event_log_enabled:
                composition.emit('EXECUTION_STARTUP_INPUT_READY',
                    {'clock_source_ns': current['clock']['source_ns'],
                     'joint_source_ns': current['joint']['source_ns'],
                     'camera_source_ns': current['camera_pair']['source_ns'],
                     'observed_wall_s': now})
            return current


def _build_trajectory_guard(composition, handle, runtime):
    from so101_demo.adapters.act.head_execution_reset import OwnedHeadScene
    from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard
    scene = handle.get('scene')
    if (type(scene) is not OwnedHeadScene or scene.receipt is None or scene.node is not runtime.node
            or scene.inputs is not composition.inputs):
        _refuse(RUNNER_REFUSED,'verified owned full scene/reset is absent')
    scene.observer.snapshot_with_receipt()
    refs = composition.inputs.refs
    guard = HeadTrajectoryGuard(checker=scene.safety.checker, feedback_port=runtime.port,
        scene_observer=scene.observer,node=runtime.node,model_xml_path=refs['scene']['path'],
        geometry_path=refs['camera_geometry']['path'],geometry_sha256=refs['camera_geometry']['sha256'],
        simulation_session_id=composition.inputs.run['session_id'],reset_epoch=scene.receipt['reset_epoch'],
        controller_state_source=runtime.owner.latest_controller_state)
    from so101_demo.act.head_execution_documents import load_search_config
    config = load_search_config(composition.inputs,composition.policy)
    if (config.get('required_search_domain_rad') != guard.search_domain
            or config.get('lock_valid_neck_rad') != guard.safe_interval):
        _refuse(RUNNER_REFUSED,'frozen controller domain differs from bound geometry')
    return guard


def _bind_prepared_transport(composition, handle, runtime, guard):
    from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher
    from so101_demo.adapters.act.head_reference_monitor import HeadReferenceMonitor
    dispatcher = HeadInventoryDispatcher(runtime.port,runtime.owner,runtime.local_state,
        guard=guard,own_inventory=runtime.own_inventory,fault_callback=runtime.fault,
        emit=(lambda kind, **record: runtime.record(kind,record))
        if composition.event_log_enabled else None)
    handle['scene'].bind_admission(runtime=runtime, guard=guard)
    # after acceptance the reference must stay on the sealed quintic; a foreign goal moves it off
    monitor = HeadReferenceMonitor(on_diverged=lambda verdict: runtime.fault(verdict['code'], dict(verdict)))
    runtime.owner.add_controller_state_listener(monitor.observe)
    handle['reference_monitor'] = monitor
    handle['neck'].bind_prepared_head(dispatcher,guard=guard,reference_monitor=monitor,
        stop_handoff=lambda occurred_ns,deadline_ns: runtime.stop('signal',dict(
            occurred_ns=occurred_ns,deadline_ns=deadline_ns)))
    if composition.event_log_enabled:
        composition.emit('EXECUTION_PREPARED_TRANSPORT_BOUND',dict(
            scope=runtime.local_state.scope,reset_epoch=guard.reset_epoch,
            model_semantic_sha256=guard.model_semantic_sha256,geometry_sha256=guard.geometry_sha256))
    return dispatcher


def _drive(composition, search, runtime, owner, capture, exposure, bound_ticks, *, after_arm=None) -> int:
    import signal
    import threading
    stop_requested = threading.Event()
    original_handler = None
    if threading.current_thread() is threading.main_thread():
        original_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda signum, frame: stop_requested.set())
    try:
        return _drive_loop(composition, search, runtime, owner, capture, exposure,
                           bound_ticks, after_arm=after_arm, signal_stop=stop_requested)
    finally:
        if original_handler is not None:
            signal.signal(signal.SIGTERM, original_handler)


def _drive_loop(composition, search, runtime, owner, capture, exposure, bound_ticks, *,
                after_arm=None, signal_stop=None) -> int:
    runtime.start()
    from so101_demo.adapters.act.head_local_runtime import HeadStartupCancelled
    def operator_stop():
        if signal_stop is None or not signal_stop.is_set():return False
        import signal
        result=dict(status='INTERRUPTED',signal=signal.SIGTERM)
        runtime.stop('sigterm',result)
        if composition.event_log_enabled:composition.emit('EXECUTION_OPERATOR_TERMINAL',result)
        return True
    if operator_stop():return 1
    try:
        runtime.arm(cancel_event=signal_stop)
    except HeadStartupCancelled:
        operator_stop()
        return 1
    if operator_stop():return 1
    if after_arm is not None:
        try: after_arm()
        except Exception:
            runtime.fault('HEAD_EXECUTION_TRAJECTORY_BINDING_FAILED')
            raise
    if operator_stop():return 1
    capture.bind_live_sink(exposure.observe)
    if operator_stop():return 1
    owner.activate_live()
    if operator_stop():return 1
    ticks = 0
    while ticks < bound_ticks:
        ticks += 1
        if signal_stop is not None and signal_stop.is_set():
            import signal
            result = dict(status='INTERRUPTED', signal=signal.SIGTERM)
            runtime.stop('sigterm', result)
            if composition.event_log_enabled:
                composition.emit('EXECUTION_OPERATOR_TERMINAL', result)
            return 1
        if runtime.faulted:
            if composition.event_log_enabled:
                composition.emit('EXECUTION_LOOP_RUNTIME_FAULT',
                                 {'ticks': ticks, 'reason': runtime.fault_reason})
            return 1
        try:
            result = search.tick()
        except Exception as error:
            if composition.event_log_enabled:
                composition.emit('EXECUTION_LOOP_REFUSED',
                                 {'ticks': ticks, 'error': type(error).__name__})
            return 1
        if result is not None:
            if composition.event_log_enabled:
                composition.emit('EXECUTION_LOOP_TERMINAL',
                                 {'ticks': ticks, 'status': result.get('status')})
            if result.get('status') == 'TARGET_LOCKED':
                runtime.stop('success',result)
                return 0
            if result.get('status') in ('TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL', 'TARGET_AMBIGUOUS'):
                runtime.stop('not_found', result)
                return 1
            if not runtime.stop_requested:
                runtime.fault('HEAD_EXECUTION_TERMINAL_FAILED')
            return 1
        # Wait at the frozen watchdog cadence so callbacks/inference can
        # progress within the original search deadline and tick bound.
        runtime._shutdown.wait(runtime.policy.watchdog_period_s)
    if composition.event_log_enabled:
        composition.emit('EXECUTION_LOOP_BOUND_REACHED', {'ticks': ticks})
    runtime.fault('HEAD_EXECUTION_LOOP_BOUND_REACHED')
    return 1
