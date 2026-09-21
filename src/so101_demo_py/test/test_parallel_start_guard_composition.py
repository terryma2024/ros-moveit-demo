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
    if sys.platform == "darwin":
        assert first.status == "FAIL", first
        assert first.checks["probe"].reason == "GPU_TARGET_UNAVAILABLE"
    else:
        assert first.status in ("PASS", "WARN"), first
    assert guard.probe_count == 1

    # Every spawn in the same epoch shares the fresh result instead of paying 2 s again.
    for _ in range(4):
        shared = guard.require_before_spawn(scope)
        if sys.platform == "darwin":
            assert shared.status == "FAIL"
            assert shared.checks["probe"].reason == "GPU_TARGET_UNAVAILABLE"
        else:
            assert shared is first
    if sys.platform == "darwin":
        # Refusals are intentionally observed again rather than cached as admission.
        assert guard.probe_count == 5
    else:
        assert guard.probe_count == 1

    # A new epoch is a new observation.
    guard.begin_epoch(GuardScope(batch_id="lg-t5", epoch=2, owner_pid=scope.owner_pid,
                                 owner_starttime_ticks=1, gpu_selector="INDEX:0",
                                 worker_count=4))
    assert guard.probe_count == (6 if sys.platform == "darwin" else 2)


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


# --------------------------------------------------------------------------------------
# Schema-v4 accelerator hook
#
# The guard is shared by both schemas. For schema v4 the policy carries the fixed MPS
# headroom floor, and the accelerator admission check becomes mandatory inside the same
# deadline. For schema v3 nothing changes: the epoch result is returned untouched.
# --------------------------------------------------------------------------------------


def _mps_policy(floor=1 << 30, **overrides):
    return StartGuardPolicy(mps_minimum_headroom_bytes=floor, **overrides)


def _healthy_mps_snapshot():
    from so101_demo.parallel_batch.accelerator_probe import AcceleratorSnapshot

    return AcceleratorSnapshot(
        kind="mps", selector="default", available_bytes=8 << 30,
        recommended_max_memory_bytes=16 << 30, current_allocated_memory_bytes=0,
        driver_allocated_memory_bytes=0, metric_source="unified-memory-proxy:vm_stat+torch.mps",
    )


def test_v3_policy_never_consults_the_accelerator_hook(tmp_path, scope):
    """A v3 policy has no floor, so the MPS vocabulary cannot influence its result."""

    policy = load_parallel_runtime_config_v3(V3_CONFIG).start_guard
    assert policy.mps_minimum_headroom_bytes is None
    coordinator = probe_module.ProbeCoordinator(tmp_path / "sg")
    guard = probe_module.EpochStartGuard(coordinator, policy,
                                         accelerator=lambda **_: _healthy_mps_snapshot())
    result = guard.begin_epoch(scope)
    assert "mps_accelerator" not in result.checks
    assert "mps_headroom" not in result.checks


def test_v4_policy_without_a_probe_fails_closed(tmp_path, scope):
    """A Darwin policy demands the accelerator check; a missing probe is a refusal."""

    coordinator = probe_module.ProbeCoordinator(tmp_path / "sg")
    guard = probe_module.EpochStartGuard(coordinator, _mps_policy())
    result = guard.begin_epoch(scope)
    assert result.status == FAIL
    assert result.checks["mps_accelerator"].reason == "MPS_ACCELERATOR_PROBE_MISSING"


def test_v4_policy_merges_a_healthy_accelerator_snapshot(tmp_path, scope):
    """A healthy accelerator read adds the headroom check without hiding the helper's checks."""

    coordinator = probe_module.ProbeCoordinator(tmp_path / "sg")
    guard = probe_module.EpochStartGuard(coordinator, _mps_policy(),
                                         accelerator=lambda **_: _healthy_mps_snapshot())
    result = guard.begin_epoch(scope)
    assert result.checks["mps_headroom"].reason == "MPS_HEADROOM_OK"
    assert result.checks["mps_headroom"].cutoff == 1 << 30
    # The helper's own checks survive the merge. The Darwin helper reports the CPU/RAM vocabulary
    # (`cpu_capacity`/`cpu_busy`/`ram`) instead of the NVML `probe` check, because the MPS proxy
    # admission replaces the GPU check on this platform: asserting the old key name would pin a
    # vocabulary this platform no longer produces instead of the property the merge guarantees.
    assert {"cpu_capacity", "cpu_busy", "ram"} <= set(result.checks), sorted(result.checks)
    assert result.checks.get("mps_accelerator") is None


def test_v4_policy_does_not_mask_a_refusing_helper(tmp_path, scope):
    """A healthy accelerator read never upgrades a helper that refuses on its own checks."""

    # The refusal is produced by the real helper, not by a double: the RAM floor is set above any
    # real machine, so the helper's own check must fail while the accelerator read stays healthy.
    coordinator = probe_module.ProbeCoordinator(tmp_path / "sg")
    guard = probe_module.EpochStartGuard(
        coordinator, _mps_policy(ram_minimum_bytes=1 << 62),
        accelerator=lambda **_: _healthy_mps_snapshot())
    result = guard.begin_epoch(scope)
    assert result.checks["mps_headroom"].reason == "MPS_HEADROOM_OK"
    assert result.checks["ram"].reason == "RAM_BELOW_MINIMUM"
    assert result.status == FAIL


def test_v4_policy_refuses_a_snapshot_below_the_fixed_floor(tmp_path, scope):
    """A headroom figure below the fixed floor is a hard refusal, not a warning."""

    from so101_demo.parallel_batch.accelerator_probe import AcceleratorSnapshot

    tight = AcceleratorSnapshot(
        kind="mps", selector="default", available_bytes=(1 << 30) - 1,
        recommended_max_memory_bytes=16 << 30, current_allocated_memory_bytes=0,
        driver_allocated_memory_bytes=0, metric_source="unified-memory-proxy:vm_stat+torch.mps",
    )
    coordinator = probe_module.ProbeCoordinator(tmp_path / "sg")
    guard = probe_module.EpochStartGuard(coordinator, _mps_policy(),
                                         accelerator=lambda **_: tight)
    result = guard.begin_epoch(scope)
    assert result.status == FAIL
    assert result.checks["mps_headroom"].reason == "MPS_HEADROOM_BELOW_MINIMUM"


def test_v4_probe_error_is_reported_with_its_own_reason(tmp_path, scope):
    """A probe refusal keeps its stable reason instead of becoming a generic failure."""

    from so101_demo.parallel_batch.accelerator_probe import ProbeError

    def refusing(**_: object):
        raise ProbeError("MPS_UNAVAILABLE", "torch.backends.mps.is_available() is false")

    coordinator = probe_module.ProbeCoordinator(tmp_path / "sg")
    guard = probe_module.EpochStartGuard(coordinator, _mps_policy(), accelerator=refusing)
    result = guard.begin_epoch(scope)
    assert result.status == FAIL
    assert result.checks["mps_accelerator"].reason == "MPS_UNAVAILABLE"


def test_v4_probe_selection_keeps_cuda_on_the_v3_path():
    """`select_accelerator_probe` returns the MPS probe only for the Darwin combination."""

    from so101_demo.parallel_batch import accelerator_probe

    assert accelerator_probe.select_accelerator_probe("cuda") is None
    selection = accelerator_probe.select_accelerator_probe("mps")
    assert isinstance(selection, accelerator_probe.MpsAcceleratorProbeSelection)
    assert selection.admission_kind == "unified-memory-proxy"
    with pytest.raises(accelerator_probe.ProbeError, match="ACCELERATOR_KIND"):
        accelerator_probe.select_accelerator_probe("tpu")


# --------------------------------------------------------------------------------------
# Fresh per-spawn semantics (design section 7)
#
# The campaign adapter takes one fresh check before any campaign child exists; every Worker
# takes its own fresh check after its spawn intent is durable and before ``Popen``. A result
# is never reused across a spawn epoch, a Worker or a retry, and the guard result binds the
# real owner identity: (batch_id, epoch, owner_pid, owner_birth, MPS:default, worker_count).
# --------------------------------------------------------------------------------------


class _ScriptedCoordinator(probe_module.ProbeCoordinator):
    """A coordinator that answers from a script and records every fresh request."""

    def __init__(self, state_root, statuses):
        super().__init__(state_root)
        self._statuses = list(statuses)
        self.scopes = []

    def check(self, policy, scope):  # noqa: D102 - the scripted answer is the subject
        from so101_demo.parallel_batch.start_guard import GuardCheck, GuardResult

        self.scopes.append(scope)
        status = self._statuses[min(len(self.scopes) - 1, len(self._statuses) - 1)]
        return GuardResult(
            scope=scope, status=status, started_monotonic_s=time.monotonic(),
            completed_monotonic_s=time.monotonic(),
            checks={"probe": GuardCheck(status, "SCRIPTED", None, None, "state")},
            snapshot=None, cleanup_state=probe_module.CLEAR)


def test_a_preflight_result_never_admits_a_later_spawn(tmp_path, scope):
    """The first spawn is admitted once; the next one takes its own fresh observation."""

    coordinator = _ScriptedCoordinator(tmp_path / "state", ["PASS", "FAIL"])
    guard = probe_module.EpochStartGuard(coordinator, StartGuardPolicy())

    first = guard.require_fresh_startable(scope)
    assert first.status == "PASS"
    with pytest.raises(probe_module.StartGuardRefused) as excinfo:
        guard.require_fresh_startable(scope)
    assert excinfo.value.result.status == FAIL
    assert len(coordinator.scopes) == 2, "a fresh request per spawn, never a cached verdict"


def test_the_fresh_spawn_form_never_reuses_even_a_healthy_result(tmp_path, scope):
    """`require_before_spawn` may share inside one epoch; a spawn admission may not."""

    coordinator = _ScriptedCoordinator(tmp_path / "state", ["PASS"])
    guard = probe_module.EpochStartGuard(coordinator, StartGuardPolicy())

    guard.require_before_spawn(scope)
    guard.require_before_spawn(scope)
    assert len(coordinator.scopes) == 1, "the epoch form is the sharing one"

    guard.require_fresh_startable(scope)
    guard.require_fresh_startable(scope)
    assert len(coordinator.scopes) == 3, "every spawn takes its own observation"


def test_the_spawn_scope_binds_the_owner_birth_and_the_mps_selector():
    """The guard scope is the real owner identity, not a defaulted counter."""

    scope = probe_module.darwin_guard_scope(batch_id="b-n1", epoch=1, worker_count=1)
    assert scope.batch_id == "b-n1"
    assert scope.epoch == 1
    assert scope.owner_pid == os.getpid()
    assert scope.gpu_selector == "MPS:default"
    assert scope.worker_count == 1
    assert scope.owner_starttime_ticks == probe_module.read_process_identity(
        os.getpid()).start_time_ticks

    campaign = probe_module.darwin_guard_scope(batch_id="b-n1", worker_count=2)
    assert campaign.epoch == probe_module.CAMPAIGN_GUARD_EPOCH
    assert campaign.worker_count == 2


def test_the_two_approved_w1_policies_demand_the_mps_probe(tmp_path, scope):
    """A v5/v6 policy carries the same floor, so the admission is mandatory there too."""

    from so101_demo.parallel_batch.contracts import (
        load_parallel_runtime_config_v5,
        load_parallel_runtime_config_v6,
    )

    package = Path(__file__).resolve().parents[1]
    for name in ("parallel_batch_v5_macos_mps_w1_retry.yaml",
                 "parallel_batch_v6_macos_mps_w1_first_pass.yaml"):
        config = (load_parallel_runtime_config_v5 if "v5" in name
                  else load_parallel_runtime_config_v6)(
            package / "config/mujoco" / name)
        missing = probe_module.EpochStartGuard(
            probe_module.ProbeCoordinator(tmp_path / name), config.start_guard)
        refused = missing.begin_epoch(scope)
        assert refused.status == FAIL
        assert refused.checks["mps_accelerator"].reason == "MPS_ACCELERATOR_PROBE_MISSING"

        healthy = probe_module.EpochStartGuard(
            probe_module.ProbeCoordinator(tmp_path / f"h-{name}"), config.start_guard,
            accelerator=lambda **_: _healthy_mps_snapshot())
        admitted = healthy.begin_epoch(scope)
        assert admitted.checks["mps_headroom"].reason == "MPS_HEADROOM_OK"


def test_a_v3_document_can_never_carry_the_mps_headroom(tmp_path):
    """The Linux v3 contract still refuses the Darwin-only field by name."""

    import yaml

    from so101_demo.parallel_batch.contracts import ContractError, parse_parallel_runtime_config_v3

    document = yaml.safe_load(V3_CONFIG.read_text())
    document["start_guard"]["mps_minimum_headroom_bytes"] = 1 << 30
    with pytest.raises(ContractError, match="UNKNOWN_START_GUARD_FIELD"):
        parse_parallel_runtime_config_v3(document)
    assert load_parallel_runtime_config_v3(V3_CONFIG).start_guard.mps_minimum_headroom_bytes is None


# --------------------------------------------------------------------------------------
# the supervisor's spawn-time guard
# --------------------------------------------------------------------------------------


ACK_CHILD = (
    "import json, os, sys, time\n"
    "ack_path = sys.argv[1]\n"
    "payload = {'pid': os.getpid(), 'pgid': os.getpgid(0), 'argv': ['ack-child']}\n"
    "temporary = ack_path + '.part'\n"
    "with open(temporary, 'w', encoding='utf-8') as handle:\n"
    "    json.dump(payload, handle)\n"
    "    handle.flush()\n"
    "    os.fsync(handle.fileno())\n"
    "os.replace(temporary, ack_path)\n"
    "time.sleep(float(sys.argv[2]))\n"
)


class _SpawnGuardDouble:
    """Records every spawn admission and the durable state it was asked in."""

    def __init__(self, statuses=("PASS",), *, observation=None, reason="SCRIPTED"):
        self.statuses = list(statuses)
        self.reason = reason
        self.scopes = []
        self.observations = []
        self._observation = observation

    def require_fresh_startable(self, scope):
        from so101_demo.parallel_batch.start_guard import GuardCheck, GuardResult

        self.scopes.append(scope)
        if self._observation is not None:
            self.observations.append(self._observation(scope))
        status = self.statuses[min(len(self.scopes) - 1, len(self.statuses) - 1)]
        result = GuardResult(
            scope=scope, status=status, started_monotonic_s=0.0, completed_monotonic_s=0.0,
            checks={"probe": GuardCheck(status, self.reason, None, None, "state")},
            snapshot=None, cleanup_state=probe_module.CLEAR)
        if status == FAIL:
            raise probe_module.StartGuardRefused(result)
        return result


class _CountingPopen:
    def __init__(self):
        self.calls = 0

    def __call__(self, argv, **kwargs):
        self.calls += 1
        return subprocess.Popen(argv, **kwargs)


def _supervisor(tmp_path, *, spawn_guard=None, popen=None, **kwargs):
    from so101_demo.parallel_batch.campaign_supervisor import CampaignSupervisor

    return CampaignSupervisor(
        "b-n1", state_root=tmp_path / "supervisor", ack_timeout_s=kwargs.pop("ack_timeout_s", 5.0),
        spawn_guard=spawn_guard, guard_worker_count=kwargs.pop("guard_worker_count", 1),
        popen=popen or subprocess.Popen, **kwargs)


def test_every_spawn_takes_its_own_epoch_after_the_intent_and_before_popen(tmp_path):
    """One fresh admission per Worker, requested after the durable intent and before Popen."""

    import json as _json

    recorder = _CountingPopen()
    observations = []

    def observe(scope):
        receipt = _json.loads((tmp_path / "supervisor/owner-receipt.json").read_text())
        children = receipt["children"]
        return {
            "epoch": scope.epoch,
            "popen_calls": recorder.calls,
            "spawning": [child["role"] for child in children if child["status"] == "SPAWNING"],
        }

    guard = _SpawnGuardDouble(("PASS", "PASS"), observation=observe)
    supervisor = _supervisor(tmp_path, spawn_guard=guard, popen=recorder)
    supervisor.acquire_claim()
    try:
        for slot in (0, 1):
            ack = tmp_path / f"ack-{slot}.json"
            record = supervisor.spawn(
                role="worker", slot=slot,
                argv=[sys.executable, "-c", ACK_CHILD, str(ack), "20"],
                nonce=f"n-{slot}", ack_path=ack, ack_timeout_s=5.0)
            assert record.status == "ACTIVE", record.reason
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()

    assert len(guard.scopes) == 2, "one fresh admission per spawn"
    first, second = guard.scopes
    assert first.epoch == 1 and second.epoch == 2, (first.epoch, second.epoch)
    assert first.batch_id == second.batch_id == "b-n1"
    assert first.owner_pid == second.owner_pid == os.getpid()
    assert first.owner_starttime_ticks == second.owner_starttime_ticks
    assert first.gpu_selector == second.gpu_selector == "MPS:default"
    assert first.worker_count == second.worker_count == 1
    for observation in guard.observations:
        # At the moment of each admission the intent exists and no child of *this* spawn has been
        # created yet: the calls before it belong to the earlier, already-resolved spawn.
        assert observation["popen_calls"] == observation["epoch"] - 1, observation
        assert observation["spawning"] == ["worker"], observation


def test_a_refused_spawn_guard_never_calls_popen_and_resolves_the_intent(tmp_path):
    """A FAIL admission is a refusal: no child, and the durable intent is not left SPAWNING."""

    import json as _json

    from so101_demo.parallel_batch.campaign_supervisor import CampaignBlocked

    recorder = _CountingPopen()
    guard = _SpawnGuardDouble(("FAIL",))
    supervisor = _supervisor(tmp_path, spawn_guard=guard, popen=recorder)
    supervisor.acquire_claim()
    try:
        ack = tmp_path / "ack.json"
        with pytest.raises(CampaignBlocked, match="START_GUARD_REFUSED"):
            supervisor.spawn(role="worker", slot=0,
                             argv=[sys.executable, "-c", ACK_CHILD, str(ack), "20"],
                             nonce="n-0", ack_path=ack, ack_timeout_s=5.0)
        # Read the receipt while the claim is still held: cleanup clears a resolved receipt.
        receipt = _json.loads((tmp_path / "supervisor/owner-receipt.json").read_text())
    finally:
        supervisor.terminate_all()

    assert recorder.calls == 0, "a refused admission must not spawn anything"
    assert [child["status"] for child in receipt["children"]] == ["FAILED"]
    assert receipt["children"][0]["reason"] == "START_GUARD_REFUSED"
    assert receipt["children"][0]["pid"] is None
    supervisor.release_claim()


def test_a_spawn_without_a_guard_is_unchanged(tmp_path):
    """The guard is opt-in: a supervisor that was given none spawns exactly as before."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    try:
        assert supervisor.spawn_guard is None
        ack = tmp_path / "ack.json"
        record = supervisor.spawn(role="worker", slot=0,
                                  argv=[sys.executable, "-c", ACK_CHILD, str(ack), "20"],
                                  nonce="n-0", ack_path=ack, ack_timeout_s=5.0)
        assert record.status == "ACTIVE"
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


@pytest.mark.parametrize("reason", ["RAM_BELOW_MINIMUM", "MPS_HEADROOM_BELOW_MINIMUM",
                                    "MPS_ACCELERATOR_PROBE_MISSING", "PROBE_CLEANUP_BLOCKED"])
def test_a_refusing_admission_never_spawns_for_any_failure_kind(tmp_path, reason):
    """RAM, MPS, probe and cleanup failures are all refusals: none of them reaches ``Popen``."""

    from so101_demo.parallel_batch.campaign_supervisor import CampaignBlocked

    recorder = _CountingPopen()
    supervisor = _supervisor(tmp_path, spawn_guard=_SpawnGuardDouble(("FAIL",), reason=reason),
                             popen=recorder)
    supervisor.acquire_claim()
    try:
        ack = tmp_path / "ack.json"
        with pytest.raises(CampaignBlocked, match="START_GUARD_REFUSED") as excinfo:
            supervisor.spawn(role="worker", slot=0,
                             argv=[sys.executable, "-c", ACK_CHILD, str(ack), "20"],
                             nonce="n-0", ack_path=ack, ack_timeout_s=5.0)
        assert excinfo.value.detail == reason
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()
    assert recorder.calls == 0


def test_a_cpu_warn_admission_still_spawns_exactly_once(tmp_path):
    """CPU busy is a WARN, not a refusal: it does not block the start and does not duplicate it."""

    recorder = _CountingPopen()
    supervisor = _supervisor(tmp_path, spawn_guard=_SpawnGuardDouble(("WARN",), reason="CPU_BUSY"),
                             popen=recorder)
    supervisor.acquire_claim()
    try:
        ack = tmp_path / "ack.json"
        record = supervisor.spawn(role="worker", slot=0,
                                  argv=[sys.executable, "-c", ACK_CHILD, str(ack), "20"],
                                  nonce="n-0", ack_path=ack, ack_timeout_s=5.0)
        assert record.status == "ACTIVE"
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()
    assert recorder.calls == 1, "a WARN admission spawns once, never twice"


def test_a_w1_and_a_w2_campaign_cannot_hold_the_claim_at_the_same_time(tmp_path):
    """One macOS service instance runs one campaign: the claim is the same MPS:DEFAULT flock."""

    from so101_demo.parallel_batch.campaign_supervisor import CLAIM_IDENTITY, CampaignBlocked

    assert CLAIM_IDENTITY == "MPS:DEFAULT"
    w2 = _supervisor(tmp_path)
    w2.acquire_claim()
    try:
        w1 = _supervisor(tmp_path, guard_worker_count=1)
        assert w1.claim_identity == w2.claim_identity == "MPS:DEFAULT"
        with pytest.raises(CampaignBlocked, match="CAMPAIGN_CLAIM_HELD"):
            w1.acquire_claim()
    finally:
        w2.release_claim()


def test_a_spawn_guard_without_the_fresh_admission_entry_is_refused(tmp_path):
    """A guard that cannot prove freshness is not a guard; the spawn is refused by name."""

    from so101_demo.parallel_batch.campaign_supervisor import CampaignBlocked

    supervisor = _supervisor(tmp_path, spawn_guard=object())
    supervisor.acquire_claim()
    try:
        ack = tmp_path / "ack.json"
        with pytest.raises(CampaignBlocked, match="SPAWN_GUARD_INVALID"):
            supervisor.spawn(role="worker", slot=0,
                             argv=[sys.executable, "-c", ACK_CHILD, str(ack), "20"],
                             nonce="n-0", ack_path=ack, ack_timeout_s=5.0)
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()
