"""Directed tests for the local primary surface the D callers consume.

These are the exact attributes the stopped-demand exposure, the inference owner
and the owned search read from their `primary`: the frozen local scope view,
readiness/fault flags, the one-shot selected-exposure deadline and the observer
camera age/policy binding. Nothing here re-introduces a monitor or an ACK.
"""

import json
import os
import subprocess
import sys
import time

import pytest

from test_act_head_local_observer import CAMERA_FRAME, observer_setup
from test_act_head_local_runtime import (armed_runtime, inventory_record, runtime_setup,
                                         wait_for)
from test_act_head_prepared_sdk import prepared


def test_local_epoch_view_is_the_frozen_scope_with_live_inventory(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    scope = row.state.scope
    epoch = runtime.epoch
    assert (epoch.epoch, epoch.generation, epoch.session_id) == (
        scope['epoch'], scope['generation'], scope['session_id'])
    assert epoch.policy_hash == scope['policy_sha256']
    assert epoch.inventory == {}
    assert epoch.stage == 'LOCAL_ARMED'
    message, goal_uuid, cdr = prepared()
    record = inventory_record(row, message, goal_uuid, cdr)
    row.state.register_prepared(record, cdr)
    assert list(epoch.inventory) == [record['goal_uuid']]
    assert epoch.inventory[record['goal_uuid']]['payload_sha256'] == record['payload_sha256']
    assert epoch.inventory[record['goal_uuid']]['typed_goal'] == record['typed_goal']
    runtime.close(timeout_s=1.)


def test_local_ready_and_failed_track_real_local_state(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = row.runtime
    assert runtime.ready is False and runtime.failed is False
    assert runtime.epoch.stage == 'LOCAL_OPEN'
    armed_runtime(row)
    assert runtime.ready is True and runtime.failed is False
    runtime.fault('HEAD_LOCAL_TEST_READY_TRACKING')
    assert runtime.ready is False and runtime.failed is True
    assert runtime.epoch.stage == 'LOCAL_FAULTED'
    runtime.close(timeout_s=1.)
    assert runtime.ready is False and runtime.epoch.stage == 'LOCAL_CLOSED'


@pytest.mark.parametrize('damage', ['empty_clear', 'extension', 'past_set'])
def test_selected_exposure_deadline_refuses_empty_clear_extension_and_past(monkeypatch, damage):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    now = runtime.monotonic()
    if damage == 'empty_clear':
        with pytest.raises(PermissionError):
            runtime.dispatch_observation_deadline(None)
    elif damage == 'extension':
        assert runtime.dispatch_observation_deadline(now + 5.) is True
        with pytest.raises(PermissionError):
            runtime.dispatch_observation_deadline(now + 6.)
        assert runtime._observation_deadline_wall_s == pytest.approx(now + 5., abs=1e-6)
    else:
        with pytest.raises(PermissionError):
            runtime.dispatch_observation_deadline(now - 1.)
    assert runtime.failed is True and runtime.ready is False
    assert row.state.snapshot['fault']['reason'] == 'HEAD_LOCAL_SELECTED_EXPOSURE_REFUSED'
    runtime.close(timeout_s=1.)


def test_selected_exposure_deadline_clears_and_rearms_without_faulting(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    assert runtime.dispatch_observation_deadline(runtime.monotonic() + 5.) is True
    assert runtime.dispatch_observation_deadline(None) is True
    assert runtime._observation_deadline_wall_s is None
    assert runtime.dispatch_observation_deadline(runtime.monotonic() + 5.) is True
    assert runtime.failed is False and runtime.ready is True
    runtime.close(timeout_s=1.)


def test_expired_selected_exposure_deadline_refuses_the_next_dispatch_guard(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    runtime.dispatch_observation_deadline(runtime.monotonic() + .05)
    assert runtime.dispatch_guard() is True
    time.sleep(.08)
    with pytest.raises((PermissionError, ValueError)):
        runtime.dispatch_guard()
    assert row.state.snapshot['fault']['reason'] == 'HEAD_LOCAL_RUNTIME_OBSERVATION_EXPIRED'
    runtime.close(timeout_s=1.)


def test_local_observer_exposes_the_camera_age_and_policy_surface(monkeypatch):
    row = observer_setup(monkeypatch)
    assert row.observer.camera_frame == CAMERA_FRAME
    assert row.observer.camera_age == row.policy.perception_max_age_s
    assert row.observer._simulation_policy is row.policy
    assert row.observer.policy is row.policy


def test_local_runtime_exposes_the_simulation_policy_to_its_callers(monkeypatch):
    row = runtime_setup(monkeypatch)
    assert row.runtime._simulation_policy is row.policy
    assert row.runtime.policy is row.policy
    assert row.runtime.port is row.port
    assert row.runtime.observer is row.observer


@pytest.mark.parametrize('entry', [
    'so101_demo.adapters.act.head_local_runtime',
    'so101_demo.cli.head_execution_run',
    'so101_demo.adapters.act.head_execution_provider',
    'so101_demo.cli.head_execution_runner',
    'so101_demo.adapters.act.head_live_exposure',
])
def test_local_modules_import_no_monitor_module_in_a_fresh_interpreter(entry):
    script = ('import json, sys\n'
              f'import {entry}\n'
              'import so101_demo.adapters.act.head_local_runtime\n'
              'import so101_demo.adapters.act.head_local_observer\n'
              'print(json.dumps(sorted(name for name in sys.modules if "monitor" in name)))\n')
    process = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                             env=dict(os.environ), timeout=120)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout.strip()) == []
