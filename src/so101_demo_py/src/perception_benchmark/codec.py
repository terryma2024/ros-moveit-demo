"""Canonical JSON and mask codecs for benchmark evidence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Mapping

import numpy as np

from so101_demo.perception_benchmark.contracts import MaskRef

def encode_mask_rle(mask: np.ndarray) -> dict[str, object]:
    value = np.asarray(mask, dtype=bool)
    if value.ndim != 2:
        raise ValueError("mask must be two-dimensional")
    flat = value.astype(np.uint8, copy=False).ravel(order="F")
    counts: list[int] = []
    current = 0
    run = 0
    for pixel in flat:
        if int(pixel) == current:
            run += 1
        else:
            counts.append(run)
            current = int(pixel)
            run = 1
    counts.append(run)
    return {
        "size": [value.shape[0], value.shape[1]],
        "counts": counts,
    }


def decode_mask_rle(document: Mapping[str, object]) -> np.ndarray:
    if not isinstance(document, Mapping) or set(document) != {"size", "counts"}:
        raise ValueError("COCO RLE document must contain exactly size and counts")
    size = document["size"]
    counts = document["counts"]
    if (
        not isinstance(size, list)
        or len(size) != 2
        or isinstance(size[0], bool)
        or isinstance(size[1], bool)
        or not isinstance(size[0], int)
        or not isinstance(size[1], int)
    ):
        raise ValueError("COCO RLE size must be a [height, width] integer list")
    height, width = size
    if (
        isinstance(height, bool)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or not isinstance(width, int)
        or height <= 0
        or width <= 0
    ):
        raise ValueError("COCO RLE dimensions must be positive integers")
    if not isinstance(counts, list) or not counts:
        raise ValueError("COCO RLE counts must be a non-empty list")
    if any(isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts):
        raise ValueError("COCO RLE counts must be nonnegative integers")
    if sum(counts) != height * width:
        raise ValueError("COCO RLE counts do not match dimensions")
    pixels = np.empty(height * width, dtype=bool)
    offset = 0
    current = False
    for count in counts:
        pixels[offset : offset + count] = current
        offset += count
        current = not current
    return pixels.reshape((height, width), order="F")


def canonical_json_bytes(document: object) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_mask(mask_ref: MaskRef, evidence_root: Path) -> np.ndarray:
    if not isinstance(mask_ref, MaskRef):
        raise ValueError("mask_ref must be a MaskRef")
    root = Path(evidence_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("evidence_root must be a directory")
    path = (root / mask_ref.relative_path).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError("relative_path escapes evidence_root")
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("mask RLE document cannot be read") from error
    if not isinstance(document, Mapping):
        raise ValueError("mask RLE document must be an object")
    mask = decode_mask_rle(document)
    if (mask.shape[1], mask.shape[0]) != (mask_ref.image_width, mask_ref.image_height):
        raise ValueError("mask dimensions do not match MaskRef")
    if int(mask.sum()) != mask_ref.pixel_count:
        raise ValueError("mask pixel_count does not match MaskRef")
    digest = sha256_bytes(mask.astype(np.uint8, copy=False).tobytes(order="C"))
    if digest != mask_ref.sha256:
        raise ValueError("mask sha256 does not match MaskRef")
    result = np.array(mask, copy=True)
    result.setflags(write=False)
    return result


def atomic_write_json(path: Path, document: object) -> str:
    payload = canonical_json_bytes(document)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return sha256_bytes(payload)
