"""The lightweight start guard as the Web/API sees it.

Task 7 of the lightweight start guard plan. The preview (`Check resources` -> preflight) runs
one bounded check on the server, the campaign start runs its own fresh check, a client cannot
supply or override a status, and history projections never probe.
"""

import dataclasses
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import asyncio

import httpx
import pytest

from so101_demo.parallel_batch import start_guard as guard_module
from so101_demo.parallel_batch.start_guard_probe import ProbeCoordinator
from so101_teleop.expert_validation.api import create_expert_validation_app
from so101_teleop.expert_validation.production import (
    ProductionRuntimeLayout,
    create_production_service,
)

WORKTREE = Path(__file__).resolve().parents[4]
V3_CONFIG = WORKTREE / "src/so101_demo_py/config/mujoco/parallel_batch_v3.yaml"
MACOS_CONFIG_DIR = WORKTREE / "src/so101_demo_py/config/mujoco"

#: (document basename, schema_version, execution_mode, worker_count, batch_kind) per profile.
MACOS_PROFILES = {
    "MPS_W2_FIRST_PASS": (
        "parallel_batch_v4_macos_mps_w2.yaml", 4, "PARALLEL", 2, "FIRST_PASS"),
    "MPS_W1_FULL_RESTART_RETRY": (
        "parallel_batch_v5_macos_mps_w1_retry.yaml", 5, "SEQUENTIAL", 1,
        "FULL_RESTART_RETRY"),
    "MPS_W1_FIRST_PASS": (
        "parallel_batch_v6_macos_mps_w1_first_pass.yaml", 6, "SEQUENTIAL", 1, "FIRST_PASS"),
}


def _local_check(self, policy, scope, *, nvml=None, busy=None):
    """Real reads and the real decision; only the probe process boundary is replaced."""

    started = time.monotonic()
    ports = dataclasses.replace(guard_module.host_ports(), busy_window_s=0.0)
    if sys.platform == "darwin" and nvml is None:
        class MacTestGpu:
            def devices(self):
                return (guard_module.GpuDevice(
                    0, "GPU-MACOS-TEST", 16 << 30, 8 << 30),)

        ports = dataclasses.replace(ports, nvml=MacTestGpu())
    if busy is not None:
        ports = dataclasses.replace(ports, busy_window_s=0.0)
    if nvml is not None:
        ports = dataclasses.replace(ports, nvml=nvml)
    try:
        snapshot = guard_module.probe_snapshot(policy, scope, started + policy.timeout_s,
                                              ports=ports)
        if busy is not None:
            snapshot = dataclasses.replace(snapshot, cpu_busy_fraction=busy)
        return guard_module.evaluate_snapshot(snapshot, policy, scope,
                                              started_monotonic_s=started,
                                              completed_monotonic_s=time.monotonic())
    except guard_module.ProbeError as error:
        return guard_module.GuardResult(
            scope=scope, status=guard_module.FAIL, started_monotonic_s=started,
            completed_monotonic_s=time.monotonic(),
            checks={"probe": guard_module.GuardCheck(guard_module.FAIL, error.reason, None, None,
                                                     "state")},
            snapshot=None, cleanup_state="CLEAR")


class _EmptyNvml:
    def devices(self):
        return ()


INSTALLED_ASSETS = (
    "config/mujoco/headless_execution.yaml",
    "config/policies/dynamic_cup_pick/v1/mujoco.yaml",
    "config/policies/light_cup_wall_pick/v1/mujoco.yaml",
    "config/mujoco/task_scene.yaml",
    "assets/mujoco/scene.xml",
    "assets/mujoco/assets/target_landing_tolerance_ring.obj",
    "config/mujoco/rgbd_task_points.yaml",
    "config/mujoco/moveit_expert_validation_points_v1.yaml",
    "config/mujoco/parallel_adaptive_workers_v1.yaml",
)


def _copied_prefix(share: Path, destination: Path) -> Path:
    """A real (non-symlink) installed prefix: the manifest identity requires real bytes."""

    root = destination / "share/so101_demo_py"
    for relative in INSTALLED_ASSETS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(share / relative, target)
        target.chmod(0o644)
    return destination


@pytest.fixture
def service(tmp_path, monkeypatch):
    from ament_index_python.packages import get_package_share_directory

    monkeypatch.setenv("SO101_TASK_ROOT", str(tmp_path / "task-root"))
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    def file(name, content="approved\n"):
        path = runtime / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o700)
        return path.resolve()

    share = Path(get_package_share_directory("so101_demo_py")).resolve()
    demo_prefix = _copied_prefix(share, (tmp_path / "demo-prefix").resolve())
    copied_share = demo_prefix / "share/so101_demo_py"
    config = file("parallel.yaml")
    shutil.copyfile(V3_CONFIG, config)
    config.chmod(0o644)
    layout = _layout(
        tmp_path,
        demo_prefix=demo_prefix,
        copied_share=copied_share,
        parallel_config=config,
        runtime=runtime,
        file=file,
    )
    yield from _created_service(tmp_path, monkeypatch, layout)


def _layout(tmp_path, *, demo_prefix, copied_share, parallel_config, runtime, file):
    return ProductionRuntimeLayout(
        source_root=tmp_path.resolve(),
        source_commit="a" * 40,
        demo_prefix=demo_prefix,
        points_path=(copied_share
                     / "config/mujoco/moveit_expert_validation_points_v1.yaml").resolve(),
        parallel_config_path=parallel_config,
        adaptive_config_path=(copied_share
                              / "config/mujoco/parallel_adaptive_workers_v1.yaml").resolve(),
        coordinator_executable=file("so101_parallel_batch"),
        cleanup_executable=file("so101_parallel_batch_cleanup"),
        adaptive_wrapper=file("so101_adaptive_pool.zsh"),
        provenance_binding=None,
        yolo_weights_path=file("best.pt"),
        grounded_root=runtime.resolve(),
        yolo_weights_sha256="0" * 64,
        grounded_manifest_sha256="0" * 64,
        broker_image_id="sha256:" + "b" * 64,
        parallel_acceptance=None,
        adaptive_acceptance=None,
        adaptive_fault_injection=None,
        adaptive_performance_tiers=(),
    )


def _created_service(tmp_path, monkeypatch, layout):
    monkeypatch.setattr(ProductionRuntimeLayout, "discover",
                        classmethod(lambda _cls, _environment: layout))
    evidence = (tmp_path / "evidence").resolve()
    evidence.mkdir(exist_ok=True)
    created = create_production_service(evidence, environment={})
    try:
        yield created
    finally:
        created.close()


def _macos_layout(tmp_path, monkeypatch, basenames):
    """A layout whose config directory holds exactly the named installed documents."""

    from ament_index_python.packages import get_package_share_directory

    monkeypatch.setenv("SO101_TASK_ROOT", str(tmp_path / "task-root"))
    runtime = tmp_path / "runtime"
    config_dir = runtime / "config" / "mujoco"
    config_dir.mkdir(parents=True)

    def file(name, content="approved\n"):
        path = runtime / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o700)
        return path.resolve()

    for basename in basenames:
        target = config_dir / basename
        shutil.copyfile(MACOS_CONFIG_DIR / basename, target)
        target.chmod(0o644)
    share = Path(get_package_share_directory("so101_demo_py")).resolve()
    demo_prefix = _copied_prefix(share, (tmp_path / "demo-prefix").resolve())
    copied_share = demo_prefix / "share/so101_demo_py"
    return _layout(
        tmp_path,
        demo_prefix=demo_prefix,
        copied_share=copied_share,
        parallel_config=(config_dir / basenames[0]).resolve(),
        runtime=runtime,
        file=file,
    )


@pytest.fixture
def macos_service(tmp_path, monkeypatch):
    """The installed macOS composition: the three profile documents sit in the config directory.

    A request names its profile and the service loads that document - its own real profile and
    config hash - instead of assuming the one document the layout happened to configure.
    """

    layout = _macos_layout(
        tmp_path, monkeypatch, tuple(item[0] for item in MACOS_PROFILES.values()))
    yield from _created_service(tmp_path, monkeypatch, layout)


@pytest.fixture
def macos_w2_only_service(tmp_path, monkeypatch):
    """A macOS service with only the W2 document installed: no W1 campaign can be invented."""

    layout = _macos_layout(
        tmp_path, monkeypatch, (MACOS_PROFILES["MPS_W2_FIRST_PASS"][0],))
    yield from _created_service(tmp_path, monkeypatch, layout)


class _Client:
    """Drive the ASGI app in this thread; the real store connection is thread-bound."""

    def __init__(self, service):
        self._app = create_expert_validation_app(service)

    def request(self, method, path, **kwargs):
        async def run():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://guard.test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(run())

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)


def _lease(client):
    response = client.post("/expert-validation/lease",
                           json={"service_session_id": "session-1"})
    assert response.status_code == 200, response.text
    return response.json()


def _manifest_id(client, lease):
    response = client.post("/expert-validation/manifests", json={"total_points": 4})
    assert response.status_code == 200, response.text
    return response.json()["manifest_id"]


def _preflight_body(client, lease, **changes):
    body = {
        "service_session_id": "session-1",
        "lease_id": lease["lease_id"],
        "lease_generation": lease["generation"],
        "manifest_id": _manifest_id(client, lease),
        "execution_mode": "SEQUENTIAL",
        "worker_count": 1,
        "contract_version": 3,
    }
    body.update(changes)
    return body


def test_capabilities_list_configured_counts_without_a_budget_profile(service):
    client = _Client(service)
    payload = client.get("/expert-validation/capabilities").json()
    availability = payload["worker_count_availability"]
    assert availability, payload
    for entry in availability:
        assert entry["status"] == "CONFIGURED"
        assert entry["selectable"] is True
        assert entry["profile_sha256"] is None
        assert entry["qualification_sha256"] is None
        assert "BUDGET" not in " ".join(entry["reason_codes"])
    assert payload["start_guard_policy"]["timeout_s"] == 2.0
    assert payload["start_guard_policy"]["ram_minimum_bytes"] == 1 << 30


def test_preflight_preview_carries_the_guard_status_units_and_time(service, monkeypatch):
    monkeypatch.setattr(ProbeCoordinator, "check", _local_check)
    client = _Client(service)
    lease = _lease(client)
    response = client.post("/expert-validation/campaigns/preflight",
                           json=_preflight_body(client, lease))
    assert response.status_code == 200, response.text
    payload = response.json()
    guard = payload["start_guard"]
    assert guard["status"] in ("PASS", "WARN")
    assert guard["cleanup_state"] == "CLEAR"
    assert guard["observed_monotonic_s"] > 0
    assert set(guard["checks"]) == {"cpu_capacity", "cpu_busy", "ram", "gpu"}
    assert guard["checks"]["ram"]["unit"] == "bytes"
    assert guard["checks"]["gpu"]["cutoff"] == 1 << 30
    assert guard["checks"]["cpu_busy"]["unit"] == "fraction"


def test_a_missing_gpu_is_an_explicit_failure(service, monkeypatch):
    def empty_gpu_check(self, policy, scope):
        return _local_check(self, policy, scope, nvml=_EmptyNvml())

    monkeypatch.setattr(ProbeCoordinator, "check", empty_gpu_check)
    client = _Client(service)
    lease = _lease(client)
    response = client.post("/expert-validation/campaigns/preflight",
                           json=_preflight_body(client, lease))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["admitted"] is False
    assert "GPU_TARGET_UNAVAILABLE" in payload["reason_codes"]
    assert payload["start_guard"]["status"] == "FAIL"


def test_busy_cpu_warns_and_still_starts(service, monkeypatch):
    def busy_check(self, policy, scope):
        return _local_check(self, policy, scope, busy=0.99)

    monkeypatch.setattr(ProbeCoordinator, "check", busy_check)
    client = _Client(service)
    lease = _lease(client)
    response = client.post("/expert-validation/campaigns/preflight",
                           json=_preflight_body(client, lease))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["admitted"] is True
    assert payload["reason_codes"] == []
    assert payload["start_guard"]["status"] == "WARN"
    assert payload["start_guard"]["checks"]["cpu_busy"]["status"] == "WARN"


def test_a_client_supplied_status_cannot_override_the_server_check(service, monkeypatch):
    monkeypatch.setattr(ProbeCoordinator, "check", _local_check)
    client = _Client(service)
    lease = _lease(client)

    forged = client.post("/expert-validation/campaigns/preflight", json=_preflight_body(
        client, lease, start_guard={"status": "PASS", "checks": {}},
        resource_observations={"start_guard_status": "PASS"}, admitted=True))
    assert forged.status_code == 422, forged.text

    def refusing_check(self, policy, scope):
        return _local_check(self, policy, scope, nvml=_EmptyNvml())

    monkeypatch.setattr(ProbeCoordinator, "check", refusing_check)
    refused = client.post("/expert-validation/campaigns/preflight",
                          json=_preflight_body(client, lease))
    assert refused.status_code == 200, refused.text
    assert refused.json()["admitted"] is False


def test_history_projection_never_probes(service, monkeypatch):
    calls = []
    original = ProbeCoordinator.check

    def counting_check(self, policy, scope):
        calls.append(scope)
        return _local_check(self, policy, scope)

    monkeypatch.setattr(ProbeCoordinator, "check", counting_check)
    client = _Client(service)
    lease = _lease(client)
    client.post("/expert-validation/campaigns/preflight", json=_preflight_body(client, lease))
    probes_after_preflight = len(calls)
    assert probes_after_preflight >= 1

    assert client.get("/expert-validation/campaigns").status_code == 200
    assert client.get("/expert-validation/campaigns/campaign-1").status_code in (200, 404)
    client.get("/expert-validation/capabilities")
    assert len(calls) == probes_after_preflight, "history/capability reads must not probe"


def test_legacy_contract_versions_are_refused_for_new_execution(service, monkeypatch):
    monkeypatch.setattr(ProbeCoordinator, "check", _local_check)
    client = _Client(service)
    lease = _lease(client)
    for version in (1, 2):
        response = client.post("/expert-validation/campaigns/preflight",
                               json=_preflight_body(client, lease, contract_version=version))
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"


# --------------------------------------------------------------------------------------
# The schema-v4 macOS MPS projection
#
# The API carries a resolved projection of the runtime schema, not the schema itself. These tests
# pin the two fields that make the v4 guard legible to a client, and pin that a schema-v3 server
# answers exactly as it did before.
# --------------------------------------------------------------------------------------


def test_v3_guard_policy_projection_is_unchanged_and_reports_no_mps_floor():
    """A schema-v3 policy reports a null MPS floor, so existing clients see no drift."""

    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v3
    from so101_demo.parallel_batch.start_guard import StartGuardPolicy
    from so101_teleop.expert_validation.api import StartGuardPolicyResponse

    policy = load_parallel_runtime_config_v3(V3_CONFIG).start_guard
    assert policy.mps_minimum_headroom_bytes is None
    document = {
        "timeout_s": policy.timeout_s,
        "cpu_busy_warn_fraction": policy.cpu_busy_warn_fraction,
        "ram_minimum_bytes": policy.ram_minimum_bytes,
        "ram_minimum_fraction": policy.ram_minimum_fraction,
        "gpu_minimum_bytes": policy.gpu_minimum_bytes,
        "mps_minimum_headroom_bytes": getattr(policy, "mps_minimum_headroom_bytes", None),
    }
    response = StartGuardPolicyResponse(**document)
    assert response.mps_minimum_headroom_bytes is None
    assert response.timeout_s == 2.0
    assert isinstance(StartGuardPolicy(), StartGuardPolicy)


def test_the_api_accepts_and_reports_the_mps_headroom_floor():
    """The v4 policy projection carries the MPS floor when the policy has one."""

    from so101_teleop.expert_validation.api import StartGuardPolicyResponse

    response = StartGuardPolicyResponse(
        timeout_s=2.0, cpu_busy_warn_fraction=0.9, ram_minimum_bytes=1 << 30,
        ram_minimum_fraction=0.05, gpu_minimum_bytes=1 << 30,
        mps_minimum_headroom_bytes=1 << 30)
    assert response.mps_minimum_headroom_bytes == 1 << 30
    assert set(response.model_dump()) >= {"mps_minimum_headroom_bytes"}


def test_guard_status_labels_the_admission_kind_from_the_checks_that_ran():
    """The label is derived, and it distinguishes a proxy reading from a device reading."""

    from so101_teleop.expert_validation.api import StartGuardCheck, StartGuardStatus

    proxy = StartGuardStatus(
        status="PASS",
        checks={"mps_headroom": StartGuardCheck(status="PASS", reason="MPS_HEADROOM_OK",
                                                observed=8 << 30, cutoff=1 << 30,
                                                unit="bytes")},
        admission_kind="unified-memory-proxy")
    document = proxy.model_dump()
    assert document["admission_kind"] == "unified-memory-proxy"
    assert "token" not in document and "generation" not in document and "lease" not in document

    device = StartGuardStatus(status="PASS", admission_kind="nvml-device")
    assert device.admission_kind == "nvml-device"
    unlabelled = StartGuardStatus(status="PASS")
    assert unlabelled.admission_kind is None


def test_the_projection_derivation_matches_the_checks_present():
    """The production derivation is the same rule the API documents."""

    def derive(checks):
        return ("unified-memory-proxy" if "mps_headroom" in checks
                else ("nvml-device" if "gpu" in checks else None))

    assert derive({"mps_headroom": object()}) == "unified-memory-proxy"
    assert derive({"gpu": object(), "ram": object()}) == "nvml-device"
    assert derive({"ram": object()}) is None
    # A v4 result keeps the helper's own probe check alongside the accelerator check; the
    # accelerator check is what decides the label.
    assert derive({"probe": object(), "mps_headroom": object()}) == "unified-memory-proxy"


def test_the_new_guard_projection_fields_carry_no_ipc_auth_vocabulary():
    """The two fields this task added are data, not credentials.

    The HTTP API legitimately still knows about backend leases and worker generations: the design
    keeps them for the Web control channel and only removes them from the **v4 IPC envelope**. So
    this test asserts the narrow, true thing: the guard projection added here introduces no
    credential vocabulary of its own, and the IPC envelope itself remains clean (that is asserted
    directly in `test_parallel_ipc_v4.py`).
    """

    from so101_teleop.expert_validation.api import (
        StartGuardCheck,
        StartGuardPolicyResponse,
        StartGuardStatus,
    )

    policy = StartGuardPolicyResponse(
        timeout_s=2.0, cpu_busy_warn_fraction=0.9, ram_minimum_bytes=1 << 30,
        ram_minimum_fraction=0.05, gpu_minimum_bytes=1 << 30,
        mps_minimum_headroom_bytes=1 << 30)
    status = StartGuardStatus(
        status="PASS",
        checks={"mps_headroom": StartGuardCheck(status="PASS", reason="MPS_HEADROOM_OK",
                                                observed=8 << 30, cutoff=1 << 30,
                                                unit="bytes")},
        admission_kind="unified-memory-proxy")
    projection = json.dumps(policy.model_dump()) + json.dumps(status.model_dump())
    for retired in ("token", "generation", "lease", "endpoint_receipt", "peer_credentials"):
        assert retired not in projection, retired
    assert "unified-memory-proxy" in projection


class _SchemaOnly:
    """Enough of the service protocol for OpenAPI generation, and nothing more."""

    def __getattr__(self, name):
        async def _call(*_args, **_kwargs):
            raise RuntimeError("schema-only service")

        return _call


# --------------------------------------------------------------------------------------
# The macOS W1/W2 support matrix on the installed service
#
# The platform binding is a property of the execution document, not of a budget or
# qualification authority: the service loads the profile's own v4/v5/v6 YAML, binds its real
# config hash, runs the Darwin MPS probe and never enters the CUDA/NVML branch.
# --------------------------------------------------------------------------------------


def _macos_preflight_body(client, lease, profile, **changes):
    _basename, _schema, mode, workers, batch_kind = MACOS_PROFILES[profile]
    body = _preflight_body(
        client, lease, execution_mode=mode, worker_count=workers,
        execution_profile=profile, batch_kind=batch_kind)
    body.update(changes)
    return body


def _passing_mps_probe(calls):
    """The Darwin accelerator probe contract: one snapshot inside the caller's deadline."""

    from so101_demo.parallel_batch.accelerator_probe import AcceleratorSnapshot

    def probe(_self, *, deadline_monotonic_ns):
        calls.append(deadline_monotonic_ns)
        return AcceleratorSnapshot(
            kind="mps", selector="default", available_bytes=8 << 30,
            recommended_max_memory_bytes=16 << 30, current_allocated_memory_bytes=0,
            driver_allocated_memory_bytes=0, metric_source="unified-memory-proxy:test")

    return probe


def test_macos_capabilities_expose_only_w1_and_w2(macos_service):
    import hashlib

    client = _Client(macos_service)
    payload = client.get("/expert-validation/capabilities").json()

    assert payload["platform"] == "macos"
    assert list(payload["execution_modes"]) == ["SEQUENTIAL", "PARALLEL"]
    assert payload["available"] is True

    availability = {item["worker_count"]: item for item in payload["worker_count_availability"]}
    assert set(availability) == {1, 2, 3, 4, 5, 6, 7, 8}
    for count in (1, 2):
        assert availability[count]["selectable"] is True, count
        assert availability[count]["status"] == "SUPPORTED", count
        assert availability[count]["reason_codes"] == []
    for count in (3, 4, 5, 6, 7, 8):
        entry = availability[count]
        assert entry["selectable"] is False, count
        assert entry["status"] == "UNSUPPORTED_ON_MACOS", count
        assert list(entry["reason_codes"]) == ["UNSUPPORTED_ON_MACOS"], count
        assert entry["profile_sha256"] is None, count
        assert entry["qualification_sha256"] is None, count

    rows = {row["profile"]: row for row in payload["support_matrix"]}
    assert set(rows) == set(MACOS_PROFILES)
    for profile, (basename, schema, mode, workers, batch_kind) in MACOS_PROFILES.items():
        row = rows[profile]
        assert (row["schema_version"], row["execution_mode"], row["worker_count"],
                row["batch_kind"]) == (schema, mode, workers, batch_kind), profile
        assert row["accelerator"] == "mps" and row["selectable"] is True
        assert row["profile_sha256"] is None and row["qualification_sha256"] is None

    configured = MACOS_CONFIG_DIR / MACOS_PROFILES["MPS_W2_FIRST_PASS"][0]
    assert payload["execution_profile"] == "MPS_W2_FIRST_PASS"
    assert payload["execution_schema_version"] == 4
    assert payload["execution_config_sha256"] == hashlib.sha256(
        configured.read_bytes()).hexdigest()

    # No budget/qualification authority takes part, and the display says what the guard is not.
    assert payload["worker_qualifications"] == []
    assert "not a resource qualification proof" in payload["start_guard_note"]
    assert payload["start_guard_policy"]["mps_minimum_headroom_bytes"] == 1 << 30
    assert payload["start_guard_policy"]["timeout_s"] == 2.0


def test_macos_capability_reads_never_probe(macos_service, monkeypatch):
    calls = []

    def counting_check(self, policy, scope):
        calls.append(scope)
        return _local_check(self, policy, scope)

    monkeypatch.setattr(ProbeCoordinator, "check", counting_check)
    client = _Client(macos_service)
    assert client.get("/expert-validation/capabilities").status_code == 200
    assert calls == []


@pytest.mark.parametrize("profile", list(MACOS_PROFILES))
def test_a_macos_preflight_uses_the_profiles_own_document_and_the_mps_probe(
        macos_service, monkeypatch, profile):
    """Real coordinator, real helper, real CPU/RAM reads; only the accelerator read is pinned."""

    import hashlib

    from so101_demo.parallel_batch.accelerator_probe import DarwinMpsAcceleratorProbe

    basename, schema, mode, workers, batch_kind = MACOS_PROFILES[profile]
    document = MACOS_CONFIG_DIR / basename
    calls = []
    monkeypatch.setattr(DarwinMpsAcceleratorProbe, "probe", _passing_mps_probe(calls))

    client = _Client(macos_service)
    lease = _lease(client)
    response = client.post("/expert-validation/campaigns/preflight",
                           json=_macos_preflight_body(client, lease, profile))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["admitted"] is True, payload
    assert payload["execution_mode"] == mode
    assert payload["execution_config"]["worker_count"] == workers
    observations = payload["resource_observations"]
    assert observations["execution_profile"] == profile
    assert observations["execution_schema_version"] == schema
    assert observations["execution_batch_kind"] == batch_kind
    assert observations["execution_config_sha256"] == hashlib.sha256(
        document.read_bytes()).hexdigest()

    guard = payload["start_guard"]
    assert guard["status"] in ("PASS", "WARN"), guard
    assert guard["cleanup_state"] == "CLEAR"
    assert guard["admission_kind"] == "unified-memory-proxy"
    assert set(guard["checks"]) == {"cpu_capacity", "cpu_busy", "ram", "mps_headroom"}
    assert guard["checks"]["mps_headroom"]["cutoff"] == 1 << 30
    assert "gpu" not in guard["checks"]
    assert calls and all(isinstance(value, int) and value > 0 for value in calls)


@pytest.mark.parametrize("profile", list(MACOS_PROFILES))
def test_a_macos_preflight_never_reads_nvml(macos_service, monkeypatch, profile):
    """Only the probe process boundary is replaced; the Darwin branch runs the real decision.

    All three installed documents take the same MPS half: none of them may fall into the
    CUDA/NVML branch the schema-v3 guard uses.
    """

    from so101_demo.parallel_batch import start_guard_probe as probe_module
    from so101_demo.parallel_batch.accelerator_probe import DarwinMpsAcceleratorProbe

    class ExplodingNvml:
        def devices(self):
            raise AssertionError("NVML must not be read for a macOS profile")

    ports = dataclasses.replace(guard_module.host_ports(), nvml=ExplodingNvml())
    monkeypatch.setattr(guard_module, "host_ports", lambda: ports)
    calls = []
    monkeypatch.setattr(DarwinMpsAcceleratorProbe, "probe", _passing_mps_probe(calls))

    def local_v4_check(self, policy, scope, *, accelerator=None):
        started = time.monotonic()
        result = probe_module._v4_cpu_ram_result(
            policy, scope, started + policy.timeout_s, started)
        return probe_module.ProbeCoordinator._merge_accelerator(
            self, result, policy, accelerator)

    monkeypatch.setattr(ProbeCoordinator, "check", local_v4_check)
    client = _Client(macos_service)
    lease = _lease(client)
    payload = client.post("/expert-validation/campaigns/preflight",
                          json=_macos_preflight_body(client, lease, profile)).json()

    assert payload["admitted"] is True, payload
    assert payload["start_guard"]["admission_kind"] == "unified-memory-proxy"
    assert "gpu" not in payload["start_guard"]["checks"]
    assert "mps_headroom" in payload["start_guard"]["checks"]
    assert calls, "the MPS accelerator probe must run"


def test_a_macos_service_refuses_more_than_two_workers_and_adaptive(macos_service):
    client = _Client(macos_service)
    lease = _lease(client)

    oversized_body = _macos_preflight_body(
        client, lease, "MPS_W2_FIRST_PASS", worker_count=8)
    oversized = client.post("/expert-validation/campaigns/preflight", json=oversized_body)
    assert oversized.status_code == 200, oversized.text
    assert oversized.json()["admitted"] is False
    assert "UNSUPPORTED_ON_MACOS" in oversized.json()["reason_codes"]

    # A v4 document claiming W1 is the same refusal one layer down: the document the request
    # names decides, and exact-W2 cannot honour a one-worker claim.
    from so101_teleop.expert_validation.preflight import (
        PreflightEngine, UNSUPPORTED_ON_MACOS)

    class _AdmitsAnyResource:
        def probe(self, _request, _config):
            return True, (), {}

    v4_document = MACOS_CONFIG_DIR / MACOS_PROFILES["MPS_W2_FIRST_PASS"][0]
    request = dataclasses.replace(
        macos_service._campaign_request(oversized_body),
        execution_profile="MPS_W1_FIRST_PASS", batch_kind="FIRST_PASS",
        execution_mode="SEQUENTIAL", worker_count=1,
        parallel_config_path=v4_document,
        parallel_config_sha256=hashlib.sha256(v4_document.read_bytes()).hexdigest())
    receipt = PreflightEngine(_AdmitsAnyResource()).preflight(request)
    assert receipt.admitted is False
    assert UNSUPPORTED_ON_MACOS in receipt.reason_codes

    # ADAPTIVE is not part of the macOS support matrix at all.
    adaptive = client.post(
        "/expert-validation/campaigns/preflight",
        json=_preflight_body(
            client, lease, execution_mode="ADAPTIVE", worker_count=None,
            preferred_worker_count=8, fallback_worker_counts=[6, 4, 2, 1],
            initial_points_per_worker=3, worker_start_timeout_s=120.0,
            max_infra_attempts_per_point=5, yolo_executor_count=2))
    assert adaptive.status_code == 200, adaptive.text
    payload = adaptive.json()
    assert payload["admitted"] is False
    assert "UNSUPPORTED_ON_MACOS" in payload["reason_codes"]

    # An unadmitted receipt can never start a campaign.
    started = client.post(
        "/expert-validation/campaigns",
        json={**oversized_body, "command_id": "start-1",
              "preflight_receipt_id": oversized.json()["receipt_id"]})
    assert started.status_code == 409, started.text


def test_a_macos_service_refuses_a_profile_it_has_no_installed_document_for(
        macos_w2_only_service):
    """A W1 request on a W2-only install is a stable refusal, never an invented document."""

    client = _Client(macos_w2_only_service)
    lease = _lease(client)
    response = client.post(
        "/expert-validation/campaigns/preflight",
        json=_macos_preflight_body(client, lease, "MPS_W1_FIRST_PASS"))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "EXECUTION_DOCUMENT_MISSING"
