#!/usr/bin/env python3
"""Shared X11/EWMH helpers for ai-station window discovery and control."""

import ctypes
import ctypes.util
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Callable


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


def classify_window(title: str, wm_class: tuple[str, ...]) -> str | None:
    classes = {value.casefold() for value in wm_class}
    if 'rviz2' in classes:
        return 'rviz'
    if 'gz-sim-gui' in classes or 'gazebo gui' in classes:
        return 'gazebo'
    return None


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

    def maximize(self, window_id):
        """Ask the window manager to add both EWMH maximized states."""
        self._send(
            window_id,
            '_NET_WM_STATE',
            (
                1,
                self._atom('_NET_WM_STATE_MAXIMIZED_VERT'),
                self._atom('_NET_WM_STATE_MAXIMIZED_HORZ'),
                1,
                0,
            ),
        )

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


def select_unique_window(windows: list[WindowInfo], role: str) -> WindowInfo:
    """Return the one window matching role; never pick from ambiguous matches."""
    matches = [
        window
        for window in windows
        if classify_window(window.title, window.wm_class) == role
    ]
    if not matches:
        raise RuntimeError(
            f'no {role} window; observed: {describe_windows(windows)}'
        )
    if len(matches) > 1:
        raise RuntimeError(
            f'multiple {role} windows: {describe_windows(matches)}'
        )
    return matches[0]


def wait_for_unique_window(
    backend,
    role,
    timeout_sec,
    poll_sec,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    """Poll until exactly one window matches role; ambiguity fails at once."""
    deadline = monotonic() + timeout_sec
    while True:
        observed = backend.windows()
        matches = [
            window
            for window in observed
            if classify_window(window.title, window.wm_class) == role
        ]
        if len(matches) > 1:
            raise RuntimeError(
                f'multiple {role} windows: {describe_windows(matches)}'
            )
        if matches:
            return matches[0]
        if monotonic() >= deadline:
            raise RuntimeError(
                f'missing {role}; observed: {describe_windows(observed)}'
            )
        sleep(poll_sec)


def maximize_window(
    backend: X11EwmhBackend,
    window: WindowInfo,
    tolerance: int,
    sleep: Callable[[float], None] = time.sleep,
) -> Rect:
    """Maximize one window through EWMH and verify it fills the work area."""
    target = backend.workarea()
    backend.maximize(window.window_id)
    sleep(0.5)
    actual = backend.geometry(window.window_id)
    if not rect_is_close(actual, target, tolerance):
        raise RuntimeError(
            f'maximize geometry mismatch for 0x{window.window_id:x}: '
            f'actual={actual!r} expected={target!r} tolerance={tolerance}'
        )
    return target
