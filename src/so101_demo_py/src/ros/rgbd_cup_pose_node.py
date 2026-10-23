"""Continuous ROS adapter for RGB-D cup-pose estimation and publication."""

from __future__ import annotations

from collections.abc import Callable
import time

from so101_demo.profiling.session import SemanticProfiler
from so101_demo.ros.rgbd_cup_pose.frames import (
    RgbdCupPoseOptions,
    _finish_runtime_wait,
    _require_open3d,
    _Runtime,
    _status_line,
)
from so101_demo.ros.rgbd_cup_pose.ros_runtime import ResourceConstructionError, _create_ros_runtime
from so101_demo.runtime.workflow_events import EventEmitter, normalize_failure_code


def _run_rgbd_cup_pose(
    options: RgbdCupPoseOptions,
    *,
    runtime_factory: Callable[
        [RgbdCupPoseOptions, float, Callable[[], float]], _Runtime
    ] = _create_ros_runtime,
    monotonic: Callable[[], float] = time.monotonic,
    open3d_preflight: Callable[[float], None] = _require_open3d,
    profiler: SemanticProfiler | None = None,
    event_emitter: EventEmitter | None = None,
) -> int:
    """Run until orderly shutdown, failing if startup never publishes a valid frame."""
    deadline = monotonic() + options.startup_timeout_s
    runtime: _Runtime | None = None
    setup_failed = False
    setup_wait_outcome = "error"
    failure_code: str | None = None
    try:
        remaining_startup_s = deadline - monotonic()
        if remaining_startup_s <= 0.0:
            raise TimeoutError("startup deadline expired before Open3D preflight")
        open3d_preflight(remaining_startup_s)
        if deadline - monotonic() <= 0.0:
            raise TimeoutError("startup deadline expired during Open3D preflight")
        if runtime_factory is _create_ros_runtime:
            runtime = _create_ros_runtime(
                options,
                deadline,
                monotonic,
                profiler=profiler,
                event_emitter=event_emitter,
            )
        else:
            runtime = runtime_factory(options, deadline, monotonic)
        if not runtime.first_valid_published and deadline - monotonic() <= 0.0:
            raise TimeoutError("startup deadline expired during ROS runtime construction")
    except TimeoutError as error:
        failure_code = "RGBD_CUP_POSE_TIMEOUT"
        setup_wait_outcome = "timeout"
        print(
            _status_line(
                "ERROR", failure="RGBD_CUP_POSE_TIMEOUT", message=str(error)
            ),
            flush=True,
        )
        setup_failed = True
    except KeyboardInterrupt:
        failure_code = "RGBD_CUP_POSE_FATAL"
        setup_wait_outcome = "interrupted"
        print(
            _status_line(
                "ERROR",
                failure="RGBD_CUP_POSE_INTERRUPTED_BEFORE_FIRST_VALID",
                message="SIGINT arrived during RGB-D cup-pose setup",
            ),
            flush=True,
        )
        setup_failed = True
    except ResourceConstructionError as error:
        failure_code = "RGBD_CUP_POSE_CLEANUP_FAILED"
        print(
            _status_line(
                "ERROR",
                failure="RGBD_CUP_POSE_CLEANUP_FAILED",
                message=str(error),
            ),
            flush=True,
        )
        setup_failed = True
    except (OSError, RuntimeError, ValueError) as error:
        failure_code = "RGBD_CUP_POSE_PREFLIGHT_FAILED"
        print(
            _status_line(
                "ERROR", failure="RGBD_CUP_POSE_PREFLIGHT_FAILED", message=str(error)
            ),
            flush=True,
        )
        setup_failed = True

    if setup_failed:
        if runtime is not None:
            _finish_runtime_wait(runtime, profiler, setup_wait_outcome)
            try:
                runtime.close()
            except BaseException as cleanup_error:
                print(
                    _status_line(
                        "ERROR",
                        failure="RGBD_CUP_POSE_CLEANUP_FAILED",
                        message=str(cleanup_error),
                    ),
                    flush=True,
                )
        if event_emitter is not None:
            event_emitter.emit(
                "PERCEPTION_FAILED",
                payload={},
                failure_code=normalize_failure_code(
                    "PERCEPTION_FAILED", failure_code
                ),
            )
        return 1

    result = 1
    wait_outcome = "error"
    try:
        while runtime.ok():
            now = monotonic()
            if not runtime.first_valid_published and now >= deadline:
                failure_code = "RGBD_CUP_POSE_TIMEOUT"
                wait_outcome = "timeout"
                print(
                    _status_line(
                        "ERROR",
                        failure="RGBD_CUP_POSE_TIMEOUT",
                        message=(
                            "no valid RGB-D cup pose was published within "
                            f"{options.startup_timeout_s:.3f} seconds"
                        ),
                    ),
                    flush=True,
                )
                result = 1
                break
            timeout_s = 0.05
            if not runtime.first_valid_published:
                timeout_s = min(timeout_s, max(0.0, deadline - now))
            runtime.spin_once(timeout_s)
        else:
            if runtime.first_valid_published:
                result = 0
            else:
                wait_outcome = "interrupted"
                failure_code = "RGBD_CUP_POSE_FATAL"
                print(
                    _status_line(
                        "ERROR",
                        failure="RGBD_CUP_POSE_SHUTDOWN_BEFORE_FIRST_VALID",
                        message=(
                            "ROS context shut down before a valid RGB-D cup pose was published"
                        ),
                    ),
                    flush=True,
                )
                result = 1
    except KeyboardInterrupt:
        wait_outcome = "interrupted"
        if runtime.first_valid_published:
            print(_status_line("STOPPED", reason="SIGINT"), flush=True)
            result = 0
        else:
            failure_code = "RGBD_CUP_POSE_FATAL"
            print(
                _status_line(
                    "ERROR",
                    failure="RGBD_CUP_POSE_INTERRUPTED_BEFORE_FIRST_VALID",
                    message="SIGINT arrived before a valid RGB-D cup pose was published",
                ),
                flush=True,
            )
            result = 1
    except RuntimeError as error:
        if runtime.first_valid_published and not runtime.ok():
            print(
                _status_line("STOPPED", reason="ROS_CONTEXT_SHUTDOWN"),
                flush=True,
            )
            result = 0
        else:
            failure_code = "RGBD_CUP_POSE_FATAL"
            print(
                _status_line(
                    "ERROR", failure="RGBD_CUP_POSE_FATAL", message=str(error)
                ),
                flush=True,
            )
            result = 1
    except (OSError, TimeoutError, ValueError) as error:
        failure_code = "RGBD_CUP_POSE_FATAL"
        wait_outcome = "timeout" if isinstance(error, TimeoutError) else "error"
        print(
            _status_line(
                "ERROR", failure="RGBD_CUP_POSE_FATAL", message=str(error)
            ),
            flush=True,
        )
        result = 1
    finally:
        _finish_runtime_wait(runtime, profiler, wait_outcome)
        try:
            runtime.close()
        except BaseException as cleanup_error:
            failure_code = "RGBD_CUP_POSE_CLEANUP_FAILED"
            print(
                _status_line(
                    "ERROR",
                    failure="RGBD_CUP_POSE_CLEANUP_FAILED",
                    message=str(cleanup_error),
                ),
                flush=True,
            )
            result = 1
    if result != 0 and event_emitter is not None:
        last_event = event_emitter.last_event
        if last_event is None or last_event.event not in {
            "PERCEPTION_FAILED",
            "CUP_POSE_PUBLISHED",
        }:
            event_emitter.emit(
                "PERCEPTION_FAILED",
                payload={},
                failure_code=normalize_failure_code(
                    "PERCEPTION_FAILED", failure_code
                ),
            )
    return result


def run_rgbd_cup_pose(
    options: RgbdCupPoseOptions,
    *,
    runtime_factory: Callable[
        [RgbdCupPoseOptions, float, Callable[[], float]], _Runtime
    ] = _create_ros_runtime,
    monotonic: Callable[[], float] = time.monotonic,
    open3d_preflight: Callable[[float], None] = _require_open3d,
    profiler: SemanticProfiler | None = None,
    event_emitter: EventEmitter | None = None,
) -> int:
    """Run the RGB-D process and optionally record its total lifetime."""

    if profiler is None:
        return _run_rgbd_cup_pose(
            options,
            runtime_factory=runtime_factory,
            monotonic=monotonic,
            open3d_preflight=open3d_preflight,
            event_emitter=event_emitter,
        )
    token = profiler.start_span("perception.total")
    try:
        result = _run_rgbd_cup_pose(
            options,
            runtime_factory=runtime_factory,
            monotonic=monotonic,
            open3d_preflight=open3d_preflight,
            profiler=profiler,
            event_emitter=event_emitter,
        )
    except Exception as error:
        profiler.finish_span(
            token,
            outcome="error",
            attributes={"error_class": type(error).__name__},
        )
        raise
    profiler.finish_span(
        token,
        outcome="published" if result == 0 else "error",
        attributes={"exit_code": result},
    )
    return result
