import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'video_extract_frame.py'
)
SPEC = importlib.util.spec_from_file_location('video_extract_frame', SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_last_frame_starts_decode_near_end():
    request = MODULE.select_frame_request(duration=1.2, at='last')
    assert request.seek_start == pytest.approx(0.2)
    assert request.keep_last_decoded_frame is True


def test_last_frame_of_short_video_starts_at_zero():
    request = MODULE.select_frame_request(duration=0.5, at='last')
    assert request.seek_start == pytest.approx(0.0)
    assert request.keep_last_decoded_frame is True


def test_numeric_timestamp_seeks_to_exact_time():
    request = MODULE.select_frame_request(duration=2.0, at='1.5')
    assert request.seek_start == pytest.approx(1.5)
    assert request.keep_last_decoded_frame is False


def test_rejects_timestamp_beyond_duration():
    with pytest.raises(ValueError, match='outside video duration'):
        MODULE.select_frame_request(duration=1.0, at='1.1')


def test_rejects_negative_timestamp():
    with pytest.raises(ValueError, match='outside video duration'):
        MODULE.select_frame_request(duration=1.0, at='-0.5')


def test_rejects_unparseable_timestamp():
    with pytest.raises(ValueError, match='not a timestamp'):
        MODULE.select_frame_request(duration=1.0, at='middle')


def make_test_video(path, duration=2.0):
    """Render a deterministic 2-second testsrc2 MKV fixture."""
    subprocess.run(
        [
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i',
            f'testsrc2=size=320x240:rate=25:duration={duration}',
            '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def video_path(tmp_path):
    return make_test_video(tmp_path / 'run.mkv')


def run_cli(*arguments):
    result = subprocess.run(
        ['python3', str(SCRIPT_PATH), *arguments],
        capture_output=True, text=True,
    )
    return result


def test_help_is_available():
    result = run_cli('--help')
    assert result.returncode == 0
    assert '--at' in result.stdout


def test_extract_last_frame(video_path, tmp_path, capsys):
    output = tmp_path / 'last.png'
    exit_code = MODULE.main(
        ['--input', str(video_path), '--at', 'last', '--output', str(output)]
    )
    assert exit_code == 0
    assert output.exists()
    assert output.stat().st_size > 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['requested_time'] == 'last'
    assert payload['source_duration_sec'] == pytest.approx(2.0, abs=0.2)
    assert payload['selected_time_sec'] <= payload['source_duration_sec']
    assert payload['selected_time_sec'] > 1.0
    assert payload['output_width'] == 320
    assert payload['output_height'] == 240


def test_extract_numeric_timestamp(video_path, tmp_path, capsys):
    output = tmp_path / 'at_1.png'
    exit_code = MODULE.main(
        ['--input', str(video_path), '--at', '1.0', '--output', str(output)]
    )
    assert exit_code == 0
    assert output.exists()
    assert output.stat().st_size > 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['requested_time'] == pytest.approx(1.0)
    assert payload['selected_time_sec'] == pytest.approx(1.0)
    assert payload['source_duration_sec'] == pytest.approx(2.0, abs=0.2)
    assert payload['output_width'] == 320
    assert payload['output_height'] == 240


def test_refuses_to_overwrite_existing_output(video_path, tmp_path, capsys):
    output = tmp_path / 'exists.png'
    output.write_bytes(b'keep me')
    exit_code = MODULE.main(
        ['--input', str(video_path), '--at', 'last', '--output', str(output)]
    )
    assert exit_code == 1
    assert output.read_bytes() == b'keep me'
    assert 'overwrite' in capsys.readouterr().err


def test_rejects_unreadable_input(tmp_path, capsys):
    missing = tmp_path / 'missing.mkv'
    output = tmp_path / 'frame.png'
    exit_code = MODULE.main(
        ['--input', str(missing), '--at', 'last', '--output', str(output)]
    )
    assert exit_code == 1
    assert not output.exists()
    assert capsys.readouterr().err


def test_rejects_timestamp_beyond_video_duration(video_path, tmp_path, capsys):
    output = tmp_path / 'frame.png'
    exit_code = MODULE.main(
        ['--input', str(video_path), '--at', '5.0', '--output', str(output)]
    )
    assert exit_code == 1
    assert not output.exists()
    assert 'outside video duration' in capsys.readouterr().err
