import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'video_sample_frames.py'
)
SPEC = importlib.util.spec_from_file_location('video_sample_frames', SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_selects_first_frame_at_or_after_each_target():
    pts = [0.00, 0.04, 0.09, 0.13, 0.20]
    selected = MODULE.select_frames(pts, start=0.0, end=0.2, interval=0.1)
    assert selected == [(0.0, 0.0), (0.1, 0.13), (0.2, 0.2)]


def test_limits_sampling_to_requested_interval():
    with pytest.raises(ValueError, match='end must be greater than start'):
        MODULE.sample_targets(start=2.0, end=1.0, interval=0.5)


def test_rejects_non_positive_interval():
    with pytest.raises(ValueError, match='interval must be positive'):
        MODULE.sample_targets(start=0.0, end=1.0, interval=0.0)
    with pytest.raises(ValueError, match='interval must be positive'):
        MODULE.sample_targets(start=0.0, end=1.0, interval=-0.5)


def test_rejects_negative_start():
    with pytest.raises(ValueError, match='start must be non-negative'):
        MODULE.sample_targets(start=-1.0, end=1.0, interval=0.5)


def test_sample_targets_generates_even_grid():
    assert MODULE.sample_targets(start=0.0, end=1.0, interval=0.25) == [
        0.0, 0.25, 0.5, 0.75, 1.0,
    ]


def test_rejects_target_beyond_last_frame():
    with pytest.raises(ValueError, match='no frame at or after target'):
        MODULE.select_frames([0.0, 0.5], start=0.0, end=1.0, interval=0.5)


def test_output_name_format():
    assert (
        MODULE.output_name(0, 0.0, 0.0)
        == '000_t000.000_pts000.000.jpg'
    )
    assert (
        MODULE.output_name(12, 1.5, 1.667)
        == '012_t001.500_pts001.667.jpg'
    )


def make_cfr_video(path, duration=2.0, rate=25):
    """Render a deterministic constant-frame-rate testsrc2 MKV fixture."""
    subprocess.run(
        [
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i',
            f'testsrc2=size=320x240:rate={rate}:duration={duration}',
            '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            str(path),
        ],
        check=True,
    )
    return path


def make_vfr_video(path):
    """Render a variable-frame-rate MKV: 1s at 30fps then 1s at 6fps."""
    subprocess.run(
        [
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=1',
            '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=6:duration=1',
            '-filter_complex', '[0:v][1:v]concat=n=2:v=1',
            '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def cfr_video(tmp_path):
    return make_cfr_video(tmp_path / 'run.mkv')


@pytest.fixture
def vfr_video(tmp_path):
    return make_vfr_video(tmp_path / 'vfr.mkv')


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
    assert '--interval' in result.stdout
    assert '--max-width' in result.stdout


def test_samples_cfr_video(cfr_video, tmp_path):
    output_dir = tmp_path / 'samples'
    exit_code = MODULE.main(
        [
            '--input', str(cfr_video),
            '--start', '0.0', '--end', '1.0', '--interval', '0.5',
            '--max-width', '160', '--output-dir', str(output_dir),
        ]
    )
    assert exit_code == 0
    names = sorted(path.name for path in output_dir.glob('*.jpg'))
    assert names == [
        '000_t000.000_pts000.000.jpg',
        '001_t000.500_pts000.520.jpg',
        '002_t001.000_pts001.000.jpg',
    ]
    for name in names:
        assert probe_image_size(output_dir / name) == (160, 120)
    index = json.loads((output_dir / 'frames.json').read_text())
    assert index['start'] == pytest.approx(0.0)
    assert index['end'] == pytest.approx(1.0)
    assert index['interval'] == pytest.approx(0.5)
    frames = index['frames']
    assert [frame['target_time_sec'] for frame in frames] == [0.0, 0.5, 1.0]
    assert [frame['pts_sec'] for frame in frames] == [0.0, 0.52, 1.0]
    assert [frame['source_frame_index'] for frame in frames] == [0, 13, 25]
    assert [frame['filename'] for frame in frames] == names


def test_does_not_upscale_when_below_max_width(cfr_video, tmp_path):
    output_dir = tmp_path / 'samples'
    exit_code = MODULE.main(
        [
            '--input', str(cfr_video),
            '--start', '0.0', '--end', '0.5', '--interval', '0.5',
            '--max-width', '640', '--output-dir', str(output_dir),
        ]
    )
    assert exit_code == 0
    assert probe_image_size(
        output_dir / '000_t000.000_pts000.000.jpg'
    ) == (320, 240)


def test_samples_vfr_video_by_pts(vfr_video, tmp_path):
    output_dir = tmp_path / 'samples'
    exit_code = MODULE.main(
        [
            '--input', str(vfr_video),
            '--start', '0.9', '--end', '1.2', '--interval', '0.1',
            '--max-width', '160', '--output-dir', str(output_dir),
        ]
    )
    assert exit_code == 0
    names = sorted(path.name for path in output_dir.glob('*.jpg'))
    assert len(names) == 4
    index = json.loads((output_dir / 'frames.json').read_text())
    frames = index['frames']
    assert [frame['target_time_sec'] for frame in frames] == [
        0.9, 1.0, 1.1, 1.2,
    ]
    # First frame at or after each target, by real presentation time:
    # the 6fps tail has no frame at 1.1 or 1.2, so they clamp forward
    # to the frames at ~1.167s and ~1.333s.
    assert [frame['pts_sec'] for frame in frames] == pytest.approx(
        [0.9, 1.0, 1.167, 1.333], abs=0.002
    )
    assert [frame['source_frame_index'] for frame in frames] == [
        27, 30, 31, 32,
    ]


def test_refuses_output_dir_with_existing_evidence(cfr_video, tmp_path,
                                                   capsys):
    output_dir = tmp_path / 'samples'
    output_dir.mkdir()
    (output_dir / 'frames.json').write_text('{}')
    exit_code = MODULE.main(
        [
            '--input', str(cfr_video),
            '--start', '0.0', '--end', '1.0', '--interval', '0.5',
            '--max-width', '160', '--output-dir', str(output_dir),
        ]
    )
    assert exit_code == 1
    assert 'evidence' in capsys.readouterr().err
    assert not list(output_dir.glob('*.jpg'))


def test_refuses_output_dir_with_existing_frames(cfr_video, tmp_path,
                                                 capsys):
    output_dir = tmp_path / 'samples'
    output_dir.mkdir()
    (output_dir / '000_t000.000_pts000.000.jpg').write_bytes(b'keep me')
    exit_code = MODULE.main(
        [
            '--input', str(cfr_video),
            '--start', '0.0', '--end', '1.0', '--interval', '0.5',
            '--max-width', '160', '--output-dir', str(output_dir),
        ]
    )
    assert exit_code == 1
    assert 'evidence' in capsys.readouterr().err
    assert (
        output_dir / '000_t000.000_pts000.000.jpg'
    ).read_bytes() == b'keep me'


def test_cli_rejects_end_before_start(cfr_video, tmp_path):
    result = run_cli(
        '--input', str(cfr_video),
        '--start', '2.0', '--end', '1.0', '--interval', '0.5',
        '--max-width', '160', '--output-dir', str(tmp_path / 'samples'),
    )
    assert result.returncode == 1
    assert 'end must be greater than start' in result.stderr
