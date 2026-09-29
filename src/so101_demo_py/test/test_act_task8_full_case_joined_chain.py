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

    from so101_demo.act.task8_live_evidence import (
        require_campaign_cases, require_case_journal_row, require_case_row_matches_bundle,
    )

    row, index, artifact_path, root = _joined_case(tmp_path)
    # the manifest is READ BACK, not rebuilt: `_joined_case` already wrote it with `write_new_manifest`, which refuses
    # to overwrite (FileExistsError) - the fixture's own rule, and the right one for a frozen document
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "contact_policy_fingerprint": manifest["contact_policy_fingerprint"]}

    # `require_campaign_cases` is the frozen manifest's own case list: nine prefixes then five full cases, all
    # unique - so this case is one of the campaign's, not one the test invented
    required = tuple(require_campaign_cases(manifest))
    assert CASE_ID in required, f"the frozen manifest names this case: {CASE_ID} of {len(required)}"

    # and the TWO per-case validators accept it - the trusted rules, not my expectations. (The campaign-level reader,
    # `validate_case_journals`, is a different rule: it demands ALL fourteen rows under one root at once, which is a
    # campaign operation rather than this single case's; what a FULL row must satisfy is the pair below.)
    from so101_demo.act.task8_live_evidence import case_row_to_journal_row

    # `run_pick_place_case` publishes the CASE row; the journal row is the trusted translator's output, and it is the
    # journal row that the qualification rules read (`_JOURNAL_KEYS`). Translating first is what the live prefix chain
    # test does, and skipping it is what my first attempt did.
    journal_row = case_row_to_journal_row(row, identities=identities, manifest_document_sha256=digest)
    checked = require_case_journal_row(journal_row, mode="full")
    assert checked, "a full row carries its sealed evidence and both retirement receipts"
    matched = require_case_row_matches_bundle(journal_row, identities=identities,
                                              manifest_document_sha256=digest)
    assert matched, "and it describes the bundle it was produced under"

    records = [json.loads((artifact_path.parent / entry["relative_path"]).read_bytes())
               for entry in index["samples"]]

    # FACT 1 - the requested command event - is NOT derivable from this artifact, and that is a finding rather than a
    # test problem: the sample record's key set is closed (`_SAMPLE_KEYS`, 24 keys) and carries no event reason, so a
    # sealed record cannot say which edge it is; the WINDOW knows it (`event_reasons`, `add_event(sample, reason)`),
    # and the sealing drops it. Recorded for the packet beside CP-1725/1726 (the index cannot say how many of its
    # entries are grid points either). What the artifact CAN show is that the case recorded its phases in order and
    # that the RELEASE phase is among them - which is where a command edge belongs:
    phases = [record["phase"] for record in records]
    assert "RELEASE" in phases, "the case reaches the phase whose command edge is at issue"
    assert len(records) >= len(PickPlaceRunner.PHASES), (
        f"and it records at least one entry per phase: {len(records)} entries")

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


def test_four_negatives_are_derived_by_corrupting_this_baseline(tmp_path):
    """P1-5's negatives, each one a mutation of the case that just passed - never a row built beside it.

    The verdict's own wording: *"The cadence negative constructs a new row rather than mutating the sealed successful
    production chain."* So every negative here takes the artifact/journal this chain produced and changes ONE thing,
    and each must be refused by the PRODUCTION rule that owns that thing.
    """

    from so101_demo.act.task8_live_evidence import (
        case_row_to_journal_row, require_case_journal_row, require_case_row_matches_bundle,
        validate_evidence_grid,
    )

    row, index, artifact_path, root = _joined_case(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "contact_policy_fingerprint": manifest["contact_policy_fingerprint"]}
    journal_row = case_row_to_journal_row(row, identities=identities, manifest_document_sha256=digest)

    # NEGATIVE 1 - a row that lost a retirement receipt is refused by the row's own rule
    without_child = {key: value for key, value in row.items() if key != "child_receipt_sha256"}
    with pytest.raises(ValueError):
        case_row_to_journal_row(without_child, identities=identities, manifest_document_sha256=digest)

    # NEGATIVE 2 - an incomplete journal: the same row, one phase short, refused by name
    short = {**journal_row, "completed_phases": list(PickPlaceRunner.PHASES)[:-1]}
    with pytest.raises(ValueError):
        require_case_journal_row(short, mode="full")

    # NEGATIVE 3 - the cadence, by moving ONE instant of the SEALED samples rather than by building a row:
    # `validate_evidence_grid` is the production rule for the grid, and the untouched baseline must pass it too
    records = [json.loads((artifact_path.parent / entry["relative_path"]).read_bytes())
               for entry in index["samples"]]
    # one record per INSTANT: the edge additions share their grid sample's moment by design, and the grid's rule is
    # about the instants (a duplicate instant is a regression, which is what the same folding does in the
    # sealed-artifact cadence test)
    by_instant = {}
    for record in records:
        by_instant.setdefault(record["sim_time_s"], record)
    grid = [by_instant[stamp] for stamp in sorted(by_instant)]
    period = 0.1
    assert validate_evidence_grid(grid, period_s=period, tolerance_s=0.01) >= 1, "the baseline passes"
    moved = [dict(record) for record in grid]
    moved[1] = {**moved[1], "sim_time_s": moved[0]["sim_time_s"] + 0.25}
    with pytest.raises(ValueError):
        validate_evidence_grid(moved, period_s=period, tolerance_s=0.01)

    # NEGATIVE 4 - a row from another bundle: the same row under foreign identities is refused
    foreign = {"source_provenance_sha256": "f" * 64, "runtime_config_sha256": "b" * 64,
               "contact_policy_fingerprint": manifest["contact_policy_fingerprint"]}
    with pytest.raises(ValueError):
        require_case_row_matches_bundle(journal_row, identities=foreign, manifest_document_sha256=digest)
