"""The one resource composition of a file-protocol stage-one development run.

A run has an optional evidence writer, one ROS node/controller port, one Head neck
owner (the dead-man, stop window and graph check of the neck controller), one detector, one inference owner, one local
runtime/observer pair and one owned search. This module is the entry's binding
point: when logging is enabled it opens one writer under the fresh run root,
binds each resource exactly once in one fixed order, proves the bound resources
share the same frozen policy and run identity, and seals the run once.

It starts nothing itself: the caller creates the stack, the model and the ROS
context and hands them here, so a run can never grow a second stack, model or
writer behind the entry's back.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping
from pathlib import Path

from so101_demo.act.head_evidence_identity import digest
from so101_demo.act.head_run_evidence import HeadRunEvidence
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from so101_demo.act.head_execution_inputs import (DEVELOPMENT_SCOPE, REQUIRED_CUDA_DEVICE,
                                                   HeadExecutionInputs)

COMPOSITION_REFUSED = 'EXECUTION_COMPOSITION_REFUSED'
RESOURCE_REBOUND = 'EXECUTION_RESOURCE_REBOUND'
COMPOSITION_CLOSED = 'EXECUTION_COMPOSITION_CLOSED'
DEVICE_REFUSED = 'EXECUTION_DEVICE_REFUSED'

#: the one order the entry binds in; a later stage may not appear before its predecessor
BIND_ORDER = ('ros', 'owner', 'detector', 'inference', 'runtime', 'search')


class HeadExecutionCompositionRefused(ValueError):
    """A refused composition step, carrying the exact code the entry records."""

    def __init__(self, code: str, detail: str = '') -> None:
        self.code = code
        self.detail = detail
        super().__init__(f'{code}: {detail}' if detail else code)


def _refuse(code: str, detail: str):
    raise HeadExecutionCompositionRefused(code, detail)


class HeadExecutionComposition:
    """One run's single resource binding, opened from verified execution inputs."""

    def __init__(self, *, inputs, policy, writer, clock_ns=time.monotonic_ns):
        self.inputs = inputs
        self.policy = policy
        self.writer = writer
        self.event_log_enabled = inputs.event_log_enabled
        self.monotonic_ns = clock_ns
        self._bound: dict[str, object] = {}
        self._sealed: dict | None = None
        self._closed = False
        self._resource_lifetimes = {}

    # ---- open --------------------------------------------------------------

    @classmethod
    def open(cls, inputs, *, capacities=None, clock_ns=time.monotonic_ns, fault_callback=None):
        """Open the run's single writer from one verified input document."""

        if type(inputs) is not HeadExecutionInputs:
            _refuse(COMPOSITION_REFUSED, 'the composition needs verified HeadExecutionInputs')
        if inputs.execution_scope != DEVELOPMENT_SCOPE:
            _refuse(COMPOSITION_REFUSED,
                    f'execution_scope {inputs.execution_scope!r} is not {DEVELOPMENT_SCOPE!r}')
        policy_bytes = _sealed_bytes(inputs, 'local_policy')
        try:
            policy = HeadSimulationPolicy.parse(json.loads(policy_bytes.decode('utf-8')))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
            _refuse(COMPOSITION_REFUSED, f'local_policy is not a frozen policy document ({error})')
        writer = None
        if inputs.event_log_enabled:
            manifest = cls.manifest(inputs, policy, opened_wall_s=time.monotonic())
            writer = HeadRunEvidence.create(inputs.run_root, manifest, capacities,
                                            fault_callback=fault_callback)
        return cls(inputs=inputs, policy=policy, writer=writer, clock_ns=clock_ns)

    @staticmethod
    def manifest(inputs, policy, *, opened_wall_s):
        """The run's manifest: the input document, every sealed ref and the frozen policy."""
        from so101_demo.act.head_execution_inputs import _declared_bytes
        freeze_ref=inputs.document['freeze_receipt']
        frozen=json.loads(_declared_bytes('freeze_receipt',freeze_ref['path'],freeze_ref['sha256']))
        return {
            'schema_version': 1,
            'kind': 'head_execution_run',
            'operation': inputs.document['operation'],
            'execution_scope': inputs.execution_scope,
            'run': inputs.run,
            'evidence_root': str(inputs.evidence_root),
            'run_root': str(inputs.run_root),
            'execution_inputs': {'path': str(inputs.document_path),
                                 'sha256': inputs.document_sha256},
            'freeze_receipt': dict(inputs.document['freeze_receipt']),
            'source_manifest': frozen.get('source_manifest'),
            'refs': {name: dict(block) for name, block in sorted(inputs.refs.items())},
            'simulation_policy_sha256': digest(policy.readback()),
            'development_pose': json.loads(json.dumps(inputs.document['development_pose'])),
            'resources_declared': dict(inputs.document['resources']),
            'ros_declared': json.loads(json.dumps(inputs.document['ros'])),
            'opened_wall_s': opened_wall_s,
            'writer_owner': 'entry',
        }

    # ---- binding -----------------------------------------------------------

    def _require_open(self):
        if self._closed:
            _refuse(COMPOSITION_CLOSED, 'the run composition is already closed')

    def _same_policy(self, candidate):
        """True when the candidate carries the exact frozen policy document."""

        try:
            return digest(candidate.readback()) == digest(self.policy.readback())
        except (AttributeError, TypeError, ValueError):
            return False

    def _require_stage(self, stage: str):
        self._require_open()
        index = BIND_ORDER.index(stage)
        missing = [earlier for earlier in BIND_ORDER[:index] if earlier not in self._bound]
        if missing:
            _refuse(COMPOSITION_REFUSED, f'{stage} requires {missing} to be bound first')
        if stage in self._bound:
            _refuse(RESOURCE_REBOUND, f'{stage} is already bound for this run')

    def _bind(self, stage: str, value):
        self._bound[stage] = value
        if self.event_log_enabled:
            stamp = self.monotonic_ns()
            self.writer.append('EXECUTION_RESOURCE_BOUND', {'stage': stage, 'run': self.inputs.run},
                               source_stamp_ns=None, observed_mono_ns=stamp,
                               occurrence_mono_ns=stamp)
        return value

    @property
    def bound_stages(self):
        return tuple(stage for stage in BIND_ORDER if stage in self._bound)

    @property
    def complete(self):
        return len(self._bound) == len(BIND_ORDER)

    def bind_ros(self, stack=None, *, node=None, port=None):
        """Bind the ros stage: either the launcher stack that owns the graph, or the node and port pair.

        The approved plan makes RestartStack the owner of the ROS graph as child processes (CP-HFP-194), so a
        stack is the natural ros binding; the node/port form stays for callers that genuinely hold in-process
        objects. Exactly one of the two forms must be given.
        """

        self._require_stage('ros')
        if stack is not None:
            if node is not None or port is not None:
                _refuse(COMPOSITION_REFUSED, 'bind the ros stage with either a stack or a node/port pair')
            if not callable(getattr(stack, 'start', None)):
                _refuse(COMPOSITION_REFUSED, 'the ros stack must expose its start method')
            if getattr(stack, 'controller_config_path', None) is None:
                _refuse(COMPOSITION_REFUSED, 'the ros stack must carry its controller configuration')
            return self._bind('ros', {'stack': stack,
                                      'environment': dict(getattr(stack, 'environment', {}) or {})})
        if node is None or port is None:
            _refuse(COMPOSITION_REFUSED, 'bind the ros stage with either a stack or a node/port pair')
        if any(not callable(getattr(node, name, None)) for name in ('get_clock', 'create_subscription')):
            _refuse(COMPOSITION_REFUSED, 'node must be the entry ROS node')
        if getattr(port, 'node', None) is not node or getattr(port, 'names', None) != ('neck_yaw_joint',):
            _refuse(COMPOSITION_REFUSED, 'port must be the entry controller port on that node')
        bound_policy = getattr(getattr(port, 'feedback_policy', None), '_bound_simulation_policy', None)
        if bound_policy is None or digest(bound_policy.readback()) != digest(self.policy.readback()):
            _refuse(COMPOSITION_REFUSED, 'the controller port is not bound to the frozen policy')
        return self._bind('ros', {'node': node, 'port': port})

    def bind_owner(self, *, owner):
        """Bind the Head neck owner: it must carry the run's generation and session."""

        self._require_stage('owner')
        run = self.inputs.run
        if (getattr(owner, 'generation', None) != run['generation']
                or getattr(owner, 'session_id', None) != run['session_id']
                or any(not callable(getattr(owner, name, None))
                       for name in ('identity', 'readback', 'close_planned', 'close_fault'))):
            _refuse(COMPOSITION_REFUSED,
                    'the neck owner must share the run generation and session and expose the owner API')
        return self._bind('owner', {'owner': owner})

    def bind_detector(self, detector, *, runtime_device):
        """Bind the one built model with the device actually observed at construction."""

        self._require_stage('detector')
        declared = self.inputs.document['resources']
        if runtime_device != declared['cuda_device'] or runtime_device != REQUIRED_CUDA_DEVICE:
            _refuse(DEVICE_REFUSED,
                    f'observed runtime device {runtime_device!r} is not {REQUIRED_CUDA_DEVICE!r}')
        if declared['allow_cpu_fallback'] is not False:
            _refuse(DEVICE_REFUSED, 'the run must not allow a CPU fallback')
        if detector is None:
            _refuse(COMPOSITION_REFUSED, 'the detector must be the one built model')
        return self._bind('detector', detector)

    def bind_inference(self, owner):
        """Bind the single inference owner that owns every CUDA call."""

        self._require_stage('inference')
        if any(not callable(getattr(owner, name, None)) for name in
               ('configuration', 'request_observation', 'next_completed_observation', 'close')):
            _refuse(COMPOSITION_REFUSED, 'the inference owner lacks the frozen owner API')
        if not self._same_policy(getattr(owner, '_simulation_policy', None)):
            _refuse(COMPOSITION_REFUSED, 'the inference owner is not bound to the frozen policy')
        return self._bind('inference', owner)

    def bind_runtime(self, *, observer, runtime):
        """Bind the local observer/runtime pair on the same port, state and policy."""

        self._require_stage('runtime')
        port = self._bound['ros']['port']
        if (getattr(observer, 'port', None) is not port or getattr(runtime, 'port', None) is not port
                or getattr(runtime, 'observer', None) is not observer
                or not self._same_policy(getattr(observer, 'policy', None))
                or not self._same_policy(getattr(runtime, 'policy', None))):
            _refuse(COMPOSITION_REFUSED,
                    'observer/runtime must share the entry port and the frozen policy document')
        state = getattr(runtime, 'local_state', None)
        expected = self.inputs.run
        if (getattr(observer, 'local_state', None) is not state or state is None
                or state.scope['policy_sha256'] != digest(self.policy.readback())
                or state.scope['epoch'] != expected['epoch']
                or state.scope['session_id'] != expected['session_id']
                or state.scope['generation'] != expected['generation']):
            _refuse(COMPOSITION_REFUSED,
                    'the local state must carry the sealed policy hash and the execution-input run identity')
        return self._bind('runtime', {'observer': observer, 'runtime': runtime})

    def bind_search(self, search):
        """Bind the owned search to that same local state; it may not open another one."""

        self._require_stage('search')
        state = self._bound['runtime']['runtime'].local_state
        if getattr(search, '_local_state', None) is not state or getattr(search, 'search_state', None) is None:
            _refuse(COMPOSITION_REFUSED,
                    'the owned search must be committed to the composition local state')
        return self._bind('search', search)

    # ---- use and seal ------------------------------------------------------

    def emit(self, kind, record, *, source_stamp_ns=None, observed_mono_ns=None,
             occurrence_mono_ns=None):
        """Enqueue one bounded event on the run's single writer."""

        self._require_open()
        if not self.event_log_enabled:
            return None
        stamp = self.monotonic_ns()
        return self.writer.append(
            kind, record, source_stamp_ns=source_stamp_ns,
            observed_mono_ns=stamp if observed_mono_ns is None else observed_mono_ns,
            occurrence_mono_ns=stamp if occurrence_mono_ns is None else occurrence_mono_ns)

    def add_artifact(self, data, *, media_type, suffix):
        self._require_open()
        if not self.event_log_enabled:
            return None
        return self.writer.add_artifact(data, media_type=media_type, suffix=suffix)

    def begin_resource_lifetime(self, name):
        self._require_open()
        if name in self._resource_lifetimes:
            _refuse(COMPOSITION_REFUSED, f'duplicate resource lifetime: {name}')
        self._resource_lifetimes[name] = False

    def finish_resource_lifetime(self, name, *, confirmed):
        self._require_open()
        if name not in self._resource_lifetimes or type(confirmed) is not bool:
            _refuse(COMPOSITION_REFUSED, f'unknown resource lifetime: {name}')
        self._resource_lifetimes[name] = confirmed

    def seal(self, completion, *, timeout_s=None):
        """Seal the run once; the completion must not claim the process OS return code."""

        self._require_open()
        unretired = [name for name, confirmed in self._resource_lifetimes.items() if not confirmed]
        if unretired:
            _refuse('EXECUTION_PRODUCERS_UNRETIRED', f'closure unconfirmed: {unretired}')
        if not isinstance(completion, Mapping):
            _refuse(COMPOSITION_REFUSED, 'the seal needs a completion mapping')
        self._closed = True
        if not self.event_log_enabled:
            if not self.complete:
                missing = [stage for stage in BIND_ORDER if stage not in self._bound]
                _refuse(COMPOSITION_REFUSED, f'incomplete composition: missing {missing}')
            return dict(completion, complete_composition=True, file_evidence_generated=False)
        if not self.complete:
            missing = [stage for stage in BIND_ORDER if stage not in self._bound]
            stamp = self.monotonic_ns()
            self.writer.append('EXECUTION_INCOMPLETE_COMPOSITION', {'missing': missing},
                               source_stamp_ns=None, observed_mono_ns=stamp,
                               occurrence_mono_ns=stamp)
            try:
                self.writer.finish(dict(completion, complete_composition=False,
                                        missing_stages=missing), timeout_s=timeout_s)
            except Exception as error:
                _refuse(COMPOSITION_REFUSED,
                        f'incomplete composition sealed as a failure ({type(error).__name__})')
            _refuse(COMPOSITION_REFUSED, f'incomplete composition: missing {missing}')
        self._sealed = self.writer.finish(dict(completion, complete_composition=True),
                                          timeout_s=timeout_s)
        return self._sealed

    @property
    def sealed(self):
        return None if self._sealed is None else dict(self._sealed)

    @property
    def closed(self):
        return self._closed

    def readback(self):
        return {
            'run': self.inputs.run,
            'execution_scope': self.inputs.execution_scope,
            'run_root': str(self.inputs.run_root),
            'execution_inputs_sha256': self.inputs.document_sha256,
            'simulation_policy_sha256': digest(self.policy.readback()),
            'bound_stages': self.bound_stages,
            'complete': self.complete,
            'device': self.inputs.document['resources']['cuda_device'],
            'allow_cpu_fallback': self.inputs.document['resources']['allow_cpu_fallback'],
            'sealed': self.sealed is not None,
            'closed': self.closed,
            'event_log_enabled': self.event_log_enabled,
            'save_all_rgb_frames': self.inputs.save_all_rgb_frames,
            'file_evidence_generated': self.writer is not None,
        }


def _sealed_bytes(inputs, name):
    """Re-read one sealed ref as a plain regular file (inputs already verified the digest)."""

    from so101_demo.act import head_execution_inputs as module

    block = inputs.refs[name]
    return module._read_plain(f'refs.{name}', Path(block['path']))


def run_head_execution(inputs, *, evidence=None):
    """Open the one composition for these inputs and return it to the entry.

    The entry receives the composition, creates the stack/model/ROS context and
    binds them through the documented order; this helper only enforces that the
    run starts from verified inputs and that exactly one writer exists. Resource
    construction stays with the entry because only it may start the stack.
    """

    if evidence is not None and not callable(evidence):
        _refuse(COMPOSITION_REFUSED, 'evidence must be callable or None')
    composition = HeadExecutionComposition.open(inputs, fault_callback=evidence)
    return composition
