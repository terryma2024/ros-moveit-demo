from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
    decode_mask_rle,
    encode_mask_rle,
    read_mask,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import MaskRef


def test_rle_round_trip_is_lossless_coco_column_major() -> None:
    mask = np.array([[False, True, True], [False, False, True]], dtype=bool)

    document = encode_mask_rle(mask)

    assert document == {
        "size": [2, 3],
        "counts": [2, 1, 1, 2],
    }
    decoded = decode_mask_rle(document)
    assert decoded.dtype == np.bool_
    assert np.array_equal(decoded, mask)


@pytest.mark.parametrize(
    "document",
    [
        {"encoding": "binary-rle-c-v1", "height": 1, "width": 1, "counts": [0, 1]},
        {"size": [1, 1], "counts": [2]},
        {"size": [1, 1], "counts": [0, 2]},
        {"size": [1, 1], "counts": [0, -1]},
        {"size": [True, 1], "counts": [0, 1]},
    ],
)
def test_rle_rejects_malformed_payloads(document: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        decode_mask_rle(document)


def test_canonical_json_and_atomic_write_have_stable_digest(tmp_path: Path) -> None:
    document = {"z": "雪", "a": [2, 1]}
    expected = b'{"a":[2,1],"z":"\xe9\x9b\xaa"}\n'

    assert canonical_json_bytes(document) == expected
    path = tmp_path / "nested" / "record.json"
    digest = atomic_write_json(path, document)

    assert path.read_bytes() == expected
    assert digest == hashlib.sha256(expected).hexdigest()
    assert digest == sha256_bytes(expected)


def test_read_mask_rejects_path_escape_and_checksum_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    mask = np.array([[True, False], [False, True]], dtype=bool)
    path = root / "masks" / "cup.json"
    atomic_write_json(path, encode_mask_rle(mask))
    digest = hashlib.sha256(mask.astype(np.uint8).tobytes(order="C")).hexdigest()
    reference = MaskRef("masks/cup.json", digest, 2, 2, 2)

    result = read_mask(reference, root)

    assert np.array_equal(result, mask)
    assert not result.flags.writeable
    with pytest.raises(ValueError, match="sha256"):
        read_mask(MaskRef("masks/cup.json", "b" * 64, 2, 2, 2), root)
    with pytest.raises(ValueError, match="relative_path"):
        MaskRef("../outside.json", digest, 2, 2, 2)


def test_read_mask_validates_declared_shape_and_pixel_count(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    mask = np.array([[True, False], [False, True]], dtype=bool)
    atomic_write_json(root / "mask.json", encode_mask_rle(mask))
    digest = hashlib.sha256(mask.astype(np.uint8).tobytes(order="C")).hexdigest()

    with pytest.raises(ValueError, match="pixel_count"):
        read_mask(MaskRef("mask.json", digest, 1, 2, 2), root)
    with pytest.raises(ValueError, match="dimensions"):
        read_mask(MaskRef("mask.json", digest, 2, 3, 2), root)


def test_atomic_write_replaces_existing_canonical_document(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text("stale", encoding="utf-8")

    atomic_write_json(path, {"b": 1, "a": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 2, "b": 1}
