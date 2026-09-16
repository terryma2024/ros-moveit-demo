"""Simulation-only SO-101 browser teleoperation service."""

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ServerMode, StepFrame

__all__ = ['ServerMode', 'StepFrame']


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    from .models import ServerMode, StepFrame

    return {
        'ServerMode': ServerMode,
        'StepFrame': StepFrame,
    }[name]
