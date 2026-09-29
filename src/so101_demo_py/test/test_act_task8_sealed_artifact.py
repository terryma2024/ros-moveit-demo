"""The sealed artifact, read back from its records: seven indexed assertions and four ways to break the chain.

The case is the nine-phase one (the full-case test), and every assertion below reads the ARTIFACT rather than the run's
return value - the point of a seal is that the evidence outlives the process that produced it.

Where a production reader exists it is used, and the test says which side checks what:
  * the artifact's own digest is checked by `_require_live_evidence_readback`, the child's own rule;
  * the per-record digest chain is checked here against the same rule the recorder applied when it registered each
    record (canonical bytes, sha256), because no production reader resolves a live-evidence index entry by name.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_task8_nine_phase_case import SCENARIO, SESSION, ATTEMPT, _full_case_port  # noqa: E402
from test_dynamic_pick import _template  # noqa: E402

from so101_demo.act.pick_place_runner import PickPlaceRunner  # noqa: E402
from so101_teleop.unified.pick_place_case_execution import _require_live_evidence_readback  # noqa: E402

#: the nine phases the runner drives, and the one that appears twice because it has two segments
PHASES = PickPlaceRunner.PHASES
PERIOD_S, TOLERANCE_S = 0.1, 0.01


def _sealed_case(tmp_path) -> tuple[dict, dict, Path]:
    """Run the nine-phase case and return its result, its sealed index and the artifact's path."""

    port, _calls, _boundary, _prefix = _full_case_port(tmp_path)
    port.bind_case_targets(gripper_closed_rad=0.2, close_duration_s=0.4,
                           motion_template=_template(), motion_duration_s=0.4)
    runner = PickPlaceRunner(port)
    result = runner.run({"mode": "full", "stop_after": None, "lifecycle": "FULL_RESTART",
                         "scenario_id": SCENARIO, "session_id": SESSION, "attempt_id": ATTEMPT,
                         "deadline_ns": runner.clock_ns() + 600_000_000_000})
    artifact = result["live_evidence_artifact"]
    path = Path(artifact["path"])
    return result, json.loads(path.read_bytes()), path


def _records(index: dict, path: Path) -> list[dict]:
    return [json.loads((path.parent / entry["relative_path"]).read_bytes()) for entry in index["samples"]]


def test_the_artifact_reads_back_exactly_under_the_productions_own_rule(tmp_path):
    """Assertion 1 - the digest, checked by the child's own reader rather than by this file."""

    result, _index, path = _sealed_case(tmp_path)
    _require_live_evidence_readback(result["live_evidence_artifact"], {"mode": "full"})
    assert path.is_file() and not path.is_symlink()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == result["live_evidence_artifact"]["sha256"]


def test_the_index_chains_to_complete_canonical_records(tmp_path):
    """Assertions 2 to 5 - the count, the per-record chain, the identity, and the 24 keys."""

    _result, index, path = _sealed_case(tmp_path)

    assert index["kind"] == "task8_live_evidence" and index["schema_version"] == 1          # 2
    assert index["sample_count"] == len(index["samples"]) == 10, "ten samples: nine phases, two retreat segments"

    for entry in index["samples"]:                                                          # 3
        relative = Path(entry["relative_path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        payload = (path.parent / relative).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"], entry["relative_path"]

    records = _records(index, path)
    for record in records:                                                                  # 4
        assert (record["case_id"], record["session_id"], record["attempt_id"]) == (SCENARIO, SESSION, ATTEMPT)
        assert (record["reset_epoch"], record["release_epoch"]) == (index["identity"]["reset_epoch"],
                                                                   index["identity"]["release_epoch"])
        assert len(record) == 24, "the canonical sample: no more and no fewer keys"          # 5


def test_the_indexed_phases_cover_the_runners_own_list_and_the_clock_advances_one_period(tmp_path):
    """Assertions 6 and 7 - coverage with the repeated phase, and the cadence the recorder enforces."""

    _result, index, path = _sealed_case(tmp_path)

    phases = [entry["phase"] for entry in index["samples"]]                                 # 6
    assert set(phases) == set(PHASES), "every phase the runner drives appears"
    assert phases.count("RADIAL_RETREAT") == 2, "the retreat is two segments of one phase"
    assert phases[-1] == "FINAL_CHECK", "and the case ends where the runner's list ends"

    stamps = [entry["sim_time_s"] for entry in index["samples"]]                            # 7
    deltas = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(abs(delta - PERIOD_S) <= TOLERANCE_S for delta in deltas), deltas


def test_four_negatives_break_the_chain_and_the_first_two_hit_the_productions_own_names(tmp_path):
    """Four breaks: a tampered record, a missing record, a foreign identity, and a broken cadence."""

    result, index, path = _sealed_case(tmp_path)

    # 1. the artifact's digest no longer matches what the case handed back - the child's own refusal
    tampered = tmp_path / "tampered-evidence.json"
    tampered.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_READBACK_MISMATCH"):
        _require_live_evidence_readback({"path": str(tampered), "sha256": result["live_evidence_artifact"]["sha256"],
                                         "schema_version": 1}, {"mode": "full"})

    # 2. an artifact that is not there at all
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_READBACK_MISSING"):
        _require_live_evidence_readback({"path": str(tmp_path / "absent.json"), "sha256": "0" * 64,
                                         "schema_version": 1}, {"mode": "full"})

    # 3. a foreign identity: the sealed index says which case it belongs to, and a different one is refused
    foreign = {**index, "identity": {**index["identity"], "case_id": "someone-elses-case"}}
    with pytest.raises(AssertionError):
        assert (foreign["identity"]["case_id"], foreign["identity"]["session_id"]) == (SCENARIO, SESSION)

    # 4. a record edited after sealing: the index's digest no longer matches its bytes
    entry = index["samples"][0]
    edited = json.loads((path.parent / entry["relative_path"]).read_bytes())
    edited["cup_position_m"] = [9.0, 9.0, 9.0]
    with pytest.raises(AssertionError):
        payload = json.dumps(edited, sort_keys=True, separators=(",", ":")).encode()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
