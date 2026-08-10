#!/usr/bin/env python3
"""Sample evidence frames from a recording by presentation time.

The sampling window and density come entirely from CLI arguments; the tool
never picks an interval or range on its own. Frame timestamps are read from
``ffprobe -show_frames`` (``best_effort_timestamp_time``) and each target
time maps to the first frame presented at or after it, so variable-frame-
rate videos stay aligned. Every selected frame is extracted with ffmpeg,
scaled down only when wider than ``--max-width`` (aspect ratio preserved),
and labeled with both the requested target time and the actual PTS. Files
are named ``000_t000.000_pts000.000.jpg`` and a ``frames.json`` index
records target time, actual PTS and source frame index per frame. Output
directories that already contain evidence are refused.
"""

import argparse
import json
import os
import subprocess
import sys
from bisect import bisect_left
from pathlib import Path


COMMAND_TIMEOUT_SEC = 120.0
# Back off this far before a selected PTS so input seeking starts at a
# keyframe that decodes forward to the exact frame.
SEEK_PREROLL_SEC = 5.0
TIME_EPSILON_SEC = 1e-9


def sample_targets(start, end, interval):
    """Build the target-time grid; the caller owns range and density."""
    if end <= start:
        raise ValueError(f'end must be greater than start: {start} .. {end}')
    if interval <= 0.0:
        raise ValueError(f'interval must be positive: {interval}')
    if start < 0.0:
        raise ValueError(f'start must be non-negative: {start}')
    targets = []
    current = start
    while current <= end + TIME_EPSILON_SEC:
        targets.append(round(min(current, end), 9))
        current += interval
    return targets


def select_frames(pts, start, end, interval):
    """Map each target to the first frame presented at or after it.

    ``pts`` must be sorted presentation timestamps in seconds. Returns
    ``(target, actual_pts)`` pairs; selection is driven by real PTS, never
    by ``frame_index / nominal_fps``, so VFR sources stay aligned.
    """
    selected = []
    for target in sample_targets(start, end, interval):
        position = bisect_left(pts, target - TIME_EPSILON_SEC)
        if position >= len(pts):
            raise ValueError(
                f'no frame at or after target {target:.3f} '
                f'(last frame pts {pts[-1]:.3f})'
            )
        selected.append((target, pts[position]))
    return selected


def output_name(index, target, pts):
    """Format the ordered, self-describing evidence file name."""
    return f'{index:03d}_t{target:07.3f}_pts{pts:07.3f}.jpg'


def probe_frame_timestamps(input_path, timeout=COMMAND_TIMEOUT_SEC):
    """Read sorted presentation timestamps and geometry with ffprobe."""
    try:
        text = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_frames', '-of', 'json', str(input_path),
            ],
            check=True, capture_output=True, text=True, timeout=timeout,
        ).stdout
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or '').strip().splitlines()
        reason = detail[-1] if detail else str(error)
        raise RuntimeError(f'input is not readable by ffprobe: {reason}')
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f'input is not readable by ffprobe: {error}')
    frames = json.loads(text).get('frames') or []
    if not frames:
        raise RuntimeError(f'input has no video frames: {input_path}')
    try:
        pts = sorted(
            float(frame['best_effort_timestamp_time']) for frame in frames
        )
    except (KeyError, ValueError) as error:
        raise RuntimeError(
            f'input frames lack presentation timestamps: {error}'
        )
    return {
        'pts': pts,
        'width': int(frames[0]['width']),
        'height': int(frames[0]['height']),
    }


def build_ffmpeg_command(input_path, target, pts, source_width, max_width,
                         output):
    """Build the single-frame extraction command for one selected PTS.

    Input seeking with ``-copyts`` keeps original timestamps, and the
    ``select`` filter passes the first frame at or after the chosen PTS.
    Scaling only applies when the source is wider than ``max_width``.
    """
    filters = [f"select='gte(t,{pts:.6f})'"]
    if source_width > max_width:
        filters.append(f'scale={max_width}:-2')
    # Two stacked lines stay readable even on narrow downscaled frames.
    label_style = 'fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6'
    filters.append(
        f"drawtext=text='target {target:.3f}':x=8:y=8:{label_style}"
    )
    filters.append(
        f"drawtext=text='pts {pts:.3f}':x=8:y=30:{label_style}"
    )
    seek = max(0.0, pts - SEEK_PREROLL_SEC)
    return [
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-copyts', '-ss', f'{seek:.6f}',
        '-i', str(input_path),
        '-vf', ','.join(filters),
        '-an', '-frames:v', '1', '-q:v', '2', str(output),
    ]


def _check_output_dir(output_dir):
    """Refuse directories that already hold sampling evidence."""
    if not output_dir.exists():
        return
    if not output_dir.is_dir():
        raise RuntimeError(f'output path is not a directory: {output_dir}')
    leftovers = [output_dir / 'frames.json']
    leftovers += sorted(output_dir.glob('*.jpg'))
    leftovers += sorted(output_dir.glob('*.png'))
    existing = [path for path in leftovers if path.exists()]
    if existing:
        raise RuntimeError(
            'refusing to write into directory that already contains '
            f'evidence: {existing[0]}'
        )


def sample_frames(input_path, start, end, interval, max_width, output_dir,
                  prober=probe_frame_timestamps, timeout=COMMAND_TIMEOUT_SEC):
    """Extract labeled frames for each target and write ``frames.json``."""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    _check_output_dir(output_dir)
    source = prober(input_path)
    selected = select_frames(source['pts'], start, end, interval)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for position, (target, pts) in enumerate(selected):
        name = output_name(position, target, pts)
        # Keep the .jpg suffix so ffmpeg can guess the image2 muxer.
        temporary = output_dir / ('.tmp-' + name)
        command = build_ffmpeg_command(
            input_path, target, pts, source['width'], max_width, temporary,
        )
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
                f'ffmpeg produced no decodable frame near pts {pts:.3f}'
            )
        os.replace(temporary, output_dir / name)
        frames.append({
            'index': position,
            'filename': name,
            'target_time_sec': target,
            'pts_sec': pts,
            'source_frame_index': source['pts'].index(pts),
        })
    index = {
        'input': str(input_path),
        'start': start,
        'end': end,
        'interval': interval,
        'max_width': max_width,
        'source_width': source['width'],
        'source_height': source['height'],
        'frames': frames,
    }
    (output_dir / 'frames.json').write_text(json.dumps(index, indent=2))
    return index


def _build_parser():
    parser = argparse.ArgumentParser(
        description='Sample labeled evidence frames by presentation time.',
    )
    parser.add_argument('--input', required=True,
                        help='video readable by ffprobe')
    parser.add_argument('--start', required=True, type=float,
                        help='first target time in seconds')
    parser.add_argument('--end', required=True, type=float,
                        help='last target time in seconds')
    parser.add_argument('--interval', required=True, type=float,
                        help='seconds between target times')
    parser.add_argument('--max-width', required=True, type=int,
                        help='scale down only when wider than this')
    parser.add_argument('--output-dir', required=True,
                        help='fresh directory for frames and frames.json')
    return parser


def main(argv=None):
    arguments = _build_parser().parse_args(argv)
    try:
        index = sample_frames(
            arguments.input, arguments.start, arguments.end,
            arguments.interval, arguments.max_width, arguments.output_dir,
        )
    except (RuntimeError, OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(json.dumps(index, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
