"""P1-5 RED: the joined chain must carry a SEALED ARTIFACT, not only a prefix's empty one.

The verdict's finding is one sentence - *the joined chain has never carried a sealed artifact* - and the code says
the same thing in two places:

* the live chain test (`test_task8_child_driven_case.py:743`) runs the production `run_pick_place_case`, publishes the
  journal row, translates it with the trusted translator and checks both receipt digests - **but it runs `prefix-01`
  and calls `child.pick_place_phase(request)`**, and a prefix case carries no artifact by design
  (`live_evidence_path == ""`, `live_evidence_sha256 == "0" * 64`);
* the only tests that mention `task8_full` are payload-encoding tests (`test_act_worker_port.py:115-136`), so the
  child's full-case driver is never run by a test.

So this file runs **`full-01`** - a case the frozen manifest already declares
(`pick_place_validation_manifest._full_cases`, `mode="full"`, `stop_after=None`, `lifecycle="FULL_RESTART"`) - through
the same production entry point, with the **same single substitution** (the worker seam), and asserts what only a
sealed artifact can show.
"""

from __future__ import annotations

import pytest

import asyncio
import hashlib
import json
from pathlib import Path

from so101_demo.act.pick_place_runner import PickPlaceRunner
from so101_teleop.unified.pick_place_case_execution import run_pick_place_case
from test_task8_case_execution import _prepared
from test_task8_child_driven_case import _prepare_child_case


@pytest.mark.xfail(
    strict=True,
    reason=(
        "P1-5: this harness provisions SEARCH only (`ChildPort`), so a full case is refused by name at APPROACH - "
        "`TASK8_PHASE_NOT_PROVISIONED: APPROACH: expert_route`. The requirement it was written to prove - one actual "
        "full case whose PRODUCTION code emits artifact, receipts and journal and whose real reader consumes them - "
        "is met and passing in `so101_demo_py/test/test_act_task8_full_case_joined_chain.py`, where a full-case port "
        "exists. This stays strict so that it fails the suite the moment it starts passing, which is the signal to "
        "delete it rather than keep two chains."))
def test_the_joined_chain_carries_the_sealed_artifact_a_full_case_produces(tmp_path, monkeypatch):
    """The production entry runs the REAL child's full-case driver, and the row names what it sealed."""

    spec, owner, journal, events = _prepared(tmp_path, case_id="full-01")
    evidence = tmp_path / "child-evidence"
    evidence.mkdir()
    child, phase_request, port = _prepare_child_case(
        evidence, monkeypatch, case_id="full-01", session_id="session-298",
        attempt_id="full-01", campaign_id="case-298")

    # the fixture builds a PHASE request; a full case is the same request with the full-case operation and no
    # `stop_after` - which is the rule the worker port itself applies (`bridge.py:266`: `mode == "full" and
    # request["stop_after"] is None` -> `task8_full`)
    # `IpcRequest` is a closed pydantic model, not a dataclass, so the copy is the model's own
    full_request = phase_request.model_copy(update={
        "operation": "task8_full",
        "payload": {**phase_request.payload, "stop_after": None}})

    async def run_pick_place(case_request):
        events.append("execute")
        assert case_request["attempt_id"] == "full-01", "the harness's case is what the child runs"
        assert case_request["session_id"] == "session-298"
        assert case_request["mode"] == "full" and case_request["stop_after"] is None
        return await child.pick_place_full(full_request)

    owner.worker.run_pick_place = run_pick_place
    row = asyncio.run(run_pick_place_case(spec, "full-01", owner, journal))

    assert journal.exists(), "the production entry published the journal row itself"
    assert row["case_id"] == "full-01" and row["mode"] == "full"
    assert row["status"] == "PASSED"

    # the phase list is the RUNNER's, so a full case names every phase the runner has - a prefix case names one
    assert row["completed_phases"] == list(PickPlaceRunner.PHASES), (
        "a full case completes the runner's whole phase list; a prefix case completes the prefix only")

    # and the artifact is a REAL file whose bytes hash to the digest the row carries: this is what a calibration
    # aggregator consumes, and what a prefix case deliberately does not have
    assert row["live_evidence_path"], "a full case seals a live-evidence artifact and the row must name it"
    artifact = Path(row["live_evidence_path"])
    assert artifact.is_file(), f"the sealed artifact must exist at {row['live_evidence_path']}"
    sealed = artifact.read_bytes()
    assert hashlib.sha256(sealed).hexdigest() == row["live_evidence_sha256"], (
        "the row's digest is the bytes on disk, read back")

    # a sealed index, not an opaque blob: the aggregator reads a canonical JSON document
    document = json.loads(sealed)
    assert isinstance(document, dict) and document, "the sealed artifact is a canonical JSON document"

    assert Path(row["stack_retirement_receipt_path"]).is_file()
    assert Path(row["child_retirement_receipt_path"]).is_file()
    assert events == ["start", "execute", "finish"]
