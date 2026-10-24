"""The formal head search calibration CLI: check-ownership, run, measure-coarse-step, measure-mujoco, measure-search-timing, measure-deadband-candidates, measure-camera, measure-workspace-projection, measure-selection-rule, measure-operating-point, measure-scenarios, measure-restarts, verify-promoted-config, qualify.

The CLI parses arguments, validates the inputs a run declares and orchestrates nothing itself: `run`
hands the phases to `so101_demo.act.head_search.calibration_run`, where the order, the entry binding, the
trajectory precondition and the run status live (plan rule 4). `check-ownership` is the
stack-free ownership gate: it reads the process table, ROS graph, GPU processes, tmux panes and evidence root,
refuses any second owner by name, binds the frozen runtime identity, writes its receipt into a brand-new
root and starts nothing (`so101_demo.act.head_search.ownership`). Every subcommand refuses a run root that
already exists, so there is no way to resume or continue a stage. `measure-coarse-step`,
`measure-mujoco`, `measure-search-timing`, `measure-deadband-candidates`, `measure-camera` and
`measure-workspace-projection` are the measurement flights the run cannot take itself - the run declares
documents, it does not render, read a sealed model, step a simulator, project a workspace or close a
control loop - so they are their own installed entries, validated
here and produced by `so101_demo.act.head_search.coarse_step_measurement`,
`so101_demo.act.head_search.mujoco_measurements`,
`so101_demo.act.head_search.timing_measurement`,
`so101_demo.act.head_search.deadband_measurement`,
`so101_demo.act.head_search.camera_measurement` and
`so101_demo.act.head_search.workspace_projection`. `measure-selection-rule` and
`measure-operating-point` are phase 3's two inputs: the first writes the rule record before any
measurement can exist, the second measures the frames that rule consumes and has the installed phase 3
select every candidate's point (`so101_demo.act.head_search.operating_point_measurement`).
`measure-scenarios` is the scenario flight: it runs the declared qualification seeds one at a time through the producer controller's closed loop, journals every outcome - including the ones that fail or refuse - and writes the aggregate that claims no verdict. `measure-admission` produces the run's `--admission` from the six sealed inputs the run declares - the
flat measurement plan the installed controller is constructed with, the six-field
`CalibrationMeasurementAdmission` for `role=calibration`, and the receipt that records every refusal the
runtime contract fixes - and `measure-bundle-inputs` produces the declared geometry and perception
parameter blocks with the live effective-value readback
(`so101_demo.act.head_search.calibration_admission_document`,
`so101_demo.act.head_search.calibration_bundle_inputs`), and `measure-episode-records` reshapes the
installed phase-3 measurement document into the per-seed contract phase 4's gate declares
(`so101_demo.act.head_search.episode_records`).
"""

from __future__ import annotations

from pathlib import Path
import sys

from so101_demo.act.head_search.qualification import (
    HEAD_SEARCH_QUALIFIED,
    qualification_parser,
    qualify_head_search,
)
from so101_demo.cli.head_search.closed_loop import (
    _measure_camera,
    _measure_deadband_candidates,
    _measure_fine_correction_episodes,
    _measure_scenarios,
)
from so101_demo.cli.head_search.common import _verify_promoted_config
from so101_demo.cli.head_search.documents import (
    _measure_admission,
    _measure_bundle_inputs,
    _measure_episode_records,
    _measure_operating_point,
    _measure_selection_rule,
)
from so101_demo.cli.head_search.flags import QUALIFICATION_READBACK_ALIASES
from so101_demo.cli.head_search.restarts import _check_ownership, _measure_restarts
from so101_demo.cli.head_search.run import _run, _serve_teleop
from so101_demo.cli.head_search.scene_measurements import (
    _measure_coarse_step,
    _measure_mujoco,
    _measure_workspace_projection,
)
from so101_demo.cli.head_search.smoke_readback import (
    _measure_production_smoke,
    _measure_qualification_readback,
)
from so101_demo.cli.head_search.stop_timing import (
    _measure_controller_stop_config,
    _measure_controller_submissions,
    _measure_feedback,
    _measure_frame_contract,
    _measure_search_timing,
    _measure_skew,
    _measure_stationary,
    _measure_stop_proofs,
)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ['measure-feedback-bootstrap']:
        print('HEAD_ONLINE_BOOTSTRAP_REMOVED: use run --execution-inputs with '
              'fresh stage-one development inputs', file=sys.stderr)
        return 2
    # Step 1's gate is stack-free and runs before any run root is claimed: it must not be routed through
    # the qualifier's four-subcommand parser, which owns the runners that do start things
    if arguments[:1] == ["check-ownership"]:
        return _check_ownership(arguments[1:])
    # `run` declares the inputs of the eight phases, so its entry is the run module's and not a stub
    if arguments[:1] == ["run"]:
        return _run(arguments[1:])
    # the one measurement the run cannot take itself is its own installed entry, never a script
    if arguments[:1] == ["measure-coarse-step"]:
        return _measure_coarse_step(arguments[1:])
    # the sealed scene's own declaration is the other document the run declares but does not read itself
    if arguments[:1] == ["measure-mujoco"]:
        return _measure_mujoco(arguments[1:])
    # the bounded stop-point sweep's settle and frame timing is the third flight the run cannot take
    if arguments[:1] == ["measure-search-timing"]:
        return _measure_search_timing(arguments[1:])
    # the closed-loop deadband lock trials are the fourth flight the run cannot take
    if arguments[:1] == ["measure-deadband-candidates"]:
        return _measure_deadband_candidates(arguments[1:])
    # the camera's centre jitter is the fifth flight the run cannot take; its safety margin is a
    # declaration this entry reads or refuses, never a number it makes up
    if arguments[:1] == ["measure-camera"]:
        return _measure_camera(arguments[1:])
    # the held-out fine-correction episodes are the sixth closed-loop flight: one scene per held-out seed,
    # the production controller's own sweep and corrections, and the selected model closing the loop
    if arguments[:1] == ["measure-fine-correction-episodes"]:
        return _measure_fine_correction_episodes(arguments[1:])
    # The forty serial scenarios are their own installed flight: the closed loop per declared
    # qualification seed, the per-scenario journal, and the honest aggregate that claims no verdict
    if arguments[:1] == ["measure-scenarios"]:
        return _measure_scenarios(arguments[1:])
    # The production smoke is its own installed flight: one owned stack, the production
    # closed loop, the sealed journal and the aggregator the qualification gate consumes
    if arguments[:1] == ["measure-production-smoke"]:
        return _measure_production_smoke(arguments[1:])
    # the during-qualification readback: the same entry under the aggregate's own vocabulary for it
    if arguments[:1] == ["measure-qualification-readback"]:
        return _measure_qualification_readback(arguments[1:])
    for alias in QUALIFICATION_READBACK_ALIASES:
        if arguments[:1] == [alias]:
            return _measure_qualification_readback(
                arguments[1:], entry=f"so101_head_search_calibration {alias}"
            )
    # The three restarts are their own installed flight: one owned stack per anchor, the
    # production admission for every neck goal, and a teardown the phase proves before the next anchor
    if arguments[:1] == ["measure-restarts"]:
        return _measure_restarts(arguments[1:])
    # the legal pick workspace's projection is the sixth: it reads the scene's camera pose and projects,
    # loading no detector, no renderer and no GPU
    if arguments[:1] == ["measure-workspace-projection"]:
        return _measure_workspace_projection(arguments[1:])
    # the controller's stopped tolerance is a declaration of the running controller: this entry cites it
    if arguments[:1] == ["measure-controller-stop-config"]:
        return _measure_controller_stop_config(arguments[1:])
    # the feedback period is declared; the feedback resolution is declared or refused, never defaulted
    if arguments[:1] == ["measure-feedback"]:
        return _measure_feedback(arguments[1:])
    # the stationary velocity noise, the goal-admission lead and the stop proofs are the last three flights
    if arguments[:1] == ["measure-stationary"]:
        return _measure_stationary(arguments[1:])
    if arguments[:1] == ["measure-controller-submissions"]:
        return _measure_controller_submissions(arguments[1:])
    if arguments[:1] == ["measure-stop-proofs"]:
        return _measure_stop_proofs(arguments[1:])
    # the running-topic frame contract declaration is the seventh measurement's declaration half; the
    # skew measurement that paces itself against it is the eighth
    if arguments[:1] == ["measure-frame-contract"]:
        return _measure_frame_contract(arguments[1:])
    if arguments[:1] == ["measure-skew"]:
        return _measure_skew(arguments[1:])
    # phase 3's two inputs are the two flights whose ordering is part of the evidence: the rule record is
    # written before the measurement it governs can own a directory, and the measurement is the one the
    # rule consumes
    if arguments[:1] == ["measure-selection-rule"]:
        return _measure_selection_rule(arguments[1:])
    if arguments[:1] == ["measure-operating-point"]:
        return _measure_operating_point(arguments[1:])
    # the run's admission is its own declared input: the plan, the six-field admission and the receipt
    # that records the refusals are produced here, from the same six sealed inputs the run declares
    if arguments[:1] == ["measure-admission"]:
        return _measure_admission(arguments[1:])
    # the run's declared parameter evidence is its other declared input: the six blocks with the live
    # effective-value readback are produced here
    if arguments[:1] == ["measure-bundle-inputs"]:
        return _measure_bundle_inputs(arguments[1:])
    # phase 4's gate reads the measured calibration episodes one document per seed: this entry reshapes
    # the installed phase-3 measurement document into that declared contract, verbatim
    if arguments[:1] == ["measure-episode-records"]:
        return _measure_episode_records(arguments[1:])
    parsed = qualification_parser().parse_args(arguments)
    run_root = Path(parsed.run_root)
    if parsed.command == "verify-promoted-config":
        return _verify_promoted_config(
            run_root, parsed.approved_bundle_sha256, parsed.promoted_config
        )
    if parsed.command == "qualify":
        # the aggregate phase: only the declared evidence that was actually presented goes in, and an
        # absent flag stays absent so the verdict refuses it by name instead of defaulting to something
        inputs = {
            name: value
            for name, value in (
                ("final_run", parsed.final_run),
                ("production_config", parsed.promoted_config),
                ("approved_bundle", parsed.approved_bundle),
                ("ownership_receipt", parsed.ownership_receipt),
                ("runtime_readback", parsed.runtime_readback),
                ("production_smoke_root", parsed.production_smoke_root),
                ("scenarios_root", parsed.scenarios_root),
                ("restart_receipts", parsed.restart_receipts),
                ("teleop_acceptance_receipt", parsed.teleop_acceptance_receipt),
                ("scenario_partitions", parsed.scenario_partitions),
            )
            if value is not None
        }
        expected_runtime = {
            key: value
            for key, value in (
                ("source_commit", parsed.expected_source_commit),
                ("production_config_sha256", parsed.expected_production_config_sha256),
                ("values_sha256", parsed.expected_values_sha256),
                ("weight_sha256_declared", parsed.expected_weights_sha256),
            )
            if value is not None
        }
        if expected_runtime:
            inputs["expected_runtime"] = expected_runtime
        try:
            report = qualify_head_search(inputs, run_root)
        except ValueError as error:
            if "RUN_ROOT_ALREADY_EXISTS" not in str(error):
                raise
            print(str(error), file=sys.stderr)
            return 2
        if report["status"] == HEAD_SEARCH_QUALIFIED:
            print(f"{report['status']} {report['runtime_id']}")
            return 0
        # a refusal is not a traceback: every missing item and every violated gate is named, and the
        # exit code says no pass was published
        for reason in report["blocking_reasons"]:
            print(
                f"{reason['code']} {reason['gate']}: {reason['item']}: {reason['detail']}",
                file=sys.stderr,
            )
        print(
            f"{report['status']} missing={len(report['missing'])} "
            f"violations={len(report['violations'])} "
            f"verdict={run_root / 'qualification-verdict.json'}",
            file=sys.stderr,
        )
        return 2
    if parsed.command == "serve-teleop":
        return _serve_teleop(parsed)
    print(f"HEAD_SEARCH_COMMAND_UNKNOWN: {parsed.command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover - console script entry
    raise SystemExit(main())
