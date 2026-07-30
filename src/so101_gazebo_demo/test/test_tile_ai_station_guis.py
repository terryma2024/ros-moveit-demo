import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'tile_ai_station_guis.py'
)
SPEC = importlib.util.spec_from_file_location('tile_ai_station_guis', SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_classifies_real_ai_station_window_classes():
    assert MODULE.classify_window('moveit.rviz* - RViz', ('rviz2', 'rviz2')) == 'rviz'
    assert MODULE.classify_window('Gazebo Sim', ('gz-sim-gui', 'Gazebo GUI')) == 'gazebo'
    assert MODULE.classify_window('/data/work', ('ghostty', 'com.mitchellh.ghostty')) is None


def test_splits_actual_workarea_without_losing_pixels():
    workarea = MODULE.Rect(66, 32, 3774, 2128)
    left, right = MODULE.split_workarea(workarea)
    assert left == MODULE.Rect(66, 32, 1887, 2128)
    assert right == MODULE.Rect(1953, 32, 1887, 2128)
    assert left.width + right.width == workarea.width
    assert right.x == left.x + left.width


def test_assigns_odd_pixel_to_right_window():
    left, right = MODULE.split_workarea(MODULE.Rect(10, 20, 101, 80))
    assert left == MODULE.Rect(10, 20, 50, 80)
    assert right == MODULE.Rect(60, 20, 51, 80)


def test_parses_current_desktop_workarea_and_client_ids():
    assert MODULE.parse_current_desktop(
        '_NET_CURRENT_DESKTOP(CARDINAL) = 1'
    ) == 1
    areas = MODULE.parse_workareas(
        '_NET_WORKAREA(CARDINAL) = 66, 32, 3774, 2128, 0, 0, 1920, 1080'
    )
    assert areas == [
        MODULE.Rect(66, 32, 3774, 2128),
        MODULE.Rect(0, 0, 1920, 1080),
    ]
    assert MODULE.parse_client_ids(
        '_NET_CLIENT_LIST(WINDOW): window id # 0x3a00106, 0x3e0000e'
    ) == [0x3A00106, 0x3E0000E]


@pytest.mark.parametrize('text', ['', 'no cardinal value', '= -1'])
def test_rejects_invalid_current_desktop(text):
    with pytest.raises(ValueError):
        MODULE.parse_current_desktop(text)


def test_parses_window_title_class_and_geometry():
    properties = '''
WM_CLASS(STRING) = "gz-sim-gui", "Gazebo GUI"
_NET_WM_NAME(UTF8_STRING) = "Gazebo Sim"
WM_NAME(STRING) = "Gazebo Sim"
'''
    window = MODULE.parse_window_properties(0x3E0000E, properties)
    assert window == MODULE.WindowInfo(
        0x3E0000E,
        'Gazebo Sim',
        ('gz-sim-gui', 'Gazebo GUI'),
    )

    client_geometry = MODULE.parse_xwininfo_geometry('''
  Absolute upper-left X:  1953
  Absolute upper-left Y:  69
  Width: 1885
  Height: 2091
''')
    extents = MODULE.parse_frame_extents(
        '_NET_FRAME_EXTENTS(CARDINAL) = 0, 2, 37, 0'
    )
    assert MODULE.outer_geometry(client_geometry, extents) == MODULE.Rect(
        1953, 32, 1887, 2128
    )


def test_builds_full_moveresize_request():
    assert MODULE.moveresize_payload(MODULE.Rect(66, 32, 1887, 2128)) == (
        0x1F00,
        66,
        32,
        1887,
        2128,
    )


def test_geometry_comparison_uses_decoration_tolerance():
    target = MODULE.Rect(66, 32, 1887, 2128)
    assert MODULE.rect_is_close(MODULE.Rect(70, 36, 1879, 2120), target, 12)
    assert not MODULE.rect_is_close(
        MODULE.Rect(100, 36, 1879, 2120), target, 12
    )


def test_runtime_preflight_reports_missing_system_prerequisites():
    commands = {'xprop': '/usr/bin/xprop', 'xwininfo': None}

    with pytest.raises(
        RuntimeError,
        match=r'missing X11 prerequisites: libX11, xwininfo.*x11-utils',
    ):
        MODULE.validate_runtime_prerequisites(
            which=commands.get,
            find_library=lambda _: None,
        )

class FakeX11:
    ATOMS = {
        '_TEST_MESSAGE': 0x901,
        '_NET_WM_STATE': 0x902,
        '_NET_WM_STATE_MAXIMIZED_VERT': 0x903,
        '_NET_WM_STATE_MAXIMIZED_HORZ': 0x904,
        '_NET_MOVERESIZE_WINDOW': 0x905,
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


def test_send_builds_complete_xclientmessage_for_root_window():
    backend = backend_with_fake_x11()

    backend._send(0xABC, '_TEST_MESSAGE', (11, 22, 33, 44, 55))

    assert backend.x11.sent == {
        'display': 0x1234,
        'root': 0x5678,
        'propagate': False,
        'mask': (
            MODULE.X11EwmhBackend.SUBSTRUCTURE_NOTIFY_MASK
            | MODULE.X11EwmhBackend.SUBSTRUCTURE_REDIRECT_MASK
        ),
        'type': MODULE.X11EwmhBackend.CLIENT_MESSAGE,
        'window': 0xABC,
        'message_type': FakeX11.ATOMS['_TEST_MESSAGE'],
        'format': 32,
        'data': (11, 22, 33, 44, 55),
    }
    assert backend.x11.flush_count == 1


def test_clear_maximize_sends_remove_action_and_both_state_atoms():
    backend = backend_with_fake_x11()

    backend.clear_maximize(0xABC)

    assert backend.x11.sent['message_type'] == FakeX11.ATOMS['_NET_WM_STATE']
    assert backend.x11.sent['data'] == (
        0,
        FakeX11.ATOMS['_NET_WM_STATE_MAXIMIZED_VERT'],
        FakeX11.ATOMS['_NET_WM_STATE_MAXIMIZED_HORZ'],
        1,
        0,
    )


def test_move_resize_sends_full_ewmh_geometry_payload():
    backend = backend_with_fake_x11()

    backend.move_resize(0xABC, MODULE.Rect(66, 32, 1887, 2128))

    assert (
        backend.x11.sent['message_type']
        == FakeX11.ATOMS['_NET_MOVERESIZE_WINDOW']
    )
    assert backend.x11.sent['data'] == (0x1F00, 66, 32, 1887, 2128)


class FakeBackend:
    def __init__(self, batches):
        self.batches = list(batches)
        self.requests = []
        self.targets = {}

    def workarea(self):
        return MODULE.Rect(66, 32, 3774, 2128)

    def windows(self):
        if len(self.batches) > 1:
            return self.batches.pop(0)
        return self.batches[0]

    def clear_maximize(self, window_id):
        self.requests.append(('clear', window_id))

    def move_resize(self, window_id, rect):
        self.requests.append(('move', window_id, rect))
        self.targets[window_id] = rect

    def geometry(self, window_id):
        return self.targets[window_id]


RVIZ = MODULE.WindowInfo(0x31, 'MoveIt - RViz', ('rviz2', 'rviz2'))
GAZEBO = MODULE.WindowInfo(0x32, 'Gazebo Sim', ('gz-sim-gui', 'Gazebo GUI'))


def test_waits_then_tiles_and_verifies_both_windows():
    backend = FakeBackend([[], [RVIZ, GAZEBO]])
    result = MODULE.tile_windows(
        backend,
        timeout_sec=1,
        poll_sec=0,
        geometry_tolerance=12,
        monotonic=lambda: 0,
        sleep=lambda _: None,
    )
    assert result['rviz'] == MODULE.Rect(66, 32, 1887, 2128)
    assert result['gazebo'] == MODULE.Rect(1953, 32, 1887, 2128)
    assert backend.requests == [
        ('clear', 0x31),
        ('clear', 0x32),
        ('move', 0x31, MODULE.Rect(66, 32, 1887, 2128)),
        ('move', 0x32, MODULE.Rect(1953, 32, 1887, 2128)),
    ]


def test_timeout_reports_observed_window_evidence():
    backend = FakeBackend([[RVIZ]])
    ticks = iter((0.0, 0.5, 1.1))
    with pytest.raises(RuntimeError, match='missing gazebo'):
        MODULE.tile_windows(
            backend,
            timeout_sec=1,
            poll_sec=0,
            geometry_tolerance=12,
            monotonic=lambda: next(ticks),
            sleep=lambda _: None,
        )
    assert backend.requests == []


def test_repeated_tiling_is_idempotent():
    backend = FakeBackend([[RVIZ, GAZEBO]])
    first = MODULE.tile_windows(backend, 1, 0, 12)
    second = MODULE.tile_windows(backend, 1, 0, 12)
    assert first == second
    assert backend.requests == [
        ('clear', 0x31),
        ('clear', 0x32),
        ('move', 0x31, MODULE.Rect(66, 32, 1887, 2128)),
        ('move', 0x32, MODULE.Rect(1953, 32, 1887, 2128)),
        ('clear', 0x31),
        ('clear', 0x32),
        ('move', 0x31, MODULE.Rect(66, 32, 1887, 2128)),
        ('move', 0x32, MODULE.Rect(1953, 32, 1887, 2128)),
    ]


def test_cli_parses_selected_workarea_maximize_mode():
    args = MODULE.parse_args(['--maximize', 'gazebo'])

    assert args.maximize == 'gazebo'


def test_maximize_resizes_only_selected_window_to_exact_workarea():
    backend = FakeBackend([[RVIZ, GAZEBO]])

    result = MODULE.maximize_window(
        backend,
        'gazebo',
        timeout_sec=1,
        poll_sec=0,
        geometry_tolerance=12,
    )

    assert result == MODULE.Rect(66, 32, 3774, 2128)
    assert backend.requests == [
        ('move', 0x32, MODULE.Rect(66, 32, 3774, 2128)),
    ]


def test_repeated_selected_workarea_maximize_is_idempotent():
    backend = FakeBackend([[RVIZ, GAZEBO]])

    first = MODULE.maximize_window(backend, 'rviz', 1, 0, 12)
    second = MODULE.maximize_window(backend, 'rviz', 1, 0, 12)

    assert first == second == MODULE.Rect(66, 32, 3774, 2128)
    assert backend.requests == [
        ('move', 0x31, MODULE.Rect(66, 32, 3774, 2128)),
        ('move', 0x31, MODULE.Rect(66, 32, 3774, 2128)),
    ]


def test_selected_maximize_timeout_reports_missing_selected_window():
    backend = FakeBackend([[RVIZ]])
    ticks = iter((0.0, 0.5, 1.1))

    with pytest.raises(RuntimeError, match='missing gazebo'):
        MODULE.maximize_window(
            backend,
            'gazebo',
            timeout_sec=1,
            poll_sec=0,
            geometry_tolerance=12,
            monotonic=lambda: next(ticks),
            sleep=lambda _: None,
        )

    assert backend.requests == []


def test_default_tile_restores_gazebo_after_workarea_maximize():
    backend = FakeBackend([[RVIZ, GAZEBO]])

    MODULE.maximize_window(backend, 'gazebo', 1, 0, 12)
    restored = MODULE.tile_windows(backend, 1, 0, 12)

    assert restored['gazebo'] == MODULE.Rect(1953, 32, 1887, 2128)
    assert backend.requests == [
        ('move', 0x32, MODULE.Rect(66, 32, 3774, 2128)),
        ('clear', 0x31),
        ('clear', 0x32),
        ('move', 0x31, MODULE.Rect(66, 32, 1887, 2128)),
        ('move', 0x32, MODULE.Rect(1953, 32, 1887, 2128)),
    ]
