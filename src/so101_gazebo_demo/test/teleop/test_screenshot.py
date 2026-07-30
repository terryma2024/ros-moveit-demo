import pytest

from so101_teleop.screenshot import GazeboScreenshot, Rect, ScreenshotError, Window


GAZEBO = Window(101, "Gazebo Sim", ("gz-sim-gui", "Gazebo GUI"))


def test_ambiguous_gazebo_windows_are_rejected():
    """Picking the first of two Gazebo windows could expose a stale or wrong simulation."""
    capture = GazeboScreenshot(lambda: [GAZEBO, Window(102, "Gazebo 2", ("gz-sim-gui",))],
                               lambda window_id: Rect(66, 32, 3774, 2128), lambda rect: b"png", lambda: 1.0,
                               lambda: "session-a")

    with pytest.raises(ScreenshotError, match="GAZEBO_WINDOW_AMBIGUOUS"):
        capture.capture()


def test_exact_gazebo_window_region_becomes_png_bytes():
    """Capturing the desktop instead of the outer Gazebo rectangle would leak unrelated UI."""
    result = GazeboScreenshot(lambda: [GAZEBO], lambda window_id: Rect(66, 32, 3774, 2128),
                              lambda rect: b"\x89PNG\r\n\x1a\nbody", lambda: 2.0,
                              lambda: "session-a").capture()

    assert result.geometry == Rect(66, 32, 3774, 2128)
    assert result.png.startswith(b"\x89PNG")
    assert result.session_id == "session-a"
