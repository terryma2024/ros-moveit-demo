"""The Web probe, CLI prepare and allocator share one exact-N admission gate."""

from pathlib import Path

import pytest


class SpyGate:
    """Records every admission question and refuses with one stable code."""

    execution_identity_sha256 = "a" * 64

    def __init__(self, code="EXACT_N_UNQUALIFIED"):
        self.code = code
        self.requests = []

    def admit(self, request):
        from so101_demo.parallel_batch.resource_budget import ResourceBudgetAdmission
        self.requests.append(request)
        return ResourceBudgetAdmission(
            admitted=False, reason_codes=(self.code,), worker_count=request.worker_count,
            profile_sha256="b" * 64, qualification_sha256=None,
            execution_identity_sha256=request.execution_identity_sha256,
            observation_monotonic_s=1.0)


def _config(worker_count):
    from dataclasses import replace
    from so101_demo.parallel_batch.contracts import (
        FixedExecutionConfigV2, ParallelRuntimeConfigV2, load_parallel_runtime_config_v2)
    import so101_demo
    path = Path(so101_demo.__file__).resolve().parents[1] / "config/mujoco/parallel_batch_v2.yaml"
    config = load_parallel_runtime_config_v2(path)
    return config


def _allocator(tmp_path, worker_count, gate):
    from so101_demo.parallel_batch.resources import WorkerResourceAllocator
    import so101_demo
    return WorkerResourceAllocator(
        _config(worker_count), tmp_path / "evidence", probe=None, base_environment={},
        claim_root=tmp_path / "claims", resource_gate=gate)


def _options():
    class Options:
        live_headroom_evidence = None
        live_headroom_acceptance = None
        live_headroom_current_provenance_root = None
        batch_id = "cli-batch"
    return Options()


def test_allocator_uses_the_shared_gate_and_reports_its_code(tmp_path):
    from so101_demo.parallel_batch.resources import ResourceAllocationError
    gate = SpyGate()
    allocator = _allocator(tmp_path, 4, gate)
    try:
        with pytest.raises(ResourceAllocationError) as error:
            allocator._live_headroom(4)
        assert "EXACT_N_UNQUALIFIED" in str(error.value)
        assert [(r.worker_count, r.request_kind) for r in gate.requests] == [
            (4, "FIXED_PRODUCTION")]
    finally:
        allocator.close()


def test_web_probe_uses_the_same_gate_and_code():
    from so101_teleop.expert_validation.production import _HostResourceProbe
    from so101_demo.parallel_batch.contracts import FixedExecutionConfigV2

    gate = SpyGate(code="BUDGET_PROFILE_UNAVAILABLE")
    probe = _HostResourceProbe(resource_gate=gate)
    admitted, reasons, observations = probe.probe(None, FixedExecutionConfigV2(2, "PARALLEL", 4))
    assert admitted is False
    assert "BUDGET_PROFILE_UNAVAILABLE" in reasons
    assert observations["requested_worker_count"] == 4
    assert [(r.worker_count, r.request_kind) for r in gate.requests] == [
        (4, "FIXED_PRODUCTION")]


def test_cli_prepare_uses_the_same_gate_and_code():
    from so101_demo.cli.mujoco_parallel_batch import CliError, _prepare_live_headroom

    gate = SpyGate(code="RUNTIME_FINGERPRINT_MISMATCH")
    with pytest.raises(CliError) as error:
        _prepare_live_headroom(_options(), _config(4), 4, resource_gate=gate)
    assert "RUNTIME_FINGERPRINT_MISMATCH" in str(error.value)
    assert [(r.worker_count, r.request_kind) for r in gate.requests] == [
        (4, "FIXED_PRODUCTION")]


def test_shared_gate_refuses_without_a_probe_instead_of_passing():
    from so101_demo.parallel_batch.resource_budget import (
        FixedAdmissionGate, FixedAdmissionRequest, ResourceBudgetProvider)

    gate = FixedAdmissionGate(ResourceBudgetProvider())
    decision = gate.admit(FixedAdmissionRequest(
        worker_count=4, batch_id="b1", epoch=1,
        execution_identity_sha256="a" * 64, request_kind="FIXED_PRODUCTION"))
    assert decision.admitted is False
    assert decision.reason_codes == ("RESOURCE_PROBE_FAILED",)
