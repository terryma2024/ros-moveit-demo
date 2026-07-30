import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'ai_station_x11.py'
)
SPEC = importlib.util.spec_from_file_location('ai_station_x11', SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

Rect = MODULE.Rect
WindowInfo = MODULE.WindowInfo
classify_window = MODULE.classify_window
select_unique_window = MODULE.select_unique_window
maximize_window = MODULE.maximize_window

RVIZ = WindowInfo(0x31, 'MoveIt - RViz', ('rviz2', 'rviz2'))
GAZEBO = WindowInfo(0x32, 'Gazebo Sim', ('gz-sim-gui', 'Gazebo GUI'))
GAZEBO_COPY = WindowInfo(0x33, 'Gazebo Sim', ('gz-sim-gui', 'Gazebo GUI'))
WORKAREA = Rect(66, 32, 3774, 2128)


def test_classify_window_matches_real_ai_station_windows():
    assert classify_window('moveit.rviz* - RViz', ('rviz2', 'rviz2')) == 'rviz'
    assert classify_window('Gazebo Sim', ('gz-sim-gui', 'Gazebo GUI')) == 'gazebo'
    assert classify_window('/data/work', ('ghostty', 'com.mitchellh.ghostty')) is None


def test_select_unique_window_returns_the_single_match():
    assert select_unique_window([RVIZ, GAZEBO], 'gazebo') == GAZEBO
    assert select_unique_window([RVIZ, GAZEBO], 'rviz') == RVIZ


def test_select_unique_window_rejects_ambiguous_gazebo_windows():
    windows = [
        WindowInfo(1, 'Gazebo Sim', ('gz-sim-gui', 'Gazebo GUI')),
        WindowInfo(2, 'Gazebo Sim', ('gz-sim-gui', 'Gazebo GUI')),
    ]
    with pytest.raises(RuntimeError, match='multiple gazebo windows'):
        select_unique_window(windows, 'gazebo')


def test_select_unique_window_rejects_a_missing_role():
    with pytest.raises(RuntimeError, match='no gazebo window'):
        select_unique_window([RVIZ], 'gazebo')


class FakeBackend:
    def __init__(self, workarea, geometry=None):
        self._workarea = workarea
        self._geometry = workarea if geometry is None else geometry
        self.requests = []

    def workarea(self):
        return self._workarea

    def maximize(self, window_id):
        self.requests.append(('maximize', window_id))

    def geometry(self, window_id):
        return self._geometry


def test_maximize_requests_both_states_and_verifies_workarea():
    backend = FakeBackend(workarea=Rect(66, 32, 3774, 2128))
    actual = maximize_window(backend, GAZEBO, tolerance=12, sleep=lambda _: None)
    assert actual == Rect(66, 32, 3774, 2128)
    assert backend.requests == [('maximize', GAZEBO.window_id)]


def test_maximize_waits_for_the_window_manager_to_apply_state():
    delays = []
    backend = FakeBackend(workarea=WORKAREA)
    maximize_window(backend, GAZEBO, tolerance=12, sleep=delays.append)
    assert delays == [0.5]


def test_maximize_fails_when_outer_geometry_exceeds_tolerance():
    backend = FakeBackend(
        workarea=WORKAREA,
        geometry=Rect(66, 32, 3700, 2128),
    )
    with pytest.raises(RuntimeError, match='geometry mismatch'):
        maximize_window(backend, GAZEBO, tolerance=12, sleep=lambda _: None)


class FakeX11:
    ATOMS = {
        '_NET_WM_STATE': 0x902,
        '_NET_WM_STATE_MAXIMIZED_VERT': 0x903,
        '_NET_WM_STATE_MAXIMIZED_HORZ': 0x904,
    }

    def __init__(self):
        self.sent = None
        self.flush_count = 0

    def XInternAtom(self, display, name, only_if_exists):
        assert display == 0x1234
        assert only_if_exists is False
        return self.ATOMS[name.decode()]

    def XSendEvent(self, display, root, propagate, mask, event_pointer):
        event = MODULE.ctypes.cast(
            event_pointer, MODULE.ctypes.POINTER(MODULE.XEvent)
        ).contents.xclient
        self.sent = {
            'display': display,
            'root': root,
            'propagate': propagate,
            'mask': mask,
            'type': event.type,
            'window': event.window,
            'message_type': event.message_type,
            'format': event.format,
            'data': tuple(event.data.l),
        }
        return 1

    def XFlush(self, display):
        assert display == 0x1234
        self.flush_count += 1
        return 0


def backend_with_fake_x11():
    backend = object.__new__(MODULE.X11EwmhBackend)
    backend.x11 = FakeX11()
    backend.display = 0x1234
    backend.root = 0x5678
    return backend


def test_backend_maximize_sends_add_action_with_both_state_atoms():
    backend = backend_with_fake_x11()

    backend.maximize(0xABC)

    assert backend.x11.sent['message_type'] == FakeX11.ATOMS['_NET_WM_STATE']
    assert backend.x11.sent['data'] == (
        1,
        FakeX11.ATOMS['_NET_WM_STATE_MAXIMIZED_VERT'],
        FakeX11.ATOMS['_NET_WM_STATE_MAXIMIZED_HORZ'],
        1,
        0,
    )
    assert backend.x11.flush_count == 1


class WindowBackend:
    def __init__(self, batches):
        self.batches = list(batches)

    def windows(self):
        if len(self.batches) > 1:
            return self.batches.pop(0)
        return self.batches[0]


def test_wait_for_unique_window_polls_until_the_match_appears():
    backend = WindowBackend([[], [RVIZ, GAZEBO]])
    window = MODULE.wait_for_unique_window(
        backend, 'gazebo', 1, 0, monotonic=lambda: 0, sleep=lambda _: None
    )
    assert window == GAZEBO


def test_wait_for_unique_window_rejects_multiple_matches_immediately():
    backend = WindowBackend([[GAZEBO, GAZEBO_COPY]])
    with pytest.raises(RuntimeError, match='multiple gazebo windows'):
        MODULE.wait_for_unique_window(
            backend, 'gazebo', 30, 0, monotonic=lambda: 0, sleep=lambda _: None
        )


def test_wait_for_unique_window_timeout_reports_observed_windows():
    backend = WindowBackend([[RVIZ]])
    ticks = iter((0.0, 0.5, 1.1))
    with pytest.raises(RuntimeError, match='missing gazebo'):
        MODULE.wait_for_unique_window(
            backend,
            'gazebo',
            1,
            0,
            monotonic=lambda: next(ticks),
            sleep=lambda _: None,
        )
