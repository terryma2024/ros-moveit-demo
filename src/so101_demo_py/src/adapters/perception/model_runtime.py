"""Shared model runtime setup gates."""

from __future__ import annotations

from typing import Any, Literal

from so101_demo.core.detection import RuntimeDevice

RequestedDevice = Literal["auto", "cuda", "mps", "cpu"]


class ModelSetupError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def select_runtime_device(
    requested: str,
    allow_cpu_fallback: bool,
    torch_api: Any,
) -> RuntimeDevice:
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if bool(torch_api.cuda.is_available()):
            return "cuda"
        raise ModelSetupError("DEVICE_UNAVAILABLE", "requested CUDA is unavailable")
    if requested == "mps":
        if bool(torch_api.backends.mps.is_available()):
            return "mps"
        raise ModelSetupError("DEVICE_UNAVAILABLE", "requested MPS is unavailable")
    if requested != "auto":
        raise ModelSetupError("DEVICE_UNAVAILABLE", f"unknown device request: {requested}")
    if bool(torch_api.cuda.is_available()):
        return "cuda"
    if bool(torch_api.backends.mps.is_available()):
        return "mps"
    if allow_cpu_fallback:
        return "cpu"
    raise ModelSetupError(
        "DEVICE_UNAVAILABLE",
        "auto found no accelerator and CPU fallback was not authorized",
    )
