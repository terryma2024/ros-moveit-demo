"""Web Expert Validation runs one native worker; PARALLEL and ADAPTIVE are no longer admissible.

Multi-worker collection exists only as container shards. The page keeps a single-worker SEQUENTIAL
campaign (and its FULL_RESTART retry), so the closed counts, the request contract, the preflight and
the advertised capabilities all say the same thing.
"""

from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from so101_teleop.expert_validation.api import CampaignConfiguration
from so101_teleop.expert_validation.executor_registry import ExecutorRegistry, QualificationProbes
from so101_teleop.expert_validation.preflight import (
    FIXED_WORKER_COUNTS,
    PreflightEngine,
    PreflightRejected,
)
from so101_teleop.expert_validation.supervisor import fixed_coordinator_argv
from test_expert_validation_preflight import Resources, _request

NATIVE_REFUSED = "NATIVE_MULTI_WORKER_UNSUPPORTED"


def test_the_closed_worker_counts_are_exactly_one():
    assert FIXED_WORKER_COUNTS == (1,)


def _configuration(**changes):
    values = dict(
        contract_version=3, service_session_id="s", lease_id="l", lease_generation=1,
        manifest_id="m", execution_mode="SEQUENTIAL", worker_count=1,
    )
    values.update(changes)
    return CampaignConfiguration(**values)


def test_the_request_contract_admits_one_sequential_worker():
    assert _configuration().worker_count == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"execution_mode": "SEQUENTIAL", "worker_count": 2},
        {"execution_mode": "PARALLEL", "worker_count": 2},
        {"execution_mode": "PARALLEL", "worker_count": 8},
        {
            "execution_mode": "ADAPTIVE", "worker_count": None, "preferred_worker_count": 8,
            "fallback_worker_counts": (6, 4, 2, 1), "initial_points_per_worker": 3,
            "worker_start_timeout_s": 120.0, "max_infra_attempts_per_point": 5,
            "yolo_executor_count": 2,
        },
    ],
)
def test_the_request_contract_refuses_every_multi_worker_form(changes):
    with pytest.raises(ValidationError):
        _configuration(**changes)


@pytest.mark.parametrize("mode,count", [("PARALLEL", 2), ("PARALLEL", 8), ("ADAPTIVE", 8)])
def test_preflight_rejects_parallel_and_adaptive_without_probing_resources(tmp_path, mode, count):
    class Refusing(Resources):
        def probe(self, request, config):  # pragma: no cover - must not be reached
            raise AssertionError("a refused mode must not reach the resource probe")

    request = _request(tmp_path, mode=mode, count=5, worker_count=count)
    receipt = PreflightEngine(Refusing()).preflight(request)
    assert receipt.admitted is False
    assert NATIVE_REFUSED in receipt.reason_codes
    with pytest.raises(PreflightRejected, match=NATIVE_REFUSED):
        PreflightEngine(Refusing()).require_admitted(request)


def test_preflight_still_reaches_the_resource_probe_for_one_sequential_worker(tmp_path):
    seen = []

    class Recording(Resources):
        def probe(self, request, config):
            seen.append((config.execution_mode, config.worker_count))
            return super().probe(request, config)

    receipt = PreflightEngine(Recording()).preflight(
        _request(tmp_path, mode="SEQUENTIAL", count=5, worker_count=1)
    )
    assert NATIVE_REFUSED not in receipt.reason_codes
    assert seen == [("SEQUENTIAL", 1)]


def _probes():
    return QualificationProbes(
        fixed_upstream=True, parallel_config=True, broker_image=True, resource_probe=True,
        two_worker_live_acceptance=None, adaptive_runner=True, adaptive_pool=True,
        adaptive_wrapper=True, adaptive_cleanup=True, adaptive_config=True,
        adaptive_fault_injection=True, adaptive_twenty_point_acceptance=None,
        adaptive_performance_evidence=(1, 2, 4, 6, 8),
    )


def test_the_registry_advertises_sequential_only_even_when_every_multi_worker_file_is_installed():
    capability = ExecutorRegistry.v1(_probes()).require("moveit_expert", "validate_pick_place")
    assert capability.execution_modes == ("SEQUENTIAL",)
    assert set(capability.mode_availability) == {"SEQUENTIAL"}
    assert capability.default_execution_mode == "SEQUENTIAL"


def test_the_capabilities_document_lists_one_mode_and_no_selectable_count_above_one():
    from so101_teleop.expert_validation.production_service.capabilities import ServiceCapabilities

    registry = ExecutorRegistry.v1(_probes())
    service = SimpleNamespace(
        registry=registry,
        lease_service=SimpleNamespace(
            capabilities=SimpleNamespace(duration_s=30.0, renewal_margin_s=10.0)
        ),
        layout=SimpleNamespace(parallel_config_path="/nonexistent/parallel.yaml"),
        supervisor=None,
        configured_worker_counts=(1, 2, 8),
    )
    service._execution_document = lambda: None
    service._start_guard_policy = lambda: None
    service._worker_count_availability = lambda: ServiceCapabilities._worker_count_availability(service)
    document = ServiceCapabilities.capabilities(service)
    assert tuple(document["execution_modes"]) == ("SEQUENTIAL",)
    assert tuple(document["fixed_worker_counts"]) == (1,)
    assert tuple(document["worker_count_availability"]) == ()


def test_the_single_worker_coordinator_argv_is_unchanged():
    """N=1 launches exactly the argv it always did."""

    argv = fixed_coordinator_argv(
        executable_path="/opt/so101/bin/so101_parallel_batch",
        points_path="/opt/points.yaml",
        config_path="/opt/parallel_batch_linux_cuda.yaml",
        batch_id="b001",
        worker_count=1,
        evidence_root="/evidence/campaigns/c1/b001",
        broker_image_id="so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
        yolo_weights_path="/models/yolo.pt",
        yolo_weights_sha256="a" * 64,
        grounded_root="/models/grounded",
        grounded_manifest_sha256="b" * 64,
        selected_point_ids=("task_start", "cup_test_forward_5cm"),
    )
    assert argv[1:] == [
        "/opt/so101/bin/so101_parallel_batch",
        "--points", "/opt/points.yaml",
        "--config", "/opt/parallel_batch_linux_cuda.yaml",
        "--batch-id", "b001",
        "--worker-count", "1",
        "--evidence-root", "/evidence/campaigns/c1/b001",
        "--broker-image", "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
        "--yolo-weights", "/models/yolo.pt",
        "--yolo-weights-sha256", "a" * 64,
        "--grounded-root", "/models/grounded",
        "--grounded-manifest-sha256", "b" * 64,
        "--run-mode", "execute",
        "--point-id", "task_start",
        "--point-id", "cup_test_forward_5cm",
    ]
