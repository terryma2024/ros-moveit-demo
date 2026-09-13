"""V2.1 perception-driven plan-only composition root."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dynamic_cup_pick_place")
    parser.add_argument("--backend", default="gazebo")
    parser.add_argument("--mode", choices=("plan_only", "execute"), default="plan_only")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan-only-state")
    parser.add_argument("--cup-pose-timeout-s", type=float, default=5.0)
    parser.add_argument("--scene-source", default="observe_only")
    parser.add_argument("--dynamic-policy")
    parser.add_argument("--evidence-file")
    parser.add_argument("--source-commit", default="UNRECORDED_SOURCE")
    parser.add_argument("--installed-prefix")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--expected-reset-epoch", type=int)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--batch-id")
    parser.add_argument("--coordinator-epoch", type=int)
    parser.add_argument("--worker-id")
    parser.add_argument("--worker-generation", type=int)
    parser.add_argument("--point-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--lease-generation", type=int)
    parser.add_argument(
        "--profiling",
        choices=("off", "summary", "trace"),
        default="off",
    )
    parser.add_argument("--profiling-output-root", type=Path)
    parser.add_argument("--profiling-session-id")
    return parser


def _application_arguments(arguments: list[str] | None) -> list[str]:
    raw_arguments = list(sys.argv[1:] if arguments is None else arguments)
    if "--ros-args" not in raw_arguments:
        return raw_arguments
    from rclpy.utilities import remove_ros_args

    return remove_ros_args(args=["dynamic_cup_pick_place", *raw_arguments])[1:]


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(_application_arguments(arguments))
    execute_requested = options.mode == "execute" or options.execute
    if execute_requested:
        if options.mode != "execute" or not options.execute:
            print("status=ERROR failure=EXPLICIT_EXECUTE_REQUIRED")
            return 1
        if options.backend != "mujoco":
            print("status=ERROR failure=DYNAMIC_EXECUTION_NOT_QUALIFIED")
            return 1
        if options.scene_source != "observe_only":
            print("status=ERROR failure=DYNAMIC_SCENE_SOURCE_UNSUPPORTED")
            return 1
        from ..ros.dynamic_runtime import run_dynamic_execute

        if options.profiling == "off":
            return run_dynamic_execute(options)
        parser = build_parser()
        if options.profiling_output_root is None:
            parser.error("enabled profiling requires --profiling-output-root")
        if not options.profiling_output_root.is_absolute():
            parser.error("profiling output root must be absolute")
        if not options.profiling_session_id or not options.profiling_session_id.strip():
            parser.error("enabled profiling requires --profiling-session-id")
        from ..profiling.model import ProfilingConfig, ProfilingMode
        from ..profiling.session import build_profiler

        try:
            profiler = build_profiler(
                ProfilingConfig(
                    mode=ProfilingMode.parse(options.profiling),
                    output_root=options.profiling_output_root,
                    session_id=options.profiling_session_id.strip(),
                    process_role="runtime",
                    request_id=options.session_id or None,
                    source_commit=options.source_commit,
                    installed_prefix=options.installed_prefix,
                )
            )
        except OSError:
            return run_dynamic_execute(options)
        assert profiler is not None
        token = profiler.start_span("runtime.total", {"backend": options.backend})
        try:
            result = run_dynamic_execute(options, profiler=profiler)
        except Exception as error:
            profiler.finish_span(
                token,
                outcome="error",
                attributes={"error_class": type(error).__name__},
            )
            raise
        else:
            profiler.finish_span(
                token,
                outcome="ok" if result == 0 else "error",
                attributes={"exit_code": result},
            )
            return result
        finally:
            profiler.close()
    if options.backend != "gazebo":
        print("status=ERROR failure=DYNAMIC_BACKEND_UNSUPPORTED")
        return 1
    if options.scene_source != "observe_only":
        print("status=ERROR failure=DYNAMIC_SCENE_SOURCE_UNSUPPORTED")
        return 1
    from ..ros.dynamic_runtime import run_dynamic_plan_only

    return run_dynamic_plan_only(options)


if __name__ == "__main__":
    raise SystemExit(main())
