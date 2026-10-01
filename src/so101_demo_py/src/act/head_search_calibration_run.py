"""The eight-phase calibration run: one entry, one binding, one flight, no resume, fail-fast.

Design section 8.2 fixes the run: input validation, geometry and coverage, the perception operating
point of every candidate, the frozen-candidate evaluation, the readback of the selected values, the
search parameters, the timing and stop parameters, and the bundle - in that order, once each. This
module is the orchestration of those phases and nothing else: the mathematics and the policy live in the
phase modules it calls (rule 4 of the plan), and the one phase that measures with a detector is the
repository's existing evaluation gate, called in-process rather than reimplemented here.

What the entry owns, and why (plan sections 0, 1 and 2b):

* the **bounded trajectory precondition** is checked before any phase runs and before any neck target
  exists. A production search configuration that still makes the installed controller walk the
  cumulative ``2*pi`` sweep, or whose bounded stops leave the safe interval, fails the whole run with
  `CAL_TRAJECTORY_CONTRACT_UNSATISFIED` and commands no motion at all;
* the **run root is claimed once**, exclusively. A root that already exists is refused with
  `RUN_ROOT_ALREADY_EXISTS`: there is no resume path, no stage continuation, and `run-status.json` is an
  audit record rather than a checkpoint;
* the **resources are bound exactly once**, here at the entry, and the same binder travels into phase 1.
  No phase rebinds them, and a second binding - from any phase - is refused with `CAL_BINDING_REBOUND`;
* the **single `role=calibration` measurement flight** is taken through the repository's existing
  admission; release and recorder are refused before the admission is even consulted;
* a phase that refuses **stops the run immediately**. The first failing phase, its code, the command, the
  exit code and the evidence already produced are written to `run-status.json` as `FAILED`, and no later
  phase runs;
* phases 6 and 7 do not exist yet. The run therefore never reports success: it stops at
  `search_parameters` with `CAL_PHASE_UNIMPLEMENTED` and records that refusal, instead of pretending the
  work happened. An override for an unimplemented phase is refused too, so the seam that injects a
  measurement phase can never be used to fake one that is missing.

An uncoded exception from a phase is not a design outcome: it propagates (with the earlier evidence left
on disk for forensics) rather than being dressed up as a `FAILED` run with an invented code.
"""

from __future__ import annotations

import io
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

from so101_demo.act.head_search_calibration_bundle import (
    BUNDLE_NAME,
    MANIFEST_NAME,
    RUN_STATUS_NAME,
    assemble_calibration_bundle,
)
from so101_demo.act.head_search_calibration_geometry import (
    validate_head_search_calibration_geometry,
)
from so101_demo.act.head_search_calibration_inputs import (
    CALIBRATION_ROLE,
    CalibrationInputsRefused,
    CalibrationResourceBinder,
    validate_head_search_calibration_inputs,
)
from so101_demo.act.head_search_calibration_readback import (
    READBACK_NAME,
    readback_selected_perception_values,
)
from so101_demo.act.head_search_operating_point import (
    validate_head_search_calibration_operating_point,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_calibration_run"

#: the eight phases of design section 8.2, in the only order a run may walk them
PHASES = (
    "input_validation",
    "geometry_coverage",
    "perception_operating_point",
    "frozen_candidate_evaluation",
    "selected_perception_readback",
    "search_parameters",
    "timing_stop_parameters",
    "bundle_generation",
)

#: the refusal the entry-triggered precondition raises, and the ones the run adds around the contract
CAL_TRAJECTORY_CONTRACT_UNSATISFIED = "CAL_TRAJECTORY_CONTRACT_UNSATISFIED"
CAL_PHASE_UNIMPLEMENTED = "CAL_PHASE_UNIMPLEMENTED"
CAL_SAFE_INTERVAL_MISMATCH = "CAL_SAFE_INTERVAL_MISMATCH"
#: a gate that fails without printing one of its own codes still fails the phase by name
CAL_CANDIDATE_EVALUATION_FAILED = "CAL_CANDIDATE_EVALUATION_FAILED"
#: the root belongs to one run: an existing one is never resumed, continued or overwritten
RUN_ROOT_ALREADY_EXISTS = "RUN_ROOT_ALREADY_EXISTS"
REFUSAL_CODES = (
    CAL_TRAJECTORY_CONTRACT_UNSATISFIED,
    CAL_PHASE_UNIMPLEMENTED,
    CAL_SAFE_INTERVAL_MISMATCH,
    CAL_CANDIDATE_EVALUATION_FAILED,
    RUN_ROOT_ALREADY_EXISTS,
)

#: the phases whose library modules do not exist yet, with the refusal that names them
UNIMPLEMENTED_PHASES = {
    "search_parameters": CAL_PHASE_UNIMPLEMENTED,
    "timing_stop_parameters": CAL_PHASE_UNIMPLEMENTED,
}

#: the artefact each phase owns, in the run root, exactly as design section 8.3 names it. The evidence
#: already produced is the subset of these that exists when the run stops, so a phase that wrote part of
#: its evidence before refusing (the gate writes its comparison first, HS-275) is recorded with it.
INPUTS_NAME = "calibration-inputs.json"
GEOMETRY_NAME = "geometry-measurements.json"
PERCEPTION_NAME = "perception-calibration.json"
COMPARISON_NAME = "model-comparison.json"
VERDICT_NAME = "model-selection-verdict.json"
SEARCH_NAME = "search-calibration.json"
TIMING_NAME = "timing-calibration.json"
PHASE_ARTIFACTS = {
    "input_validation": (INPUTS_NAME,),
    "geometry_coverage": (GEOMETRY_NAME,),
    "perception_operating_point": (PERCEPTION_NAME,),
    "frozen_candidate_evaluation": (COMPARISON_NAME, VERDICT_NAME),
    "selected_perception_readback": (READBACK_NAME,),
    "search_parameters": (SEARCH_NAME,),
    "timing_stop_parameters": (TIMING_NAME,),
    "bundle_generation": (BUNDLE_NAME, MANIFEST_NAME, RUN_STATUS_NAME),
}

#: the exit status a phase refusal maps to: the console script leaves 2 for a named refusal
PHASE_REFUSAL_EXIT_CODE = 2

_GATE_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,}\Z")


class CalibrationRunRefused(CalibrationInputsRefused):
    """A refusal of the run itself, carrying the phase it stopped at (None at the entry).

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of a calibration run and reads the code off the exception.
    """

    def __init__(
        self, code: str, detail: str = "", *, phase: str | None = None, exit_code: int | None = None
    ) -> None:
        self.phase = phase
        self.exit_code = exit_code
        super().__init__(code, detail)


@dataclass(frozen=True)
class CalibrationPhaseContext:
    """What a phase runner is given: the claimed run root and the documents of the earlier phases."""

    run_root: Path
    documents: Mapping[str, Mapping]

    def document(self, phase: str) -> Mapping:
        """One earlier phase's document, or a `KeyError` naming the phase that has not run."""

        return self.documents[phase]


#: a phase runner takes the context and returns the document it produced (or refuses)
PhaseRunner = Callable[[CalibrationPhaseContext], Mapping]


@dataclass(frozen=True)
class CalibrationPhaseInputs:
    """Everything the eight phases consume, gathered once at the entry.

    ``production_search_config`` is the configuration the installed controller is constructed with: the
    entry preconditions read it, so a run cannot start on a controller that would sweep past its safe
    interval. ``bundle_inputs`` carries the per-parameter evidence blocks, the runtime identity and the
    five also-recorded items (plan section 2b); the readback of phase 5 reads the bundle the phases have
    assembled so far from the same document phase 8 assembles the final one from.
    """

    production_search_config: Mapping
    sealed_inputs: Mapping
    admission: object
    generation: str
    operation: str = "neck_target"
    cpu_cores: int = 1
    gpu_device: int | str = 0
    role: str = CALIBRATION_ROLE
    binder: CalibrationResourceBinder | None = None
    selection_rule: Mapping | None = None
    operating_point_measurements: Sequence[Mapping] = ()
    candidate_id: str | None = None
    held_out_measurements: Sequence[Mapping] = ()
    evaluation_arguments: Sequence[str] = ()
    bundle_inputs: Mapping | None = None


@dataclass(frozen=True)
class CalibrationRunResult:
    """What one run leaves behind: its status, the phases that completed and the audit record."""

    status: str
    run_root: Path
    phases_run: tuple[str, ...]
    first_failing_phase: str | None
    failure_code: str | None
    run_status: Mapping
    documents: Mapping[str, Mapping] = field(default_factory=dict)


def check_trajectory_contract(*, production_search_config) -> dict:
    """The precondition of plan section 0, checked before any phase and before any neck target.

    The installed controller is the only authority on which trajectory it exposes: it is constructed
    here with the production search configuration, and the run continues only when it built the bounded
    stop plan - a declared required domain swept inside a declared safe interval - that covers the whole
    domain without a stop leaving the interval. A configuration that would walk the cumulative ``2*pi``
    sweep, or whose stops cannot cover the domain, refuses with `CAL_TRAJECTORY_CONTRACT_UNSATISFIED`.
    Constructing the planner commands no motion, and the receipt this returns says so.
    """

    from so101_demo.act.search import HeadSearchController

    if not isinstance(production_search_config, Mapping):
        raise CalibrationRunRefused(
            CAL_TRAJECTORY_CONTRACT_UNSATISFIED,
            "the run needs the search configuration the installed controller is constructed with",
        )
    config = dict(production_search_config)
    try:
        controller = HeadSearchController(config)
    except (KeyError, TypeError, ValueError) as error:
        raise CalibrationRunRefused(
            CAL_TRAJECTORY_CONTRACT_UNSATISFIED,
            f"the installed controller refuses the production search configuration: {error}",
        ) from error
    plan = controller.plan
    if plan is None:
        raise CalibrationRunRefused(
            CAL_TRAJECTORY_CONTRACT_UNSATISFIED,
            "the installed controller exposes the cumulative 2*pi sweep for this configuration: no "
            "required search domain is declared, so a neck target outside the safe interval could be "
            "commanded",
        )
    targets: list[float] = []
    while True:
        target = controller.next_target()
        if target is None:
            break
        targets.append(float(target))
    safe = [float(plan.safe_interval_rad[0]), float(plan.safe_interval_rad[1])]
    if not plan.coverage_complete:
        raise CalibrationRunRefused(
            CAL_TRAJECTORY_CONTRACT_UNSATISFIED,
            f"the bounded stop plan {targets} does not cover the required search domain "
            f"{list(plan.required_domain_rad)}",
        )
    outside = [target for target in targets if not safe[0] <= target <= safe[1]]
    if outside:
        raise CalibrationRunRefused(
            CAL_TRAJECTORY_CONTRACT_UNSATISFIED,
            f"the bounded stop plan leaves the safe interval {safe} at {outside}",
        )
    return {
        "bounded_stop_plan": True,
        "coverage_complete": True,
        "required_search_domain_rad": [
            float(plan.required_domain_rad[0]),
            float(plan.required_domain_rad[1]),
        ],
        "safe_interval_rad": safe,
        "horizontal_fov_rad": float(plan.horizontal_fov_rad),
        "coarse_step_rad": float(plan.coarse_step_rad),
        "anchor_rad": float(plan.anchor_rad),
        "targets_rad": targets,
        "motion_commanded": False,
        "config_sha256": canonical_sha256(config),
    }


def claim_run_root(run_root) -> Path:
    """Claim one brand-new run root exclusively; an existing root is a refusal, never a resume."""

    root = Path(run_root)
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        root.mkdir()
    except FileExistsError as error:
        raise CalibrationRunRefused(
            RUN_ROOT_ALREADY_EXISTS,
            f"{root} exists and no runner may resume, continue or overwrite it",
        ) from error
    return root


def require_one_safe_interval(*, binding, sealed_inputs) -> None:
    """One safe interval for every neck target: the admission's must be the sealed geometry's.

    Design section 8.2 binds all neck targets to one generation, one measurement plan and one safe
    interval. The generation and the plan travel from the admission into every sweep-check receipt; the
    interval is the one the geometry seal measured, so an admission that granted a different interval
    would vouch for targets the seal never allowed. The mismatch is refused before the geometry phase
    issues a single receipt. The seal is read through phase 2's own loader, so this check cannot drift
    from the interval that phase itself uses.
    """

    from so101_demo.act.head_search_calibration_geometry import load_sealed_geometry

    loaded = load_sealed_geometry(sealed_inputs)
    sealed_interval = [float(value) for value in loaded["geometry"]["lock_valid_neck_rad"]]
    granted = [float(value) for value in binding["safe_interval_rad"]]
    if sealed_interval != granted:
        raise CalibrationRunRefused(
            CAL_SAFE_INTERVAL_MISMATCH,
            f"the admission binds the safe interval {granted} but the sealed geometry measured "
            f"{sealed_interval}, so the receipts would not vouch for the targets they bind",
            phase="geometry_coverage",
        )


def bundle_under_assembly(*, bundle_inputs) -> Mapping:
    """The bundle document as far as the phases have filled it, for the phase-5 readback.

    Design section 7.2 puts the readback of the selected perception values before the search and timing
    parameters, so what the readback can compare is the bundle the phases have assembled up to that
    point - the parameter evidence blocks of the phases that have run, under the runtime identity the run
    records. Phase 8 assembles the final document from the same evidence, so the values phase 5 certifies
    are the values the bundle carries.
    """

    if not isinstance(bundle_inputs, Mapping):
        raise ValueError("a run needs the bundle inputs phase 5 reads back and phase 8 assembles")
    evidence = bundle_inputs.get("parameter_evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("the bundle inputs carry no parameter evidence")
    identity = bundle_inputs.get("runtime_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("the bundle inputs carry no runtime identity")
    parameters: dict[str, object] = {}
    for phase in PHASES:
        document = evidence.get(phase)
        if document is None:
            continue
        blocks = document.get("parameters") if isinstance(document, Mapping) else None
        if not isinstance(blocks, Mapping):
            raise ValueError(f"the {phase} parameter evidence carries no parameters")
        parameters.update(blocks)
    return {"parameters": parameters, "runtime_identity": dict(identity)}


def evaluate_frozen_candidates(*, arguments, output_dir, gate=None) -> dict:
    """Phase 4: run the repository's existing gate and read back the decision it owns.

    The gate is `so101_demo.cli.evaluate_head_search_yolo_candidates`; it is called in-process with its
    own arguments, so its measurement, its margins and its codes stay in one place. The run root owns the
    gate's output - `--output` is fixed to it - and on failure the gate's own refusal code travels into
    the run, with `CAL_CANDIDATE_EVALUATION_FAILED` only for a failure that names none.
    """

    if gate is None:  # imported here: the gate pulls in numpy and the detector contracts
        from so101_demo.cli import evaluate_head_search_yolo_candidates as gate
    output = Path(output_dir)
    argv = [str(item) for item in arguments]
    if "--output" in argv:
        raise ValueError(
            "the run root owns the gate's output: pass output_dir and not --output in the arguments"
        )
    argv += ["--output", str(output)]
    captured = io.StringIO()
    with redirect_stdout(captured):
        exit_code = gate.main(argv)
    report = captured.getvalue()
    if exit_code != 0:
        code = _gate_failure_code(report) or CAL_CANDIDATE_EVALUATION_FAILED
        # the operator still sees what the gate printed, on the stream a failure belongs to
        if report:
            print(report, file=sys.stderr, end="" if report.endswith("\n") else "\n")
        raise CalibrationRunRefused(
            code,
            f"the frozen-candidate gate exited {exit_code}",
            phase="frozen_candidate_evaluation",
            exit_code=exit_code,
        )
    verdict = _document(output / VERDICT_NAME)
    comparison = _document(output / COMPARISON_NAME)
    selected = verdict.get("selected")
    if type(selected) is not str or not selected:
        raise CalibrationRunRefused(
            CAL_CANDIDATE_EVALUATION_FAILED,
            f"the gate's verdict names no selected candidate: {output / VERDICT_NAME}",
            phase="frozen_candidate_evaluation",
        )
    frozen = _frozen_candidate_of_arguments(selected, argv)
    return {
        "phase": "frozen_candidate_evaluation",
        "exit_code": 0,
        "command": argv,
        "output_dir": str(output),
        "selected_candidate_id": selected,
        "frozen_candidate": frozen,
        "comparison": comparison,
        "verdict": verdict,
    }


def execute_calibration_run(
    *,
    run_root,
    phase_inputs: CalibrationPhaseInputs,
    command: str | None = None,
    phase_runners: Mapping[str, PhaseRunner] | None = None,
) -> CalibrationRunResult:
    """Walk the eight phases once, in order, and stop at the first refusal.

    The order of the entry is the one the plan fixes: the trajectory precondition first (so a controller
    that would sweep past its safe interval never sees a neck target), then the exclusive claim on the
    run root, then the single resource binding, and only then the phases. `phase_runners` replaces the
    runner of an implemented phase - the measurement phases need a detector, so the orchestration is
    tested with a synthetic one - and is refused for a phase that does not exist yet.
    """

    if not isinstance(phase_inputs, CalibrationPhaseInputs):
        raise ValueError("a run needs the calibration phase inputs the phases consume")

    check_trajectory_contract(production_search_config=phase_inputs.production_search_config)
    root = claim_run_root(run_root)
    run_command = command if command is not None else _default_command(root)
    binder = phase_inputs.binder if phase_inputs.binder is not None else CalibrationResourceBinder()
    runners = _phase_runners(phase_inputs=phase_inputs, binder=binder, command=run_command)
    for name, runner in dict(phase_runners or {}).items():
        if name not in runners:
            raise ValueError(
                f"{name!r} is not a phase this run implements, so it cannot be replaced: a run never "
                "pretends a phase it does not have"
            )
        runners[name] = runner

    documents: dict[str, Mapping] = {}
    produced: list[str] = []
    for phase in PHASES:
        if phase in UNIMPLEMENTED_PHASES:
            return _failed(
                root=root,
                phase=phase,
                code=UNIMPLEMENTED_PHASES[phase],
                command=run_command,
                produced=produced,
                documents=documents,
            )
        context = CalibrationPhaseContext(run_root=root, documents=dict(documents))
        try:
            document = runners[phase](context)
        except CalibrationInputsRefused as error:
            _extend(produced, _produced_by(root, phase))
            return _failed(
                root=root,
                phase=phase,
                code=error.code,
                command=run_command,
                produced=produced,
                documents=documents,
                exit_code=PHASE_REFUSAL_EXIT_CODE
                if getattr(error, "exit_code", None) is None
                else int(error.exit_code),
            )
        if not isinstance(document, Mapping):
            raise ValueError(f"the {phase} phase produced no document")
        documents[phase] = document
        _extend(produced, _produced_by(root, phase))

    run_status = documents["bundle_generation"].get("run_status")
    if not isinstance(run_status, Mapping) or run_status.get("status") != "SUCCEEDED":
        raise ValueError("the bundle phase did not record a SUCCEEDED run status")
    return CalibrationRunResult(
        status="SUCCEEDED",
        run_root=root,
        phases_run=tuple(documents),
        first_failing_phase=None,
        failure_code=None,
        run_status=run_status,
        documents=dict(documents),
    )


def _phase_runners(
    *, phase_inputs: CalibrationPhaseInputs, binder: CalibrationResourceBinder, command: str
) -> dict[str, PhaseRunner]:
    """The runner of every implemented phase: each calls its own library module and writes only its own."""

    def input_validation(context: CalibrationPhaseContext) -> Mapping:
        return validate_head_search_calibration_inputs(
            sealed_inputs=phase_inputs.sealed_inputs,
            admission=phase_inputs.admission,
            generation=phase_inputs.generation,
            operation=phase_inputs.operation,
            cpu_cores=phase_inputs.cpu_cores,
            gpu_device=phase_inputs.gpu_device,
            role=phase_inputs.role,
            binder=binder,
            output_path=context.run_root / INPUTS_NAME,
        )

    def geometry_coverage(context: CalibrationPhaseContext) -> Mapping:
        binding = _resource_binding(context)
        require_one_safe_interval(binding=binding, sealed_inputs=phase_inputs.sealed_inputs)
        return validate_head_search_calibration_geometry(
            sealed_inputs=phase_inputs.sealed_inputs,
            generation=binding["generation"],
            measurement_plan_sha256=binding["measurement_plan_sha256"],
            output_path=context.run_root / GEOMETRY_NAME,
        )

    def perception_operating_point(context: CalibrationPhaseContext) -> Mapping:
        return validate_head_search_calibration_operating_point(
            rule=phase_inputs.selection_rule,
            measurements=phase_inputs.operating_point_measurements,
            candidate_id=phase_inputs.candidate_id,
            held_out_measurements=phase_inputs.held_out_measurements,
            output_path=context.run_root / PERCEPTION_NAME,
        )

    def frozen_candidate_evaluation(context: CalibrationPhaseContext) -> Mapping:
        return evaluate_frozen_candidates(
            arguments=phase_inputs.evaluation_arguments,
            output_dir=context.run_root,
        )

    def selected_perception_readback(context: CalibrationPhaseContext) -> Mapping:
        return readback_selected_perception_values(
            bundle=bundle_under_assembly(bundle_inputs=phase_inputs.bundle_inputs),
            operating_point=context.document("perception_operating_point"),
            frozen_candidate=_selected_frozen_candidate(context),
            output_path=context.run_root / READBACK_NAME,
        )

    def bundle_generation(context: CalibrationPhaseContext) -> Mapping:
        bundle_inputs = phase_inputs.bundle_inputs
        if not isinstance(bundle_inputs, Mapping):
            raise ValueError("a run needs the bundle inputs phase 8 assembles")
        return assemble_calibration_bundle(
            status="SUCCEEDED",
            command=command,
            exit_code=0,
            phase_inputs=bundle_inputs.get("parameter_evidence"),
            controlled_dependencies=_controlled_dependencies(context),
            runtime_identity=bundle_inputs.get("runtime_identity"),
            also_recorded=bundle_inputs.get("also_recorded"),
            output_dir=context.run_root,
        )

    return {
        "input_validation": input_validation,
        "geometry_coverage": geometry_coverage,
        "perception_operating_point": perception_operating_point,
        "frozen_candidate_evaluation": frozen_candidate_evaluation,
        "selected_perception_readback": selected_perception_readback,
        "bundle_generation": bundle_generation,
    }


def _failed(
    *,
    root: Path,
    phase: str,
    code: str,
    command: str,
    produced: Sequence[str],
    documents: Mapping[str, Mapping],
    exit_code: int = PHASE_REFUSAL_EXIT_CODE,
) -> CalibrationRunResult:
    """Record the first failing phase and stop: a FAILED run-status and nothing else.

    Phase 8's own assembly writes the failed status, so a failed run produces only `run-status.json` and
    never a bundle a later step could mistake for a promotable one.
    """

    assembled = assemble_calibration_bundle(
        status="FAILED",
        failure={
            "phase": phase,
            "code": code,
            "command": command,
            "exit_code": int(exit_code),
            "evidence_produced": list(produced),
        },
        output_dir=root,
    )
    return CalibrationRunResult(
        status="FAILED",
        run_root=root,
        phases_run=tuple(documents),
        first_failing_phase=phase,
        failure_code=code,
        run_status=assembled["run_status"],
        documents=dict(documents),
    )


def _default_command(root: Path) -> str:
    return f"ros2 run so101_demo_py so101_head_search_calibration run --run-root {root}"


def _produced_by(root: Path, phase: str) -> list[str]:
    """The artefacts of one phase that exist in the run root, in the order the phase owns them."""

    return [name for name in PHASE_ARTIFACTS[phase] if (root / name).is_file()]


def _extend(produced: list[str], names: Sequence[str]) -> None:
    for name in names:
        if name not in produced:
            produced.append(name)


def _resource_binding(context: CalibrationPhaseContext) -> Mapping:
    binding = context.document("input_validation").get("resource_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("the input phase recorded no resource binding")
    return binding


def _selected_frozen_candidate(context: CalibrationPhaseContext) -> Mapping:
    frozen = context.document("frozen_candidate_evaluation").get("frozen_candidate")
    if not isinstance(frozen, Mapping):
        raise ValueError("the evaluation phase recorded no selected frozen candidate document")
    return frozen


def _controlled_dependencies(context: CalibrationPhaseContext) -> Mapping:
    """The sealed inputs the run actually read, each with the digest the manifest measured."""

    inputs = context.document("input_validation").get("manifest")
    sealed = inputs.get("inputs") if isinstance(inputs, Mapping) else None
    if not isinstance(sealed, Mapping):
        raise ValueError("the input phase recorded no sealed-input manifest")
    return {
        name: {"path": record["path"], "sha256": record["sha256"]}
        for name, record in sealed.items()
    }


def _document(path: Path) -> Mapping:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise CalibrationRunRefused(
            CAL_CANDIDATE_EVALUATION_FAILED,
            f"{path} is not a document",
            phase="frozen_candidate_evaluation",
        )
    return document


def _frozen_candidate_of_arguments(selected: str, arguments: Sequence[str]) -> Mapping:
    """Load the frozen document of the candidate the gate selected, from the arguments it was given."""

    from so101_demo.perception_benchmark.head_search_models import load_frozen_candidate

    paths = [
        arguments[index + 1]
        for index, item in enumerate(arguments)
        if item == "--candidate" and index + 1 < len(arguments)
    ]
    for path in paths:
        candidate = load_frozen_candidate(path)
        if candidate.candidate_id == selected:
            return dict(candidate.document)
    raise CalibrationRunRefused(
        CAL_CANDIDATE_EVALUATION_FAILED,
        f"the gate selected candidate {selected!r} but none of {paths} is its frozen document",
        phase="frozen_candidate_evaluation",
    )


def _gate_failure_code(report: str) -> str | None:
    """The gate's own refusal code, read from the JSON line it prints when it fails."""

    lines = [line for line in report.strip().splitlines() if line.strip()]
    if not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except ValueError:
        return None
    failure = payload.get("failure") if isinstance(payload, Mapping) else None
    if type(failure) is not str or not failure:
        return None
    token = failure.split(":", 1)[0].strip()
    return token if _GATE_CODE.fullmatch(token) else None
