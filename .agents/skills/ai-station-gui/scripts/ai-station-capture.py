#!/usr/bin/env python3
"""Capture a fresh ai-station desktop and optional operator windows."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable

from PIL import ImageGrab


WINDOW_GEOMETRY = re.compile(
    r"(?P<width>\d+)x(?P<height>\d+)(?P<x>[+-]\d+)(?P<y>[+-]\d+)"
)
WINDOW_ID = re.compile(r"0x[0-9a-fA-F]+")
OPTIONAL_WINDOWS = {
    "rviz": ("rviz",),
    "ghostty": ("ghostty", "com.mitchellh.ghostty"),
}


def read_process_environment(pid: int) -> dict[str, str]:
    raw = Path(f"/proc/{pid}/environ").read_bytes()
    entries = (item for item in raw.split(b"\0") if item)
    return {
        key.decode(): value.decode()
        for key, value in (entry.split(b"=", 1) for entry in entries)
    }


def find_gnome_environment() -> dict[str, str]:
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
        raise RuntimeError("No active GNOME X11 session was found")

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


def list_windows() -> list[dict[str, int | str]]:
    output = subprocess.run(
        ["xwininfo", "-root", "-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    windows: list[dict[str, int | str]] = []
    for line in output.splitlines():
        id_match = WINDOW_ID.search(line)
        geometry_match = WINDOW_GEOMETRY.search(line)
        if not id_match or not geometry_match:
            continue
        values = {
            name: int(geometry_match.group(name))
            for name in ("width", "height", "x", "y")
        }
        if values["width"] < 50 or values["height"] < 50:
            continue
        windows.append(
            {
                "id": int(id_match.group(), 16),
                "description": line.strip(),
                **values,
            }
        )
    return windows


def find_window(
    windows: list[dict[str, int | str]], patterns: tuple[str, ...]
) -> dict[str, int | str] | None:
    matches = [
        window
        for window in windows
        if any(pattern in str(window["description"]).lower() for pattern in patterns)
    ]
    return (
        max(matches, key=lambda window: int(window["width"]) * int(window["height"]))
        if matches
        else None
    )


class X11WindowManager:
    def __init__(self, display_name: str) -> None:
        library_name = ctypes.util.find_library("X11") or "libX11.so.6"
        xtst_library_name = ctypes.util.find_library("Xtst") or "libXtst.so.6"
        self.x11 = ctypes.cdll.LoadLibrary(library_name)
        self.xtst = ctypes.cdll.LoadLibrary(xtst_library_name)
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XSetInputFocus.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self.x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x11.XStringToKeysym.restype = ctypes.c_ulong
        self.x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XKeysymToKeycode.restype = ctypes.c_uint
        self.xtst.XTestFakeKeyEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.display = self.x11.XOpenDisplay(display_name.encode())
        if not self.display:
            raise RuntimeError(f"Unable to open X11 display {display_name}")

    def raise_window(self, window_id: int) -> None:
        self.x11.XRaiseWindow(self.display, window_id)
        self.x11.XFlush(self.display)

    def focus_window(self, window_id: int) -> None:
        self.raise_window(window_id)
        self.x11.XSetInputFocus(self.display, window_id, 2, 0)
        self.x11.XFlush(self.display)

    def send_shortcut(self, modifiers: tuple[str, ...], key: str) -> None:
        names = (*modifiers, key)
        keycodes = []
        for name in names:
            keysym = self.x11.XStringToKeysym(name.encode())
            keycode = self.x11.XKeysymToKeycode(self.display, keysym)
            if not keycode:
                raise RuntimeError(f"Unable to resolve X11 key: {name}")
            keycodes.append(keycode)
        for keycode in keycodes:
            self.xtst.XTestFakeKeyEvent(self.display, keycode, True, 0)
        for keycode in reversed(keycodes):
            self.xtst.XTestFakeKeyEvent(self.display, keycode, False, 0)
        self.x11.XFlush(self.display)

    def close(self) -> None:
        if self.display:
            self.x11.XCloseDisplay(self.display)
            self.display = None


def active_window_id() -> int | None:
    result = subprocess.run(
        ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
        check=False,
        capture_output=True,
        text=True,
    )
    match = WINDOW_ID.search(result.stdout)
    return int(match.group(), 16) if match else None


def grab_desktop(display_name: str, output_path: Path) -> None:
    ImageGrab.grab(xdisplay=display_name).save(output_path, "PNG")


def capture_window(
    manager: X11WindowManager,
    window: dict[str, int | str],
    output_path: Path,
    display_name: str,
) -> None:
    manager.raise_window(int(window["id"]))
    time.sleep(0.35)
    x = int(window["x"])
    y = int(window["y"])
    width = int(window["width"])
    height = int(window["height"])
    image = ImageGrab.grab(
        bbox=(x, y, x + width, y + height),
        xdisplay=display_name,
    )
    image.save(output_path, "PNG")


def _capture_atomically(output_path: Path, writer: Callable[[Path], None]) -> None:
    temporary = output_path.with_name(f".{output_path.stem}-{uuid.uuid4().hex}.tmp.png")
    try:
        writer(temporary)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError(f"Capture did not produce a nonempty image: {output_path.name}")
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)


def capture_session(
    output_root: Path,
    test_ghostty_tabs: bool = False,
    *,
    environment_loader=find_gnome_environment,
    window_loader=list_windows,
    desktop_grabber=grab_desktop,
    window_grabber=capture_window,
    manager_factory=X11WindowManager,
) -> dict[str, object]:
    environment = environment_loader()
    display_name = environment["DISPLAY"]
    captured_at = time.strftime("%Y%m%dT%H%M%S")
    output_dir = output_root.expanduser().resolve() / (
        f"{captured_at}-{uuid.uuid4().hex[:12]}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    desktop_path = output_dir / "desktop.png"
    _capture_atomically(
        desktop_path,
        lambda temporary: desktop_grabber(display_name, temporary),
    )

    windows = window_loader()
    selected = {
        name: find_window(windows, patterns)
        for name, patterns in OPTIONAL_WINDOWS.items()
    }
    paths: dict[str, str | None] = {
        "desktop": str(desktop_path),
        "rviz": None,
        "ghostty": None,
    }
    captured_windows: list[str] = []
    missing_windows = [name for name in OPTIONAL_WINDOWS if selected[name] is None]
    manager = None
    original_window = None
    tab_result = "not_requested"

    try:
        if any(selected.values()):
            manager = manager_factory(display_name)
            original_window = active_window_id()
            for name in sorted(OPTIONAL_WINDOWS):
                window = selected[name]
                if window is None:
                    continue
                output_path = output_dir / f"{name}.png"
                _capture_atomically(
                    output_path,
                    lambda temporary, selected_window=window: window_grabber(
                        manager, selected_window, temporary, display_name
                    ),
                )
                paths[name] = str(output_path)
                captured_windows.append(name)

        ghostty = selected["ghostty"]
        if test_ghostty_tabs and ghostty is None:
            tab_result = "skipped_no_window"
        elif test_ghostty_tabs:
            assert manager is not None
            manager.focus_window(int(ghostty["id"]))
            manager.send_shortcut(("Control_L",), "Tab")
            time.sleep(0.6)
            switched = output_dir / "ghostty-after-ctrl-tab.png"
            _capture_atomically(
                switched,
                lambda temporary: window_grabber(
                    manager, ghostty, temporary, display_name
                ),
            )
            manager.focus_window(int(ghostty["id"]))
            manager.send_shortcut(("Control_L",), "Page_Up")
            time.sleep(0.6)
            restored = output_dir / "ghostty-after-restore.png"
            _capture_atomically(
                restored,
                lambda temporary: window_grabber(
                    manager, ghostty, temporary, display_name
                ),
            )
            paths["ghostty_after_ctrl_tab"] = str(switched)
            paths["ghostty_after_restore"] = str(restored)
            tab_result = "completed"

        if manager is not None and original_window:
            manager.focus_window(original_window)
    finally:
        if manager is not None:
            manager.close()

    return {
        "captured_at": captured_at,
        **paths,
        "captured_windows": captured_windows,
        "missing_windows": missing_windows,
        "capture_mode": "desktop_and_windows" if captured_windows else "desktop_only",
        "ghostty_tab_test": tab_result,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.home() / ".cache" / "codex-captures",
    )
    parser.add_argument("--test-ghostty-tabs", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = capture_session(args.output_root, args.test_ghostty_tabs)
    except Exception as error:  # pragma: no cover - CLI boundary
        print(f"capture failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
