"""The service's start guard must accept the document the host can actually execute.

The validation domain loaded every execution document as schema 3. On macOS that both rejected the
schema-4 document (`UNKNOWN_CONFIG_FIELD`) and built an NVML guard, which refuses every preflight with
`GPU_TARGET_UNAVAILABLE` because there is no CUDA device. The document decides: v3 keeps the NVML guard,
v4/MPS gets the Darwin accelerator its policy asks for.

The composition is cached per execution document - keyed by the profile, the document hash, the
accelerator and the selector it resolved - but a verdict is never cached: every request and every
spawn epoch runs its own fresh probe.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from so101_teleop.expert_validation.production import _LazyStartGuard

REPO = Path(__file__).parents[4]
CONFIG_DIR = REPO / "src" / "so101_demo_py" / "config" / "mujoco"

V3_DOCUMENT = CONFIG_DIR / "parallel_batch_v3.yaml"
V4_DOCUMENT = CONFIG_DIR / "parallel_batch_v4_macos_mps_w2.yaml"
V5_DOCUMENT = CONFIG_DIR / "parallel_batch_v5_macos_mps_w1_retry.yaml"
V6_DOCUMENT = CONFIG_DIR / "parallel_batch_v6_macos_mps_w1_first_pass.yaml"
DARWIN_ONLY = pytest.mark.skipif(
    sys.platform != "darwin", reason="the guard composes installed MPS documents on macOS"
)


@DARWIN_ONLY
def test_the_macos_document_composes_a_guard_its_host_can_run():
    guard = _LazyStartGuard(
        {"SO101_VALIDATION_PARALLEL_CONFIG": str(V4_DOCUMENT)}
    )
    assert guard.gpu_selector == "MPS:default"
    assert guard.policy.mps_minimum_headroom_bytes == 1073741824


def test_the_v3_document_keeps_the_nvml_guard():
    guard = _LazyStartGuard(
        {"SO101_VALIDATION_PARALLEL_CONFIG": str(V3_DOCUMENT)}
    )
    assert guard.gpu_selector.startswith("INDEX:")
    assert guard.policy.mps_minimum_headroom_bytes is None


@pytest.mark.parametrize(
    ("document", "profile", "selector"),
    [
        (V4_DOCUMENT, "MPS_W2_FIRST_PASS", "MPS:default"),
        (V5_DOCUMENT, "MPS_W1_FULL_RESTART_RETRY", "MPS:default"),
        (V6_DOCUMENT, "MPS_W1_FIRST_PASS", "MPS:default"),
    ],
)
@DARWIN_ONLY
def test_every_macos_profile_selects_the_darwin_mps_accelerator(document, profile, selector):
    guard = _LazyStartGuard({"SO101_VALIDATION_PARALLEL_CONFIG": str(document)})

    admission = guard.admission()
    assert admission.profile == profile
    assert admission.selector == selector
    assert admission.accelerator is not None
    assert admission.composition_key == (
        profile, hashlib.sha256(document.read_bytes()).hexdigest(),
        "mps", selector)


@DARWIN_ONLY
def test_the_composition_is_cached_but_a_changed_document_is_not_reused(tmp_path, monkeypatch):
    """The cache key is (profile, config_sha256, accelerator, selector); bytes decide identity."""

    monkeypatch.delenv("SO101_TASK_ROOT", raising=False)
    copy = tmp_path / "parallel.yaml"
    copy.write_bytes(V4_DOCUMENT.read_bytes())
    guard = _LazyStartGuard({"SO101_VALIDATION_PARALLEL_CONFIG": str(copy)})

    first = guard.admission()
    second = guard.admission()
    assert first is second
    # Composing the guard wiring reads the document and nothing else: it starts no probe
    # process, so it needs no task root either.
    assert first.policy.timeout_s == 2.0

    # The same profile with different bytes is a different composition, not a cache hit.
    changed = tmp_path / "changed.yaml"
    changed.write_bytes(
        V4_DOCUMENT.read_bytes().replace(b"cpu_busy_warn_fraction: 0.90",
                                         b"cpu_busy_warn_fraction: 0.80"))
    assert changed.read_bytes() != copy.read_bytes()
    other = _LazyStartGuard({"SO101_VALIDATION_PARALLEL_CONFIG": str(changed)}).admission()
    assert other.profile == first.profile
    assert other.composition_key != first.composition_key


@DARWIN_ONLY
def test_every_request_and_spawn_epoch_takes_a_fresh_probe(monkeypatch, tmp_path):
    """A cached composition must never accept a previous verdict."""

    from so101_demo.parallel_batch.start_guard import (
        FAIL, PASS, GuardCheck, GuardResult)
    from so101_demo.parallel_batch.start_guard_probe import ProbeCoordinator

    monkeypatch.setenv("SO101_TASK_ROOT", str(tmp_path))
    calls = []

    def check(self, policy, scope, *, accelerator=None):
        calls.append(scope)
        status = PASS if len(calls) == 1 else FAIL
        reason = "MPS_HEADROOM_OK" if status == PASS else "RAM_BELOW_MINIMUM"
        return GuardResult(
            scope=scope, status=status, started_monotonic_s=1.0, completed_monotonic_s=2.0,
            checks={"ram": GuardCheck(status, reason, 1, 1 << 30, "bytes")},
            snapshot=None, cleanup_state="CLEAR")

    monkeypatch.setattr(ProbeCoordinator, "check", check)
    guard = _LazyStartGuard({"SO101_VALIDATION_PARALLEL_CONFIG": str(V4_DOCUMENT)})
    scope = SimpleNamespace(
        batch_id="web-preflight", epoch=1, owner_pid=1, owner_starttime_ticks=1,
        gpu_selector="MPS:default", worker_count=2)

    first = guard.begin_epoch(scope)
    second = guard.begin_epoch(scope)

    assert first.status == PASS and second.status == FAIL
    assert len(calls) == 2, "each epoch runs its own probe, never the one before it"


def test_a_platform_bound_capability_document_does_not_consult_the_budget_source():
    """macOS capabilities are the support matrix; no budget or qualification authority is read."""

    from so101_teleop.unified.app import UnifiedServices, create_unified_app

    consulted = []

    class CountingBudgetSource:
        contract_version = 2

        def decision(self, selected_n, runtime_identity):
            consulted.append(selected_n)
            raise AssertionError("the budget source must not be consulted on macOS")

    class PlatformBoundValidation:
        artifacts = None

        def health(self):
            return {"ok": True}

        def capabilities(self):
            return {
                "available": True,
                "platform": "macos",
                "execution_modes": ["SEQUENTIAL", "PARALLEL"],
                "support_matrix": [
                    {"profile": "MPS_W2_FIRST_PASS", "schema_version": 4,
                     "execution_mode": "PARALLEL", "worker_count": 2,
                     "batch_kind": "FIRST_PASS", "selectable": True, "status": "SUPPORTED"},
                    {"profile": "MPS_W1_FULL_RESTART_RETRY", "schema_version": 5,
                     "execution_mode": "SEQUENTIAL", "worker_count": 1,
                     "batch_kind": "FULL_RESTART_RETRY", "selectable": True,
                     "status": "SUPPORTED"},
                    {"profile": "MPS_W1_FIRST_PASS", "schema_version": 6,
                     "execution_mode": "SEQUENTIAL", "worker_count": 1,
                     "batch_kind": "FIRST_PASS", "selectable": True, "status": "SUPPORTED"},
                ],
                "worker_count_availability": [
                    {"worker_count": 1, "selectable": True, "status": "SUPPORTED"},
                    {"worker_count": 2, "selectable": True, "status": "SUPPORTED"},
                    {"worker_count": 8, "selectable": False, "status": "UNSUPPORTED_ON_MACOS",
                     "reason_codes": ["UNSUPPORTED_ON_MACOS"]},
                ],
            }

    services = UnifiedServices(
        teleop=None, tasks=None, validation=PlatformBoundValidation(),
        budget_source=CountingBudgetSource())
    app = create_unified_app(services, static_dir=None, capture_dir=None,
                             bind_address="127.0.0.1")

    with TestClient(app) as client:
        payload = client.get("/expert-validation/capabilities").json()

    assert consulted == []
    assert payload["worker_qualifications"] == []
    assert payload["platform"] == "macos"
    assert [row["profile"] for row in payload["support_matrix"]] == [
        "MPS_W2_FIRST_PASS", "MPS_W1_FULL_RESTART_RETRY", "MPS_W1_FIRST_PASS"]
    assert payload["worker_count_availability"][-1]["status"] == "UNSUPPORTED_ON_MACOS"
