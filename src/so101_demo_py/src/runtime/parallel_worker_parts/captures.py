"""Lease keys, safe paths and the RGB and numeric captures of a point."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import stat
from typing import Any

import numpy as np

from so101_demo.parallel_batch.contracts import RunMode
from so101_demo.runtime.parallel_worker_parts.process_tree import (
    _IDENTIFIER,
    SourceStampedCapture,
    _finite_timestamp,
)
from so101_demo.runtime.parallel_worker_parts.receipts import (
    InferenceSnapshotReceipt,
    NumericEvidenceReceipt,
)


class WorkerCaptures:
    @staticmethod
    def _lease_value(lease: Any, name: str) -> Any:
        value = getattr(lease, name, None)
        if name in {"batch_id", "worker_id", "point_id", "attempt_id"}:
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise RuntimeError(f"lease {name} is not a canonical identity")
        elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeError(f"lease {name} is not a canonical identity")
        return value

    def _lease_key(self, lease: Any) -> tuple[object, ...]:
        key = tuple(
            self._lease_value(lease, name)
            for name in (
                "batch_id",
                "coordinator_epoch",
                "worker_id",
                "worker_generation",
                "point_id",
                "attempt_id",
                "lease_generation",
            )
        )
        if key[2] != self.resources.worker_id or key[3] != self.resources.generation:
            raise RuntimeError("lease identity does not own this Worker root")
        if self._batch_id is None:
            self._batch_id = str(key[0])
        elif key[0] != self._batch_id:
            raise RuntimeError("lease batch identity does not own this Worker root")
        return key

    def _assert_safe_path(self, path: Path) -> None:
        root = self.resources.worker_root.absolute()
        target = Path(path).absolute()
        try:
            relative = target.relative_to(root)
        except ValueError as error:
            raise RuntimeError("artifact path escaped the Worker root") from error
        current = root
        if current.is_symlink():
            raise RuntimeError("artifact path contains a symlink")
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeError("artifact path contains a symlink")

    def _point_root(self, lease: Any) -> tuple[tuple[object, ...], Path]:
        key = self._lease_key(lease)
        collection = "attempts" if self.run_mode is RunMode.EXECUTE else "validations"
        root = (
            self.resources.worker_root
            / collection
            / str(key[4])
            / str(key[5])
            / "working"
        )
        self._assert_safe_path(root)
        return key, root

    def _validate_regular_receipt_path(
        self, actual: Path, expected: Path, *, label: str
    ) -> Path:
        actual = Path(actual)
        if actual != expected:
            raise RuntimeError(f"{label} receipt escaped its canonical point identity")
        self._assert_safe_path(actual)
        if actual.is_symlink() or not actual.is_file():
            raise RuntimeError(f"{label} receipt is not a regular artifact")
        return actual

    def _capture_fresh_rgb(
        self, lease: Any, name: str, boundary: float
    ) -> SourceStampedCapture:
        boundary = _finite_timestamp("capture boundary", boundary)
        _key, point_root = self._point_root(lease)
        path = point_root / name
        self._assert_safe_path(path)
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"{name} capture would overwrite point evidence")
        captured = self._capture_rgb(path, boundary)
        if type(captured) is not SourceStampedCapture:
            raise RuntimeError(f"{name} capture lacks a source-stamped receipt")
        self._validate_regular_receipt_path(captured.path, path, label=name)
        if captured.source_stamp_monotonic_s <= boundary:
            raise RuntimeError(f"{name} source stamp is not newer than boundary")
        self._captured.append(path)
        return captured

    def _capture_inference_rgb(
        self, lease: Any, boundary: float
    ) -> InferenceSnapshotReceipt:
        boundary = _finite_timestamp("capture boundary", boundary)
        key, point_root = self._point_root(lease)
        path = point_root / "perception/input/rgb.npy"
        self._assert_safe_path(path)
        if path.exists() or path.is_symlink():
            raise RuntimeError("inference RGB would overwrite point evidence")
        captured = self._capture_rgb(path, boundary)
        if type(captured) is not InferenceSnapshotReceipt:
            raise RuntimeError("inference RGB lacks an immutable snapshot receipt")
        self._validate_regular_receipt_path(
            captured.path, path, label="inference RGB"
        )
        info = path.stat()
        if stat.S_IMODE(info.st_mode) != 0o400 or info.st_uid != os.getuid():
            raise RuntimeError("inference RGB is not immutable and Worker-owned")
        if captured.source_stamp_monotonic_s <= boundary:
            raise RuntimeError("inference RGB source stamp is not newer than boundary")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != captured.input_sha256:
            raise RuntimeError("inference RGB hash does not match its receipt")
        try:
            rgb = np.load(io.BytesIO(payload), allow_pickle=False)
        except (OSError, ValueError) as error:
            raise RuntimeError("inference RGB is not canonical NPY") from error
        if (
            rgb.dtype != np.uint8
            or tuple(rgb.shape) != captured.shape
            or rgb.ndim != 3
            or rgb.shape[2] != 3
        ):
            raise RuntimeError("inference RGB shape or dtype does not match its receipt")
        self._captured.append(path)
        self._inference_receipts[key] = captured
        return captured

    def _capture_numeric(
        self, lease: Any, localized: Any, boundary: float
    ) -> NumericEvidenceReceipt:
        key, point_root = self._point_root(lease)
        numeric_root = point_root / "numeric"
        self._assert_safe_path(numeric_root)
        if any(
            (numeric_root / name).exists()
            for name in ("depth.json", "tf.json", "physical.json")
        ):
            raise RuntimeError("numeric evidence would overwrite point evidence")
        receipt = self._capture_numeric_evidence(
            lease, localized, numeric_root, boundary
        )
        if type(receipt) is not NumericEvidenceReceipt:
            raise RuntimeError("numeric evidence lacks a strict source-stamped receipt")
        expected = (
            numeric_root / "depth.json",
            numeric_root / "tf.json",
            numeric_root / "physical.json",
        )
        for actual, path, label in zip(
            (receipt.depth_path, receipt.tf_path, receipt.physical_path),
            expected,
            ("depth", "TF", "physical"),
        ):
            self._validate_regular_receipt_path(actual, path, label=label)
        if receipt.source_stamp_monotonic_s <= boundary:
            raise RuntimeError(
                "numeric evidence source stamp is not newer than reset boundary"
            )
        self._numeric_receipts[key] = receipt
        return receipt
