"""Profiling configuration and event value contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, TypeAlias


class ProfilingMode(str, Enum):
    """Public profiling modes."""

    OFF = "off"
    SUMMARY = "summary"
    TRACE = "trace"

    @classmethod
    def parse(cls, value: str) -> "ProfilingMode":
        try:
            return cls(value)
        except ValueError as error:
            choices = ", ".join(mode.value for mode in cls)
            raise ValueError(
                f"profiling must be one of: {choices}; got {value!r}"
            ) from error


@dataclass(frozen=True, slots=True)
class ProfilingConfig:
    """Immutable process-local profiling configuration."""

    mode: ProfilingMode
    output_root: Path | None
    session_id: str
    process_role: str
    request_id: str | None = None
    source_commit: str | None = None
    installed_prefix: str | None = None

    @classmethod
    def disabled(
        cls,
        *,
        session_id: str,
        process_role: str,
    ) -> "ProfilingConfig":
        return cls(
            mode=ProfilingMode.OFF,
            output_root=None,
            session_id=session_id,
            process_role=process_role,
        )


Scalar: TypeAlias = str | int | float | bool | None


def validate_attributes(values: Mapping[str, object]) -> dict[str, Scalar]:
    """Return scalar JSON attributes or reject unsafe structured payloads."""

    validated: dict[str, Scalar] = {}
    for key, value in values.items():
        if not isinstance(key, str):
            raise TypeError("profiling attribute names must be strings")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise TypeError(
                f"profiling attribute {key!r} must be a scalar JSON value"
            )
        validated[key] = value
    return validated
