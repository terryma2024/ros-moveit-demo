"""Directed tests for the local inference-owner binding on the local runtime.

The single CUDA owner must bind the local runtime as its live primary, take the
frozen schema-1 stopped observation request, expose the completed-observation
channel and keep the whole reachable call path free of any monitor module.

Cleanup is fixture-owned: a failing assertion must never strand the owner's
non-daemon worker thread, which would keep the whole session from exiting.
"""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from so101_demo.act.head_evidence_identity import digest
from so101_demo.adapters.act.head_inference_owner import HeadInferenceOwner
from test_act_head_local_runtime import armed_runtime, runtime_setup, wait_for


class Detector:
    def __init__(self):
        self.calls = []

    def reset(self):
        self.calls.append('reset')

    def detect(self, pixels, **kwargs):
        self.calls.append(('detect', pixels))
        return []


class LocalLive:
    """A live exposure whose primary is the local runtime and whose model calls are recorded."""

    def __init__(self, primary, policy, *, with_observation_channel=True):
        self.primary = primary
        self._simulation_policy = policy
        self.monotonic = primary.monotonic
        self.activated = 0
        self.inferences = []
        self.completed = []
        if with_observation_channel:
            self.next_completed_observation = self._next_completed_observation

    def activate(self):
        if not self.primary.ready:
            raise PermissionError('LOCAL_LIVE_NOT_READY')
        self.activated += 1

    def infer(self, *, observation_request=None):
        self.inferences.append(None if observation_request is None else dict(observation_request))
        if observation_request is not None:
            self.completed.append(dict(observation_request))
            return dict(observation_request)
        return None

    def freeze_retirement(self):
        return dict(retired=True, inference_calls=len(self.inferences))

    def retirement_snapshot(self):
        return dict(retired=True, inference_calls=len(self.inferences))

    def records_snapshot(self):
        return [dict(row) for row in self.completed]

    def _next_completed_observation(self, after_sequence):
        for row in self.completed:
            if row['observation_sequence'] == after_sequence + 1:
                return dict(row)
        return None


@pytest.fixture
def local(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    owners = []

    def owner_for(policy=None):
        detector = Detector()
        owner = HeadInferenceOwner(
            factory=lambda: dict(runtime=detector, runtime_device='cuda'),
            fault_callback=runtime.fault,
            simulation_policy=row.policy if policy is None else policy)
        owners.append(owner)
        return owner, detector

    def bind(owner, **kwargs):
        live = LocalLive(runtime, row.policy, **kwargs)
        owner.configuration(timeout_s=5.)
        owner.bind_live(lambda built: live, timeout_s=5.)
        owner.activate_live()
        assert wait_for(lambda: live.activated == 1)
        return live

    yield SimpleNamespace(row=row, runtime=runtime, owner_for=owner_for, bind=bind)
    for owner in owners:
        try:
            owner.close(timeout_s=5.)
        except Exception:
            pass
    try:
        runtime.close(timeout_s=1.)
    except Exception:
        pass


def stopped_request(row, *, sequence=1, motion_epoch=0, settled_wall_s=None, requested_wall_s=None,
                    deadline_wall_s=None, settled_source_floor_ns=1):
    policy = row.policy
    now = row.runtime.monotonic()
    scope = row.state.scope
    return dict(epoch=scope['epoch'], generation=scope['generation'], session_id=scope['session_id'],
                policy_sha256=scope['policy_sha256'], schema_version=1,
                simulation_policy_sha256=digest(policy.readback()), motion_epoch=motion_epoch,
                observation_sequence=sequence, settled_source_floor_ns=settled_source_floor_ns,
                settled_wall_s=now - .01 if settled_wall_s is None else settled_wall_s,
                requested_wall_s=now if requested_wall_s is None else requested_wall_s,
                search_deadline_ns=round((now + 10. if deadline_wall_s is None else deadline_wall_s) * 1e9))


def test_local_primary_completes_the_single_owner_live_binding(local):
    owner, detector = local.owner_for()
    live = local.bind(owner)
    assert owner.infer() is None
    retired = owner.close(timeout_s=5.)
    assert retired['retired'] is True and retired['factory_count'] == 1
    assert retired['inference_owner']['daemon'] is False
    assert retired['live']['retired'] is True
    assert detector.calls == []
    assert live.activated == 1


def test_local_observation_request_reaches_the_owned_cuda_channel(local):
    owner, _ = local.owner_for()
    live = local.bind(owner)
    request = stopped_request(local.row)
    bound = owner.request_observation(request)
    assert bound['observation_sequence'] == 1
    assert bound['search_deadline_ns'] == request['search_deadline_ns']
    assert bound['motion_epoch'] == 0
    assert wait_for(lambda: any(row is not None for row in live.inferences))
    delivered = [row for row in live.inferences if row is not None][0]
    assert delivered['observation_sequence'] == 1
    assert wait_for(lambda: owner.next_completed_observation(0) is not None)
    completed = owner.next_completed_observation(0)
    assert completed['observation_sequence'] == 1
    assert owner.next_completed_observation(1) is None


def test_local_observation_request_sequence_is_strict(local):
    owner, _ = local.owner_for()
    live = local.bind(owner)
    assert owner.request_observation(stopped_request(local.row))['observation_sequence'] == 1
    assert wait_for(lambda: len(live.completed) == 1)
    with pytest.raises(PermissionError):
        owner.request_observation(stopped_request(local.row, sequence=1, motion_epoch=0,
                                                  requested_wall_s=local.runtime.monotonic() + .001))
    with pytest.raises(PermissionError):
        owner.request_observation(stopped_request(local.row, sequence=3, motion_epoch=1))


def test_local_observation_request_is_refused_before_the_live_stage(local):
    owner, _ = local.owner_for()
    owner.configuration(timeout_s=5.)
    with pytest.raises(PermissionError):
        owner.request_observation(stopped_request(local.row))


def test_local_observation_passthrough_refuses_a_live_without_the_channel(local):
    owner, _ = local.owner_for()
    local.bind(owner, with_observation_channel=False)
    with pytest.raises(PermissionError):
        owner.next_completed_observation(0)
    assert local.runtime.failed is False and local.runtime.ready is True


def test_local_inference_call_path_imports_no_monitor_module():
    script = '''
import json, sys, time
from so101_demo.act.head_evidence_identity import digest
from so101_demo.act.head_simulation_policy import (HeadSimulationPolicy,
    validate_stopped_observation_request)
from so101_demo.adapters.act.head_inference_owner import HeadInferenceOwner

policy = HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document())
now = time.monotonic()
scope = dict(epoch='epoch-probe', generation=1, session_id='session-probe',
             policy_sha256=digest(policy.readback()))
request = dict(scope, schema_version=1,
               simulation_policy_sha256=digest(policy.readback()), motion_epoch=0,
               observation_sequence=1, settled_source_floor_ns=1, settled_wall_s=now - .01,
               requested_wall_s=now, search_deadline_ns=round((now + 10.) * 1e9))
validate_stopped_observation_request(request, policy=policy, expected_scope=scope, now_wall_s=now)

class Detector:
    def reset(self): return None
    def detect(self, pixels, **kwargs): return []

owner = HeadInferenceOwner(factory=lambda: dict(runtime=Detector(), runtime_device='cuda'),
                           fault_callback=lambda reason: None, simulation_policy=policy)
owner.configuration(timeout_s=5.)
owner.close(timeout_s=5.)
print(json.dumps(sorted(name for name in sys.modules if 'monitor' in name)))
'''
    process = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                             env=dict(os.environ), timeout=180)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout.strip()) == []
