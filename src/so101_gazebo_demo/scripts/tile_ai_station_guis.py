#!/usr/bin/env python3
"""Tile RViz and Gazebo Sim across the current EWMH work area."""

import argparse
import sys
import time
from dataclasses import dataclass
import ctypes
import ctypes.util
import os
import shutil
import subprocess
import re


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class WindowInfo:
    window_id: int
    title: str
    wm_class: tuple[str, ...]
    geometry: Rect | None = None


def classify_window(title, wm_class):
    classes = {value.casefold() for value in wm_class}
    if 'rviz2' in classes:
        return 'rviz'
    if 'gz-sim-gui' in classes or 'gazebo gui' in classes:
        return 'gazebo'
    return None


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


def parse_current_desktop(text):
    match = re.search(r'=\s*(\d+)\s*$', text)
    if match is None:
        raise ValueError(f'invalid _NET_CURRENT_DESKTOP: {text!r}')
    return int(match.group(1))


def parse_workareas(text):
    payload = text.split('=', 1)
    if len(payload) != 2:
        raise ValueError(f'invalid _NET_WORKAREA: {text!r}')
    values = [int(value) for value in re.findall(r'-?\d+', payload[1])]
    if not values or len(values) % 4:
        raise ValueError(f'invalid _NET_WORKAREA: {text!r}')
    areas = [Rect(*values[index:index + 4]) for index in range(0, len(values), 4)]
    if any(area.width <= 0 or area.height <= 0 for area in areas):
        raise ValueError(f'invalid _NET_WORKAREA dimensions: {areas!r}')
    return areas


def parse_client_ids(text):
    return [int(value, 16) for value in re.findall(r'0x[0-9a-fA-F]+', text)]


def parse_window_properties(window_id, text):
    title_match = re.search(r'_NET_WM_NAME\([^)]*\) = "([^"]*)"', text)
    if title_match is None:
        title_match = re.search(r'WM_NAME\([^)]*\) = "([^"]*)"', text)
    class_match = re.search(r'WM_CLASS\([^)]*\) = (.+)', text)
    title = title_match.group(1) if title_match else ''
    classes = tuple(re.findall(r'"([^"]*)"', class_match.group(1))) if class_match else ()
    return WindowInfo(window_id, title, classes)


def parse_xwininfo_geometry(text):
    def value(label):
        match = re.search(rf'{re.escape(label)}:\s*(-?\d+)', text)
        if match is None:
            raise ValueError(f'missing {label} in xwininfo output')
        return int(match.group(1))

    return Rect(
        value('Absolute upper-left X'),
        value('Absolute upper-left Y'),
        value('Width'),
        value('Height'),
    )


def parse_frame_extents(text):
    payload = text.split('=', 1)
    if len(payload) != 2:
        raise ValueError(f'invalid _NET_FRAME_EXTENTS: {text!r}')
    values = tuple(int(value) for value in re.findall(r'-?\d+', payload[1]))
    if len(values) != 4 or any(value < 0 for value in values):
        raise ValueError(f'invalid _NET_FRAME_EXTENTS: {text!r}')
    return values


def outer_geometry(client, extents):
    left, right, top, bottom = extents
    return Rect(
        client.x - left,
        client.y - top,
        client.width + left + right,
        client.height + top + bottom,
    )


def moveresize_payload(rect):
    source_indication_and_fields = 0x1F00
    return (
        source_indication_and_fields,
        rect.x,
        rect.y,
        rect.width,
        rect.height,
    )


def rect_is_close(actual, expected, tolerance):
    return all(
        abs(left - right) <= tolerance
        for left, right in zip(
            (actual.x, actual.y, actual.width, actual.height),
            (expected.x, expected.y, expected.width, expected.height),
        )
    )


class ClientMessageData(ctypes.Union):
    _fields_ = [
        ('b', ctypes.c_char * 20),
        ('s', ctypes.c_short * 10),
        ('l', ctypes.c_long * 5),
    ]


class XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ('type', ctypes.c_int),
        ('serial', ctypes.c_ulong),
        ('send_event', ctypes.c_int),
        ('display', ctypes.c_void_p),
        ('window', ctypes.c_ulong),
        ('message_type', ctypes.c_ulong),
        ('format', ctypes.c_int),
        ('data', ClientMessageData),
    ]


class XEvent(ctypes.Union):
    _fields_ = [('xclient', XClientMessageEvent), ('pad', ctypes.c_long * 24)]


def validate_runtime_prerequisites(
    which=shutil.which,
    find_library=ctypes.util.find_library,
):
    """Fail early with the exact system packages needed by the X11 backend."""
    missing = []
    if find_library('X11') is None:
        missing.append('libX11')
    missing.extend(command for command in ('xprop', 'xwininfo') if which(command) is None)
    if missing:
        raise RuntimeError(
            f"missing X11 prerequisites: {', '.join(missing)}; "
            'install Ubuntu packages libx11-6 and x11-utils'
        )


class X11EwmhBackend:
    CLIENT_MESSAGE = 33
    SUBSTRUCTURE_NOTIFY_MASK = 1 << 19
    SUBSTRUCTURE_REDIRECT_MASK = 1 << 20

    def __init__(self, environment=None):
        self.environment = dict(os.environ if environment is None else environment)
        validate_runtime_prerequisites()
        if not self.environment.get('DISPLAY'):
            raise RuntimeError('DISPLAY is not set; source ~/gui-env.zsh first')
        library_name = ctypes.util.find_library('X11')
        if library_name is None:
            raise RuntimeError('libX11 was not found')
        self.x11 = ctypes.cdll.LoadLibrary(library_name)
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self.x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.x11.XInternAtom.restype = ctypes.c_ulong
        self.x11.XSendEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.POINTER(XEvent),
        ]
        self.x11.XSendEvent.restype = ctypes.c_int
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.x11.XFlush.restype = ctypes.c_int
        self.display = self.x11.XOpenDisplay(
            self.environment['DISPLAY'].encode()
        )
        if not self.display:
            raise RuntimeError(
                f"cannot open X display {self.environment['DISPLAY']}"
            )
        self.root = self.x11.XDefaultRootWindow(self.display)

    def _command(self, arguments):
        return subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
            env=self.environment,
        ).stdout

    def _atom(self, name):
        return self.x11.XInternAtom(self.display, name.encode(), False)

    def _send(self, window_id, message_name, payload):
        event = XEvent()
        event.xclient.type = self.CLIENT_MESSAGE
        event.xclient.serial = 0
        event.xclient.send_event = True
        event.xclient.display = self.display
        event.xclient.window = window_id
        event.xclient.message_type = self._atom(message_name)
        event.xclient.format = 32
        for index, value in enumerate(payload):
            event.xclient.data.l[index] = value
        mask = self.SUBSTRUCTURE_NOTIFY_MASK | self.SUBSTRUCTURE_REDIRECT_MASK
        sent = self.x11.XSendEvent(
            self.display,
            self.root,
            False,
            mask,
            ctypes.byref(event),
        )
        self.x11.XFlush(self.display)
        if sent == 0:
            raise RuntimeError(f'XSendEvent failed for window 0x{window_id:x}')

    def workarea(self):
        desktop = parse_current_desktop(
            self._command(['xprop', '-root', '_NET_CURRENT_DESKTOP'])
        )
        areas = parse_workareas(
            self._command(['xprop', '-root', '_NET_WORKAREA'])
        )
        if desktop >= len(areas):
            raise RuntimeError(f'no workarea for desktop {desktop}: {areas!r}')
        return areas[desktop]

    def windows(self):
        ids = parse_client_ids(
            self._command(['xprop', '-root', '_NET_CLIENT_LIST'])
        )
        return [
            parse_window_properties(
                window_id,
                self._command([
                    'xprop', '-id', hex(window_id),
                    '_NET_WM_NAME', 'WM_NAME', 'WM_CLASS',
                ]),
            )
            for window_id in ids
        ]

    def geometry(self, window_id):
        client = parse_xwininfo_geometry(
            self._command(['xwininfo', '-id', hex(window_id)])
        )
        extents = parse_frame_extents(
            self._command([
                'xprop', '-id', hex(window_id), '_NET_FRAME_EXTENTS'
            ])
        )
        return outer_geometry(client, extents)

    def clear_maximize(self, window_id):
        self._send(
            window_id,
            '_NET_WM_STATE',
            (
                0,
                self._atom('_NET_WM_STATE_MAXIMIZED_VERT'),
                self._atom('_NET_WM_STATE_MAXIMIZED_HORZ'),
                1,
                0,
            ),
        )

    def move_resize(self, window_id, rect):
        self._send(
            window_id, '_NET_MOVERESIZE_WINDOW', moveresize_payload(rect)
        )


def describe_windows(windows):
    return '; '.join(
        f'0x{window.window_id:x} title={window.title!r} class={window.wm_class!r}'
        for window in windows
    ) or '<none>'


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


def maximize_window(
    backend,
    role,
    timeout_sec,
    poll_sec,
    geometry_tolerance,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    selected = wait_for_windows(
        backend, (role,), timeout_sec, poll_sec, monotonic, sleep
    )
    target = backend.workarea()
    window_id = selected[role].window_id
    backend.move_resize(window_id, target)
    sleep(0.5)
    actual = backend.geometry(window_id)
    if not rect_is_close(actual, target, geometry_tolerance):
        raise RuntimeError(
            f'{role} geometry mismatch: actual={actual!r} '
            f'expected={target!r} tolerance={geometry_tolerance}'
        )
    return target


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
            target = maximize_window(
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
