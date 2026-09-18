"""The real composition: one epoch-scoped start guard covering the CLI and the allocator.

Task 5 of the lightweight start guard plan. These tests drive the installed composition and
the real helper; the only thing they replace is the *lowest* port (the probe process port for
the unreapable branch), never the admission decision itself.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from so101_demo.parallel_batch import start_guard_probe as probe_module
from so101_demo.parallel_batch.contracts import (
    BatchKindV3,
    BatchRequestV3,
    ContractError,
    RunMode,
    load_parallel_runtime_config_v3,
)
from so101_demo.parallel_batch.start_guard import FAIL, GuardScope, StartGuardPolicy

PACKAGE = Path(__file__).resolve().parents[1]
V3_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v3.yaml"


@pytest.fixture
def scope():
    return GuardScope(batch_id="lg-t5", epoch=1, owner_pid=os.getpid(),
                      owner_starttime_ticks=1, gpu_selector="INDEX:0", worker_count=4)


@pytest.fixture
def guard(tmp_path):
    policy = load_parallel_runtime_config_v3(V3_CONFIG).start_guard
    coordinator = probe_module.ProbeCoordinator(tmp_path / "start-guard-state")
    return probe_module.EpochStartGuard(coordinator, policy)


def test_one_probe_covers_the_epoch_and_a_new_epoch_probes_again(guard, scope):
    first = guard.begin_epoch(scope)
    assert first.status in ("PASS", "WARN"), first
    assert guard.probe_count == 1

    # Every spawn in the same epoch shares the fresh result instead of paying 2 s again.
    for _ in range(4):
        shared = guard.require_before_spawn(scope)
        assert shared is first
    assert guard.probe_count == 1

    # A new epoch is a new observation.
    guard.begin_epoch(GuardScope(batch_id="lg-t5", epoch=2, owner_pid=scope.owner_pid,
                                 owner_starttime_ticks=1, gpu_selector="INDEX:0",
                                 worker_count=4))
    assert guard.probe_count == 2


def test_scope_change_and_expiry_force_a_fresh_probe(guard, scope):
    guard.begin_epoch(scope)
    changed = GuardScope(batch_id="lg-t5", epoch=1, owner_pid=scope.owner_pid,
                         owner_starttime_ticks=1, gpu_selector="INDEX:0", worker_count=8)
    guard.require_before_spawn(changed)
    assert guard.probe_count == 2

    # A result older than the policy deadline is never reused.
    stale = probe_module.EpochStartGuard(
        guard._coordinator, StartGuardPolicy(), clock=lambda: 1e9)
    stale.begin_epoch(scope)
    stale.require_before_spawn(scope)
    assert stale.probe_count == 2


def test_failed_guard_never_allocates_and_is_not_reused(tmp_path, scope):
    class RefusingCoordinator(probe_module.ProbeCoordinator):
        def check(self, policy, scope):  # noqa: D102 - deliberate refusal, not a fake decision
            from so101_demo.parallel_batch.start_guard import GuardCheck, GuardResult
            return GuardResult(
                scope=scope, status=FAIL, started_monotonic_s=0.0, completed_monotonic_s=0.0,
                checks={"probe": GuardCheck(FAIL, "RAM_BELOW_MINIMUM", 1, 1 << 30, "bytes")},
                snapshot=None, cleanup_state=probe_module.CLEAR)

    guard = probe_module.EpochStartGuard(
        RefusingCoordinator(tmp_path / "state"), StartGuardPolicy())
    with pytest.raises(probe_module.StartGuardRefused) as excinfo:
        guard.require_startable(scope)
    assert excinfo.value.reason == "RAM_BELOW_MINIMUM"
    assert excinfo.value.result.status == FAIL


def test_cleanup_blocked_is_refused_even_for_a_warn_result(tmp_path, scope):
    class BlockedCoordinator(probe_module.ProbeCoordinator):
        def check(self, policy, scope):  # noqa: D102 - deliberate blocked state
            from so101_demo.parallel_batch.start_guard import GuardCheck, GuardResult
            return GuardResult(
                scope=scope, status="WARN", started_monotonic_s=0.0, completed_monotonic_s=0.0,
                checks={"probe": GuardCheck("WARN", probe_module.PROBE_CLEANUP_BLOCKED, None,
                                            None, "state")},
                snapshot=None, cleanup_state=probe_module.PROBE_CLEANUP_BLOCKED)

    guard = probe_module.EpochStartGuard(
        BlockedCoordinator(tmp_path / "state"), StartGuardPolicy())
    with pytest.raises(probe_module.StartGuardRefused):
        guard.require_startable(scope)


def test_installed_composition_uses_the_task_state_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SO101_TASK_ROOT", str(tmp_path))
    config = load_parallel_runtime_config_v3(V3_CONFIG)
    guard = probe_module.compose_default_start_guard(config.start_guard)
    assert guard.policy == config.start_guard
    assert (tmp_path / "start-guard-state").is_dir()


def test_budget_modules_are_absent_from_the_composition_import_graph():
    """Importing the composition must not pull the retired budget chain back in."""

    script = (
        "import json, sys\n"
        "from so101_demo.parallel_batch import start_guard_probe\n"
        "from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v3\n"
        "config = load_parallel_runtime_config_v3(__import__('pathlib').Path(%r))\n"
        "guard = start_guard_probe.compose_default_start_guard(config.start_guard)\n"
        "print(json.dumps(sorted(n for n in sys.modules if 'parallel_batch' in n)))\n"
    ) % str(V3_CONFIG)
    env = dict(os.environ)
    env["SO101_TASK_ROOT"] = "/tmp/so101-composition-import-graph"
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                               env=env)
    assert completed.returncode == 0, completed.stderr
    modules = json.loads(completed.stdout.strip().splitlines()[-1])
    for retired in ("resource_budget", "resource_measurement", "measurement_control",
                    "owned_resources"):
        assert not any(retired in name for name in modules), modules


def test_fixed_request_keeps_every_slot_when_points_are_fewer(tmp_path):
    request = BatchRequestV3(batch_id="lg-t5-fixed", run_mode=RunMode.EXECUTE,
                             selected_point_ids=("p1",), worker_count=4,
                             evidence_root=tmp_path, batch_kind=BatchKindV3.FIRST_PASS)
    assert request.worker_count == 4  # never min(worker_count, points)
    assert len(request.selected_point_ids) == 1
    document = json.loads(json.dumps({"schema_version": 3, "batch_id": request.batch_id,
                                      "run_mode": str(request.run_mode),
                                      "selected_point_ids": list(request.selected_point_ids),
                                      "worker_count": request.worker_count,
                                      "evidence_root": str(request.evidence_root),
                                      "batch_kind": str(request.batch_kind)}))
    from so101_demo.parallel_batch.contracts import batch_request_from_document
    assert batch_request_from_document(document, for_execution=True) == request


def test_no_active_path_imports_the_retired_budget_chain():
    """The active entry points must not be able to import the deleted modules.

    A meta-path trap makes any residual import chain fail loudly instead of relying on a
    text search, and the real composition is then driven end to end.
    """

    script = (
        "import json, sys\n"
        "RETIRED = ('so101_demo.parallel_batch.resource_budget',\n"
        "           'so101_demo.parallel_batch.resource_measurement',\n"
        "           'so101_demo.parallel_batch.measurement_control',\n"
        "           'so101_demo.parallel_batch.owned_resources')\n"
        "class Trap:\n"
        "    def find_module(self, name, path=None):\n"
        "        return self if name in RETIRED else None\n"
        "    def load_module(self, name):\n"
        "        raise AssertionError('retired module imported: ' + name)\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name in RETIRED:\n"
        "            raise AssertionError('retired module imported: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Trap())\n"
        "import so101_demo.cli.mujoco_parallel_batch as cli\n"
        "import so101_demo.parallel_batch.resources as resources\n"
        "import so101_demo.parallel_batch.adaptive_pool as adaptive\n"
        "import so101_demo.parallel_batch.contracts as contracts\n"
        "from so101_demo.parallel_batch.start_guard_probe import compose_default_start_guard\n"
        "config = contracts.load_parallel_runtime_config_v3(__import__('pathlib').Path(%r))\n"
        "guard = compose_default_start_guard(config.start_guard)\n"
        "print(json.dumps({'imported': sorted(n for n in sys.modules if 'parallel_batch' in n)}))\n"
    ) % str(V3_CONFIG)
    env = dict(os.environ)
    env["SO101_TASK_ROOT"] = "/tmp/so101-retired-chain-trap"
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                               env=env)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    for retired in ("resource_budget", "resource_measurement", "measurement_control",
                    "owned_resources"):
        assert not any(retired in name for name in payload["imported"]), payload["imported"]
