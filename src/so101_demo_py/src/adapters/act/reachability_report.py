"""Task 10 candidate port: verifies EXACT candidate identities from a supplied reachability report.

The report holds the 14 gate results and their evidence hashes per candidate identity. A candidate
absent from the report is refused rather than guessed at, and a gate whose evidence hash is missing or
malformed refuses the whole verification.
"""

from __future__ import annotations

import json
from pathlib import Path

from so101_demo.act.candidate_source import candidate_identity
from so101_demo.act.sampling import REACHABILITY_GATES

_REPORT_KEYS = frozenset({"schema_version", "kind", "gates"})
_GATE_KEYS = frozenset({"ok", "evidence_sha256"})


class ReachabilityReportPort:
    """A `candidate_port` whose `verify` answers only for candidates it holds evidence for."""

    def __init__(self, report: dict) -> None:
        if (not isinstance(report, dict) or set(report) != _REPORT_KEYS
                or report["schema_version"] != 1
                or report["kind"] != "act_candidate_reachability"):
            raise ValueError("REACHABILITY_REPORT_INVALID")
        gates = report["gates"]
        if not isinstance(gates, dict):
            raise ValueError("REACHABILITY_REPORT_INVALID")
        for identity, entry in gates.items():
            if not isinstance(identity, str) or len(identity) != 64:
                raise ValueError("REACHABILITY_REPORT_INVALID")
            if not isinstance(entry, dict) or set(entry) != set(REACHABILITY_GATES):
                raise ValueError("REACHABILITY_REPORT_INVALID")
            for name, gate in entry.items():
                if (not isinstance(gate, dict) or set(gate) != _GATE_KEYS
                        or type(gate["ok"]) is not bool
                        or not isinstance(gate["evidence_sha256"], str)
                        or len(gate["evidence_sha256"]) != 64):
                    raise ValueError("REACHABILITY_REPORT_INVALID")
        self._gates = gates

    @classmethod
    def from_path(cls, path: Path) -> "ReachabilityReportPort":
        return cls(json.loads(Path(path).read_bytes()))

    def verify(self, item: dict) -> dict:
        identity = candidate_identity(item)
        entry = self._gates.get(identity)
        if entry is None:
            raise ValueError("CANDIDATE_NOT_IN_REACHABILITY_REPORT")
        return {name: entry[name]["ok"] for name in sorted(REACHABILITY_GATES)}
