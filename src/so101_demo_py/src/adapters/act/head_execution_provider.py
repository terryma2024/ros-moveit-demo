"""The installed resource provider of one stage-one development run.

The formal entry (`run --execution-inputs`) resolves this module and calls
`provide(composition, inputs)`. The provider is the only place that constructs a
run's stack, model, native pair and local search, and it constructs them from the
sealed execution inputs alone: no ambient default, no second stack, no fallback.

Resolution is explicit and fail-closed. Every constructor is named by module and
attribute and must exist in the installed tree; the closed-loop runner that
drives the owned search is named the same way, so a tree without it refuses the
run instead of pretending to execute one. Assembly is ordered, binds every
resource through the composition exactly once, and tears the already-built
resources down on any failure so a refused run leaks neither a stack nor a thread.
"""

from __future__ import annotations

import os
import math
import threading
import time

from pathlib import Path

import importlib
from collections.abc import Mapping

from so101_demo.act.head_execution_inputs import DEVELOPMENT_SCOPE, HeadExecutionInputs

PROVIDER_REFUSED = 'EXECUTION_PROVIDER_REFUSED'
RESOURCE_ABSENT = 'EXECUTION_PROVIDER_RESOURCE_ABSENT'
RUNNER_ABSENT = 'EXECUTION_PROVIDER_RUNNER_ABSENT'
LOCAL_SET_ABSENT = 'EXECUTION_PROVIDER_LOCAL_SET_ABSENT'
ADMISSION_ABSENT = 'EXECUTION_PROVIDER_ADMISSION_ABSENT'
SCOPE_REFUSED = 'EXECUTION_PROVIDER_SCOPE_REFUSED'

#: the installed constructors of this run's resources, in binding order
RESOURCE_MODULES = {
    'stack': ('so101_demo.act.head_execution_stack', 'RestartStack'),
    'detector': ('so101_demo.adapters.act.detector', 'build_bound_head_detector'),
    'native': ('so101_demo.adapters.act.head_reservation_authority', 'HeadReservationAuthority'),
    'revoker': ('so101_demo.adapters.act.head_revocation', 'NativeRevocationClient'),
}

#: the closed-loop driver of the owned search on those resources
RUNNER_MODULE = ('so101_demo.cli.head_execution_runner', 'run_owned_search')

#: the composition binding each constructed resource goes through
RESOURCE_BINDING = {
    'stack': 'bind_ros',
    # native, revoker and detector are constructed and bound by the runner: bind_detector needs
    # native bound first, and bind_authority compares the authority's guard and fault to the local
    # runtime's own methods, so both must happen after that runtime exists
}


class HeadExecutionProviderRefused(RuntimeError):
    """A refused provider step, carrying the exact code the entry records."""

    def __init__(self, code: str, detail: str = '') -> None:
        self.code = code
        self.detail = detail
        super().__init__(f'{code}: {detail}' if detail else code)


class _OwnedLocalROS:
    """Retire only this provider's node, private context and executor threads."""

    def __init__(self):
        self.context = self.node = self.port = None
        self.buffer = self.listener = None
        self.stop = threading.Event()
        self.threads = []
        self.original_runtimes = []

    def retain_originals_until_close(self, runtime):
        if self.stop.is_set() or runtime.node is not self.node and self.node is not None:
            raise PermissionError('HEAD_ORIGINAL_OWNER_INVALID')
        if any(runtime is other for other in self.original_runtimes):
            raise PermissionError('HEAD_ORIGINAL_OWNER_REBOUND')
        self.original_runtimes.append(runtime)

    def close(self):
        self.stop.set()
        deadline = time.monotonic() + 1.
        for thread in self.threads:
            thread.join(max(0., deadline - time.monotonic()))
        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError('HEAD_LOCAL_EXECUTOR_RETIRE_UNCONFIRMED')
        from so101_demo.act.head_execution_documents import retirement_unconfirmed
        original_receipts = [runtime.retire_originals(timeout_s=max(0., deadline-time.monotonic()))
                             for runtime in self.original_runtimes]
        if any(retirement_unconfirmed(receipt) for receipt in original_receipts):
            raise RuntimeError('HEAD_LOCAL_ORIGINAL_RETIRE_UNCONFIRMED')
        if self.port is not None:
            from so101_demo.act.head_execution_documents import retirement_unconfirmed
            receipt = self.port.close_head_io(timeout_s=max(0., deadline - time.monotonic()))
            if retirement_unconfirmed(receipt):
                raise RuntimeError('HEAD_LOCAL_IO_RETIRE_UNCONFIRMED')
        if self.node is not None:
            if self.listener is not None:
                self.listener.unregister()
            if self.buffer is not None:
                self.buffer.jump_handle.unregister()
            self.node.destroy_node()
        if self.context is not None and self.context.ok():
            self.context.shutdown()
        return {'retired': True, 'executor_threads_alive': False,
                'context_shutdown': True, 'originals': original_receipts}


def _refuse(code: str, detail: str):
    raise HeadExecutionProviderRefused(code, detail)


def _resolve(module_name: str, attribute: str, *, code: str, what: str):
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    candidate = getattr(module, attribute, None)
    if not callable(candidate):
        if code == RUNNER_ABSENT:
            return None
        _refuse(code, f'{what} {module_name}.{attribute} is not an installed callable')
    return candidate



def _run_node_name(run_id) -> str:
    """The ROS node name of one run: the run id sanitised, because ROS forbids anything else."""

    import re

    sanitised = re.sub(r'[^A-Za-z0-9_]', '_', str(run_id))
    if not sanitised or not (sanitised[0].isalpha() or sanitised[0] == '_'):
        sanitised = 'r_' + sanitised
    return 'head_run_' + sanitised


def _admission_material(inputs) -> bool:
    """True only when the sealed inputs name the detector binding material (CP-HFP-079)."""

    # snapshot_root is a declared top-level directory field (CP-HFP-099), never a ref, so the
    # predicate reads the sealed pair from the refs and the root from the document
    if inputs.execution_scope == DEVELOPMENT_SCOPE:
        return ({'development_config','weights','frozen_c','camera_geometry'} <= set(inputs.refs)
                and 'snapshot_root' in inputs.document)
    return ({'binding', 'report'} <= set(inputs.refs) and 'snapshot_root' in inputs.document)


def resource_plan(inputs, *, modules: Mapping | None = None):
    """Resolve the installed constructors and their exact arguments from verified inputs."""

    if type(inputs) is not HeadExecutionInputs:
        _refuse(PROVIDER_REFUSED, 'the provider needs verified HeadExecutionInputs')
    if inputs.execution_scope != DEVELOPMENT_SCOPE:
        _refuse(SCOPE_REFUSED, f'{inputs.execution_scope!r} is not {DEVELOPMENT_SCOPE!r}')
    stop_declaration = inputs.document.get('stop_declaration', {})
    teardown_timeout_s = stop_declaration.get('teardown_timeout_s')
    if (type(teardown_timeout_s) not in (int, float)
            or not math.isfinite(teardown_timeout_s) or teardown_timeout_s <= 0):
        _refuse(PROVIDER_REFUSED, 'the run must declare a positive finite teardown timeout')
    declared = inputs.document['resources']
    if declared['cuda_device'] != 'cuda:0' or declared['allow_cpu_fallback'] is not False:
        _refuse(PROVIDER_REFUSED, 'the run must declare cuda:0 with no CPU fallback')
    table = dict(RESOURCE_MODULES) if modules is None else dict(modules)
    constructors, missing = {}, []
    for stage, (module_name, attribute) in table.items():
        constructor = _resolve(module_name, attribute, code=RESOURCE_ABSENT, what=stage)
        if constructor is None:
            missing.append(f'{stage}={module_name}.{attribute}')
        else:
            constructors[stage] = constructor
    if missing:
        _refuse(RESOURCE_ABSENT, 'not installed: ' + ', '.join(sorted(missing)))
    runner = _resolve(*RUNNER_MODULE, code=RUNNER_ABSENT, what='runner')
    refs = {name: dict(block) for name, block in sorted(inputs.refs.items())}
    plan = {
        'run': inputs.run,
        'scope': inputs.execution_scope,
        'refs': refs,
        'ros': dict(inputs.document['ros']),
        'resources': dict(declared),
        'pose': inputs.document['development_pose'],
        # the authority needs a native endpoint, never a sealed file (CP-HFP-181)
        'constructors': {
            'stack': {'callable': constructors['stack'],

                      'keywords': {'controller_config_path': refs['controller_config']['path'],
                                   'session_id': inputs.run['session_id'],
                                   'teardown_timeout_s': teardown_timeout_s,
                                   # the stack spawns its children with this mapping (CP-HFP-586), so it carries the run's
                                   # environment — and with it the PYTHONPATH the controller spawner needs
                                   'environment': dict(os.environ,
                                                       **inputs.document['ros']['environment']),
                                   # the real transport needs the model, the scene, the plugin descriptor
                                   # and the workspace it runs in (CP-HFP-188); the first three come from
                                   # verified refs and the workspace from the declared ROS environment
                                   'urdf_path': refs['urdf']['path'],
                                   'scene_path': refs['scene']['path'],
                                   'plugin_config_path': refs['mujoco_plugin']['path'],
                                   'workspace': inputs.document['ros']['environment'].get(
                                       'ROS_WORKSPACE', str(inputs.evidence_root))}},
            'detector': {'callable': constructors['detector'],
                         'keywords': {'path': refs['development_config']['path'],
                                      'weights': refs['weights']['path'],
                                      'weights_sha256': refs['weights']['sha256'],
                                      'cuda_device': declared['cuda_device'],
                                      'allow_cpu_fallback': declared['allow_cpu_fallback']}},
            'native': {'callable': constructors['native'],
                       'keywords': {}},
            'revoker': {'callable': constructors['revoker'],
                        'keywords': {}},
        },
        'native_provisioning': True,
        'runner': None if runner is None else {'callable': runner, 'module': RUNNER_MODULE},
    }
    return plan


def assemble(composition, inputs, *, plan):
    """Construct every planned resource in binding order, bind it once, return the handle."""

    built: list[tuple[str, object]] = []
    handle: dict[str, object] = {'run': dict(inputs.run), 'scope': inputs.execution_scope}
    composition.begin_resource_lifetime('provider_ros')
    try:
        stack_entry = plan['constructors']['stack']
        stack = stack_entry['callable'](**stack_entry['keywords'])
        built.append(('stack', stack))
        # the approved plan makes the stack the owner of the ROS graph as child processes, so the ros
        # stage binds the stack itself (CP-HFP-194); a stack that also carries an in-process node and port
        # is bound the old way, which keeps the legacy callers working
        node, port = getattr(stack, 'node', None), getattr(stack, 'port', None)
        # ros is bound exactly once per path: a stack that carries an in-process node and port is bound
        # here, and a launcher stack is bound below, after the run has built its own local set (CP-HFP-216)
        if node is not None and port is not None:
            composition.bind_ros(node=node, port=port)
        handle['stack'] = stack
        if node is None or port is None:
            local_ros = _OwnedLocalROS()
            # Stack shutdown precedes original-producer/executor retirement.
            built.insert(0, ('local_ros', local_ros))
            handle['local_ros'] = local_ros
            # the launcher stack owns the graph as child processes, so the run builds its own local set
            # exactly as the phase-one reference does (CP-HFP-209/212): node, action client, controller
            # port bound to the frozen policy, the stopped capture, the settlement callable and the
            # authority endpoint the provision socket names. Nothing here is invented.
            try:
                from rclpy.context import Context
                from rclpy.node import Node
                from rclpy.parameter import Parameter
                from rclpy.action import ActionClient
                from control_msgs.action import FollowJointTrajectory
                from so101_demo.adapters.act.ros_neck import RosControllerPort
                from so101_demo.adapters.act.head_stopped_capture import (
                    StoppedHeadCapture)
                from so101_demo.act.head_feedback import bound_goal_settlement

                import rclpy
                context = Context()
                local_ros.context = context
                rclpy.init(context=context)
                local_node = Node(_run_node_name(inputs.run['run_id']), context=context,
                                   parameter_overrides=[Parameter('use_sim_time', value=True)])
                local_ros.node = local_node
                from tf2_ros import Buffer, TransformListener
                local_ros.buffer = Buffer(node=local_node)
                local_ros.listener = TransformListener(local_ros.buffer, local_node,
                                                       spin_thread=False)
                handle['buffer'] = local_ros.buffer
                client = ActionClient(local_node, FollowJointTrajectory,
                                       '/neck_controller/follow_joint_trajectory')
                from so101_demo.act.head_feedback import FeedbackPolicy
                # the feedback document must be bound to the run policy, otherwise the unbound fallback
                # triple refuses it (CP-HFP-220); FeedbackPolicy.parse accepts an already-parsed policy,
                # so the port's own parse call passes it through unchanged
                bound_feedback = FeedbackPolicy.parse(composition.policy.feedback_values(),
                                                       simulation_policy=composition.policy)
                import json
                development_config = json.loads(
                    Path(inputs.refs['development_config']['path']).read_text(encoding='utf-8'))
                development_values = development_config['values']
                local_port = RosControllerPort(local_node, client, ('neck_yaw_joint',),
                                                stop_velocity_rad_s=development_values['stop_velocity_rad_s'],
                                                max_age_s=development_values['max_age_s'],
                                                feedback_policy=bound_feedback)
                local_ros.port = local_port
                capture = StoppedHeadCapture(local_node, local_port,
                                              frame_id=development_config['camera']['frame_id'],
                                              strict=False, emit=lambda *arguments, **keywords: None)
                from so101_demo.adapters.act.ros_neck import RosNeckSearchPort
                # MUJOCO_DEVELOPMENT_UNQUALIFIED scope (plan lines 163/207, CP-HFP-273): the run's values
                # come from the development config it declares, and the neck duration from the declared search
                # timeout — this scope requires neither a qualified report nor a calibration bundle
                search_timeout_s = float(development_values.get('search_timeout_s') or 30.0)
                neck = RosNeckSearchPort(local_node, session_id=str(inputs.run['session_id']),
                                  attempt_id=str(inputs.run['epoch']), goal_duration_s=search_timeout_s,
                                  submit_lead_s=float(development_values['submit_lead_s']),
                                  stop_timeout_s=float(development_values['stop_latency_s']),
                                  stop_velocity_rad_s=float(development_values['stop_velocity_rad_s']),
                                  max_age_s=float(development_values['max_age_s']),
                                  command_guard=lambda *arguments, **keywords: False,
                                  controller_port=local_port, feedback_policy=bound_feedback)
                handle['node'], handle['port'] = local_node, local_port
                # the launcher stack owns the ROS graph as child processes (plan line 194) and starts
                # it itself (CP-HFP-569): without a live graph the observer receives nothing and the
                # runtime cannot arm, which is what runs 076-087 measured
                stack_resource = handle.get('stack')
                if callable(getattr(stack_resource, 'start', None)):
                    stack_resource.start()
                # Spin each distinct node on its own context. In production,
                # the provider, stack and port refer to the same owned node.
                spin_nodes = []
                for candidate in (handle.get('node'),
                                   getattr(handle.get('stack'), 'node', None),
                                   getattr(handle.get('stack'), 'port', None)):
                    candidate_node = getattr(candidate, 'node', candidate)
                    if (candidate_node is not None
                            and all(candidate_node is not seen for seen in spin_nodes)):
                        spin_nodes.append(candidate_node)
                spin_node = spin_nodes[0] if spin_nodes else None
                if spin_node is not None:
                    def spin_owned_node(node=spin_node):
                        executor = None
                        try:
                            from rclpy.executors import SingleThreadedExecutor
                            # This node owns a private context. The global executor
                            # used by rclpy.spin_once belongs to the default context.
                            executor = SingleThreadedExecutor(context=node.context)
                            executor.add_node(node)
                            turns = 0
                            last_report = time.monotonic()
                            while node.context.ok() and not local_ros.stop.is_set():
                                executor.spin_once(timeout_sec=.1)
                                turns += 1
                                now = time.monotonic()
                                if turns % 200 == 0 or now - last_report > 5.0:
                                    last_report = now
                                    print('SPIN_TURNS %d' % turns, flush=True)
                        except Exception as error:
                            import sys
                            if not local_ros.stop.is_set():
                                print('LOCAL_SPIN_STOPPED %s: %s'
                                      % (type(error).__name__, error),
                                      file=sys.stderr, flush=True)
                            return
                        finally:
                            if executor is not None:
                                executor.shutdown(timeout_sec=1.)

                    for index, node_to_spin in enumerate(spin_nodes):
                        thread = threading.Thread(target=spin_owned_node, args=(node_to_spin,),
                                                       name='head-local-spin-%d' % index,
                                                       daemon=True)
                        local_ros.threads.append(thread)
                        thread.start()
                handle['capture'], handle['neck'] = capture, neck
                handle['settlement'] = bound_goal_settlement
                composition.bind_ros(node=local_node, port=local_port)
            except Exception as error:
                _refuse(LOCAL_SET_ABSENT,
                        f'the run could not build its local set ({type(error).__name__}: {error})')


        # the runner reads stack.node and stack.port directly (CP-HFP-510). When the plan's stack is the
        # launcher form the provider built its own local set, so those two are bound onto the stack the
        # run owns; when the stack already carries them this is a no-op.
        stack_resource = handle.get('stack')
        if stack_resource is not None and getattr(stack_resource, 'node', None) is None:
            provider_node = locals().get('local_node')
            provider_port = locals().get('local_port')
            if provider_node is not None and provider_port is not None:
                try:
                    stack_resource.node = provider_node
                    stack_resource.port = provider_port
                except Exception:
                    pass
        if plan.get('native_provisioning') is True:
            from .head_execution_native import provision_owned_native
            credentials = provision_owned_native(inputs, stack, composition.policy)
            handle['native_provisions'] = credentials['provision_receipts']
            handle['native_child'] = credentials['native_child']
            composition.emit('NATIVE_CHILD_BOUND', credentials['native_child'])
            composition.emit('NATIVE_PROVISIONS', credentials['provision_receipts'])
            for stage, key in (('native', 'native_keywords'), ('revoker', 'revoker_keywords')):
                handle[stage + '_entry'] = dict(plan['constructors'][stage],
                                               keywords=credentials[key])
        else:
            # Explicit constructor injection is used by directed tests. Native
            # production constructors refuse empty/missing scope themselves.
            handle['native_entry'] = dict(plan['constructors']['native'])
            handle['revoker_entry'] = dict(plan['constructors']['revoker'])
        if plan.get('native_provisioning') is True:
            from .head_execution_scene import load_scene_safety
            from .head_execution_reset import OwnedHeadScene, rebase_startup_originals
            safety = load_scene_safety(inputs)
            scene = OwnedHeadScene(node=stack.node, inputs=inputs, safety=safety,
                max_age_s=composition.policy.feedback_receipt_timeout_s,
                startup_ready=stack.wait_startup,
                emit=lambda kind, record: composition.emit(kind, record))
            # Keep scene originals through stack teardown, then retire this
            # subscription before its owned node/context closes.
            built.insert(max(0,len(built)-1), ('scene',scene))
            handle['scene'] = scene
            reset_receipt = scene.reset()
            rebase_startup_originals(handle['capture'],stack.port,reset_receipt)
            scene.resume()
        handle['detector_entry'] = dict(plan['constructors']['detector'])
        handle['built'] = tuple(stage for stage, _ in built)
        return handle
    except Exception:
        failures = teardown(built)
        composition.finish_resource_lifetime('provider_ros', confirmed=not failures)
        _preserve_stack_log(composition, handle.get('stack'))
        if failures:
            composition.emit('EXECUTION_PROVIDER_RETIRE_FAILED', {'failures': failures})
        raise


def bind_local(composition, *, owner, observer, runtime, search):
    """Bind the locally constructed owner/observer/runtime/search through the composition."""

    composition.bind_inference(owner)
    composition.bind_runtime(observer=observer, runtime=runtime)
    composition.bind_search(search)
    return {'owner': owner, 'observer': observer, 'runtime': runtime, 'search': search}


def teardown(built):
    """Best-effort reverse teardown; a failing close is reported, never hidden."""

    failures = []
    for stage, resource in reversed(list(built)):
        for name in ('close', 'stop', 'shutdown'):
            candidate = getattr(resource, name, None)
            if callable(candidate):
                children = tuple(getattr(resource,'processes',())) if stage == 'stack' else ()
                try:
                    receipt = candidate()
                    if stage == 'stack':
                        resource.head_retirement_receipt = receipt
                    from so101_demo.act.head_execution_documents import retirement_unconfirmed
                    if retirement_unconfirmed(receipt):
                        failures.append((stage, name, 'HEAD_RETIREMENT_UNCONFIRMED'))
                except Exception as error:
                    failures.append((stage, name, type(error).__name__))
                if children:
                    resource.head_retirement_children = [dict(pid=p.pid,rc=p.poll(),argv=p.args)
                                                         for p in children]
                    if any(p.poll() is None for p in children):
                        failures.append((stage,name,'HEAD_CHILD_EXIT_UNCONFIRMED'))
                break
    return failures


def provide(composition, inputs, *, plan=None):
    """The installed provider: resolve, construct, bind, run the owned search, tear down."""

    injected = plan is not None
    plan = resource_plan(inputs) if plan is None else plan
    if plan is None and not _admission_material(inputs):
        _refuse(ADMISSION_ABSENT,
                'the sealed inputs name no binding, report or owned snapshot root, so no model could '
                'be built; refusing before any resource is constructed')
    if not injected and not _admission_material(inputs):
        _refuse(ADMISSION_ABSENT,
                'the sealed inputs name no development detector material or declared snapshot root, so no '
                'model could be built; refusing before any resource is constructed')
    if plan.get('runner') is None:
        _refuse(RUNNER_ABSENT,
                f'the closed-loop runner {RUNNER_MODULE[0]}.{RUNNER_MODULE[1]} is not installed; '
                'this run would have nothing to drive the owned search, so it refuses before '
                'constructing any resource')
    handle = assemble(composition, inputs, plan=plan)
    try:
        if inputs.execution_scope == 'MUJOCO_DEVELOPMENT_UNQUALIFIED':
            # the development scope composes its detector block instead of validating a sealed
            # calibration document it does not have (CP-HFP-536): one injected loader, nothing else
            from so101_demo.act.head_execution_documents import development_detector_loader
            return plan['runner']['callable'](composition, handle,
                                              detector_loader=development_detector_loader(inputs))
        return plan['runner']['callable'](composition, handle)
    finally:
        failures = teardown([(stage, handle[stage]) for stage in ('local_ros', 'scene', 'stack')
                  if stage in handle])
        composition.finish_resource_lifetime('provider_ros', confirmed=not failures)
        _preserve_stack_log(composition, handle.get('stack'))
        if failures:
            composition.emit('EXECUTION_PROVIDER_RETIRE_FAILED', {'failures': failures})
            _refuse(PROVIDER_REFUSED, f'owned teardown failed: {failures}')


def _preserve_stack_log(composition, stack):
    """Retain the closed child log before sealing; no atexit producer mutates a seal."""
    path = getattr(stack, 'log_path', None)
    children = getattr(stack,'head_retirement_children',None)
    receipt = getattr(stack, 'head_retirement_receipt', None)
    if isinstance(receipt, dict):
        composition.emit('EXECUTION_STACK_RETIREMENT', receipt)
    if children is not None:
        composition.emit('EXECUTION_CHILD_RETIREMENT', {'children':children})
    if path is not None and Path(path).is_file():
        ref = composition.add_artifact(Path(path).read_bytes(), media_type='text/plain', suffix='log')
        composition.emit('EXECUTION_STACK_LOG', {'artifact': ref, 'source_path': str(path)})
