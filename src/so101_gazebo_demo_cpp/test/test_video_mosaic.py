import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'video_mosaic.py'
)
SPEC = importlib.util.spec_from_file_location('video_mosaic', SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_grid_assigns_all_frames_without_empty_middle_cells():
    layout = MODULE.calculate_grid(frame_count=10, columns=4)
    assert layout.rows == 3
    assert layout.cells == 12


def test_grid_exact_fit_has_no_padding_cells():
    layout = MODULE.calculate_grid(frame_count=8, columns=4)
    assert layout.rows == 2
    assert layout.cells == 8


def test_grid_rejects_non_positive_columns():
    with pytest.raises(ValueError, match='columns must be positive'):
        MODULE.calculate_grid(frame_count=10, columns=0)


def test_grid_rejects_zero_frames():
    with pytest.raises(ValueError, match='frame_count must be positive'):
        MODULE.calculate_grid(frame_count=0, columns=4)


def test_scale_caps_final_mosaic_width():
    scale = MODULE.mosaic_scale(
        frame_width=960, columns=4, padding=4, max_width=2400,
    )
    assert scale.scaled_frame_width < 600


def test_scale_never_upscales():
    scale = MODULE.mosaic_scale(
        frame_width=320, columns=2, padding=4, max_width=1000,
    )
    assert scale.scaled_frame_width == 320


def test_scale_rejects_too_small_max_width():
    with pytest.raises(ValueError, match='max_width'):
        MODULE.mosaic_scale(
            frame_width=960, columns=4, padding=4, max_width=20,
        )


def make_color_frame(path, color, size='320x240'):
    """Render one solid-color JPEG frame like a Task 6 sample."""
    subprocess.run(
        [
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', f'color=c={color}:size={size}',
            '-frames:v', '1', '-q:v', '2', str(path),
        ],
        check=True,
    )
    return path


COLORS = [
    'red', 'green', 'blue', 'yellow', 'magenta',
    'cyan', 'white', 'gray', 'orange', 'purple',
]


@pytest.fixture
def ten_frames(tmp_path):
    frames_dir = tmp_path / 'frames'
    frames_dir.mkdir()
    entries = []
    for index, color in enumerate(COLORS):
        name = f'{index:03d}_t{index:07.3f}_pts{index:07.3f}.jpg'
        make_color_frame(frames_dir / name, color)
        entries.append({
            'index': index,
            'filename': name,
            'target_time_sec': float(index),
            'pts_sec': float(index),
            'source_frame_index': index * 25,
        })
    (frames_dir / 'frames.json').write_text(
        json.dumps({'frames': entries}, indent=2)
    )
    return frames_dir


def run_cli(*arguments):
    return subprocess.run(
        ['python3', str(SCRIPT_PATH), *arguments],
        capture_output=True, text=True,
    )


def probe_image_size(path):
    payload = json.loads(
        subprocess.run(
            [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height', '-of', 'json',
                str(path),
            ],
            check=True, capture_output=True, text=True,
        ).stdout
    )
    stream = payload['streams'][0]
    return stream['width'], stream['height']


def test_help_is_available():
    result = run_cli('--help')
    assert result.returncode == 0
    assert '--frames' in result.stdout
    assert '--columns' in result.stdout
    assert '--output' in result.stdout
    assert '--max-width' in result.stdout


def test_frame_order_prefers_frames_json(tmp_path):
    frames_dir = tmp_path / 'frames'
    frames_dir.mkdir()
    for name in ('aaa.jpg', 'bbb.jpg', 'ccc.jpg'):
        (frames_dir / name).write_bytes(b'x')
    (frames_dir / 'frames.json').write_text(
        json.dumps({'frames': [
            {'filename': 'ccc.jpg'},
            {'filename': 'aaa.jpg'},
            {'filename': 'bbb.jpg'},
        ]})
    )
    order = MODULE.resolve_frame_order(frames_dir)
    assert [path.name for path in order] == ['ccc.jpg', 'aaa.jpg', 'bbb.jpg']


def test_frame_order_falls_back_to_sorted_names(tmp_path):
    frames_dir = tmp_path / 'frames'
    frames_dir.mkdir()
    for name in ('002.jpg', '000.jpg', '001.jpg'):
        (frames_dir / name).write_bytes(b'x')
    order = MODULE.resolve_frame_order(frames_dir)
    assert [path.name for path in order] == ['000.jpg', '001.jpg', '002.jpg']


def test_frame_order_rejects_empty_dir(tmp_path):
    frames_dir = tmp_path / 'frames'
    frames_dir.mkdir()
    with pytest.raises(RuntimeError, match='no frames'):
        MODULE.resolve_frame_order(frames_dir)


def test_frame_order_rejects_missing_json_entry(tmp_path):
    frames_dir = tmp_path / 'frames'
    frames_dir.mkdir()
    (frames_dir / 'frames.json').write_text(
        json.dumps({'frames': [{'filename': 'gone.jpg'}]})
    )
    with pytest.raises(RuntimeError, match='missing'):
        MODULE.resolve_frame_order(frames_dir)


def test_builds_ten_frame_four_column_mosaic(ten_frames, tmp_path):
    output = tmp_path / 'mosaic.jpg'
    before = {
        path.name: path.read_bytes() for path in ten_frames.glob('*.jpg')
    }
    exit_code = MODULE.main(
        [
            '--frames', str(ten_frames),
            '--columns', '4',
            '--output', str(output),
            '--max-width', '700',
        ]
    )
    assert exit_code == 0
    width, height = probe_image_size(output)
    assert width <= 700
    # Scaled frame width is (700 - 2*4 margin - 3*4 padding) // 4 = 170,
    # so each 320x240 frame shrinks to 170x128 and three rows plus the
    # padding and margin give an exact, verifiable mosaic geometry.
    assert width == 4 * 170 + 3 * 4 + 2 * 4
    assert height == 3 * 128 + 2 * 4 + 2 * 4
    # Source frames are evidence and must stay untouched.
    after = {
        path.name: path.read_bytes() for path in ten_frames.glob('*.jpg')
    }
    assert after == before


def test_refuses_zero_frames(tmp_path):
    frames_dir = tmp_path / 'frames'
    frames_dir.mkdir()
    result = run_cli(
        '--frames', str(frames_dir),
        '--columns', '4',
        '--output', str(tmp_path / 'mosaic.jpg'),
        '--max-width', '700',
    )
    assert result.returncode == 1
    assert 'no frames' in result.stderr
    assert not (tmp_path / 'mosaic.jpg').exists()


def test_refuses_to_overwrite_existing_output(ten_frames, tmp_path):
    output = tmp_path / 'mosaic.jpg'
    output.write_bytes(b'keep me')
    result = run_cli(
        '--frames', str(ten_frames),
        '--columns', '4',
        '--output', str(output),
        '--max-width', '700',
    )
    assert result.returncode == 1
    assert 'refusing' in result.stderr
    assert output.read_bytes() == b'keep me'
