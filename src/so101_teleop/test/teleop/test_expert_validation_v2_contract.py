"""Closed v2 teleop contract: no quota key, versioned requests, availability."""

import pytest

from so101_teleop.expert_validation.api import (
    CampaignConfiguration, CapabilitiesResponse, WorkerCountAvailability)


def _fixed_body(**changes):
    body = {
        'contract_version': 2, 'service_session_id': 'browser-a', 'lease_id': 'lease-a',
        'lease_generation': 1, 'manifest_id': 'manifest-20',
        'execution_mode': 'PARALLEL', 'worker_count': 2,
    }
    body.update(changes)
    return body


def test_v2_fixed_config_is_mode_and_count_only():
    configuration = CampaignConfiguration(**_fixed_body())
    assert configuration.worker_count == 2
    assert not hasattr(configuration, 'max_points_per_worker')
    with pytest.raises(Exception):
        CampaignConfiguration(**_fixed_body(max_points_per_worker=5))
    with pytest.raises(Exception):
        CampaignConfiguration(**_fixed_body(contract_version=1))
    with pytest.raises(Exception):
        CampaignConfiguration(**_fixed_body(execution_mode='SEQUENTIAL', worker_count=2))


def test_v2_adaptive_config_keeps_its_own_fields_without_quota():
    configuration = CampaignConfiguration(
        contract_version=2, service_session_id='browser-a', lease_id='lease-a',
        lease_generation=1, manifest_id='manifest-20', execution_mode='ADAPTIVE',
        preferred_worker_count=8, fallback_worker_counts=(6, 4, 2, 1),
        initial_points_per_worker=3, worker_start_timeout_s=30.0,
        max_infra_attempts_per_point=2, yolo_executor_count=2)
    assert configuration.preferred_worker_count == 8
    assert not hasattr(configuration, 'max_points_per_worker')


def test_worker_count_availability_is_explicit_and_unqualified_by_default():
    item = WorkerCountAvailability(
        worker_count=4, selectable=False, status='NOT_MEASURED',
        reason_codes=('BUDGET_PROFILE_UNAVAILABLE',), profile_sha256=None,
        qualification_sha256=None)
    assert item.selectable is False
    capabilities = CapabilitiesResponse(available=True)
    assert not hasattr(capabilities, 'fixed_max_points_per_worker')
    assert [entry.worker_count for entry in capabilities.worker_count_availability] == [
        2, 3, 4, 5, 6, 7, 8]
