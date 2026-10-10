"""Synthetic committed episodes -> the REAL export code -> an exported dataset, for the training-path tests and the GPU smoke.

Nothing here fakes the exporter: the episodes are sealed recorder directories (`act_export_fixture.write_sealed_episode`) whose commit
proof is the one controlled commit-reader double the export tests already use, and the dataset is written by `export_dataset`.
"""
import math
import zlib

from act_export_fixture import complete_export_entries

KW = dict(source_manifest_sha256="a" * 64, campaign_index_sha256="b" * 64)


def smooth_png(width, height, seed):
    """A real RGB PNG (colour type 2, 8 bit) whose pixels are a smooth function of the position and the seed (cheap to build and compress)."""
    import struct

    import numpy as np
    x = np.arange(width, dtype=np.int32)[None, :, None]
    y = np.arange(height, dtype=np.int32)[:, None, None]
    c = np.arange(3, dtype=np.int32)[None, None, :]
    pixels = ((x * (3 + seed % 5) + y * (2 + seed % 3) + c * 61 + seed * 7) % 256).astype(np.uint8)
    raw = np.concatenate([np.zeros((height, 1), dtype=np.uint8), pixels.reshape(height, width * 3)], axis=1).tobytes()

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


def episode_content(scene_index, rows, *, neck=(0.0, 1.0)):
    """Rows whose action is a smooth function of the state (learnable) and whose neck sin/cos state dimensions never move."""
    content_rows = []
    for index in range(rows):
        phase = 0.35 * index + 0.7 * scene_index
        arm = [0.4 * math.sin(phase + joint) + 0.05 * scene_index for joint in range(5)]
        gripper = 0.5 + 0.4 * math.sin(phase * 0.5)
        state = [arm[0], arm[1], arm[2], arm[3], arm[4], gripper, neck[0], neck[1]]
        action = [value + 0.1 * math.cos(phase) for value in state[:6]]
        content_rows.append({"observation": {"sim_time_s": round(index * 0.1, 6), "state": state,
                                             "head_png": f"frames/{index:06d}-head.png", "wrist_png": f"frames/{index:06d}-wrist.png"},
                             "action": action})
    return {"frames": rows, "rows": content_rows}


def synthetic_dataset(tmp_path, monkeypatch, *, splits, rows=12, size=(64, 48), neck=(0.0, 1.0), name="dataset"):
    """Export ``splits`` ({scene_id: split}) through the real `export_dataset`; returns the dataset path."""
    from so101_demo.act.bundle import export_dataset
    width, height = size
    scene_ids = tuple(splits)
    contents = {scene: episode_content(index, rows, neck=neck) for index, scene in enumerate(scene_ids)}
    counter = {"n": 0}

    def frame(png_name):
        counter["n"] += 1
        return smooth_png(width, height, counter["n"])
    entries = complete_export_entries(tmp_path, monkeypatch, scene_ids, contents=contents, splits=splits, frame=frame)
    dataset = tmp_path / name
    export_dataset(entries, dataset, **KW)
    return dataset


class Monkey:
    """The one `setattr` the commit-reader double needs, for scripts that run outside pytest."""

    def setattr(self, target, name, value):
        setattr(target, name, value)
