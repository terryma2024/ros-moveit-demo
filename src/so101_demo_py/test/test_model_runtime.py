from __future__ import annotations

from types import SimpleNamespace

import pytest

from so101_demo.adapters.perception.model_runtime import (
    ModelSetupError,
    select_runtime_device,
)


class _DeviceAvailability:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


def fake_torch(*, cuda: bool, mps: bool) -> SimpleNamespace:
    return SimpleNamespace(
        cuda=_DeviceAvailability(cuda),
        backends=SimpleNamespace(mps=_DeviceAvailability(mps)),
    )


def test_auto_prefers_cuda_then_mps_and_requires_cpu_authorization() -> None:
    assert select_runtime_device("auto", False, fake_torch(cuda=True, mps=True)) == "cuda"
    assert select_runtime_device("auto", False, fake_torch(cuda=False, mps=True)) == "mps"
    with pytest.raises(ModelSetupError, match="DEVICE_UNAVAILABLE"):
        select_runtime_device("auto", False, fake_torch(cuda=False, mps=False))
    assert select_runtime_device("auto", True, fake_torch(cuda=False, mps=False)) == "cpu"


def test_explicit_accelerator_never_falls_back() -> None:
    with pytest.raises(ModelSetupError, match="requested MPS is unavailable"):
        select_runtime_device("mps", True, fake_torch(cuda=False, mps=False))


def test_model_setup_error_exposes_read_only_code_and_detail() -> None:
    error = ModelSetupError("DEVICE_UNAVAILABLE", "requested CUDA is unavailable")

    assert error.code == "DEVICE_UNAVAILABLE"
    assert error.detail == "requested CUDA is unavailable"
    with pytest.raises(AttributeError):
        error.code = "MODEL_UNAVAILABLE"
    with pytest.raises(AttributeError):
        error.detail = "weights are unavailable"
