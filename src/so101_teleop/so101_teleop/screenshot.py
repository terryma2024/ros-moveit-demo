"""Gazebo-only X11 capture with an explicit unique-window requirement."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Window:
    window_id: int
    title: str
    wm_class: tuple[str, ...]


@dataclass(frozen=True)
class ScreenshotResult:
    png: bytes
    timestamp: float
    geometry: Rect
    session_id: str


class ScreenshotError(RuntimeError):
    pass


def is_gazebo(window: Window) -> bool:
    classes = {value.casefold() for value in window.wm_class}
    return "gz-sim-gui" in classes or "gazebo gui" in classes


class GazeboScreenshot:
    def __init__(self, windows: Callable[[], Iterable[Window]], geometry: Callable[[int], Rect],
                 capture_rect: Callable[[Rect], bytes], now: Callable[[], float],
                 session_id: Callable[[], str]) -> None:
        self._windows = windows
        self._geometry = geometry
        self._capture_rect = capture_rect
        self._now = now
        self._session_id = session_id

    def capture(self) -> ScreenshotResult:
        candidates = [window for window in self._windows() if is_gazebo(window)]
        if not candidates:
            raise ScreenshotError("GAZEBO_WINDOW_NOT_FOUND")
        if len(candidates) != 1:
            raise ScreenshotError("GAZEBO_WINDOW_AMBIGUOUS")
        geometry = self._geometry(candidates[0].window_id)
        png = self._capture_rect(geometry)
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ScreenshotError("GAZEBO_SCREENSHOT_NOT_PNG")
        return ScreenshotResult(png, self._now(), geometry, self._session_id())


def ffmpeg_capture(display: str) -> Callable[[Rect], bytes]:
    def capture(rect: Rect) -> bytes:
        completed = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "x11grab", "-video_size",
             f"{rect.width}x{rect.height}", "-i", f"{display}+{rect.x},{rect.y}", "-frames:v", "1",
             "-f", "image2pipe", "-vcodec", "png", "pipe:1"], check=False, capture_output=True)
        if completed.returncode:
            raise ScreenshotError("GAZEBO_SCREENSHOT_CAPTURE_FAILED")
        return completed.stdout
    return capture
