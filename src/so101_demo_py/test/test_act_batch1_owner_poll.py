"""Batch 1: the evidence boundary owns the adapter and polls owner health."""

import pytest


class _Adapter:
    def __init__(self, hazard=None):
        self.hazard = hazard
        self.calls = 0
        self.on_hazard = None

    def check_health(self, *, now_ns=None):
        self.calls += 1
        return self.hazard


class _Admission:
    def __init__(self):
        self.revocations = []

    def revoke_current(self, reason):
        self.revocations.append(reason)


def _evidence(adapter):
    from so101_demo.adapters.act.pick_place_sources import PickPlaceRosEvidence

    return PickPlaceRosEvidence.__new__(PickPlaceRosEvidence), adapter


def _wire(adapter):
    import queue

    evidence, _ = _evidence(adapter)
    evidence._hazards = queue.SimpleQueue()
    evidence._hazards_latched = []
    evidence._authority_revoked = False
    evidence.physics_clock = adapter
    adapter.on_hazard = evidence._enqueue_hazard
    return evidence


def test_healthy_adapter_latches_nothing_and_revokes_nothing():
    adapter = _Adapter()
    admission = _Admission()
    evidence = _wire(adapter)
    assert evidence.poll_owner_health(now_ns=1, admission=admission) is None
    assert evidence._hazards_latched == []
    assert admission.revocations == []
    assert evidence.authority_revoked() is False


def test_health_loss_latches_exactly_once_and_revokes_exactly_once():
    adapter = _Adapter(hazard="PHYSICS_CLOCK_SILENT")
    admission = _Admission()
    evidence = _wire(adapter)
    assert evidence.poll_owner_health(now_ns=1, admission=admission) == "PHYSICS_CLOCK_SILENT"
    assert evidence.poll_owner_health(now_ns=2, admission=admission) == "PHYSICS_CLOCK_SILENT"
    assert evidence.take_hazard() == "PHYSICS_CLOCK_SILENT"
    assert evidence._hazards_latched == ["PHYSICS_CLOCK_SILENT"], "latched more than once"
    assert admission.revocations == ["PHYSICS_CLOCK_SILENT"], "revoked more than once"
    assert evidence.authority_revoked() is True


def test_subsequent_sample_use_is_refused_after_revocation():
    adapter = _Adapter(hazard="PHYSICS_CLOCK_SILENT")
    admission = _Admission()
    evidence = _wire(adapter)
    evidence.poll_owner_health(now_ns=1, admission=admission)
    with pytest.raises(Exception, match="TASK8_SOURCE_AUTHORITY_REVOKED"):
        evidence.capture("attempt-1")


def test_adapter_hazard_callback_feeds_the_same_latch():
    adapter = _Adapter()
    evidence = _wire(adapter)
    adapter.on_hazard("PHYSICS_CLOCK_HAZARD")
    assert evidence.take_hazard() == "PHYSICS_CLOCK_HAZARD"
