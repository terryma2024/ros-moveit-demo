#!/usr/bin/env python3
"""Extract one reproducible evidence frame from a finished recording.

The input must be readable by ffprobe. ``--at last`` decodes the final
one-second window and relies on the image muxer's ``-update 1`` behavior so
the destination ends up holding the last decoded frame. A numeric ``--at``
seeks to the exact timestamp and emits exactly one frame. The frame is
written to a temporary PNG and atomically renamed only after ffmpeg succeeds
and the image is non-empty. Existing evidence files are never overwritten.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import namedtuple
from pathlib import Path


LAST_FRAME_WINDOW_SEC = 1.0
COMMAND_TIMEOUT_SEC = 60.0

FrameRequest = namedtuple(
    'FrameRequest',
    ['requested', 'seek_start', 'selected_time', 'keep_last_decoded_frame'],
)


def probe_video(input_path, timeout=COMMAND_TIMEOUT_SEC):
    """Read duration and resolution with ffprobe; raise when unreadable."""
    try:
        text = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-show_entries', 'format=duration',
                '-of', 'json', str(input_path),
            ],
            check=True, capture_output=True, text=True, timeout=timeout,
        ).stdout
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or '').strip().splitlines()
        reason = detail[-1] if detail else str(error)
        raise RuntimeError(f'input is not readable by ffprobe: {reason}')
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f'input is not readable by ffprobe: {error}')
    payload = json.loads(text)
    streams = payload.get('streams') or []
    if not streams:
        raise RuntimeError(f'input has no video stream: {input_path}')
    stream = streams[0]
    return {
        'duration_sec': float(payload['format']['duration']),
        'width': int(stream['width']),
        'height': int(stream['height']),
    }


def select_frame_request(duration, at):
    """Resolve ``--at`` into a seek position and extraction strategy.

    ``last`` starts decoding one second before the end (clamped to zero) so
    the image muxer's update behavior keeps the final decoded frame. A
    numeric timestamp must lie inside the video duration.
    """
    if at == 'last':
        return FrameRequest(
            requested='last',
            seek_start=max(0.0, duration - LAST_FRAME_WINDOW_SEC),
            selected_time=duration,
            keep_last_decoded_frame=True,
        )
    try:
        timestamp = float(at)
    except ValueError:
        raise ValueError(f'not a timestamp or "last": {at!r}')
    if timestamp < 0.0 or timestamp > duration:
        raise ValueError(
            f'timestamp {timestamp} is outside video duration {duration}'
        )
    return FrameRequest(
        requested=timestamp,
        seek_start=timestamp,
        selected_time=timestamp,
        keep_last_decoded_frame=False,
    )


def build_ffmpeg_command(input_path, request, output):
    """Build the extraction command; never overwrite blindly (no -y)."""
    command = [
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-ss', f'{request.seek_start:.6f}',
        '-i', str(input_path),
        '-an', '-c:v', 'png', '-f', 'image2',
    ]
    if request.keep_last_decoded_frame:
        # Decode the whole tail window; -update 1 rewrites the single image
        # for every decoded frame, leaving the last one on disk.
        command += ['-update', '1']
    else:
        command += ['-frames:v', '1']
    command.append(str(output))
    return command


def extract_frame(input_path, at, output, prober=probe_video,
                  timeout=COMMAND_TIMEOUT_SEC):
    """Extract one frame and return its JSON metadata payload."""
    input_path = Path(input_path)
    output = Path(output)
    if output.exists():
        raise RuntimeError(f'refusing to overwrite existing output: {output}')
    source = prober(input_path)
    request = select_frame_request(source['duration_sec'], at)
    temporary = output.with_name(output.name + '.tmp')
    if temporary.exists():
        raise RuntimeError(f'refusing to overwrite existing output: {temporary}')
    command = build_ffmpeg_command(input_path, request, temporary)
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or '').strip().splitlines()
        reason = detail[-1] if detail else str(error)
        raise RuntimeError(f'ffmpeg frame extraction failed: {reason}')
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f'ffmpeg frame extraction failed: {error}')
    if not temporary.exists() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f'ffmpeg produced no decodable frame near {request.selected_time}'
        )
    os.replace(temporary, output)
    return {
        'input': str(input_path),
        'output': str(output),
        'requested_time': request.requested,
        'selected_time_sec': request.selected_time,
        'source_duration_sec': source['duration_sec'],
        'output_width': source['width'],
        'output_height': source['height'],
    }


def _build_parser():
    parser = argparse.ArgumentParser(
        description='Extract one evidence frame (PNG) from a recording.',
    )
    parser.add_argument('--input', required=True,
                        help='video readable by ffprobe')
    parser.add_argument('--at', required=True, metavar='last|SECONDS',
                        help='"last" decoded frame or an exact timestamp')
    parser.add_argument('--output', required=True,
                        help='PNG output path; must not exist yet')
    return parser


def main(argv=None):
    arguments = _build_parser().parse_args(argv)
    try:
        payload = extract_frame(arguments.input, arguments.at, arguments.output)
    except (RuntimeError, OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
