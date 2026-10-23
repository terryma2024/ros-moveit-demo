"""Original ROS values that JSON cannot carry (NaN, +/-inf) are kept as explicit tags, never dropped or rewritten.

The retained audit rows are canonical JSON with `allow_nan=False`. A `/joint_states` message from the joint_state_broadcaster has NaN
in the arrays of an interface it does not provide (effort, here), and the Recorder keeps the original message with every row (one such row failed the writer and ended the recording). `json_safe` replaces each non-finite float by `{"__non_finite_float__":
"nan" | "inf" | "-inf"}`; `restore_non_finite` is its exact inverse, so the original is recoverable and nothing is invented.
"""

from __future__ import annotations

import math

TAG = "__non_finite_float__"


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {TAG: "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")}
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def restore_non_finite(value):
    if isinstance(value, dict):
        if set(value) == {TAG}:
            return {"nan": math.nan, "inf": math.inf, "-inf": -math.inf}[value[TAG]]
        return {key: restore_non_finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [restore_non_finite(item) for item in value]
    return value
