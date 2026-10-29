"""The terminal, cadence, stop, restart, smoke and teleop gates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path

from so101_demo.act.head_search.aggregate.contracts import (
    ANCHORS,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    MINIMUM_SCREENSHOTS,
    PASSED,
    QUAL_BUNDLE_MISSING,
    QUAL_CADENCE_BROKEN,
    QUAL_CADENCE_MISSING,
    QUAL_DIGEST_MISMATCH,
    QUAL_OUTCOME_DISAGREES,
    QUAL_RESTART_COUNT,
    QUAL_RESTART_INCOMPLETE,
    QUAL_RESTART_MISSING,
    QUAL_RESTART_UNREADABLE,
    QUAL_SMOKE_INCOMPLETE,
    QUAL_SMOKE_MISSING,
    QUAL_STOP_PROOF_MISSING,
    QUAL_STOP_PROOF_UNPROVEN,
    QUAL_TELEOP_INCOMPLETE,
    QUAL_TELEOP_MISSING,
    QUAL_TERMINALS_UNJUDGEABLE,
    RESTART_KIND,
    SMOKE_JOURNAL_ARTIFACT,
    SMOKE_KIND,
    SOCKET_PATH_LIMIT_BYTES,
    STOP_PROOF_SAMPLES,
    TELEOP_E2E_CASE,
    TELEOP_KIND,
    _digest,
    _finite,
    _path,
    _read_json,
    _Reasons,
)
from so101_demo.act.head_search.aggregate.run_gates import classify_qualification_terminal
from so101_demo.act.head_search.scenarios.contracts import (
    ARTIFACT as SCENARIOS_ARTIFACT,
)
from so101_demo.act.head_search.scenarios.contracts import (
    JOURNAL_ARTIFACT as SCENARIOS_JOURNAL_ARTIFACT,
)


def _gate_terminals(journal: Mapping, reasons: _Reasons) -> dict:
    entries = journal.get("entries") if isinstance(journal, Mapping) else None
    entries = entries if isinstance(entries, Mapping) else {}
    rows = journal.get("rows") if isinstance(journal, Mapping) else None
    rows = rows if isinstance(rows, Mapping) else {}
    if not entries:
        reasons.absent(
            "scenario_terminals",
            QUAL_TERMINALS_UNJUDGEABLE,
            SCENARIOS_JOURNAL_ARTIFACT,
            "no per-scenario evidence was readable, so no terminal status can be judged",
        )
        return {}
    passed = 0
    codes: dict[str, int] = {}
    for seed in sorted(entries):
        entry = entries[seed]
        verdict = classify_qualification_terminal(entry)
        if verdict["verdict"] == PASSED:
            passed += 1
        else:
            codes[str(verdict["code"])] = codes.get(str(verdict["code"]), 0) + 1
            reasons.violated(
                "scenario_terminals",
                str(verdict["code"]),
                f"scenario {seed} ({entry.get('condition_class')})",
                str(verdict["detail"]),
            )
        row = rows.get(seed) if isinstance(rows, Mapping) else None
        if isinstance(row, Mapping):
            row_passed = row.get("outcome") == PASSED
            if row_passed != (verdict["verdict"] == PASSED):
                reasons.violated(
                    "scenario_terminals",
                    QUAL_OUTCOME_DISAGREES,
                    f"scenario {seed} ({entry.get('condition_class')})",
                    f"the journal row reads outcome={row.get('outcome')!r} while the artefact's terminal "
                    f"{entry.get('terminal_status')!r} is judged {verdict['verdict']}",
                )
    return {"passed": passed, "judged": len(entries), "outcome_codes": codes}


def _gate_cadence(journal: Mapping, reasons: _Reasons) -> dict:
    rows = journal.get("rows") if isinstance(journal, Mapping) else None
    rows = rows if isinstance(rows, Mapping) else {}
    document = None
    if isinstance(journal, Mapping) and journal.get("document"):
        document, _ = _read_json(Path(journal["document"]))
    if not rows:
        reasons.absent(
            "frame_cadence",
            QUAL_CADENCE_MISSING,
            SCENARIOS_JOURNAL_ARTIFACT,
            "no journal rows were readable, so the 10 Hz contract cannot be checked",
        )
        return {}
    broken = []
    for seed in sorted(rows):
        cadence = rows[seed].get("frame_cadence")
        if not isinstance(cadence, Mapping):
            broken.append(f"{seed}: no frame_cadence block")
            continue
        if (
            cadence.get("continuous") is not True
            or int(cadence.get("duplicate_count", 0)) != 0
            or int(cadence.get("backward_count", 0)) != 0
            or int(cadence.get("undeclared_gap_count", 0)) != 0
        ):
            broken.append(f"{seed}: {dict(cadence)}")
            continue
        if not _finite(cadence.get("frame_period_s")) or abs(
            float(cadence["frame_period_s"]) - FRAME_PERIOD_S
        ) > 1e-9:
            broken.append(f"{seed}: frame period {cadence.get('frame_period_s')!r} is not 10 Hz")
    if broken:
        reasons.violated(
            "frame_cadence",
            QUAL_CADENCE_BROKEN,
            SCENARIOS_JOURNAL_ARTIFACT,
            f"{len(broken)} of {len(rows)} scenarios violate the 10 Hz frame contract: {broken[:4]}",
        )
    if isinstance(document, Mapping) and document.get("cadence_all_continuous") is not True:
        reasons.violated(
            "frame_cadence",
            QUAL_CADENCE_BROKEN,
            SCENARIOS_ARTIFACT,
            "the scenarios document does not claim continuous cadence for all forty scenarios",
        )
    return {"checked": len(rows), "broken": len(broken)}


def _gate_stops(journal: Mapping, reasons: _Reasons) -> dict:
    rows = journal.get("rows") if isinstance(journal, Mapping) else None
    rows = rows if isinstance(rows, Mapping) else {}
    document = None
    if isinstance(journal, Mapping) and journal.get("document"):
        document, _ = _read_json(Path(journal["document"]))
    if not rows:
        reasons.absent(
            "stop_proofs",
            QUAL_STOP_PROOF_MISSING,
            SCENARIOS_JOURNAL_ARTIFACT,
            "no journal rows were readable, so no stop proof can be read",
        )
        return {}
    unproven = []
    for seed in sorted(rows):
        proof = rows[seed].get("stop_proof")
        if not isinstance(proof, Mapping):
            unproven.append(f"{seed}: no stop_proof block")
            continue
        if (
            proof.get("proven") is not True
            or int(proof.get("longest_consecutive_run", 0)) < STOP_PROOF_SAMPLES
            or int(proof.get("sample_count", 0)) < STOP_PROOF_SAMPLES
        ):
            unproven.append(
                f"{seed}: proven={proof.get('proven')!r} "
                f"consecutive={proof.get('longest_consecutive_run')!r} "
                f"samples={proof.get('sample_count')!r}"
            )
    if unproven:
        reasons.violated(
            "stop_proofs",
            QUAL_STOP_PROOF_UNPROVEN,
            SCENARIOS_JOURNAL_ARTIFACT,
            f"{len(unproven)} of {len(rows)} scenarios carry no proven stop: {unproven[:4]}",
        )
    if isinstance(document, Mapping) and document.get("stop_proofs_all_proven") is not True:
        reasons.violated(
            "stop_proofs",
            QUAL_STOP_PROOF_UNPROVEN,
            SCENARIOS_ARTIFACT,
            "the scenarios document does not claim a proven stop for all forty scenarios",
        )
    return {"checked": len(rows), "unproven": len(unproven)}


def _gate_restarts(
    declared: Mapping, runtime: Mapping, approved: Mapping, reasons: _Reasons
) -> dict:
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else {}
    if not isinstance(observed_runtime, Mapping):
        observed_runtime = {}
    presented = declared.get("restart_receipts")
    if presented is None:
        reasons.absent(
            "anchor_restarts",
            QUAL_RESTART_MISSING,
            "restart_receipts",
            "no FULL_RESTART anchor receipts were presented; the plan fixes exactly one independent "
            "restart for each of default, left and forward",
        )
        return {}
    if isinstance(presented, (str, bytes)) or not isinstance(presented, Sequence):
        reasons.absent(
            "anchor_restarts",
            QUAL_RESTART_UNREADABLE,
            "restart_receipts",
            "the restart receipts must be the sequence of receipt files",
        )
        return {}
    readings: dict = {"receipts": {}, "seen": []}
    by_anchor: dict[str, list[tuple[Path, dict]]] = {}
    for value in presented:
        path = _path(value)
        if path is None:
            reasons.absent(
                "anchor_restarts", QUAL_RESTART_UNREADABLE, "restart_receipts", "an empty receipt path"
            )
            continue
        document, error = _read_json(path)
        if document is None:
            reasons.absent(
                "anchor_restarts", QUAL_RESTART_UNREADABLE, path.name, error
            )
            continue
        anchor = str(document.get("anchor", ""))
        by_anchor.setdefault(anchor, []).append((path, document))
        readings["seen"].append(anchor)
    for anchor in ANCHORS:
        receipts = by_anchor.get(anchor, [])
        if not receipts:
            reasons.absent(
                "anchor_restarts",
                QUAL_RESTART_MISSING,
                f"restart_{anchor}",
                f"exactly one independent FULL_RESTART receipt for the {anchor!r} anchor must be "
                f"presented; none was",
            )
            continue
        if len(receipts) > 1:
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_COUNT,
                f"restart_{anchor}",
                f"{len(receipts)} receipts were presented for the {anchor!r} anchor; the manifest must "
                f"contain each anchor exactly once",
            )
        path, document = receipts[0]
        readings["receipts"][anchor] = {"path": str(path), "sha256": _digest(path)}
        label = f"restart_{anchor}"
        if document.get("kind") != RESTART_KIND:
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"kind {document.get('kind')!r} is not {RESTART_KIND!r}",
            )
        if document.get("lifecycle") != "FULL_RESTART":
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"lifecycle {document.get('lifecycle')!r} is not FULL_RESTART",
            )
        teardown = document.get("teardown")
        teardown = teardown if isinstance(teardown, Mapping) else {}
        for field in ("previous_stack_stopped", "controller_owner_stopped", "children_exited", "graph_clear"):
            if teardown.get(field) is not True:
                reasons.violated(
                    "anchor_restarts",
                    QUAL_RESTART_INCOMPLETE,
                    label,
                    f"the teardown did not prove {field}",
                )
        reconstruction = document.get("reconstruction")
        reconstruction = reconstruction if isinstance(reconstruction, Mapping) else {}
        for field in ("stack_started", "one_mujoco_instance", "one_controller_owner"):
            if reconstruction.get(field) is not True:
                reasons.violated(
                    "anchor_restarts",
                    QUAL_RESTART_INCOMPLETE,
                    label,
                    f"the reconstruction did not prove {field}",
                )
        detector = document.get("detector")
        detector = detector if isinstance(detector, Mapping) else {}
        if int(detector.get("count", 0)) != 1 or str(detector.get("device", "")) != "cuda":
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart did not run exactly one CUDA detector: count={detector.get('count')!r} "
                f"device={detector.get('device')!r}",
            )
        if detector.get("weights_sha256") not in (None, observed_runtime.get("weight_sha256_declared")):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart detector ran weights {detector.get('weights_sha256')!r}",
            )
        search = document.get("search")
        search = search if isinstance(search, Mapping) else {}
        if (
            search.get("terminal_status") != "TARGET_LOCKED"
            or search.get("coverage_complete") is not True
            or int(search.get("wrong_locks", 0)) != 0
        ):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart search did not end on a clean lock: {dict(search)}",
            )
        lock = document.get("lock")
        lock = lock if isinstance(lock, Mapping) else {}
        if int(lock.get("consecutive_frames", 0)) < 3:
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart lock carried {lock.get('consecutive_frames')!r} consecutive frames",
            )
        timing = document.get("timing")
        timing = timing if isinstance(timing, Mapping) else {}
        if (
            timing.get("cadence_continuous") is not True
            or timing.get("within_thresholds") is not True
            or abs(float(timing.get("frame_rate_hz", 0.0)) - FRAME_RATE_HZ) > 1e-9
        ):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart timing gates did not pass: {dict(timing)}",
            )
        stop = document.get("stop")
        stop = stop if isinstance(stop, Mapping) else {}
        if (
            stop.get("proven") is not True
            or int(stop.get("qualifying_samples", 0)) < STOP_PROOF_SAMPLES
        ):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart stop proof is unproven: {dict(stop)}",
            )
        gates = document.get("gates")
        gates = gates if isinstance(gates, Mapping) else {}
        failed = sorted(
            name
            for name in ("graph", "detector", "search", "lock", "timing", "stop")
            if gates.get(name) != "PASS"
        )
        if failed:
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart did not pass {failed}",
            )
        restart_runtime = document.get("runtime")
        restart_runtime = restart_runtime if isinstance(restart_runtime, Mapping) else {}
        for key in (
            "source_commit",
            "production_config_sha256",
            "values_sha256",
            "weight_sha256_declared",
            "weight_sha256_observed",
            "allow_cpu_fallback",
            "cuda_device",
        ):
            if key in restart_runtime and restart_runtime.get(key) != observed_runtime.get(key):
                reasons.violated(
                    "anchor_restarts",
                    QUAL_RESTART_INCOMPLETE,
                    label,
                    f"the restart ran {key}={restart_runtime.get(key)!r}, the presented frozen runtime "
                    f"is {observed_runtime.get(key)!r}",
                )
        bundle = approved.get("bundle_sha256") if isinstance(approved, Mapping) else None
        if bundle and document.get("approved_bundle_sha256") not in (None, bundle):
            reasons.violated(
                "anchor_restarts",
                QUAL_RESTART_INCOMPLETE,
                label,
                f"the restart ran the bundle {document.get('approved_bundle_sha256')!r}, the presented "
                f"approved bundle is {bundle!r}",
            )
    extra = sorted(anchor for anchor in by_anchor if anchor not in ANCHORS)
    if extra:
        reasons.violated(
            "anchor_restarts",
            QUAL_RESTART_COUNT,
            "restart_receipts",
            f"receipts were presented for anchors outside the declared three: {extra}",
        )
    return readings


def _gate_smoke(declared: Mapping, runtime: Mapping, reasons: _Reasons) -> dict:
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else {}
    if not isinstance(observed_runtime, Mapping):
        observed_runtime = {}
    root = _path(declared.get("production_smoke_root"))
    if root is None:
        reasons.absent(
            "production_smoke",
            QUAL_SMOKE_MISSING,
            "production_smoke_root",
            "no production smoke phase root was presented; the plan requires producer -> sealed journal "
            "-> actual aggregator, and a planning-coverage proof is not a smoke journal",
        )
        return {}
    readings: dict = {"root": str(root)}
    journal_path = root / SMOKE_JOURNAL_ARTIFACT
    document, error = _read_json(journal_path)
    if document is None:
        present = sorted(path.name for path in root.iterdir()) if root.is_dir() else []
        reasons.absent(
            "production_smoke",
            QUAL_SMOKE_MISSING,
            f"production_smoke journal ({SMOKE_JOURNAL_ARTIFACT})",
            f"{error}; the root carries {present}, which is not the smoke journal the plan requires",
        )
        return readings
    readings["journal"] = str(journal_path)
    readings["sha256"] = _digest(journal_path)
    label = SMOKE_JOURNAL_ARTIFACT
    if document.get("kind") != SMOKE_KIND or document.get("phase") != "production_smoke":
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"kind {document.get('kind')!r} / phase {document.get('phase')!r} is not the production "
            f"smoke journal",
        )
    producer = document.get("producer")
    producer = producer if isinstance(producer, Mapping) else {}
    if not producer.get("entry") or producer.get("stack_owned") is not True:
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke does not declare the producer that owned its stack: {dict(producer)}",
        )
    sealed = document.get("journal")
    sealed = sealed if isinstance(sealed, Mapping) else {}
    sealed_path = _path(sealed.get("path"))
    if sealed_path is None or not sealed_path.is_file():
        reasons.absent(
            "production_smoke",
            QUAL_SMOKE_MISSING,
            "production_smoke sealed journal",
            f"the smoke journal names no readable sealed journal: {sealed.get('path')!r}",
        )
    else:
        sealed_digest = _digest(sealed_path)
        readings["sealed_journal"] = str(sealed_path)
        readings["sealed_journal_sha256"] = sealed_digest
        if sealed.get("sha256") != sealed_digest:
            reasons.violated(
                "production_smoke",
                QUAL_DIGEST_MISMATCH,
                "production_smoke sealed journal",
                f"the declared journal digest {sealed.get('sha256')!r} is not the digest of "
                f"{sealed_path} ({sealed_digest})",
            )
        aggregator = document.get("aggregator")
        aggregator = aggregator if isinstance(aggregator, Mapping) else {}
        if (
            aggregator.get("journal_sha256") != sealed_digest
            or aggregator.get("status") != "SUCCEEDED"
            or not aggregator.get("entry")
        ):
            reasons.violated(
                "production_smoke",
                QUAL_SMOKE_INCOMPLETE,
                label,
                f"the aggregator did not consume the sealed journal: {dict(aggregator)}",
            )
    if document.get("terminal_status") != "TARGET_LOCKED":
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke ended on {document.get('terminal_status')!r}, not TARGET_LOCKED",
        )
    if document.get("zero_wrong_locks") is not True:
        reasons.violated(
            "production_smoke", QUAL_SMOKE_INCOMPLETE, label, "the smoke does not claim zero wrong locks"
        )
    cadence = document.get("frame_cadence")
    cadence = cadence if isinstance(cadence, Mapping) else {}
    if (
        cadence.get("continuous") is not True
        or int(cadence.get("duplicate_count", 0)) != 0
        or int(cadence.get("backward_count", 0)) != 0
        or int(cadence.get("undeclared_gap_count", 0)) != 0
    ):
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke does not carry a continuous 10 Hz sequence: {dict(cadence)}",
        )
    commands = document.get("commands")
    commands = commands if isinstance(commands, Mapping) else {}
    if commands.get("bounded") is not True or int(commands.get("outside_corridor_count", -1)) != 0:
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke does not prove bounded commands: {dict(commands)}",
        )
    proof = document.get("stop_proof")
    proof = proof if isinstance(proof, Mapping) else {}
    if proof.get("proven") is not True or int(proof.get("qualifying_samples", 0)) < STOP_PROOF_SAMPLES:
        reasons.violated(
            "production_smoke",
            QUAL_STOP_PROOF_UNPROVEN,
            label,
            f"the smoke carries no proven three-sample stop: {dict(proof)}",
        )
    detector = document.get("detector")
    detector = detector if isinstance(detector, Mapping) else {}
    if (
        int(detector.get("count", 0)) != 1
        or str(detector.get("device", "")) != "cuda"
        or detector.get("allow_cpu_fallback") is not False
    ):
        reasons.violated(
            "production_smoke",
            QUAL_SMOKE_INCOMPLETE,
            label,
            f"the smoke did not run exactly one CUDA detector without CPU fallback: {dict(detector)}",
        )
    smoke_runtime = document.get("runtime")
    smoke_runtime = smoke_runtime if isinstance(smoke_runtime, Mapping) else {}
    for key in (
        "source_commit",
        "production_config_sha256",
        "values_sha256",
        "weight_sha256_declared",
        "weight_sha256_observed",
    ):
        if key in smoke_runtime and smoke_runtime.get(key) != observed_runtime.get(key):
            reasons.violated(
                "production_smoke",
                QUAL_SMOKE_INCOMPLETE,
                label,
                f"the smoke ran {key}={smoke_runtime.get(key)!r}, the presented frozen runtime is "
                f"{observed_runtime.get(key)!r}",
            )
    return readings


def _gate_teleop(
    declared: Mapping, runtime: Mapping, approved: Mapping, reasons: _Reasons
) -> dict:
    observed_runtime = runtime.get("runtime") if isinstance(runtime, Mapping) else {}
    if not isinstance(observed_runtime, Mapping):
        observed_runtime = {}
    path = _path(declared.get("teleop_acceptance_receipt"))
    if path is None:
        reasons.absent(
            "teleop_acceptance",
            QUAL_TELEOP_MISSING,
            "teleop_acceptance_receipt",
            "no Teleop acceptance receipt was presented; the separately owned acceptance fixture is the "
            "last declaration the plan requires before a qualification verdict",
        )
        return {}
    document, error = _read_json(path)
    if document is None:
        reasons.absent(
            "teleop_acceptance", QUAL_TELEOP_MISSING, "teleop_acceptance_receipt", error
        )
        return {}
    root = path.parent
    readings = {"receipt": str(path), "sha256": _digest(path)}
    label = "teleop_acceptance_receipt"
    if document.get("kind") != TELEOP_KIND or document.get("operation") != "TELEOP_ACCEPTANCE":
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"kind {document.get('kind')!r} / operation {document.get('operation')!r} is not a Teleop "
            f"acceptance receipt",
        )
    if document.get("source_commit") not in (None, observed_runtime.get("source_commit")):
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance ran the commit {document.get('source_commit')!r}, the frozen runtime is "
            f"{observed_runtime.get('source_commit')!r}",
        )
    bundle = approved.get("bundle_sha256") if isinstance(approved, Mapping) else None
    if not bundle:
        reasons.absent(
            "teleop_acceptance",
            QUAL_BUNDLE_MISSING,
            "approved_bundle",
            "no approved bundle was presented, so the acceptance cannot be bound to one",
        )
    elif document.get("bundle_sha256") != bundle:
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance ran the bundle {document.get('bundle_sha256')!r}, the approved bundle is "
            f"{bundle!r}",
        )
    report = document.get("qualification_report")
    report = report if isinstance(report, Mapping) else {}
    report_path = _path(report.get("path"))
    if report.get("status") != "HEAD_SEARCH_QUALIFIED":
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance did not start from a closed head-only report: "
            f"status {report.get('status')!r}",
        )
    elif report_path is None or not report_path.is_file():
        reasons.absent(
            "teleop_acceptance",
            QUAL_TELEOP_MISSING,
            "teleop acceptance qualification_report",
            f"the cited closed report {report.get('path')!r} does not exist",
        )
    elif report.get("sha256") != _digest(report_path):
        reasons.violated(
            "teleop_acceptance",
            QUAL_DIGEST_MISMATCH,
            "teleop acceptance qualification_report",
            f"the cited report digests to {_digest(report_path)}, not {report.get('sha256')!r}",
        )
    else:
        readings["qualification_report"] = {
            "path": str(report_path),
            "sha256": report.get("sha256"),
        }
    detector = document.get("detector")
    detector = detector if isinstance(detector, Mapping) else {}
    if int(detector.get("count", -1)) != 1 or int(detector.get("teleop_detector_factory_count", -1)) != 0:
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance must show one detector and a Teleop detector factory count of zero: "
            f"{dict(detector)}",
        )
    teardown = document.get("teardown")
    teardown = teardown if isinstance(teardown, Mapping) else {}
    if (
        teardown.get("controller_stopped") is not True
        or teardown.get("graph_clear") is not True
        or int(teardown.get("process_groups_exited", 0)) < 2
    ):
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the acceptance does not prove controller stop, both process groups exited and a clear "
            f"graph: {dict(teardown)}",
        )
    bridge = document.get("bridge")
    bridge = bridge if isinstance(bridge, Mapping) else {}
    sockets = bridge.get("socket_paths")
    sockets = sockets if isinstance(sockets, Sequence) and not isinstance(sockets, (str, bytes)) else []
    overlong = [str(name) for name in sockets if len(os.fsencode(str(name))) > SOCKET_PATH_LIMIT_BYTES]
    if len(sockets) < 2 or overlong:
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the bridge socket paths must all be {SOCKET_PATH_LIMIT_BYTES} bytes or fewer: "
            f"{overlong or sockets}",
        )
    else:
        readings["socket_path_bytes"] = max(len(os.fsencode(str(name))) for name in sockets)
    cleanup = bridge.get("cleanup_receipt")
    cleanup = cleanup if isinstance(cleanup, Mapping) else {}
    cleanup_path = _path(cleanup.get("path"))
    if cleanup_path is None or not cleanup_path.is_file():
        reasons.absent(
            "teleop_acceptance",
            QUAL_TELEOP_MISSING,
            "teleop acceptance cleanup_receipt",
            f"the bridge cleanup receipt {cleanup.get('path')!r} does not exist",
        )
    elif cleanup.get("sha256") not in (None, _digest(cleanup_path)):
        reasons.violated(
            "teleop_acceptance",
            QUAL_DIGEST_MISMATCH,
            "teleop acceptance cleanup_receipt",
            f"the cleanup receipt digests to {_digest(cleanup_path)}, not {cleanup.get('sha256')!r}",
        )
    e2e = document.get("e2e")
    e2e = e2e if isinstance(e2e, Mapping) else {}
    screenshots = e2e.get("screenshots")
    screenshots = (
        screenshots
        if isinstance(screenshots, Sequence) and not isinstance(screenshots, (str, bytes))
        else []
    )
    present = []
    for name in screenshots:
        candidate = Path(str(name))
        if not candidate.is_absolute():
            candidate = root / candidate
        present.append(candidate)
    missing_shots = [str(candidate) for candidate in present if not candidate.is_file()]
    if (
        e2e.get("case") != TELEOP_E2E_CASE
        or e2e.get("status") != "PASSED"
        or int(e2e.get("raw_overlay_pairs", 0)) < 1
        or len(present) < MINIMUM_SCREENSHOTS
        or missing_shots
    ):
        reasons.violated(
            "teleop_acceptance",
            QUAL_TELEOP_INCOMPLETE,
            label,
            f"the installed acceptance did not pass with fresh evidence: case={e2e.get('case')!r} "
            f"status={e2e.get('status')!r} pairs={e2e.get('raw_overlay_pairs')!r} "
            f"screenshots={len(present)} missing={missing_shots[:3]}",
        )
    else:
        readings["screenshots"] = [str(candidate) for candidate in present]
    return readings
