"""Task 11A recovery: terminal scenes are skipped, and nothing held is reset blind."""

import json
from pathlib import Path

import pytest

from so101_demo.act.parallel_collection_recovery import ActFixedWaveRecovery
from so101_demo.adapters.act.parallel_collection_results import ActCollectionResultStore


class _EvidencePort:
    def __init__(self, *, path=None, digest=None, events=None):
        self._path, self._digest = path, digest
        self.events = events if events is not None else []

    def capture(self, scene_id, context):
        self.events.append(f"evidence:{scene_id}")
        if self._path is None:
            return {"path": "absent", "sha256": "0" * 64}
        return {"path": str(self._path), "sha256": self._digest or ""}


class _RecoveryPort:
    def __init__(self, *, recovered=True, events=None):
        self._recovered = recovered
        self.events = events if events is not None else []

    def recover(self, scene_id, context, evidence):
        self.events.append(f"recover:{scene_id}")
        return {"recovered": self._recovered}


class _ResetPort:
    def __init__(self, *, events=None):
        self.calls = []
        self.events = events if events is not None else []

    def reset(self, scene_id, context):
        self.events.append(f"reset:{scene_id}")
        self.calls.append(scene_id)


def _fixture(tmp_path, *, holding_state="SAFE", terminal=()):
    store = ActCollectionResultStore(tmp_path)
    for scene_id in terminal:
        store.publish({"scene_id": scene_id, "status": "PASSED", "qc": "PASS", "done": True,
                       "interventions": 0, "coordinator_committed": True, "reset_epoch": 1})
    events = []
    recovery = ActFixedWaveRecovery(
        store=store, evidence_port=_EvidencePort(path=None, events=events),
        recovery_port=_RecoveryPort(events=events), reset_port=_ResetPort(events=events),
        manifest_scene_ids=("s-1", "s-2", "s-3"))
    return store, recovery, events


def test_a_terminal_scene_is_never_collected_again(tmp_path):
    store, recovery, _ = _fixture(tmp_path, terminal=("s-1", "s-3"))
    outcome = recovery.resume({"wave_index": 0, "scene_ids": ["s-1", "s-2", "s-3"],
                               "holding_state": "SAFE"}, context=None)
    assert outcome["already_terminal"] == ["s-1", "s-3"]
    assert outcome["reset"] == ["s-2"] and recovery.reset_port.calls == ["s-2"]


def test_a_held_scene_requires_verified_evidence_and_a_recovery_before_any_reset(tmp_path):
    evidence_file = tmp_path / "held.json"
    evidence_file.write_text("{}")
    digest = __import__("hashlib").sha256(evidence_file.read_bytes()).hexdigest()
    store, recovery, events = _fixture(tmp_path, holding_state="HELD")
    recovery.evidence_port = _EvidencePort(path=evidence_file, digest=digest, events=events)
    outcome = recovery.resume({"wave_index": 0, "scene_ids": ["s-1"], "holding_state": "HELD"},
                              context=None)
    assert outcome["recovered"] == ["s-1"] and recovery.reset_port.calls == ["s-1"]
    # the order is the guarantee: evidence, then the recovery transaction, then the reset
    assert events == ["evidence:s-1", "recover:s-1", "reset:s-1"]


def test_unproven_evidence_or_an_unknown_state_resets_nothing(tmp_path):
    store, recovery, _ = _fixture(tmp_path, holding_state="HELD")
    with pytest.raises(ValueError, match="RECOVERY_EVIDENCE_UNPROVEN"):
        recovery.resume({"wave_index": 0, "scene_ids": ["s-1"], "holding_state": "HELD"},
                        context=None)
    assert recovery.reset_port.calls == []                      # nothing was reset

    evidence_file = tmp_path / "held.json"
    evidence_file.write_text("{}")
    store, recovery, _ = _fixture(tmp_path, holding_state="UNKNOWN")
    recovery.evidence_port = _EvidencePort(path=evidence_file, digest="f" * 64)   # wrong digest
    with pytest.raises(ValueError, match="RECOVERY_EVIDENCE_UNPROVEN"):
        recovery.resume({"wave_index": 0, "scene_ids": ["s-1"], "holding_state": "UNKNOWN"},
                        context=None)
    assert recovery.reset_port.calls == []
    with pytest.raises(ValueError, match="WAVE_HOLDING_STATE_UNKNOWN"):
        recovery.resume({"wave_index": 0, "scene_ids": ["s-1"], "holding_state": "MAYBE"},
                        context=None)
    assert recovery.reset_port.calls == []
    # an unproven recovery transaction also blocks the reset
    recovery.evidence_port = _EvidencePort(path=evidence_file,
                                           digest=__import__("hashlib").sha256(
                                               evidence_file.read_bytes()).hexdigest())
    recovery.recovery_port = _RecoveryPort(recovered=False)
    with pytest.raises(ValueError, match="RECOVERY_TRANSACTION_UNPROVEN"):
        recovery.resume({"wave_index": 0, "scene_ids": ["s-1"], "holding_state": "UNKNOWN"},
                        context=None)
    assert recovery.reset_port.calls == []


def test_a_wave_that_is_not_part_of_the_manifest_is_refused(tmp_path):
    store, recovery, _ = _fixture(tmp_path)
    with pytest.raises(ValueError, match="WAVE_PARTITION_MISMATCH"):
        recovery.resume({"wave_index": 0, "scene_ids": ["s-9"], "holding_state": "SAFE"},
                        context=None)
    with pytest.raises(ValueError, match="WAVE_RECORD_INVALID"):
        recovery.resume({"wave_index": 0, "scene_ids": ["s-1", "s-1"], "holding_state": "SAFE"},
                        context=None)
    with pytest.raises(ValueError, match="WAVE_RECORD_INVALID"):
        recovery.resume({"scene_ids": ["s-1"]}, context=None)
