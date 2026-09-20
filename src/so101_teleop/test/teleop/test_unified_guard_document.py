"""The service's start guard must accept the document the host can actually execute.

The validation domain loaded every execution document as schema 3. On macOS that both rejected the
schema-4 document (`UNKNOWN_CONFIG_FIELD`) and built an NVML guard, which refuses every preflight with
`GPU_TARGET_UNAVAILABLE` because there is no CUDA device. The document decides: v3 keeps the NVML guard,
v4/MPS gets the Darwin accelerator its policy asks for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from so101_teleop.expert_validation.production import _LazyStartGuard

REPO = Path(__file__).parents[4]
CONFIG_DIR = REPO / "src" / "so101_demo_py" / "config" / "mujoco"


def test_the_macos_document_composes_a_guard_its_host_can_run():
    guard = _LazyStartGuard(
        {"SO101_VALIDATION_PARALLEL_CONFIG": str(CONFIG_DIR / "parallel_batch_v4_macos_mps_w2.yaml")}
    )
    assert guard.gpu_selector == "MPS:default"
    assert guard.policy.mps_minimum_headroom_bytes == 1073741824


def test_the_v3_document_keeps_the_nvml_guard():
    guard = _LazyStartGuard(
        {"SO101_VALIDATION_PARALLEL_CONFIG": str(CONFIG_DIR / "parallel_batch_v3.yaml")}
    )
    assert guard.gpu_selector.startswith("INDEX:")
    assert guard.policy.mps_minimum_headroom_bytes is None
