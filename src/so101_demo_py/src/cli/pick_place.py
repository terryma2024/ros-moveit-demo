"""ROS-free command-line entry point for the MuJoCo workflow."""

import argparse
import sys
from pathlib import Path

from ..application.pick_place import LiveRuntimeConfig, run_live_workflow
from ..backends.mujoco.lifecycle import resume_physics
from ..core.domain import RunMode, RunRequest, RunStatus, State
from ..core.runner import FileCheckpointStore, StateMachineRunner, dry_run_actions


def _optional_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pick_place_state_machine")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in RunMode],
        default=RunMode.DRY_RUN.value,
    )
    parser.add_argument("--fail-at", choices=[state.value for state in State])
    parser.add_argument("--stop-after", choices=[state.value for state in State])
    parser.add_argument("--plan-only-state", choices=[state.value for state in State])
    parser.add_argument("--resume", nargs="?", const=True, default=False, type=_optional_bool)
    parser.add_argument("--step", action="store_true")
    parser.add_argument("--force-continue", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-reset-epoch", type=int)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--motion-policy", type=Path)
    parser.add_argument("--contact-policy", type=Path)
    parser.add_argument("--max-state-transitions", type=int, default=100)
    return parser


def _state(value: str | None) -> State | None:
    return None if value is None else State(value)


def print_result(result) -> None:
    print(f"status={result.status.value}")
    print(f"current_state={result.current_state.value}")
    if result.next_state is not None:
        print(f"next_state={result.next_state.value}")
    print(f"transition_count={result.transition_count}")
    print("state_trace=" + ",".join(state.value for state in result.state_trace))
    if result.failure is not None:
        print(f"failure={result.failure.code}")
        if result.failure.message:
            print(f"failure_message={result.failure.message}")
        if result.failure.metrics:
            metrics = " ".join(
                f"{key}={value:.12g}" for key, value in sorted(result.failure.metrics.items())
            )
            print(f"failure_metrics {metrics}")


def main(arguments: list[str] | None = None) -> int:
    if arguments is None:
        arguments = sys.argv[1:]
        if "--ros-args" in arguments:
            arguments = arguments[: arguments.index("--ros-args")]
    options = build_parser().parse_args(arguments)
    if options.mode == RunMode.EXECUTE.value:
        if not options.execute:
            print("status=ERROR")
            print("current_state=ERROR")
            print("failure=EXPLICIT_EXECUTE_REQUIRED")
            return 1
        if (
            not options.session_id
            or options.expected_reset_epoch is None
            or options.evidence_root is None
            or options.motion_policy is None
            or options.contact_policy is None
        ):
            print("status=ERROR")
            print("current_state=ERROR")
            print("failure=LIVE_RUNTIME_CONFIG_REQUIRED")
            return 1
        result = run_live_workflow(
            LiveRuntimeConfig(
                simulation_session_id=options.session_id,
                expected_reset_epoch=options.expected_reset_epoch,
                evidence_root=options.evidence_root,
                motion_policy=options.motion_policy,
                contact_policy=options.contact_policy,
            ),
            resume=resume_physics,
        )
        if result.success:
            print("status=DONE")
            print("current_state=DONE")
            print(f"transition_count={len(result.completed_phases)}")
            print("state_trace=" + ",".join(result.completed_phases))
            print(f"evidence_manifest={result.manifest_path}")
            return 0
        print("status=ERROR")
        print("current_state=ERROR")
        print(f"failure={result.failure}")
        print(f"failed_phase={result.failed_phase}")
        print(f"evidence_manifest={result.manifest_path}")
        return 1
    request = RunRequest(
        mode=RunMode(options.mode),
        stop_after=_state(options.stop_after),
        resume=options.resume,
        fail_at=_state(options.fail_at),
        max_state_transitions=options.max_state_transitions,
        single_step=options.step,
        force_continue=options.force_continue,
        plan_only_state=_state(options.plan_only_state),
    )
    store = None if options.checkpoint is None else FileCheckpointStore(options.checkpoint)
    runner = StateMachineRunner(
        dry_run_actions(), checkpoint_store=store, session_id=options.session_id
    )
    result = runner.run(request)
    print_result(result)
    return (
        0
        if result.status
        in {
            RunStatus.DONE,
            RunStatus.PLAN_ONLY_COMPLETE,
            RunStatus.CHECKPOINT_COMPLETE,
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
