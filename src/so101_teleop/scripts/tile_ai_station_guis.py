#!/usr/bin/env python3
"""Tile RViz and Gazebo Sim across the current EWMH work area."""

import argparse
import ctypes  # noqa: F401  (re-exported for tests and callers)
import subprocess
import sys
import time

from so101_teleop.gui.x11 import (  # noqa: F401
    ClientMessageData,
    Rect,
    WindowInfo,
    XClientMessageEvent,
    XEvent,
    X11EwmhBackend,
    classify_window,
    describe_windows,
    maximize_window,
    moveresize_payload,
    outer_geometry,
    parse_client_ids,
    parse_current_desktop,
    parse_frame_extents,
    parse_window_properties,
    parse_workareas,
    parse_xwininfo_geometry,
    rect_is_close,
    select_unique_window,
    validate_runtime_prerequisites,
    wait_for_unique_window,
)


def split_workarea(workarea):
    left_width = workarea.width // 2
    right_width = workarea.width - left_width
    return (
        Rect(workarea.x, workarea.y, left_width, workarea.height),
        Rect(
            workarea.x + left_width,
            workarea.y,
            right_width,
            workarea.height,
        ),
    )


def wait_for_windows(backend, roles, timeout_sec, poll_sec, monotonic, sleep):
    deadline = monotonic() + timeout_sec
    while True:
        observed = backend.windows()
        selected = {
            role: window
            for window in observed
            if (role := classify_window(window.title, window.wm_class))
        }
        missing = [role for role in roles if role not in selected]
        if not missing:
            return selected
        if monotonic() >= deadline:
            raise RuntimeError(
                f"missing {', '.join(missing)}; observed: "
                f'{describe_windows(observed)}'
            )
        sleep(poll_sec)


def tile_windows(
    backend,
    timeout_sec,
    poll_sec,
    geometry_tolerance,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    selected = wait_for_windows(
        backend, ('rviz', 'gazebo'), timeout_sec, poll_sec, monotonic, sleep
    )

    left, right = split_workarea(backend.workarea())
    targets = {'rviz': left, 'gazebo': right}
    for role in ('rviz', 'gazebo'):
        backend.clear_maximize(selected[role].window_id)
    for role in ('rviz', 'gazebo'):
        backend.move_resize(selected[role].window_id, targets[role])
    sleep(0.5)

    for role in ('rviz', 'gazebo'):
        actual = backend.geometry(selected[role].window_id)
        if not rect_is_close(actual, targets[role], geometry_tolerance):
            raise RuntimeError(
                f'{role} geometry mismatch: actual={actual!r} '
                f'expected={targets[role]!r} tolerance={geometry_tolerance}'
            )
    return targets


def maximize_role(
    backend,
    role,
    timeout_sec,
    poll_sec,
    geometry_tolerance,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    """Wait for the unique window of role and maximize it onto the work area."""
    window = wait_for_unique_window(
        backend, role, timeout_sec, poll_sec, monotonic, sleep
    )
    return maximize_window(backend, window, geometry_tolerance, sleep)


def parse_args(arguments=None):
    parser = argparse.ArgumentParser(
        description='Tile RViz left and Gazebo Sim right on ai-station.'
    )
    parser.add_argument('--left', choices=('rviz',), default='rviz')
    parser.add_argument('--right', choices=('gazebo',), default='gazebo')
    parser.add_argument('--maximize', choices=('gazebo', 'rviz'))
    parser.add_argument('--timeout-sec', type=float, default=30.0)
    parser.add_argument('--poll-sec', type=float, default=0.25)
    parser.add_argument('--geometry-tolerance', type=int, default=12)
    return parser.parse_args(arguments)


def main(arguments=None):
    args = parse_args(arguments)
    try:
        backend = X11EwmhBackend()
        if args.maximize:
            target = maximize_role(
                backend,
                args.maximize,
                timeout_sec=args.timeout_sec,
                poll_sec=args.poll_sec,
                geometry_tolerance=args.geometry_tolerance,
            )
        else:
            result = tile_windows(
                backend,
                timeout_sec=args.timeout_sec,
                poll_sec=args.poll_sec,
                geometry_tolerance=args.geometry_tolerance,
            )
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as error:
        print(f'LAYOUT_ERROR {error}', file=sys.stderr)
        return 2
    if args.maximize:
        print(f'LAYOUT_OK {args.maximize.upper()}={target}')
    else:
        print(f'LAYOUT_OK RVIZ={result["rviz"]} GAZEBO={result["gazebo"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
