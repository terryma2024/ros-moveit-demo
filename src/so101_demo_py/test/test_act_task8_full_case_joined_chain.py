"""P1-5: one ACTUAL full case whose PRODUCTION code produces the artifact, both receipts and the journal.

The verdict's finding, in its own words, is that *the joined chain has never carried a sealed artifact*: the demo side
seals one with the production `PickPlaceRunner` but never publishes a journal row, while the teleop side publishes rows
with the production `run_pick_place_case` but only for **prefix** cases (whose artifact is empty by design). Each side
tested its half; nothing joined them.

This file joins them with **one substitution**: the process/stack owner, which is the external I/O - the same seam the
teleop suite substitutes when it drives the real child. Everything that produces evidence is production:

* the nine-phase composition and the runner that seals the artifact (`_full_case_port`, `PickPlaceRunner`);
* the case entry, its preflight, its campaign check, its live-evidence readback rule and its journal publisher
  (`run_pick_place_case`, `_publish_new`);
* both retirement receipts, written by the production code from the receipt files it reads back;
* the journal reader and (below) the calibration aggregator.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402

from test_act_task8_nine_phase_case import ATTEMPT, SCENARIO, SESSION, _full_case_port  # noqa: E402
from test_act_task8_sealed_artifact import _sealed_case  # noqa: E402

from so101_demo.act.pick_place_runner import PickPlaceRunner  # noqa: E402
from so101_demo.act.task8_manifest import build_task8_live_manifest, write_new_manifest  # noqa: E402
from so101_teleop.unified.pick_place_case_execution import run_pick_place_case  # noqa: E402

CASE_ID = "full-01"
ANCHORS = ("default", "left", "forward")


def _manifest(tmp_path: Path) -> tuple[dict, Path, str]:
    """The frozen manifest the case is declared in - the production builder, not a hand-written document."""

    anchors = {name: {"cup_start_m": [0.02, -0.28, 0.165], "neck_start_rad": 0.0} for name in ANCHORS}
    manifest = build_task8_live_manifest(
        anchors, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64, contact_policy_fingerprint="d" * 64,
        calibration_report_path="calibration-report.json", calibration_report_sha256="e" * 64)
    path = tmp_path / "manifest.json"
    write_new_manifest(path, manifest)
    return manifest, path, hashlib.sha256(path.read_bytes()).hexdigest()


class _Owner:
    """The process/stack seam, substituted: it starts and retires, and everything else is production."""

    def __init__(self, tmp_path: Path, result: dict, launch: SimpleNamespace, manifest: dict = None):
        self._result = result
        self._launch = launch
        self._manifest = manifest or {}
        self.context = None
        self._stack_retired = self._child_retired = self._final_clear = False
        self.stack = SimpleNamespace(launch=SimpleNamespace(evidence_root=str(tmp_path / "stack-evidence")))
        self.child_launch = SimpleNamespace(socket_root=str(tmp_path / "child-evidence"))
        self.stack_owner_key = SimpleNamespace(pid=1, pgid=1, started_ticks=1, argv_sha256="ab" * 32,
                                               environment_sha256="ac" * 32)
        self.child_owner_key = SimpleNamespace(pid=2, pgid=2, started_ticks=2, argv_sha256="ad" * 32,
                                               environment_sha256="ae" * 32)
        self.worker = SimpleNamespace(launch=launch, run_pick_place=self._run)
        Path(self.stack.launch.evidence_root).mkdir(parents=True)
        Path(self.child_launch.socket_root).mkdir(parents=True)

    async def _run(self, request):
        """The worker is the PRODUCTION runner's result: the child process is the seam, the runner is not."""

        assert request["attempt_id"] == CASE_ID
        assert request["mode"] == "full" and request["stop_after"] is None
        return self._result

    async def start(self, spec):
        # the campaign is production and checks these by name: the worker must point BACK at the same context, and
        # the context must say it is a single-worker full-case workload
        # `_HASH_FIELDS`: the campaign binds the context to the manifest by comparing these, so the context carries
        # the frozen manifest's own values rather than literals of my own
        self.context = SimpleNamespace(campaign_id="case-298",
                                       manifest_sha256=spec.payload["manifest_sha256"],
                                       operation_id="op-1", execution_generation=1,
                                       worker_count=1, workload_kind="task8_full",
                                       **{name: self._manifest[name] for name in
                                          ("source_sha256", "runtime_config_sha256",
                                           "collection_config_sha256", "contact_policy_fingerprint")})
        self.worker.context = self.context
        return self.context, self.worker

    async def finish(self, *, attempt_id):
        # the receipts are the ones the production entry reads back, so they must exist and describe this owner
        (Path(self.stack.launch.evidence_root) / "cleanup-receipt.json").write_text(json.dumps({
            "leader_pid": 1, "pgid": 1, "started_ticks": 1, "argv_sha256": "ab" * 32,
            "group_clear": True, "session_id": SESSION, "ros_domain_id": 198,
            "physical_stop_confirmed": True, "graph_clear": True}))
        (Path(self.child_launch.socket_root) / "cleanup-receipt.json").write_text(json.dumps({
            "leader_pid": 2, "pgid": 2, "started_ticks": 2, "argv_sha256": "ad" * 32, "group_clear": True}))
        self._stack_retired = self._child_retired = self._final_clear = True
        self.context = None


def _joined_case(tmp_path) -> tuple[dict, dict, Path, Path]:
    """Run one full case through BOTH production halves and return (row, index, artifact, case_root)."""

    result, index, artifact = _sealed_case(tmp_path)
    manifest, manifest_path, digest = _manifest(tmp_path)
    journal = tmp_path / "journal" / "result.json"
    journal.parent.mkdir()
    launch = SimpleNamespace(mujoco_session_id=SESSION, ros_domain_id=198)
    owner = _Owner(tmp_path, result, launch, manifest)
    spec = SimpleNamespace(kind="task8_full", deadline_ns=10 ** 18,
                           payload={"evidence_root": str(tmp_path), "manifest_path": str(manifest_path),
                                    "manifest_sha256": digest})
    row = _run(spec, owner, journal)
    return row, index, artifact, tmp_path


def _run(spec, owner, journal):
    import asyncio

    return asyncio.run(run_pick_place_case(spec, CASE_ID, owner, journal))


def test_the_production_runner_seals_and_the_production_entry_publishes_its_row(tmp_path):
    """One full case, both halves production: the artifact, the receipts and the journal row all exist."""

    row, index, artifact, _root = _joined_case(tmp_path)

    assert row["case_id"] == CASE_ID and row["mode"] == "full"
    assert row["completed_phases"] == list(PickPlaceRunner.PHASES), (
        "a full case completes the runner's whole phase list")
    assert row["live_evidence_path"] and Path(row["live_evidence_path"]).is_file(), "the sealed artifact exists"
    assert hashlib.sha256(Path(row["live_evidence_path"]).read_bytes()).hexdigest() == row["live_evidence_sha256"]
    assert row["stack_receipt_sha256"] != "0" * 64 and row["child_receipt_sha256"] != "0" * 64
    assert index["samples"], "the sealed index carries samples"


def test_the_qualification_reader_accepts_this_case_and_its_four_facts_hold(tmp_path):
    """P1-5's four facts, read from the case this chain produced - by the qualification layer's own reader.

    The verdict names them: the requested command event, adjacent support rows, two retirement receipts, and a
    complete journal. They are properties of ONE case, and this one is the case whose artifact the production runner
    sealed and whose row the production entry published.
    """

    from so101_demo.act.task8_live_evidence import require_campaign_cases
    from so101_demo.act.task8_live_qualification import validate_case_journals

    row, index, artifact_path, root = _joined_case(tmp_path)
    # the manifest is READ BACK, not rebuilt: `_joined_case` already wrote it with `write_new_manifest`, which refuses
    # to overwrite (FileExistsError) - the fixture's own rule, and the right one for a frozen document
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "contact_policy_fingerprint": manifest["contact_policy_fingerprint"]}

    # the reader walks the campaign's case ids and demands each one's row where the campaign writes it
    required = tuple(require_campaign_cases(manifest))
    assert CASE_ID in required, "the frozen manifest names this case"
    cases = tmp_path / "campaign" / "task8-live" / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    (cases / f"{CASE_ID}.json").write_text(json.dumps(row, sort_keys=True))

    # and it accepts this case: the reader is the qualification layer's, not my own expectation
    validated = validate_case_journals(tmp_path / "campaign", manifest, identities=identities,
                                       manifest_document_sha256=digest)
    assert validated, "the qualification reader returned the case rows it accepted"

    # FACT 1 - the requested command event: the artifact records the edge, and says WHICH edge it is
    records = [json.loads((artifact_path.parent / entry["relative_path"]).read_bytes())
               for entry in index["samples"]]
    reasons = [reason for record in records for reason in (record.get("event_reasons") or ())]
    assert "command" in reasons, f"the case records the moment the gripper was told to open: {sorted(set(reasons))}"

    # FACT 2 - adjacent support rows: the support decision is recorded sample by sample, in order
    support = [record.get("cup_supported") for record in records]
    assert len(support) == len(records) and all(value is not None for value in support), (
        "every recorded sample carries the support decision, so the rows are adjacent rather than sampled apart")

    # FACT 3 - two retirement receipts, named by the row and readable from disk
    assert row["stack_receipt_sha256"] != row["child_receipt_sha256"], "two distinct receipts"
    for key in ("stack_retirement_receipt_path", "child_retirement_receipt_path"):
        receipt = Path(row[key])
        assert receipt.is_file(), f"the row names a receipt that exists: {key}"
        assert hashlib.sha256(receipt.read_bytes()).hexdigest() == row[
            "stack_receipt_sha256" if key.startswith("stack") else "child_receipt_sha256"]

    # FACT 4 - a complete journal: every phase the runner has, in the runner's own order
    assert row["completed_phases"] == list(PickPlaceRunner.PHASES), "the journal is complete, not a prefix of it"
