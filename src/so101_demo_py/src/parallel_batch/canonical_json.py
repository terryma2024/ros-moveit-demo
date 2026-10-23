"""Canonical JSON digest shared by the parallel-validation receipts and runtime closures."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping

from so101_demo.parallel_batch.contracts.common import ContractError


def canonical_sha256(value: object) -> str:
    """Canonical UTF-8 JSON digest: sorted keys, no NaN, explicit types."""

    _require_json_safe(value)
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ContractError("CANONICAL_JSON") from error
    return hashlib.sha256(payload).hexdigest()


def _require_json_safe(value: object, path: str = "$") -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"NONFINITE: {path}")
    elif isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(f"JSON_KEY_TYPE: {path}")
            _require_json_safe(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_json_safe(item, f"{path}[{index}]")
    else:
        raise ContractError(f"JSON_TYPE: {path}")
