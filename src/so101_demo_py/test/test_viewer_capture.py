import os
from pathlib import Path

import pytest


def test_viewer_capture_requires_one_mujoco_window(tmp_path: Path) -> None:
    from so101_demo.runtime.viewer_capture import MacViewerCapture

    class Windows:
        def list_windows(self, pid):
            assert pid == 321
            return [{"window_id": 99, "owner_pid": 321, "title": "MuJoCo", "onscreen": True}]

    def screenshot(window_id, output):
        assert window_id == 99
        output.write_bytes(b"\x89PNG\r\n\x1a\nvalid")
        os.utime(output, (20.0, 20.0))

    capture = MacViewerCapture(321, Windows(), screenshot, clock=lambda: 20.0)
    result = capture.capture(tmp_path / "mujoco-viewer.png", terminal_timestamp=19.0)
    assert result.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result.window_title == "MuJoCo"


@pytest.mark.parametrize("windows", [[], [{"window_id": 1}, {"window_id": 2}]])
def test_viewer_capture_rejects_zero_or_ambiguous_windows(
    tmp_path: Path, windows
) -> None:
    from so101_demo.runtime.viewer_capture import MacViewerCapture

    backend = type("Windows", (), {"list_windows": lambda _self, _pid: windows})()
    capture = MacViewerCapture(321, backend, lambda *_args: None)
    with pytest.raises(RuntimeError, match="exactly one"):
        capture.capture(tmp_path / "viewer.png")
