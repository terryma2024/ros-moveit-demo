"""The Teacher's own execution bound stays at the frozen 240 s when the stage and lease bounds are raised for offline processing."""

import os
import time
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch import contracts
from so101_demo.parallel_batch.contracts import RunMode, teacher_execution_bound_s

from paths import PACKAGE_ROOT
from test_offline_recording_switch import FakePilot

ACT_FILE = PACKAGE_ROOT / "config/mujoco/parallel_batch_act_offline.yaml"
ORIGINAL_FILE = PACKAGE_ROOT / "config/mujoco/parallel_batch_linux_cuda.yaml"


@pytest.fixture(autouse=True)
def _fresh_fake_pilots():
    FakePilot.instances.clear()
    FakePilot.log = None
    yield
    FakePilot.instances.clear()
    FakePilot.log = None


# ---- the Teacher's bound is separate from the stage bound ---------------------------------------------------------------------

def test_the_act_config_raises_the_stage_and_lease_bounds_and_the_teacher_bound_stays_at_the_frozen_value():
    act = contracts.load_parallel_runtime_config_linux_cuda(ACT_FILE)
    original = contracts.load_parallel_runtime_config_linux_cuda(ORIGINAL_FILE)
    assert (act.executing_hard_timeout_s, act.lease_duration_s) == (1500.0, 1500.0)
    assert contracts.TEACHER_EXECUTION_BOUND_S == 240.0
    assert teacher_execution_bound_s(act) == 240.0, "the stage bound is 1500 s; the Teacher's bound is not"
    assert teacher_execution_bound_s(original) == 240.0
    differing = {name for name in act.__slots__ if getattr(act, name) != getattr(original, name)}
    assert differing == {"executing_hard_timeout_s", "lease_duration_s"}
    assert "teacher_execution_timeout_s" not in {item.name for item in contracts.fields(contracts.ParallelRuntimeConfigLinuxCuda)}


def test_the_teacher_bound_helper_never_exceeds_the_frozen_value_and_honours_a_smaller_one():
    assert teacher_execution_bound_s(SimpleNamespace(executing_hard_timeout_s=240.0)) == 240.0
    assert teacher_execution_bound_s(SimpleNamespace(executing_hard_timeout_s=1500.0)) == 240.0
    assert teacher_execution_bound_s(SimpleNamespace(executing_hard_timeout_s=10.0)) == 10.0
    assert teacher_execution_bound_s(SimpleNamespace()) == 180.0


def test_the_stage_and_lease_floors_still_refuse_a_value_below_the_original(tmp_path):
    for field, bad in (("executing_hard_timeout_s", "239.0"), ("lease_duration_s", "299.0")):
        broken = tmp_path / f"{field}.yaml"
        broken.write_text(ACT_FILE.read_text().replace(f"{field}: 1500.0", f"{field}: {bad}"))
        with pytest.raises(contracts.ContractError, match="FROZEN_RUNTIME_VALUE"):
            contracts.load_parallel_runtime_config_linux_cuda(broken)


def test_versions_four_to_six_keep_every_pin_exactly():
    for pins in (contracts.FROZEN_RUNTIME_VALUES_MACOS_MPS_TWO_WORKER, contracts.FROZEN_RUNTIME_VALUES_MACOS_MPS_SINGLE_WORKER_RETRY, contracts.FROZEN_RUNTIME_VALUES_MACOS_MPS_SINGLE_WORKER_FIRST_PASS):
        assert pins["executing_hard_timeout_s"] == 240.0 and pins["lease_duration_s"] == 300.0
    assert contracts._FROZEN_RUNTIME_VALUES_LINUX_CUDA["executing_hard_timeout_s"] == 240.0
    # the v3 closed field list is exactly the dataclass (the v4 work froze that surface) and the v4 list is untouched by this change
    assert set(contracts.EXECUTION_LINUX_CUDA_FIELDS) == {item.name for item in contracts.fields(contracts.ParallelRuntimeConfigLinuxCuda)} - {
        "schema_version", "start_guard"}


def test_a_teacher_that_runs_past_240_s_is_still_waited_for_only_240_s_under_the_act_config(tmp_path, monkeypatch):
    """`execute_result` waits for the Teacher child no longer than the Teacher bound, whatever the stage bound is."""
    import so101_demo.runtime.parallel_ros_runtime as runtime_module
    from so101_demo.parallel_batch.contracts import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    from test_parallel_ros_runtime import _lease

    observations = iter((100.0, 200.0, 300.0, 341.0, 342.0))   # the deadline is 100 + 240 = 340 s
    waitpid_calls = []
    monkeypatch.setattr(time, "monotonic", lambda: next(observations))
    monkeypatch.setattr(time, "sleep", lambda _duration: None)
    monkeypatch.setattr(os, "waitpid", lambda pid, options: (waitpid_calls.append((pid, options)) or (0, 0)))
    ports = ParallelRosRuntimePorts(SimpleNamespace(worker_root=tmp_path, session_id="session-1"), catalog={},
                                    config=contracts.load_parallel_runtime_config_linux_cuda(ACT_FILE))
    receipt = ports.execute_result(_lease(), SimpleNamespace(reset_epoch="reset-17"), SimpleNamespace(pid=417))
    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert waitpid_calls == [(417, os.WNOHANG), (417, os.WNOHANG)], "it gave up at 340 s, not at 1600 s"


def _worker_with(config):
    from test_parallel_batch_worker import Fake

    fake = Fake(RunMode.EXECUTE)
    ports = fake.ports()
    ports["config"] = config
    return fake, ports


def test_the_workers_teacher_deadline_guard_still_fires_at_240_s_under_the_act_config(monkeypatch):
    from test_parallel_batch_worker import _expert_blocked_with_a_lost_coordinator, _wait_for_watchdog_fault
    from test_parallel_batch_worker import Fake

    act = contracts.load_parallel_runtime_config_linux_cuda(ACT_FILE)
    real_ports = Fake.ports
    monkeypatch.setattr(Fake, "ports", lambda self: {**real_ports(self), "config": act})
    fake = Fake(RunMode.EXECUTE)
    worker, thread, result, release = _expert_blocked_with_a_lost_coordinator(fake)
    _wait_for_watchdog_fault(worker)
    time.sleep(0.1)
    assert "cancel_motion" not in fake.runtime.calls
    fake.clock.now += 240.0 - 1.0
    time.sleep(0.1)
    assert "cancel_motion" not in fake.runtime.calls, "cancelled before the Teacher bound"
    fake.clock.now += 1.0
    deadline = time.monotonic() + 2.0
    while "confirm_no_controller_goal" not in fake.runtime.calls:
        assert time.monotonic() < deadline, "the Teacher deadline guard never fired at 240 s under the ACT config"
        time.sleep(0.01)
    receipts = [call for call in fake.runtime.calls if isinstance(call, tuple) and call[0] == "revocation"]
    assert dict(receipts[0][3])["reason"] == "TEACHER_EXECUTION_DEADLINE"
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()
