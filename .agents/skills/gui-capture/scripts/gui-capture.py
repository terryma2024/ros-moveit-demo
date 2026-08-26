#!/usr/bin/env python3
"""Capture one GUI window on macOS or GNOME X11, or a GNOME X11 desktop."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import platform as host_platform
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable


WINDOW_GEOMETRY = re.compile(
    r"(?P<width>\d+)x(?P<height>\d+)(?P<x>[+-]\d+)(?P<y>[+-]\d+)"
)
WINDOW_OFFSET = re.compile(r"(?P<x>[+-]\d+)(?P<y>[+-]\d+)")
WINDOW_ID = re.compile(r"0x[0-9a-fA-F]+")
WINDOW_TITLE = re.compile(r'0x[0-9a-fA-F]+\s+"([^"]*)"')
WINDOW_CLASS = re.compile(r'\("([^"]*)"\s+"([^"]*)"\)')

class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


def _completed_stdout(command: list[str], runner=subprocess.run) -> str:
    completed = runner(command, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def parse_macos_window_inventory(payload: str) -> list[dict[str, object]]:
    rows = json.loads(payload)
    windows: list[dict[str, object]] = []
    for row in rows:
        bounds = row.get("bounds") or {}
        width = int(bounds.get("Width", bounds.get("width", 0)))
        height = int(bounds.get("Height", bounds.get("height", 0)))
        if (
            int(row.get("layer", 0)) != 0
            or not bool(row.get("onscreen", False))
            or float(row.get("alpha", 1)) <= 0
            or width < 50
            or height < 50
        ):
            continue
        windows.append(
            {
                "id": int(row["id"]),
                "owner": str(row.get("owner", "")),
                "owner_pid": int(row.get("owner_pid", 0)),
                "title": str(row.get("title", "")),
                "x": int(bounds.get("X", bounds.get("x", 0))),
                "y": int(bounds.get("Y", bounds.get("y", 0))),
                "width": width,
                "height": height,
            }
        )
    return windows


def _macos_cf_string(core_foundation, value: int | None) -> str:
    if not value:
        return ""
    length = core_foundation.CFStringGetLength(value)
    capacity = core_foundation.CFStringGetMaximumSizeForEncoding(
        length, 0x08000100
    ) + 1
    buffer = ctypes.create_string_buffer(capacity)
    if not core_foundation.CFStringGetCString(
        value, buffer, capacity, 0x08000100
    ):
        return ""
    return buffer.value.decode("utf-8", errors="replace")


def _macos_cf_number(core_foundation, value: int | None, *, floating=False):
    if not value:
        return 0.0 if floating else 0
    output = ctypes.c_double() if floating else ctypes.c_longlong()
    number_type = 6 if floating else 4
    if not core_foundation.CFNumberGetValue(value, number_type, ctypes.byref(output)):
        return 0.0 if floating else 0
    return output.value


def _macos_window_rows() -> list[dict[str, object]]:
    core_graphics = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    core_foundation = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    core_graphics.CGWindowListCopyWindowInfo.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    core_graphics.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    core_graphics.CGRectMakeWithDictionaryRepresentation.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(CGRect),
    ]
    core_graphics.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
    core_foundation.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    core_foundation.CFArrayGetCount.restype = ctypes.c_long
    core_foundation.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    core_foundation.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    core_foundation.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    core_foundation.CFDictionaryGetValue.restype = ctypes.c_void_p
    core_foundation.CFStringGetLength.argtypes = [ctypes.c_void_p]
    core_foundation.CFStringGetLength.restype = ctypes.c_long
    core_foundation.CFStringGetMaximumSizeForEncoding.argtypes = [
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    core_foundation.CFStringGetMaximumSizeForEncoding.restype = ctypes.c_long
    core_foundation.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    core_foundation.CFStringGetCString.restype = ctypes.c_bool
    core_foundation.CFNumberGetValue.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
    ]
    core_foundation.CFNumberGetValue.restype = ctypes.c_bool
    core_foundation.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
    core_foundation.CFBooleanGetValue.restype = ctypes.c_bool
    core_foundation.CFRelease.argtypes = [ctypes.c_void_p]

    keys = {
        name: ctypes.c_void_p.in_dll(core_graphics, name).value
        for name in (
            "kCGWindowNumber",
            "kCGWindowOwnerName",
            "kCGWindowOwnerPID",
            "kCGWindowName",
            "kCGWindowLayer",
            "kCGWindowIsOnscreen",
            "kCGWindowAlpha",
            "kCGWindowBounds",
        )
    }

    def value(dictionary: int, key: str) -> int | None:
        return core_foundation.CFDictionaryGetValue(dictionary, keys[key])

    window_array = core_graphics.CGWindowListCopyWindowInfo(17, 0)
    if not window_array:
        raise RuntimeError("CoreGraphics returned no window inventory")
    rows: list[dict[str, object]] = []
    try:
        for index in range(core_foundation.CFArrayGetCount(window_array)):
            dictionary = core_foundation.CFArrayGetValueAtIndex(window_array, index)
            bounds = CGRect()
            bounds_value = value(dictionary, "kCGWindowBounds")
            if not bounds_value or not core_graphics.CGRectMakeWithDictionaryRepresentation(
                bounds_value, ctypes.byref(bounds)
            ):
                continue
            onscreen_value = value(dictionary, "kCGWindowIsOnscreen")
            rows.append(
                {
                    "id": _macos_cf_number(
                        core_foundation, value(dictionary, "kCGWindowNumber")
                    ),
                    "owner": _macos_cf_string(
                        core_foundation, value(dictionary, "kCGWindowOwnerName")
                    ),
                    "owner_pid": _macos_cf_number(
                        core_foundation, value(dictionary, "kCGWindowOwnerPID")
                    ),
                    "title": _macos_cf_string(
                        core_foundation, value(dictionary, "kCGWindowName")
                    ),
                    "layer": _macos_cf_number(
                        core_foundation, value(dictionary, "kCGWindowLayer")
                    ),
                    "onscreen": bool(
                        onscreen_value
                        and core_foundation.CFBooleanGetValue(onscreen_value)
                    ),
                    "alpha": _macos_cf_number(
                        core_foundation,
                        value(dictionary, "kCGWindowAlpha"),
                        floating=True,
                    ),
                    "bounds": {
                        "X": bounds.origin.x,
                        "Y": bounds.origin.y,
                        "Width": bounds.size.width,
                        "Height": bounds.size.height,
                    },
                }
            )
    finally:
        core_foundation.CFRelease(window_array)
    return rows


def list_macos_windows() -> list[dict[str, object]]:
    return parse_macos_window_inventory(json.dumps(_macos_window_rows()))


def focus_macos_window(window: dict[str, object], *, runner=subprocess.run) -> None:
    target = json.dumps(
        {
            key: window[key]
            for key in ("owner_pid", "title", "x", "y", "width", "height")
        }
    )
    script = f"""
const target = {target};
const systemEvents = Application('System Events');
const processes = systemEvents.processes().filter(
  (process) => Number(process.unixId()) === Number(target.owner_pid)
);
if (processes.length !== 1) {{
  throw new Error('Unable to resolve one Accessibility process for PID ' + target.owner_pid);
}}
const process = processes[0];
process.frontmost = true;
delay(0.15);
const matches = process.windows().filter((window) => {{
  const position = window.position();
  const size = window.size();
  return String(window.name()) === String(target.title) &&
    Math.abs(Number(position[0]) - Number(target.x)) <= 4 &&
    Math.abs(Number(position[1]) - Number(target.y)) <= 4 &&
    Math.abs(Number(size[0]) - Number(target.width)) <= 8 &&
    Math.abs(Number(size[1]) - Number(target.height)) <= 8;
}});
if (matches.length !== 1) {{
  throw new Error('Unable to map the CoreGraphics window to one Accessibility window');
}}
const raiseAction = matches[0].actions.byName('AXRaise');
if (!raiseAction.exists()) {{
  throw new Error('The target window does not expose AXRaise');
}}
raiseAction.perform();
delay(0.2);
"""
    runner(
        ["osascript", "-l", "JavaScript", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )


def capture_macos_window(
    window: dict[str, object],
    output_path: Path,
    *,
    focus_window=focus_macos_window,
    runner=subprocess.run,
    sleeper=time.sleep,
) -> None:
    focus_window(window)
    sleeper(0.25)
    runner(
        ["screencapture", "-x", "-l", str(window["id"]), str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def capture_macos_desktop(
    output_path: Path,
    *,
    runner=subprocess.run,
) -> None:
    runner(
        ["screencapture", "-x", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def read_process_environment(pid: int) -> dict[str, str]:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
    return {
        key.decode(): value.decode()
        for entry in raw.split(b"\0")
        if entry
        for key, value in [entry.split(b"=", 1)]
    }


def find_gnome_x11_environment() -> dict[str, str]:
    result = subprocess.run(
        ["pgrep", "-x", "gnome-shell"],
        check=True,
        capture_output=True,
        text=True,
    )
    candidates: list[tuple[int, dict[str, str]]] = []
    for value in result.stdout.split():
        pid = int(value)
        try:
            environment = read_process_environment(pid)
        except (FileNotFoundError, PermissionError):
            continue
        if environment.get("DISPLAY") and environment.get("XDG_SESSION_TYPE") == "x11":
            candidates.append((pid, environment))
    if not candidates:
        raise RuntimeError(
            "No active GNOME X11 session was found; GNOME Wayland requires a loaded "
            "semantic GUI driver or a portal-aware capture tool"
        )
    _, environment = max(candidates, key=lambda item: item[0])
    for name in (
        "DISPLAY",
        "XAUTHORITY",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
    ):
        if value := environment.get(name):
            os.environ[name] = value
    return environment


def parse_gnome_x11_window_inventory(payload: str) -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []
    for line in payload.splitlines():
        id_match = WINDOW_ID.search(line)
        geometry_match = WINDOW_GEOMETRY.search(line)
        if not id_match or not geometry_match:
            continue
        absolute_offsets = list(WINDOW_OFFSET.finditer(line))
        if not absolute_offsets:
            continue
        offset = absolute_offsets[-1]
        width = int(geometry_match.group("width"))
        height = int(geometry_match.group("height"))
        if width < 50 or height < 50:
            continue
        title_match = WINDOW_TITLE.search(line)
        class_match = WINDOW_CLASS.search(line)
        wm_class = class_match.groups() if class_match else ()
        windows.append(
            {
                "id": int(id_match.group(), 16),
                "owner": "/".join(wm_class),
                "title": title_match.group(1) if title_match else "",
                "wm_class": wm_class,
                "x": int(offset.group("x")),
                "y": int(offset.group("y")),
                "width": width,
                "height": height,
                "description": line.strip(),
            }
        )
    return windows


def list_gnome_x11_windows(*, runner=subprocess.run) -> list[dict[str, object]]:
    payload = _completed_stdout(
        ["xwininfo", "-root", "-tree"],
        runner=runner,
    )
    return parse_gnome_x11_window_inventory(payload)


class ClientMessageData(ctypes.Union):
    _fields_ = [
        ("b", ctypes.c_char * 20),
        ("s", ctypes.c_short * 10),
        ("l", ctypes.c_long * 5),
    ]


class XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", ClientMessageData),
    ]


class XEvent(ctypes.Union):
    _fields_ = [("xclient", XClientMessageEvent), ("pad", ctypes.c_long * 24)]


class X11WindowManager:
    CLIENT_MESSAGE = 33
    SUBSTRUCTURE_NOTIFY_MASK = 1 << 19
    SUBSTRUCTURE_REDIRECT_MASK = 1 << 20

    def __init__(self, display_name: str) -> None:
        self.x11 = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("X11") or "libX11.so.6"
        )
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
        self.x11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.display = self.x11.XOpenDisplay(display_name.encode())
        if not self.display:
            raise RuntimeError(f"Unable to open X11 display {display_name}")
        self.root = self.x11.XDefaultRootWindow(self.display)

    def raise_window(self, window_id: int) -> None:
        self.x11.XRaiseWindow(self.display, window_id)
        self.x11.XFlush(self.display)

    def activate_window(self, window_id: int) -> None:
        event = XEvent()
        event.xclient.type = self.CLIENT_MESSAGE
        event.xclient.send_event = True
        event.xclient.display = self.display
        event.xclient.window = window_id
        event.xclient.message_type = self.x11.XInternAtom(
            self.display, b"_NET_ACTIVE_WINDOW", False
        )
        event.xclient.format = 32
        event.xclient.data.l[0] = 1
        mask = self.SUBSTRUCTURE_NOTIFY_MASK | self.SUBSTRUCTURE_REDIRECT_MASK
        sent = self.x11.XSendEvent(
            self.display,
            self.root,
            False,
            mask,
            ctypes.byref(event),
        )
        if sent == 0:
            raise RuntimeError(f"Unable to activate X11 window 0x{window_id:x}")
        self.x11.XFlush(self.display)

    def close(self) -> None:
        if self.display:
            self.x11.XCloseDisplay(self.display)
            self.display = None


def active_gnome_x11_window_id(*, runner=subprocess.run) -> int | None:
    completed = runner(
        ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
        check=False,
        capture_output=True,
        text=True,
    )
    match = WINDOW_ID.search(completed.stdout)
    return int(match.group(), 16) if match else None


def capture_gnome_x11_window(
    window: dict[str, object],
    output_path: Path,
    *,
    display_name: str,
    manager_factory=X11WindowManager,
    sleeper=time.sleep,
) -> None:
    from PIL import ImageGrab

    manager = manager_factory(display_name)
    original = active_gnome_x11_window_id()
    try:
        manager.raise_window(int(window.get("raise_id", window["id"])))
        manager.activate_window(int(window["id"]))
        sleeper(0.35)
        x, y = int(window["x"]), int(window["y"])
        width, height = int(window["width"]), int(window["height"])
        ImageGrab.grab(
            bbox=(x, y, x + width, y + height),
            xdisplay=display_name,
        ).save(output_path, "PNG")
    finally:
        try:
            if original:
                manager.activate_window(original)
        finally:
            manager.close()


def capture_gnome_x11_desktop(output_path: Path, *, display_name: str) -> None:
    from PIL import ImageGrab

    ImageGrab.grab(xdisplay=display_name).save(output_path, "PNG")


def select_window(
    windows: list[dict[str, object]],
    *,
    query: str | None = None,
    window_id: int | None = None,
) -> dict[str, object]:
    if window_id is not None:
        matches = [window for window in windows if int(window["id"]) == window_id]
        if len(matches) != 1:
            raise RuntimeError(f"window id {window_id} was not found")
        return dict(matches[0])
    if not query:
        raise RuntimeError("a window query or exact window id is required")
    needle = query.casefold()
    matches = []
    for window in windows:
        title = str(window.get("title", ""))
        owner = str(window.get("owner", ""))
        wm_class = " ".join(map(str, window.get("wm_class", ())))
        haystack = " ".join((title, owner, wm_class)).casefold()
        if needle not in haystack:
            continue
        score = 3 if title.casefold() == needle else 2 if owner.casefold() == needle else 1
        matches.append((score, window))
    if not matches:
        raise RuntimeError(f"no visible window matched {query!r}")
    best_score = max(score for score, _window in matches)
    best = [window for score, window in matches if score == best_score]
    if len(best) != 1:
        choices = ", ".join(
            f"{window['id']}:{window.get('owner', '')}:{window.get('title', '')}"
            for window in best
        )
        raise RuntimeError(
            f"ambiguous window query {query!r}; choose --window-id from: {choices}"
        )
    return dict(best[0])


def _capture_atomically(output_path: Path, writer: Callable[[Path], None]) -> None:
    temporary = output_path.with_name(
        f"{output_path.stem}-{uuid.uuid4().hex}.tmp.png"
    )
    try:
        writer(temporary)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError(
                f"capture did not produce a nonempty image: {output_path.name}"
            )
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)


def _public_window(window: dict[str, object]) -> dict[str, object]:
    return {
        key: window[key]
        for key in ("id", "owner", "title", "x", "y", "width", "height")
        if key in window
    }


def capture_session(
    output_root: Path,
    *,
    query: str | None = None,
    window_id: int | None = None,
    desktop: bool = False,
    platform_name: str,
    session_type: str | None = None,
    window_loader: Callable[[], list[dict[str, object]]] | None = None,
    window_grabber: Callable[[dict[str, object], Path], None] | None = None,
    desktop_grabber: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    captured_at = time.strftime("%Y%m%dT%H%M%S")
    output_dir = output_root.expanduser().resolve() / (
        f"{captured_at}-{uuid.uuid4().hex[:12]}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    if desktop:
        if desktop_grabber is None:
            raise RuntimeError("desktop capture backend is unavailable")
        output_path = output_dir / "desktop.png"
        _capture_atomically(output_path, desktop_grabber)
        selected = None
        mode = "desktop"
    else:
        if window_loader is None or window_grabber is None:
            raise RuntimeError("window capture backend is unavailable")
        selected = select_window(window_loader(), query=query, window_id=window_id)
        output_path = output_dir / "window.png"
        _capture_atomically(
            output_path,
            lambda temporary: window_grabber(selected, temporary),
        )
        mode = "window"

    return {
        "captured_at": captured_at,
        "platform": platform_name,
        "session_type": session_type
        or ("aqua" if platform_name == "macos" else "x11"),
        "capture_mode": mode,
        "selector": {"query": query, "window_id": window_id},
        "window": _public_window(selected) if selected else None,
        "image": str(output_path),
    }


def resolve_backend(requested: str):
    system = host_platform.system()
    backend = requested
    if backend == "auto":
        backend = (
            "macos"
            if system == "Darwin"
            else "gnome-x11"
            if system == "Linux"
            else ""
        )
    if backend == "macos":
        if system != "Darwin":
            raise RuntimeError("the macOS backend can run only on macOS")
        return {
            "platform_name": "macos",
            "session_type": "aqua",
            "window_loader": list_macos_windows,
            "window_grabber": capture_macos_window,
            "desktop_grabber": capture_macos_desktop,
        }
    if backend == "gnome-x11":
        if system != "Linux":
            raise RuntimeError("the GNOME X11 backend can run only on Linux")
        environment = find_gnome_x11_environment()
        display_name = environment["DISPLAY"]
        return {
            "platform_name": "gnome",
            "session_type": "x11",
            "window_loader": list_gnome_x11_windows,
            "window_grabber": lambda window, output: capture_gnome_x11_window(
                window, output, display_name=display_name
            ),
            "desktop_grabber": lambda output: capture_gnome_x11_desktop(
                output, display_name=display_name
            ),
        }
    raise RuntimeError(f"unsupported GUI platform: {system}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--window")
    parser.add_argument("--window-id", type=lambda value: int(value, 0))
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--list-windows", action="store_true")
    parser.add_argument(
        "--platform",
        choices=("auto", "macos", "gnome-x11"),
        default="auto",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        backend = resolve_backend(args.platform)
        if args.list_windows:
            print(json.dumps(backend["window_loader"](), ensure_ascii=True))
            return 0
        if args.output_root is None:
            raise RuntimeError("--output-root is required for capture")
        if args.desktop and (args.window or args.window_id is not None):
            raise RuntimeError("choose desktop capture or one target window")
        if not args.desktop and not args.window and args.window_id is None:
            raise RuntimeError("--window or --window-id is required")
        manifest = capture_session(
            args.output_root,
            query=args.window,
            window_id=args.window_id,
            desktop=args.desktop,
            **backend,
        )
    except Exception as error:  # pragma: no cover - CLI boundary
        print(f"capture failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
