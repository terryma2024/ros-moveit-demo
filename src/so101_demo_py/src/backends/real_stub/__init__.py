"""Fail-closed extension boundary for future real SO-101 support."""

from .backend import RealStubBackend, RejectedResult
from .safety import RealStubSafetyConfiguration, parse_safety_configuration

__all__ = (
    "RealStubBackend",
    "RealStubSafetyConfiguration",
    "RejectedResult",
    "parse_safety_configuration",
)
