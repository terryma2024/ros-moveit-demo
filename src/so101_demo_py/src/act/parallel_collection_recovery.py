"""Task 11A recovery: a wave is re-entered from what actually happened.

Two rules shape this module. A scene that already has a sealed result is never collected again, so a
re-entered wave only does the work that is genuinely outstanding. And a scene whose holding state is
HELD or UNKNOWN is never reset directly: evidence is captured and *verified* first, then an independent
recovery transaction runs, and only then may a reset be attempted — because a cup in the gripper, or a
state nobody can describe, is exactly where a blind reset destroys the thing worth knowing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

WAVE_RECORD_KEYS = frozenset({"wave_index", "scene_ids", "holding_state"})
_HOLDING_STATES = ("SAFE", "HELD", "UNKNOWN")
_EVIDENCE_REQUIRED = ("HELD", "UNKNOWN")


def _verify_evidence(evidence) -> dict:
    if (not isinstance(evidence, dict) or not isinstance(evidence.get("path"), str)
            or not isinstance(evidence.get("sha256"), str) or len(evidence["sha256"]) != 64):
        raise ValueError("RECOVERY_EVIDENCE_UNPROVEN")
    path = Path(evidence["path"])
    if not path.is_file():
        raise ValueError("RECOVERY_EVIDENCE_UNPROVEN")
    if hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]:
        raise ValueError("RECOVERY_EVIDENCE_UNPROVEN")
    return evidence


class ActFixedWaveRecovery:
    """Resumes one wave: what is terminal stays terminal, and nothing held is reset blind."""

    def __init__(self, *, store, evidence_port, recovery_port, reset_port, manifest_scene_ids) -> None:
        self.store = store
        self.evidence_port = evidence_port
        self.recovery_port = recovery_port
        self.reset_port = reset_port
        self.manifest_scene_ids = tuple(manifest_scene_ids)

    def _require_partition(self, scene_ids) -> tuple:
        if not isinstance(scene_ids, (list, tuple)) or not scene_ids:
            raise ValueError("WAVE_RECORD_INVALID")
        ids = tuple(scene_ids)
        if any(not isinstance(scene_id, str) for scene_id in ids) or len(set(ids)) != len(ids):
            raise ValueError("WAVE_RECORD_INVALID")
        unknown = [scene_id for scene_id in ids if scene_id not in self.manifest_scene_ids]
        if unknown:
            raise ValueError("WAVE_PARTITION_MISMATCH")
        return ids

    def resume(self, wave_record: dict, context) -> dict:
        if not isinstance(wave_record, dict) or set(wave_record) != WAVE_RECORD_KEYS:
            raise ValueError("WAVE_RECORD_INVALID")
        if type(wave_record["wave_index"]) is not int or wave_record["wave_index"] < 0:
            raise ValueError("WAVE_RECORD_INVALID")
        holding_state = wave_record["holding_state"]
        if holding_state not in _HOLDING_STATES:
            raise ValueError("WAVE_HOLDING_STATE_UNKNOWN")
        ids = self._require_partition(wave_record["scene_ids"])

        already_terminal, recovered, reset = [], [], []
        for scene_id in ids:
            if self.store.has_result(scene_id):
                already_terminal.append(scene_id)          # never collected twice
                continue
            if holding_state in _EVIDENCE_REQUIRED:
                # evidence first, verified against its bytes, before anything is reset
                evidence = _verify_evidence(self.evidence_port.capture(scene_id, context))
                outcome = self.recovery_port.recover(scene_id, context, evidence)
                if not isinstance(outcome, dict) or outcome.get("recovered") is not True:
                    raise ValueError("RECOVERY_TRANSACTION_UNPROVEN")
                recovered.append(scene_id)
            self.reset_port.reset(scene_id, context)
            reset.append(scene_id)
        return {"wave_index": wave_record["wave_index"], "holding_state": holding_state,
                "already_terminal": already_terminal, "recovered": recovered, "reset": reset}
