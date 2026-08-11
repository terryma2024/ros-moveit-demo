import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai-station-capture.py"
SPEC = importlib.util.spec_from_file_location("ai_station_capture", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def fake_desktop_png(_display_name: str, output_path: Path) -> None:
    output_path.write_bytes(b"desktop-png")


def fake_window_png(_manager, _window, output_path: Path, _display_name: str) -> None:
    output_path.write_bytes(b"window-png")


class FakeWindowManager:
    def __init__(self, _display_name: str):
        self.shortcuts = []
        self.focused = []
        self.closed = False

    def focus_window(self, window_id):
        self.focused.append(window_id)

    def send_shortcut(self, modifiers, key):
        self.shortcuts.append((modifiers, key))

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "present,expected_mode,expected_missing",
    [
        ({"rviz", "ghostty"}, "desktop_and_windows", []),
        ({"rviz"}, "desktop_and_windows", ["ghostty"]),
        ({"ghostty"}, "desktop_and_windows", ["rviz"]),
        (set(), "desktop_only", ["rviz", "ghostty"]),
    ],
)
def test_optional_window_matrix(present, expected_mode, expected_missing, tmp_path):
    windows = [
        {
            "id": index,
            "description": name,
            "width": 800,
            "height": 600,
            "x": 0,
            "y": 0,
        }
        for index, name in enumerate(sorted(present), start=1)
    ]
    manifest = MODULE.capture_session(
        tmp_path,
        environment_loader=lambda: {"DISPLAY": ":1"},
        window_loader=lambda: windows,
        desktop_grabber=fake_desktop_png,
        window_grabber=fake_window_png,
        manager_factory=FakeWindowManager,
    )

    assert manifest["capture_mode"] == expected_mode
    assert manifest["missing_windows"] == expected_missing
    assert manifest["captured_windows"] == sorted(present)
    assert Path(manifest["desktop"]).parent.parent == tmp_path
    for field in ("desktop", "rviz", "ghostty"):
        path = manifest[field]
        if path is not None:
            artifact = Path(path)
            assert artifact.is_file()
            assert artifact.stat().st_size > 0


def test_each_capture_uses_a_fresh_unique_directory(tmp_path):
    kwargs = {
        "environment_loader": lambda: {"DISPLAY": ":1"},
        "window_loader": lambda: [],
        "desktop_grabber": fake_desktop_png,
        "window_grabber": fake_window_png,
        "manager_factory": FakeWindowManager,
    }

    first = MODULE.capture_session(tmp_path, **kwargs)
    second = MODULE.capture_session(tmp_path, **kwargs)

    assert Path(first["desktop"]).parent != Path(second["desktop"]).parent


def test_tab_test_skips_without_ghostty_and_sends_no_key(tmp_path):
    managers = []

    def factory(display_name):
        manager = FakeWindowManager(display_name)
        managers.append(manager)
        return manager

    manifest = MODULE.capture_session(
        tmp_path,
        test_ghostty_tabs=True,
        environment_loader=lambda: {"DISPLAY": ":1"},
        window_loader=lambda: [],
        desktop_grabber=fake_desktop_png,
        window_grabber=fake_window_png,
        manager_factory=factory,
    )

    assert manifest["ghostty_tab_test"] == "skipped_no_window"
    assert managers == []
