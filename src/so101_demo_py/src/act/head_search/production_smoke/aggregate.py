"""Aggregate, write and fly the production smoke."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import time

from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.production_smoke.journal import (
    AGGREGATOR_ENTRY,
    ANCHORS,
    CONDITION_CLASS,
    CONDITION_CLASS_DEFINITION,
    FIT_WARNING,
    JOURNAL_ARTIFACT,
    KIND,
    OPERATION,
    PHASE,
    RECEIPT_ARTIFACT,
    RECEIPT_KIND,
    RESTART_CODE_MAP,
    SCHEMA_VERSION,
    SEALED_ARTIFACT,
    SEALED_KIND,
    SMOKE_ANCHOR_UNDECLARED,
    SMOKE_CADENCE_BROKEN,
    SMOKE_COMMANDS_UNBOUNDED,
    SMOKE_CUP_NOT_PLACED,
    SMOKE_DETECTOR_FAILED,
    SMOKE_GPU_NOT_RELEASED,
    SMOKE_JOURNAL_INVALID,
    SMOKE_JOURNAL_UNREADABLE,
    SMOKE_LOCK_UNPROVEN,
    SMOKE_OWNERSHIP_MISMATCH,
    SMOKE_OWNERSHIP_REFUSED,
    SMOKE_PROBE_FAILED,
    SMOKE_RUN_ROOT_EXISTS,
    SMOKE_RUNTIME_UNVERIFIED,
    SMOKE_SEAL_MISMATCH,
    SMOKE_STACK_START_FAILED,
    SMOKE_STOP_UNPROVEN,
    SMOKE_TEARDOWN_UNPROVEN,
    STDERR_LOG,
    STDOUT_LOG,
    _cadence_summary,
    _commands_summary,
    _digest,
    _finite,
    _gate,
    _read_json,
    _refuse,
    _stop_summary,
    _utc_now,
    _write,
    classify_terminal,
    sealed_journal_document,
    smoke_cadence,
    smoke_commands,
    validate_smoke_journal,
    write_coverage_proof,
)
from so101_demo.act.head_search.qualification import _require_new_root
from so101_demo.act.head_search.restarts.contracts import (
    RESTART_OWNERSHIP_MISMATCH,
    RESTART_OWNERSHIP_REFUSED,
    RESTART_RUNTIME_UNVERIFIED,
)
from so101_demo.act.head_search.restarts.observation import (
    anchor_declarations,
    read_ownership_receipt,
    require_runtime_of_record,
)
from so101_demo.act.head_search.scenarios.stop_proof import stop_proof
from so101_demo.act.head_search.timing_measurement.contracts import (
    FRAME_RATE_HZ,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def aggregate_production_smoke(
    sealed_journal_path,
    *,
    run_root=None,
    producer: Mapping | None = None,
    entry: str = AGGREGATOR_ENTRY,
    now=time.gmtime,
) -> dict:
    """Read a sealed journal back off disk and write the document the qualification gate consumes.

    This is the middle link of the plan's "producer -> sealed journal -> actual aggregator" chain, and it
    is deliberately a **reader**: it opens the file, refuses a body whose digest is not the one the seal
    declares, and then re-derives the cadence, the commands, the stop proof and the terminal from the raw
    records. It never consults the flight's own summary, and it writes ``production-smoke-journal.json``.
    """

    path = Path(sealed_journal_path)
    try:
        sealed = _read_json(path)
    except (OSError, ValueError) as error:
        raise _refuse(
            SMOKE_JOURNAL_UNREADABLE,
            f"the sealed journal {path} cannot be read as one document ({error}); an aggregator with no "
            f"sealed journal has nothing to aggregate",
        ) from error
    if sealed.get("kind") != SEALED_KIND:
        raise _refuse(
            SMOKE_JOURNAL_UNREADABLE,
            f"{path} carries kind {sealed.get('kind')!r}, not {SEALED_KIND!r}",
        )
    declared_digest = (sealed.get("sealed") or {}).get("body_sha256")
    body = {key: value for key, value in sealed.items() if key != "sealed"}
    computed = canonical_sha256(body)
    if declared_digest != computed:
        raise _refuse(
            SMOKE_SEAL_MISMATCH,
            f"the sealed journal's body digest is {computed}, not the declared {declared_digest!r}: the "
            f"file was edited after it was sealed",
        )

    root = Path(run_root) if run_root is not None else Path(str(sealed.get("run_root")))
    runtime = dict(sealed.get("runtime") or {})
    thresholds = (
        sealed.get("control_thresholds")
        if isinstance(sealed.get("control_thresholds"), Mapping)
        else {}
    )
    stop = sealed.get("stop") if isinstance(sealed.get("stop"), Mapping) else {}
    velocity_limit = thresholds.get("stop_velocity_rad_s")
    if velocity_limit is None:
        velocity_limit = stop.get("velocity_limit_rad_s")
    if not _finite(velocity_limit) or float(velocity_limit) <= 0.0:
        raise _refuse(
            SMOKE_JOURNAL_UNREADABLE,
            f"the sealed journal records no positive stop velocity limit ({velocity_limit!r}), so the held "
            f"samples cannot be judged against the promoted stop_velocity_rad_s",
        )
    corridor = (sealed.get("corridors") or {}).get("lock_valid_neck_rad")
    commands_record = sealed.get("commands")
    if isinstance(commands_record, Mapping):
        commands_record = {**dict(commands_record), "corridor_rad": corridor}
    cadence = smoke_cadence(list(sealed.get("frames") or ()))
    commands = smoke_commands(commands_record)
    proof = stop_proof(
        list(stop.get("samples") or ()),
        velocity_limit_rad_s=float(velocity_limit),
        required_samples=3,
    )
    proof["held_at_rad"] = stop.get("held_at_rad")
    proof["source"] = stop.get("source")
    proof["controller_stop_confirmed"] = stop.get("controller_stop_confirmed")
    proof["criterion"] = stop.get("criterion")
    classification = (
        classify_terminal(
            sealed.get("terminal_status"),
            condition_class=str(sealed.get("condition_class") or CONDITION_CLASS),
            coverage=sealed.get("coverage"),
            seed=f"{PHASE}-{sealed.get('anchor')}",
        )
        if not sealed.get("flight_refusal")
        else None
    )
    detector = sealed.get("detector") if isinstance(sealed.get("detector"), Mapping) else {}
    teardown = sealed.get("teardown") if isinstance(sealed.get("teardown"), Mapping) else {}
    stack = sealed.get("stack") if isinstance(sealed.get("stack"), Mapping) else {}
    lock = sealed.get("lock") if isinstance(sealed.get("lock"), Mapping) else {}
    scene = sealed.get("scene") if isinstance(sealed.get("scene"), Mapping) else {}
    camera = sealed.get("camera") if isinstance(sealed.get("camera"), Mapping) else {}
    reconstruction = (
        sealed.get("reconstruction") if isinstance(sealed.get("reconstruction"), Mapping) else {}
    )

    teardown_fields = (
        "previous_stack_stopped",
        "controller_owner_stopped",
        "children_exited",
        "graph_clear",
    )
    gates = {
        "stack": _gate(
            "stack",
            bool(stack.get("nodes"))
            and reconstruction.get("stack_started") is True
            and reconstruction.get("one_mujoco_instance") is True,
            f"nodes={list(stack.get('nodes') or ())}, reconstruction={dict(reconstruction)}",
        ),
        "detector": _gate(
            "detector",
            int(detector.get("count", 0)) == 1
            and str(detector.get("device", "")) == "cuda"
            and detector.get("allow_cpu_fallback") is False
            and detector.get("weights_sha256") == runtime.get("weight_sha256_declared"),
            f"detector={dict(detector)}",
        ),
        "scene": _gate(
            "scene",
            bool(scene.get("point_m")) and bool(scene.get("service")),
            f"the anchor's cup placement: {dict(scene)}",
        ),
        "search": _gate(
            "search",
            bool(classification) and classification["outcome"] == "PASSED",
            (
                "no terminal was recorded"
                if not classification
                else f"terminal {sealed.get('terminal_status')!r}: "
                f"{classification['outcome']} {classification['outcome_code'] or ''} "
                f"{classification['outcome_detail'] or ''}".strip()
            ),
        ),
        "lock": _gate(
            "lock",
            int(lock.get("consecutive_frames", 0)) >= 3,
            f"lock={dict(lock)}",
        ),
        "cadence": _gate(
            "cadence", cadence["continuous"] is True, f"cadence={_cadence_summary(cadence)}"
        ),
        "commands": _gate(
            "commands",
            commands["bounded"] is True and int(commands["outside_corridor_count"]) == 0,
            f"commands={_commands_summary(commands)}",
        ),
        "stop": _gate(
            "stop",
            proof["proven"] is True and int(proof["qualifying_samples"]) >= 3,
            f"stop_proof={_stop_summary(proof)}",
        ),
        "teardown": _gate(
            "teardown",
            all(teardown.get(field) is True for field in teardown_fields),
            f"teardown={ {field: teardown.get(field) for field in teardown_fields} }",
        ),
        "gpu": _gate(
            "gpu",
            teardown.get("gpu_released") is True,
            f"gpu_compute_apps={list(teardown.get('gpu_compute_apps') or ())}",
        ),
    }

    refuse_on = {
        "stack": SMOKE_STACK_START_FAILED,
        "detector": SMOKE_DETECTOR_FAILED,
        "scene": SMOKE_CUP_NOT_PLACED,
        "search": SMOKE_LOCK_UNPROVEN,
        "lock": SMOKE_LOCK_UNPROVEN,
        "cadence": SMOKE_CADENCE_BROKEN,
        "commands": SMOKE_COMMANDS_UNBOUNDED,
        "stop": SMOKE_STOP_UNPROVEN,
        "teardown": SMOKE_TEARDOWN_UNPROVEN,
        "gpu": SMOKE_GPU_NOT_RELEASED,
    }
    refusals: list[dict] = []
    flight_refusal = sealed.get("flight_refusal")
    if isinstance(flight_refusal, Mapping) and flight_refusal:
        original = str(flight_refusal.get("code") or "")
        refusals.append(
            {
                "code": RESTART_CODE_MAP.get(original, SMOKE_PROBE_FAILED),
                "detail": f"the flight refused with {original}: {flight_refusal.get('detail')}",
                "flight_code": original,
            }
        )
    for name in (
        "stack",
        "detector",
        "scene",
        "search",
        "lock",
        "cadence",
        "commands",
        "stop",
        "teardown",
        "gpu",
    ):
        if gates[name]["status"] != "PASS":
            refusals.append({"code": refuse_on[name], "detail": gates[name]["detail"]})

    sealed_digest = _digest(path)
    measured_rate = camera.get("measured_rate_hz")
    document: dict = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "operation": OPERATION,
        "phase": PHASE,
        "run_root": str(root),
        "anchor": sealed.get("anchor"),
        "condition_class": sealed.get("condition_class"),
        "condition_class_definition": CONDITION_CLASS_DEFINITION,
        "producer": dict(sealed.get("producer") or {}),
        "aggregator": {
            "entry": entry,
            "journal_sha256": sealed_digest,
            "status": "SUCCEEDED",
            "body_sha256": computed,
            "at_utc": _utc_now(now),
            "definition": (
                "the aggregator read the sealed journal back from disk, re-derived every reading below "
                "from its raw records, and wrote this document; SUCCEEDED means the read and the "
                "re-derivation both happened, not that the gates passed"
            ),
        },
        "journal": {
            "path": str(path),
            "sha256": sealed_digest,
            "kind": SEALED_KIND,
            "body_sha256": computed,
            "frames": cadence["frame_count"],
            "command_count": commands["command_count"],
            "stop_sample_count": proof["sample_count"],
        },
        "ownership": dict(sealed.get("ownership") or {}),
        "runtime": runtime,
        "coverage_proof": sealed.get("coverage_proof"),
        "approved_bundle_sha256": sealed.get("approved_bundle_sha256"),
        "seal_sha256": sealed.get("seal_sha256"),
        "terminal_status": sealed.get("terminal_status"),
        "terminal": dict(sealed.get("terminal") or {}),
        "outcome": None if not classification else classification["outcome"],
        "outcome_code": None if not classification else classification["outcome_code"],
        "outcome_detail": None if not classification else classification["outcome_detail"],
        "zero_wrong_locks": bool(
            classification is not None
            and classification["outcome"] == "PASSED"
            and int(lock.get("consecutive_frames", 0)) >= 3
        ),
        "frame_cadence": cadence,
        "commands": commands,
        "stop_proof": proof,
        "lock": dict(lock),
        "detector": dict(detector),
        "stack": dict(stack),
        "camera": dict(camera),
        "clock": dict(sealed.get("clock") or {}),
        "scene": dict(scene),
        "admission": dict(sealed.get("admission") or {}),
        "adapter_liveness": dict(sealed.get("adapter_liveness") or {}),
        "neck_port": dict(sealed.get("neck_port") or {}),
        "reconstruction": dict(reconstruction),
        "teardown": dict(teardown),
        "corridors": dict(sealed.get("corridors") or {}),
        "provenance": {
            "run_root": str(root),
            "final_run": runtime.get("final_run"),
            "source_commit": runtime.get("source_commit"),
            "production_config": runtime.get("production_config"),
            "production_config_sha256": runtime.get("production_config_sha256"),
            "values_sha256": runtime.get("values_sha256"),
            "weight_path": runtime.get("weight_path"),
            "weight_sha256": runtime.get("weight_sha256_observed"),
            "approved_bundle_sha256": sealed.get("approved_bundle_sha256"),
            "seal_sha256": sealed.get("seal_sha256"),
            "anchor": sealed.get("anchor"),
            "condition_class": sealed.get("condition_class"),
            "nodes": list(stack.get("nodes") or ()),
            "node_count": len(stack.get("nodes") or ()),
            "device": detector.get("device"),
            "model_id": detector.get("model_id"),
            "published_frame_id": camera.get("published_frame_id"),
            "declared_rate_hz": FRAME_RATE_HZ,
            "measured_rate_hz": measured_rate,
            "consumed_frame_rate_hz": cadence["achieved_rate_hz"],
            "elapsed_s": sealed.get("elapsed_s"),
            "producer_elapsed_s": sealed.get("producer_elapsed_s"),
            "started_at_utc": sealed.get("started_at_utc"),
            "finished_at_utc": sealed.get("finished_at_utc"),
            "teardown_proof": {field: teardown.get(field) for field in teardown_fields}
            | {"gpu_released": teardown.get("gpu_released")},
        },
        "frames": list(sealed.get("frames") or ()),
        "gates": {name: gates[name]["status"] for name in gates},
        "gate_details": gates,
        "refusals": refusals,
        "status": "REFUSED" if refusals else "PASS",
        "flight_refusal": None if flight_refusal is None else dict(flight_refusal),
        "started_at_utc": sealed.get("started_at_utc"),
        "finished_at_utc": sealed.get("finished_at_utc"),
        "elapsed_s": sealed.get("elapsed_s"),
        "fit_warning": FIT_WARNING,
    }
    if producer is not None:
        document["producer"] = {**dict(producer), "stack_owned": True}
    # the artefact's own digest covers everything except itself and the aggregation instant, so reading
    # the same sealed journal twice reproduces the same digest
    digest_body = {key: value for key, value in document.items() if key != "sha256"}
    digest_body["aggregator"] = {
        key: value for key, value in digest_body["aggregator"].items() if key != "at_utc"
    }
    document["sha256"] = canonical_sha256(digest_body)

    problems = validate_smoke_journal(document)
    if problems:
        raise _refuse(
            SMOKE_JOURNAL_INVALID,
            f"the aggregated journal does not carry the shape the qualification gate reads: {problems}",
        )
    root.mkdir(parents=True, exist_ok=True)
    _write(root, JOURNAL_ARTIFACT, document)
    _write(
        root,
        RECEIPT_ARTIFACT,
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RECEIPT_KIND,
            "operation": OPERATION,
            "phase": PHASE,
            "run_root": str(root),
            "anchor": document["anchor"],
            "journal": str(root / JOURNAL_ARTIFACT),
            "journal_sha256": _digest(root / JOURNAL_ARTIFACT),
            "sealed_journal": str(path),
            "sealed_journal_sha256": sealed_digest,
            "gates": document["gates"],
            "refusals": refusals,
            "status": document["status"],
            "sha256": document["sha256"],
        },
    )
    return document


def write_head_search_production_smoke(
    *,
    run_root,
    ownership_receipt,
    runtime: Mapping,
    seal: Mapping,
    workdir,
    run_flight,
    producer: Mapping,
    approved_bundle_sha256: str,
    anchor: str = "default",
    condition_class: str = CONDITION_CLASS,
    values: Mapping | None = None,
    now=time.gmtime,
) -> dict:
    """Claim a brand-new run root, fly one anchor through the production path, seal it and aggregate it.

    The order is fixed and it is the plan's: the class is judged against the plan's own vocabulary, the
    runtime is the CUDA-only runtime of record, the Step 1 receipt must guard exactly this run root, the
    seal must declare this anchor, and only then is the root claimed and the stack started. A flight that
    refuses leaves its sealed journal and its journal behind: a run that did not pass is still readable.
    """

    root = Path(run_root)
    if root.exists():
        raise _refuse(
            SMOKE_RUN_ROOT_EXISTS,
            f"{root} exists; a qualification phase is never resumed, continued or overwritten",
        )
    classify_terminal(None, condition_class=condition_class)
    if anchor not in ANCHORS:
        raise _refuse(
            SMOKE_ANCHOR_UNDECLARED,
            f"the smoke anchor {anchor!r} is not one of the plan's anchors {list(ANCHORS)}",
        )
    try:
        runtime = require_runtime_of_record(runtime)
    except CalibrationInputsRefused as error:
        raise _refuse(SMOKE_RUNTIME_UNVERIFIED, f"{error.code}: {error.detail}") from error
    try:
        ownership = read_ownership_receipt(ownership_receipt, run_root=root)
    except CalibrationInputsRefused as error:
        code = {
            RESTART_OWNERSHIP_REFUSED: SMOKE_OWNERSHIP_REFUSED,
            RESTART_OWNERSHIP_MISMATCH: SMOKE_OWNERSHIP_MISMATCH,
            RESTART_RUNTIME_UNVERIFIED: SMOKE_RUNTIME_UNVERIFIED,
        }.get(error.code, SMOKE_OWNERSHIP_MISMATCH)
        raise _refuse(code, f"{error.code}: {error.detail}") from error
    try:
        declared = anchor_declarations(seal, [anchor])
    except CalibrationInputsRefused as error:
        raise _refuse(SMOKE_ANCHOR_UNDECLARED, f"{error.code}: {error.detail}") from error
    if len(declared) != 1:
        raise _refuse(
            SMOKE_ANCHOR_UNDECLARED,
            f"the seal resolves the anchor {anchor!r} to {len(declared)} declarations, not one",
        )
    declared = declared[0]
    from so101_demo.act.head_search.deadband_measurement.lock_trial import motion_corridor_rad
    from so101_demo.act.head_search.fine_correction_episodes.episode import fine_corridor_rad

    corridors = {
        "lock_valid_neck_rad": list(fine_corridor_rad(geometry_seal=seal)),
        "required_search_domain_rad": [
            float(bound) for bound in seal["required_search_domain_rad"]
        ],
        "sweep_corridor_rad": list(motion_corridor_rad(geometry_seal=seal)),
        "lock_valid_definition": (
            "the seal's own lock_valid_neck_rad: the interval a lock is valid in, the interval the "
            "controller's plan clamps its stops to, and the corridor every commanded target is judged "
            "against (the seal's `default` anchor starts outside the required search domain, so "
            "that domain cannot bound the anchor start without refusing the plan's own anchor)"
        ),
    }

    _require_new_root(root)
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    # the plan the flight walks is proven before anything is commanded, and the proof stays in the run
    # root: the plan's coverage gate cites this artefact, while the smoke's own success is the journal
    coverage = write_coverage_proof(
        root, seal, anchor, anchor_rad=float(declared["neck_start_rad"])
    )
    anchor_root = root / anchor
    anchor_root.mkdir()
    started = time.time()
    started_at = _utc_now(now)
    evidence: dict = {}
    flight_refusal: dict | None = None
    stdout = (anchor_root / STDOUT_LOG).open("a", encoding="utf-8")
    stderr = (anchor_root / STDERR_LOG).open("a", encoding="utf-8")
    try:
        evidence = dict(
            run_flight(
                anchor=anchor,
                root=root,
                anchor_root=anchor_root,
                declared=declared,
                runtime=runtime,
                ownership=ownership,
                run_root=root,
                approved_bundle_sha256=approved_bundle_sha256,
                producer={**dict(producer), "stack_owned": True},
                values=dict(values or {}),
                seal=seal,
                stdout=stdout,
                stderr=stderr,
            )
            or {}
        )
    except CalibrationInputsRefused as error:
        flight_refusal = {"code": error.code, "detail": error.detail}
        print(f"the flight refused: {error}", file=stderr)
    finally:
        stdout.close()
        stderr.close()
    elapsed = time.time() - started

    sealed_document = sealed_journal_document(
        run_root=root,
        anchor=anchor,
        condition_class=condition_class,
        declared=declared,
        runtime=runtime,
        ownership=ownership,
        approved_bundle_sha256=approved_bundle_sha256,
        seal=seal,
        producer=producer,
        corridors=corridors,
        values=values,
        coverage=coverage,
        evidence=evidence,
        flight_refusal=flight_refusal,
        started_at_utc=started_at,
        finished_at_utc=_utc_now(now),
        elapsed_s=elapsed,
        now=now,
    )
    sealed_path = _write(root, SEALED_ARTIFACT, sealed_document)
    journal = aggregate_production_smoke(sealed_path, run_root=root, producer=producer, now=now)
    return {
        "run_root": str(root),
        "anchor_root": str(anchor_root),
        "sealed_journal": str(sealed_path),
        "sealed_journal_sha256": _digest(sealed_path),
        "journal": str(root / JOURNAL_ARTIFACT),
        "receipt": str(root / RECEIPT_ARTIFACT),
        "evidence": evidence,
        "document": journal,
        "gates": dict(journal["gates"]),
        "refusals": list(journal["refusals"]),
        "status": journal["status"],
        "elapsed_s": elapsed,
    }


def run_smoke_flight(**kwargs) -> dict:
    """Run development through the formal entry; legacy execution requires migration."""

    if 'execution_inputs' in kwargs:
        if set(kwargs) != {'execution_inputs'}:
            raise _refuse('SMOKE_EXECUTION_INPUTS_MIXED',
                          'development inputs cannot be mixed with qualification anchor arguments')
        from so101_demo.act.head_execution_inputs import HeadExecutionInputs
        from so101_demo.cli.head_execution_run import main

        inputs = HeadExecutionInputs.parse(kwargs['execution_inputs'])
        code = main(['--execution-inputs', str(inputs.document_path)])
        return dict(operation=inputs.document['operation'],
                    execution_scope=inputs.execution_scope,
                    qualification_status='NOT_QUALIFIED',
                    business_return_code=code, run_root=str(inputs.run_root),
                    execution_inputs_sha256=inputs.document_sha256)

    raise _refuse('HEAD_LEGACY_EXECUTION_REMOVED',
                  'use run --execution-inputs; legacy qualification execution is not migrated')


def read_runtime_of_record(final_run, production_config=None) -> dict:
    """The frozen runtime's own identity, read off disk through the Step 1 reader."""

    from so101_demo.act.head_search.restarts.observation import read_runtime_of_record as read

    return read(final_run, production_config)
