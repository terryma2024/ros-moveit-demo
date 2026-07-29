#!/usr/bin/env python3
"""Build one bounded-size mosaic from previously sampled evidence frames.

The frames, their order and the column count all come from the caller; the
tool never samples frames, never picks columns and never modifies the input
images. When the frames directory holds a ``frames.json`` index written by
``video_sample_frames.py`` its order wins, otherwise image files are used
in sorted name order. Timestamps are already burned into each frame by the
sampler, so no labels are drawn here. Frames are normalized to a uniform
scaled width and tiled with ffmpeg's ``tile=<columns>x<rows>:padding=4:
margin=4`` filter; the whole grid is scaled down so the final mosaic width
never exceeds ``--max-width``. Zero frames and existing outputs are
refused.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


COMMAND_TIMEOUT_SEC = 120.0
TILE_PADDING_PX = 4
TILE_MARGIN_PX = 4
# Per-entry display time in the concat list; the value is irrelevant to the
# single tiled output frame but stills need a nonzero duration.
CONCAT_ENTRY_DURATION_SEC = 0.04
FRAME_SUFFIXES = ('.jpg', '.jpeg', '.png')


@dataclass
class GridLayout:
    """Row count and total cell count for a column-bounded grid."""

    rows: int
    cells: int


@dataclass
class MosaicScale:
    """Uniform per-frame width that keeps the mosaic within bounds."""

    scaled_frame_width: int


def calculate_grid(frame_count, columns):
    """Lay out ``frame_count`` frames into ``columns`` columns.

    Rows grow only when a column is full, so empty cells can only appear
    in the last row, never in the middle of the mosaic.
    """
    if columns < 1:
        raise ValueError(f'columns must be positive: {columns}')
    if frame_count < 1:
        raise ValueError(f'frame_count must be positive: {frame_count}')
    rows = math.ceil(frame_count / columns)
    return GridLayout(rows=rows, cells=rows * columns)


def mosaic_scale(frame_width, columns, padding, max_width):
    """Compute the uniform frame width that bounds the mosaic width.

    A mosaic is ``2 * margin + columns * width + (columns - 1) * padding``
    pixels wide. Frames keep their size when that already fits and are
    only ever scaled down, never up.
    """
    if frame_width < 1:
        raise ValueError(f'frame_width must be positive: {frame_width}')
    if max_width < 1:
        raise ValueError(f'max_width must be positive: {max_width}')
    available = (
        max_width - 2 * TILE_MARGIN_PX - padding * (columns - 1)
    )
    if available < columns:
        raise ValueError(
            f'max_width {max_width} leaves no room for {columns} columns'
        )
    unscaled = (
        2 * TILE_MARGIN_PX + columns * frame_width
        + padding * (columns - 1)
    )
    if unscaled <= max_width:
        return MosaicScale(scaled_frame_width=frame_width)
    scaled = available // columns
    # Keep the width even so the 4:2:0 tile output stays exact.
    scaled -= scaled % 2
    if scaled < 2:
        raise ValueError(
            f'max_width {max_width} cannot fit {columns} columns'
        )
    return MosaicScale(scaled_frame_width=scaled)


def resolve_frame_order(frames_dir):
    """Return the ordered frame paths for the mosaic.

    The ``frames.json`` index from the sampler defines the order when it
    exists; otherwise image files fall back to sorted name order.
    """
    frames_dir = Path(frames_dir)
    if not frames_dir.is_dir():
        raise RuntimeError(f'frames path is not a directory: {frames_dir}')
    index_path = frames_dir / 'frames.json'
    if index_path.exists():
        try:
            entries = json.loads(index_path.read_text())['frames']
        except (KeyError, ValueError) as error:
            raise RuntimeError(f'frames.json is not readable: {error}')
        order = [frames_dir / entry['filename'] for entry in entries]
        for path in order:
            if not path.exists():
                raise RuntimeError(
                    f'frames.json references a missing frame: {path.name}'
                )
    else:
        order = sorted(
            path for path in frames_dir.iterdir()
            if path.suffix.lower() in FRAME_SUFFIXES
        )
    if not order:
        raise RuntimeError(f'no frames found in: {frames_dir}')
    return order


def probe_frame_size(frame_path, timeout=COMMAND_TIMEOUT_SEC):
    """Read pixel dimensions of one frame with ffprobe."""
    try:
        text = subprocess.run(
            [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height', '-of', 'json',
                str(frame_path),
            ],
            check=True, capture_output=True, text=True, timeout=timeout,
        ).stdout
        stream = json.loads(text)['streams'][0]
        return int(stream['width']), int(stream['height'])
    except (subprocess.CalledProcessError, OSError, KeyError, IndexError,
            ValueError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f'frame is not readable by ffprobe: {error}')


def write_concat_list(frame_paths, list_path):
    """Write a temporary concat demuxer list in mosaic order.

    Every entry gets a nonzero duration so stills survive demuxing; the
    last file is repeated because the demuxer ignores the final duration.
    """
    lines = []
    for path in frame_paths:
        lines.append(f"file '{path}'")
        lines.append(f'duration {CONCAT_ENTRY_DURATION_SEC}')
    lines.append(f"file '{frame_paths[-1]}'")
    Path(list_path).write_text('\n'.join(lines) + '\n')


def build_ffmpeg_command(list_path, columns, rows, scaled_width, output):
    """Build the concat-plus-tile command for one bounded mosaic.

    Scaling to a uniform width normalizes the input dimensions before
    tiling; timestamps are already burned in by the sampler, so no
    ``drawtext`` happens here.
    """
    filters = (
        f'scale={scaled_width}:-2,'
        f'tile={columns}x{rows}'
        f':padding={TILE_PADDING_PX}:margin={TILE_MARGIN_PX}'
    )
    return [
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-f', 'concat', '-safe', '0', '-i', str(list_path),
        '-vf', filters,
        '-an', '-frames:v', '1', '-q:v', '2', str(output),
    ]


def build_mosaic(frames_dir, columns, output, max_width,
                 timeout=COMMAND_TIMEOUT_SEC):
    """Tile the ordered frames into one bounded mosaic image."""
    frames_dir = Path(frames_dir)
    output = Path(output)
    if output.exists():
        raise RuntimeError(f'refusing to overwrite existing output: {output}')
    frame_paths = resolve_frame_order(frames_dir)
    grid = calculate_grid(len(frame_paths), columns)
    frame_width, frame_height = probe_frame_size(frame_paths[0])
    scale = mosaic_scale(frame_width, columns, TILE_PADDING_PX, max_width)
    temporary = output.with_name('.tmp-' + output.name)
    with tempfile.TemporaryDirectory(prefix='video-mosaic-') as scratch:
        list_path = Path(scratch) / 'concat.txt'
        write_concat_list(frame_paths, list_path)
        command = build_ffmpeg_command(
            list_path, columns, grid.rows,
            scale.scaled_frame_width, temporary,
        )
        try:
            subprocess.run(
                command, check=True, capture_output=True, text=True,
                timeout=timeout,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or '').strip().splitlines()
            reason = detail[-1] if detail else str(error)
            raise RuntimeError(f'ffmpeg mosaic failed: {reason}')
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f'ffmpeg mosaic failed: {error}')
    if not temporary.exists() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError('ffmpeg produced no mosaic frame')
    os.replace(temporary, output)
    return {
        'frames_dir': str(frames_dir),
        'frame_count': len(frame_paths),
        'columns': columns,
        'rows': grid.rows,
        'source_frame_width': frame_width,
        'source_frame_height': frame_height,
        'scaled_frame_width': scale.scaled_frame_width,
        'max_width': max_width,
        'output': str(output),
    }


def _build_parser():
    parser = argparse.ArgumentParser(
        description='Tile sampled evidence frames into a bounded mosaic.',
    )
    parser.add_argument('--frames', required=True,
                        help='directory with frames and optional frames.json')
    parser.add_argument('--columns', required=True, type=int,
                        help='mosaic column count, chosen by the caller')
    parser.add_argument('--output', required=True,
                        help='fresh mosaic image path; never overwritten')
    parser.add_argument('--max-width', required=True, type=int,
                        help='cap on the final mosaic width in pixels')
    return parser


def main(argv=None):
    arguments = _build_parser().parse_args(argv)
    try:
        summary = build_mosaic(
            arguments.frames, arguments.columns,
            arguments.output, arguments.max_width,
        )
    except (RuntimeError, OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
