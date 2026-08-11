import importlib.util
from pathlib import Path
from types import SimpleNamespace

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
        self.activated = []
        self.closed = False

    def focus_window(self, window_id):
        self.focused.append(window_id)

    def activate_window(self, window_id):
        self.activated.append(window_id)

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


def test_capture_failure_restores_original_window_before_closing_manager(monkeypatch, tmp_path):
    managers = []

    def factory(display_name):
        manager = FakeWindowManager(display_name)
        managers.append(manager)
        return manager

    monkeypatch.setattr(MODULE, "active_window_id", lambda: 99)

    with pytest.raises(RuntimeError, match="capture failed"):
        MODULE.capture_session(
            tmp_path,
            environment_loader=lambda: {"DISPLAY": ":1"},
            window_loader=lambda: [{
                "id": 42,
                "description": "rviz",
                "width": 800,
                "height": 600,
                "x": 0,
                "y": 0,
            }],
            desktop_grabber=fake_desktop_png,
            window_grabber=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("capture failed")
            ),
            manager_factory=factory,
        )

    assert managers[0].activated == [99]
    assert managers[0].closed is True


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


def test_window_inventory_uses_absolute_geometry_from_xwininfo(monkeypatch):
    output = (
        '  0x4200106 "moveit.rviz - RViz": ("rviz2" "rviz2")  '
        '1887x2091+14+49  +712+124\n'
    )
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=output),
    )

    windows = MODULE.list_windows()

    assert windows[0]["x"] == 712
    assert windows[0]["y"] == 124


def test_window_capture_activates_selected_window_before_grab(monkeypatch, tmp_path):
    activated = []
    raised = []

    class Manager:
        def raise_window(self, window_id):
            raised.append(window_id)

        def activate_window(self, window_id):
            activated.append(window_id)

    class Image:
        def save(self, output_path, _format):
            output_path.write_bytes(b"focused-window")

    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        MODULE.ImageGrab,
        "grab",
        lambda **_kwargs: Image(),
    )
    output = tmp_path / "window.png"

    MODULE.capture_window(
        Manager(),
        {
            "id": 42,
            "raise_id": 84,
            "x": 10,
            "y": 20,
            "width": 100,
            "height": 80,
        },
        output,
        ":1",
    )

    assert raised == [84]
    assert activated == [42]
    assert output.read_bytes() == b"focused-window"


def test_find_window_prefers_application_client_and_pairs_mutter_frame():
    title = "moveit.rviz - RViz"
    windows = [
        {
            "id": 10,
            "title": title,
            "wm_class": ("mutter-x11-frames", "mutter-x11-frames"),
            "description": f'{title} mutter-x11-frames',
            "width": 1915,
            "height": 2157,
            "x": 698,
            "y": 75,
        },
        {
            "id": 20,
            "title": title,
            "wm_class": ("rviz2", "rviz2"),
            "description": f'{title} rviz2',
            "width": 1887,
            "height": 2091,
            "x": 712,
            "y": 124,
        },
    ]

    selected = MODULE.find_window(windows, ("rviz",))

    assert selected["id"] == 20
    assert selected["raise_id"] == 10
